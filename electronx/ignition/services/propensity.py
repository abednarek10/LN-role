"""Activation propensity model (spec D1, CTO memo §4).

Target: **P(becomes Active within 60 days of the snapshot)** — Active = ≥4
distinct trading days within 30 calendar days (D2).

* Population per snapshot ``t``: non-LP accounts signed before ``t`` that have
  never been Active before ``t``.
* Snapshots weekly; **purged time split** (v1.1): test on
  ``t ∈ (AS_OF − 120 d, AS_OF − 60 d]`` (labels fully observed); train on snapshots
  at least 60 d before the first test snapshot, so no train label window overlaps
  the test period. Also reported: AUC on unseen accounts, the v1 adjacent split and
  a 5-flag funnel baseline (``report["honest"]``).
* Production: ``StandardScaler`` + ``LogisticRegression`` (unweighted, so
  probabilities stay calibrated for the EV ranking). Holdout metrics come from
  the train-only fit; the served model is then refit on train + test.
  Challenger: ``HistGradientBoostingClassifier`` reported side-by-side.
* Reasons: per-account contribution ``coef_j × z_j`` (standardized), top 3 by
  magnitude, labelled from ``content/reason_labels.json``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .. import definitions as D
from ..config import CONTENT_DIR, SEED
from .features import FEATURES, MODEL_FEATURES, activation_labels, features_as_of, first_active_at

TARGET = "P(Active within 60 days of snapshot) — Active = ≥4 distinct trading days within 30 calendar days"
SNAPSHOT_START = datetime(2026, 2, 2)
SNAPSHOT_STEP_D = 7
TRAIN_END = D.AS_OF - timedelta(days=120)
TEST_END = D.AS_OF - timedelta(days=D.ACTIVATION_WINDOW_D)
N_REASONS = 3
P_DISPLAY_CAP = 0.95  # X11: probabilities above this display as ">95%"
LR_C = 0.05  # strong L2: shrinks collinear funnel flags toward interpretable signs


@lru_cache(maxsize=1)
def reason_labels() -> dict[str, dict[str, str]]:
    raw = json.loads((CONTENT_DIR / "reason_labels.json").read_text())
    return {k: v for k, v in raw.items() if not k.startswith("_")}


@dataclass
class ModelBundle:
    model: Pipeline
    challenger: HistGradientBoostingClassifier
    features: list[str]
    report: dict
    train: pd.DataFrame = field(repr=False)
    test: pd.DataFrame = field(repr=False)
    holdout_model: Pipeline | None = field(default=None, repr=False)  # train-only fit behind the metrics
    trained_as_of: datetime = D.AS_OF


def snapshot_dates(start: datetime = SNAPSHOT_START, end: datetime = TEST_END) -> list[datetime]:
    out, t = [], start
    while t <= end:
        out.append(t)
        t += timedelta(days=SNAPSHOT_STEP_D)
    return out


def _population(frames, t: pd.Timestamp, fa: pd.Series) -> list[int]:
    acc = frames.accounts
    ob = frames.onboarding_events
    signed = ob[(ob["step"] == "contract_signed") & (ob["ts"] < t)]["account_id"].unique()
    lp = set(acc.loc[acc["is_liquidity_partner"], "id"])
    already = set(fa[fa < t].index)
    return [int(a) for a in signed if a not in lp and a not in already]


def build_dataset(frames, snapshots: list[datetime] | None = None) -> pd.DataFrame:
    """Stacked (snapshot, account) rows: features + ``label`` + ``snapshot``."""
    snapshots = snapshots or snapshot_dates()
    fa = first_active_at(frames.trades)
    parts = []
    for t in snapshots:
        t = pd.Timestamp(t)
        ids = _population(frames, t, fa)
        if not ids:
            continue
        X = features_as_of(frames, t, ids)
        y = activation_labels(frames, t, account_ids=ids)
        X = X.assign(label=y.reindex(X.index).to_numpy(), snapshot=t)
        parts.append(X.reset_index())
    return pd.concat(parts, ignore_index=True)


def _lift_top_decile(y: np.ndarray, p: np.ndarray) -> float:
    n = max(1, int(round(len(p) * 0.1)))
    top = np.argsort(-p, kind="stable")[:n]
    base = y.mean()
    return float(y[top].mean() / base) if base > 0 else 0.0


def _gain_curve(y: np.ndarray, p: np.ndarray) -> list[dict]:
    order = np.argsort(-p, kind="stable")
    ys = y[order]
    tot = max(ys.sum(), 1)
    out = []
    for k in range(1, 11):
        n = int(round(len(ys) * k / 10))
        out.append({"pct_accounts": round(k / 10, 2), "pct_positives": round(float(ys[:n].sum() / tot), 4)})
    return out


def _calibration(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[dict]:
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    out = []
    for b in range(bins):
        m = idx == b
        if m.sum() == 0:
            continue
        out.append({
            "bin": f"{edges[b]:.1f}-{edges[b + 1]:.1f}",
            "predicted": round(float(p[m].mean()), 4),
            "observed": round(float(y[m].mean()), 4),
            "n": int(m.sum()),
        })
    return out


GAP_DAYS = D.ACTIVATION_WINDOW_D  # purge between the last train snapshot and the first test snapshot
BASELINE_FLAGS = ["kyc_approved", "funded", "api_key", "ticket_opened", "traded"]
BASELINE_NAME = "Funnel flags (KYC approved, funded, API key, ticket opened, traded) — logistic regression"


def _lr() -> Pipeline:
    return Pipeline([("scale", StandardScaler()), ("lr", LogisticRegression(C=LR_C, max_iter=5000))])


def _auc(y, p) -> float | None:
    y = np.asarray(y)
    return round(float(roc_auc_score(y, p)), 4) if len(np.unique(y)) > 1 else None


def train_model(frames, seed: int = SEED) -> ModelBundle:
    """Fit + evaluate. Headline metrics use a **purged** split: train snapshots end
    ``GAP_DAYS`` before the first test snapshot, so no training label window
    (t, t+60 d] overlaps the test period (v1.1 X11 / CTO B4)."""
    feats = list(MODEL_FEATURES)
    data = build_dataset(frames)
    test = data[(data["snapshot"] > pd.Timestamp(TRAIN_END)) & (data["snapshot"] <= pd.Timestamp(TEST_END))]
    gap_end = test["snapshot"].min() - pd.Timedelta(days=GAP_DAYS)
    train = data[data["snapshot"] <= gap_end]
    train_adj = data[data["snapshot"] <= pd.Timestamp(TRAIN_END)]  # v1 split, reported for comparison only
    Xtr, ytr = train[feats].to_numpy(), train["label"].to_numpy().astype(int)
    Xte, yte = test[feats].to_numpy(), test["label"].to_numpy().astype(int)

    model = _lr().fit(Xtr, ytr)
    p = model.predict_proba(Xte)[:, 1]
    unseen = ~test["account_id"].isin(set(train["account_id"])).to_numpy()
    adj = _lr().fit(train_adj[feats].to_numpy(), train_adj["label"].to_numpy().astype(int))
    p_adj = adj.predict_proba(Xte)[:, 1]
    base = Pipeline([("scale", StandardScaler()), ("lr", LogisticRegression(C=1.0, max_iter=5000))])
    base.fit(train[BASELINE_FLAGS].to_numpy(), ytr)
    pb = base.predict_proba(test[BASELINE_FLAGS].to_numpy())[:, 1]

    challenger = HistGradientBoostingClassifier(
        max_depth=3, learning_rate=0.05, max_iter=250, l2_regularization=1.0, random_state=seed
    )
    challenger.fit(Xtr, ytr)
    pc = challenger.predict_proba(Xte)[:, 1]

    # Production model = same spec refit on every labelled snapshot (train..test end)
    # so live scores reflect the most recent funnel; metrics stay out-of-sample.
    holdout_model = model
    served = data[data["snapshot"] <= pd.Timestamp(TEST_END)]
    model = _lr().fit(served[feats].to_numpy(), served["label"].to_numpy().astype(int))

    labels = reason_labels()
    coefs = model.named_steps["lr"].coef_[0]
    coef_rows = sorted(
        ({"feature": f, "label": labels.get(f, {}).get("label", f), "coef": round(float(c), 4)}
         for f, c in zip(feats, coefs)),
        key=lambda r: -abs(r["coef"]),
    )
    auc_gap = _auc(yte, p)
    auc_unseen = _auc(yte[unseen], p[unseen])
    baseline_auc = _auc(yte, pb)
    honest = {
        "gap_days": GAP_DAYS,
        "auc_gap": auc_gap,
        "auc_unseen": auc_unseen,
        "unseen_n": int(unseen.sum()),
        "auc_adjacent": _auc(yte, p_adj),
        "baseline_name": BASELINE_NAME,
        "baseline_auc": baseline_auc,
        "baseline_auc_unseen": _auc(yte[unseen], pb[unseen]),
        "lift_vs_baseline": round(auc_gap - baseline_auc, 4) if auc_gap and baseline_auc else None,
        "train_window": [str(train["snapshot"].min().date()), str(train["snapshot"].max().date())],
        "test_window": [str(test["snapshot"].min().date()), str(test["snapshot"].max().date())],
        "note": (f"Headline AUC uses a {GAP_DAYS}-day purge between the last training snapshot and the first "
                 "test snapshot, so no training label window overlaps the test period. 'Unseen' scores only "
                 "test accounts never present in training. The funnel-flag baseline shows how much of the "
                 "signal is simply onboarding stage; synthetic data — illustrative."),
    }
    report = {
        "target": TARGET,
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "train_accounts": int(train["account_id"].nunique()),
        "test_accounts": int(test["account_id"].nunique()),
        "train_window": honest["train_window"],
        "test_window": honest["test_window"],
        "auc": auc_gap,
        "pr_auc": round(float(average_precision_score(yte, p)), 4),
        "brier": round(float(brier_score_loss(yte, p)), 4),
        "base_rate": round(float(yte.mean()), 4),
        "lift_top_decile": round(_lift_top_decile(yte, p), 3),
        "gain_curve": _gain_curve(yte, p),
        "calibration": _calibration(yte, p),
        "coefficients": coef_rows,
        "challenger": {
            "name": "HistGradientBoostingClassifier",
            "auc": _auc(yte, pc),
            "pr_auc": round(float(average_precision_score(yte, pc)), 4),
            "lift_top_decile": round(_lift_top_decile(yte, pc), 3),
        },
        "honest": honest,
        "excluded_features": [f for f in FEATURES if f not in feats],
        "display_cap": P_DISPLAY_CAP,
    }
    return ModelBundle(model=model, challenger=challenger, features=feats, report=report,
                       train=train, test=test, holdout_model=holdout_model)


def model_report(bundle: ModelBundle) -> dict:
    """``/scoring/model`` payload (without ``as_of``; the router adds it)."""
    return json.loads(json.dumps(bundle.report))


_ONE_HOT_PREFIXES = ("seg_", "iso_", "lead_")


def _reasons(contrib: np.ndarray, z: np.ndarray, raw: np.ndarray, features: list[str], k: int = N_REASONS) -> list[list[dict]]:
    """Top-k contributions per row. Text states the account's fact (high/low vs
    population mean); direction is the sign of the log-odds contribution.
    Absent one-hot categories ("not a REP") are never used as reasons."""
    labels = reason_labels()
    one_hot = np.array([f.startswith(_ONE_HOT_PREFIXES) for f in features])
    out = []
    for c_row, z_row, x_row in zip(contrib, z, raw):
        eligible = ~(one_hot & (x_row == 0))
        score = np.where(eligible, np.abs(c_row), -1.0)
        top = [j for j in np.argsort(-score, kind="stable")[:k] if score[j] > 0]
        items = []
        for j in top:
            f = features[j]
            lab = labels.get(f, {})
            text = lab.get("high" if z_row[j] > 0 else "low", lab.get("label", f))
            items.append({"feature": f, "label": text, "direction": "+" if c_row[j] > 0 else "-",
                          "weight": round(float(c_row[j]), 3)})
        out.append(items)
    return out


def p_display(p: float) -> str:
    """Display string for a probability, capped at ">95%" (X11)."""
    if p > P_DISPLAY_CAP:
        return f">{P_DISPLAY_CAP:.0%}"
    if p < 0.01:
        return "<1%"
    return f"{p:.0%}"


def score_accounts(bundle: ModelBundle, frames, t=D.AS_OF, account_ids=None) -> pd.DataFrame:
    """Score accounts at ``t``.

    Returns columns ``account_id, p_active, reasons, already_active, p_display``
    (``p_display`` caps at ">95%", v1.1 X11) where
    ``reasons`` is a list of ``{feature, label, direction('+'|'-'), weight}``
    (weight = contribution to the log-odds). Default population: every
    non-liquidity-partner account. ``already_active`` marks accounts that were
    Active before ``t`` (outside the model's training population — their
    ``p_active`` is reported but should not drive activation ranking).
    """
    t = pd.Timestamp(t)
    acc = frames.accounts
    if account_ids is None:
        account_ids = acc.loc[~acc["is_liquidity_partner"], "id"].tolist()
    X = features_as_of(frames, t, account_ids)
    Xv = X[bundle.features].to_numpy()
    p = bundle.model.predict_proba(Xv)[:, 1]
    scaler = bundle.model.named_steps["scale"]
    coefs = bundle.model.named_steps["lr"].coef_[0]
    z = scaler.transform(Xv)
    contrib = z * coefs
    fa = first_active_at(frames.trades[frames.trades["ts"] < t])
    out = pd.DataFrame({
        "account_id": X.index.astype(int),
        "p_active": np.round(p, 4),
        "reasons": _reasons(contrib, z, Xv, bundle.features),
        "already_active": X.index.isin(fa.index),
        "p_display": [p_display(v) for v in p],
    })
    return out.reset_index(drop=True)
