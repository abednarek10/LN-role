"""Activation propensity model (spec D1, CTO memo §4).

Target: **P(becomes Active within 60 days of the snapshot)** — Active = ≥4
distinct trading days within 30 calendar days (D2).

* Population per snapshot ``t``: non-LP accounts signed before ``t`` that have
  never been Active before ``t``.
* Snapshots weekly; **time-based split**: train on ``t ≤ AS_OF − 120 d``, test
  on ``t ∈ (AS_OF − 120 d, AS_OF − 60 d]`` (labels fully observed).
* Production: ``StandardScaler`` + ``LogisticRegression`` (unweighted, so
  probabilities stay calibrated for the EV ranking). Challenger:
  ``HistGradientBoostingClassifier`` reported side-by-side.
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
from .features import FEATURES, activation_labels, features_as_of, first_active_at

TARGET = "P(Active within 60 days of snapshot) — Active = ≥4 distinct trading days within 30 calendar days"
SNAPSHOT_START = datetime(2026, 2, 2)
SNAPSHOT_STEP_D = 7
TRAIN_END = D.AS_OF - timedelta(days=120)
TEST_END = D.AS_OF - timedelta(days=D.ACTIVATION_WINDOW_D)
N_REASONS = 3


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


def train_model(frames, seed: int = SEED) -> ModelBundle:
    data = build_dataset(frames)
    train = data[data["snapshot"] <= pd.Timestamp(TRAIN_END)]
    test = data[(data["snapshot"] > pd.Timestamp(TRAIN_END)) & (data["snapshot"] <= pd.Timestamp(TEST_END))]
    Xtr, ytr = train[FEATURES].to_numpy(), train["label"].to_numpy().astype(int)
    Xte, yte = test[FEATURES].to_numpy(), test["label"].to_numpy().astype(int)

    model = Pipeline([
        ("scale", StandardScaler()),
        ("lr", LogisticRegression(C=0.3, max_iter=5000)),
    ])
    model.fit(Xtr, ytr)
    p = model.predict_proba(Xte)[:, 1]

    challenger = HistGradientBoostingClassifier(
        max_depth=3, learning_rate=0.05, max_iter=250, l2_regularization=1.0, random_state=seed
    )
    challenger.fit(Xtr, ytr)
    pc = challenger.predict_proba(Xte)[:, 1]

    labels = reason_labels()
    coefs = model.named_steps["lr"].coef_[0]
    coef_rows = sorted(
        ({"feature": f, "label": labels.get(f, {}).get("label", f), "coef": round(float(c), 4)}
         for f, c in zip(FEATURES, coefs)),
        key=lambda r: -abs(r["coef"]),
    )
    report = {
        "target": TARGET,
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "train_accounts": int(train["account_id"].nunique()),
        "test_accounts": int(test["account_id"].nunique()),
        "train_window": [str(train["snapshot"].min().date()), str(train["snapshot"].max().date())],
        "test_window": [str(test["snapshot"].min().date()), str(test["snapshot"].max().date())],
        "auc": round(float(roc_auc_score(yte, p)), 4),
        "pr_auc": round(float(average_precision_score(yte, p)), 4),
        "brier": round(float(brier_score_loss(yte, p)), 4),
        "base_rate": round(float(yte.mean()), 4),
        "lift_top_decile": round(_lift_top_decile(yte, p), 3),
        "gain_curve": _gain_curve(yte, p),
        "calibration": _calibration(yte, p),
        "coefficients": coef_rows,
        "challenger": {
            "name": "HistGradientBoostingClassifier",
            "auc": round(float(roc_auc_score(yte, pc)), 4),
            "pr_auc": round(float(average_precision_score(yte, pc)), 4),
            "lift_top_decile": round(_lift_top_decile(yte, pc), 3),
        },
    }
    return ModelBundle(model=model, challenger=challenger, features=list(FEATURES), report=report,
                       train=train, test=test)


def model_report(bundle: ModelBundle) -> dict:
    """``/scoring/model`` payload (without ``as_of``; the router adds it)."""
    return json.loads(json.dumps(bundle.report))


def _reasons(contrib: np.ndarray, features: list[str], k: int = N_REASONS) -> list[list[dict]]:
    labels = reason_labels()
    out = []
    for row in contrib:
        top = np.argsort(-np.abs(row), kind="stable")[:k]
        items = []
        for j in top:
            f = features[j]
            sign = "+" if row[j] > 0 else "-"
            lab = labels.get(f, {})
            items.append({"feature": f, "label": lab.get(sign, lab.get("label", f)), "direction": sign,
                          "weight": round(float(row[j]), 3)})
        out.append(items)
    return out


def score_accounts(bundle: ModelBundle, frames, t=D.AS_OF, account_ids=None) -> pd.DataFrame:
    """Score accounts at ``t``.

    Returns columns ``account_id, p_active, reasons, already_active`` where
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
    contrib = scaler.transform(Xv) * coefs
    fa = first_active_at(frames.trades[frames.trades["ts"] < t])
    out = pd.DataFrame({
        "account_id": X.index.astype(int),
        "p_active": np.round(p, 4),
        "reasons": _reasons(contrib, bundle.features),
        "already_active": X.index.isin(fa.index),
    })
    return out.reset_index(drop=True)
