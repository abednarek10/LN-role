"""Propensity model: holdout quality, time split, leakage, reasons, scoring."""
from __future__ import annotations

import inspect
from dataclasses import replace
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from ignition import definitions as D
from ignition.services import features as F
from ignition.services import propensity as P


def test_holdout_quality(model_bundle):
    r = P.model_report(model_bundle)
    assert 0.70 <= r["auc"] <= 0.90, r["auc"]
    assert r["lift_top_decile"] >= 2.0
    assert 0 < r["base_rate"] < 0.6
    assert r["brier"] < r["base_rate"] * (1 - r["base_rate"])  # beats the constant predictor
    assert r["challenger"]["name"] == "HistGradientBoostingClassifier"
    assert 0.65 <= r["challenger"]["auc"] <= 0.95


def test_report_shape_matches_api_contract(model_bundle):
    r = P.model_report(model_bundle)
    for k in ("target", "train_n", "test_n", "auc", "pr_auc", "brier", "base_rate", "lift_top_decile", "gain_curve",
              "calibration", "coefficients", "challenger"):
        assert k in r
    assert set(r["challenger"]) >= {"name", "auc", "lift_top_decile"}
    gains = [g["pct_positives"] for g in r["gain_curve"]]
    assert gains == sorted(gains) and gains[-1] == pytest.approx(1.0) and gains[0] > 0.1 * 2
    assert all(set(c) == {"bin", "predicted", "observed", "n"} for c in r["calibration"])
    assert sum(c["n"] for c in r["calibration"]) == r["test_n"]
    assert {c["feature"] for c in r["coefficients"]} == set(F.FEATURES)
    assert all(isinstance(c["label"], str) and c["label"] for c in r["coefficients"])


def test_time_based_split(model_bundle):
    tr, te = model_bundle.train, model_bundle.test
    assert tr["snapshot"].max() < te["snapshot"].min()
    assert te["snapshot"].max() + pd.Timedelta(days=D.ACTIVATION_WINDOW_D) <= pd.Timestamp(D.AS_OF)
    assert tr["snapshot"].max() <= pd.Timestamp(P.TRAIN_END)


def test_population_excludes_lp_and_already_active(model_bundle, frames):
    lp = set(frames.accounts.loc[frames.accounts["is_liquidity_partner"], "id"])
    data = pd.concat([model_bundle.train, model_bundle.test])
    assert not set(data["account_id"]) & lp
    fa = F.first_active_at(frames.trades)
    merged = data.assign(fa=data["account_id"].map(fa))
    assert not (merged["fa"] < merged["snapshot"]).any()


def test_labels_match_active_definition(frames):
    t = pd.Timestamp("2026-06-01")
    y = F.activation_labels(frames, t)
    fa = F.first_active_at(frames.trades)
    for aid in y[y == 1].index[:25]:
        d = fa[aid]
        assert t < d <= t + pd.Timedelta(days=60)
        days = frames.trades[(frames.trades["account_id"] == aid) & (frames.trades["ts"] <= d)]["ts"].dt.normalize().unique()
        days = sorted(days)[-4:]
        assert len(days) == 4 and (days[-1] - days[0]) <= pd.Timedelta(days=29)


def _truncate(frames, t):
    t = pd.Timestamp(t)
    return replace(
        frames,
        activities=frames.activities[frames.activities["ts"] < t],
        onboarding_events=frames.onboarding_events[frames.onboarding_events["ts"] < t],
        trades=frames.trades[frames.trades["ts"] < t],
        market_prices=frames.market_prices[frames.market_prices["ts"] < t],
    )


@pytest.mark.parametrize("t", [datetime(2026, 3, 2), datetime(2026, 6, 1), datetime(2026, 8, 17, 13)])
def test_no_leakage_from_future_rows(frames, t):
    """Features at t are unchanged after deleting every row with ts >= t."""
    full = F.features_as_of(frames, t)
    cut = F.features_as_of(_truncate(frames, t), t)
    pd.testing.assert_frame_equal(full, cut)


def test_no_leakage_from_outcome_columns(frames):
    """Scrambling stage / *_at / latent columns doesn't move features."""
    t = datetime(2026, 6, 1)
    acc = frames.accounts.copy()
    for c in ("signed_at", "kyc_approved_at", "funded_at", "first_trade_at", "first_qualifying_trade_at",
              "active_since"):
        acc[c] = pd.NaT
    acc["stage"] = "TARGET"
    acc["latent_propensity"] = 0.0
    pd.testing.assert_frame_equal(F.features_as_of(frames, t), F.features_as_of(replace(frames, accounts=acc), t))
    src = inspect.getsource(F.features_as_of) + inspect.getsource(F.static_features)
    assert "latent_propensity" not in src and '"stage"' not in src


def test_feature_matrix_sane(frames):
    X = F.features_as_of(frames, D.AS_OF)
    assert list(X.columns) == F.FEATURES
    assert len(X) == len(frames.accounts)
    assert np.isfinite(X.to_numpy()).all()
    assert X.index.name == "account_id"


def test_score_accounts(model_bundle, frames):
    sc = P.score_accounts(model_bundle, frames)
    assert list(sc.columns[:3]) == ["account_id", "p_active", "reasons"]
    lp = set(frames.accounts.loc[frames.accounts["is_liquidity_partner"], "id"])
    assert not set(sc["account_id"]) & lp
    assert len(sc) == len(frames.accounts) - len(lp)
    assert sc["p_active"].between(0, 1).all()
    for reasons in sc["reasons"]:
        assert 1 <= len(reasons) <= 3
        for r in reasons:
            assert r["direction"] in ("+", "-") and isinstance(r["label"], str) and r["label"]
            assert (r["weight"] > 0) == (r["direction"] == "+")
    # funded-not-trading accounts outrank never-logged-in signers on average
    acc = frames.accounts.set_index("id")
    st = sc.assign(stage=sc["account_id"].map(acc["stage"]))
    assert st[st["stage"] == "FUNDED"]["p_active"].mean() > st[st["stage"] == "TARGET"]["p_active"].mean()
    active = st[st["stage"].isin(D.ACTIVE_STAGES)]
    assert active["already_active"].all()


def test_contributions_sum_to_logit(model_bundle, frames):
    ids = frames.accounts.loc[frames.accounts["stage"] == "FUNDED", "id"].tolist()[:20]
    X = F.features_as_of(frames, D.AS_OF, ids)[model_bundle.features].to_numpy()
    scaler = model_bundle.model.named_steps["scale"]
    lr = model_bundle.model.named_steps["lr"]
    contrib = scaler.transform(X) * lr.coef_[0]
    logit = contrib.sum(axis=1) + lr.intercept_[0]
    p = model_bundle.model.predict_proba(X)[:, 1]
    assert np.allclose(1 / (1 + np.exp(-logit)), p)


def test_reason_labels_cover_features():
    labels = P.reason_labels()
    for f in F.FEATURES:
        assert f in labels and {"label", "high", "low"} <= set(labels[f]), f


def test_reasons_state_facts(model_bundle, frames):
    """Reason text matches the account's actual value; absent one-hots never appear."""
    sc = P.score_accounts(model_bundle, frames).set_index("account_id")
    acc = frames.accounts.set_index("id")
    labels = P.reason_labels()
    for aid, reasons in sc["reasons"].items():
        for r in reasons:
            f = r["feature"]
            if f.startswith("seg_"):
                assert acc.loc[aid, "segment"] == f[4:]
                assert r["label"] == labels[f]["high"]
            if f.startswith("iso_"):
                assert acc.loc[aid, "primary_iso"] == f[4:]


def test_score_at_past_snapshot_uses_past_only(model_bundle, frames):
    t = datetime(2026, 7, 6)
    a = P.score_accounts(model_bundle, frames, t=t)
    b = P.score_accounts(model_bundle, _truncate(frames, t), t=t)
    pd.testing.assert_series_equal(a["p_active"], b["p_active"])


def test_snapshot_schedule():
    snaps = P.snapshot_dates()
    assert snaps[0] == P.SNAPSHOT_START and all((b - a) == timedelta(days=7) for a, b in zip(snaps, snaps[1:]))
    assert snaps[-1] <= P.TEST_END
