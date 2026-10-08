"""Funnel step math on a hand-built onboarding pivot."""
from __future__ import annotations

import pandas as pd
import pytest

from ignition import definitions as D
from ignition.services import funnel as F

T0 = pd.Timestamp("2026-06-01")


def pivot(rows: dict[int, dict[str, float]]) -> pd.DataFrame:
    """{account: {step: day offset}} → account × step first-ts pivot."""
    df = pd.DataFrame(index=list(rows), columns=D.ONBOARDING_STEPS, dtype="datetime64[ns]")
    for a, steps in rows.items():
        for s, d in steps.items():
            df.loc[a, s] = T0 + pd.Timedelta(days=d)
    return df


def test_step_conversion_median_p75():
    p = pivot({
        1: {"contract_signed": 0, "platform_account_created": 1, "first_login": 2, "kyc_submitted": 4},
        2: {"contract_signed": 0, "platform_account_created": 1, "first_login": 4},
        3: {"contract_signed": 0, "platform_account_created": 3},
        4: {"contract_signed": 0},
    })
    st = {s["step"]: s for s in F.step_stats(p)}
    assert st["contract_signed"]["n"] == 4 and st["contract_signed"]["conv_from_prev"] is None
    assert st["platform_account_created"]["n"] == 3 and st["platform_account_created"]["conv_from_prev"] == 0.75
    assert st["platform_account_created"]["n_mature"] == 4  # all signed ≥ 90 d before AS_OF
    assert st["platform_account_created"]["median_days_from_prev"] == pytest.approx(1.0)
    assert st["platform_account_created"]["p75_days"] == pytest.approx(2.0)
    assert st["first_login"]["conv_from_prev"] == pytest.approx(2 / 3, abs=1e-4)
    assert st["first_login"]["median_days_from_prev"] == pytest.approx(2.0)  # (1, 3)
    assert st["kyc_submitted"]["conv_from_prev"] == 0.5
    assert st["kyc_approved"]["n"] == 0 and st["kyc_approved"]["conv_from_prev"] == 0.0
    assert st["bank_linked"]["conv_from_prev"] is None  # 0 / 0
    assert [s["step"] for s in F.step_stats(p)] == D.MAIN_PATH_STEPS


def test_mature_cohorts_exclude_in_flight_accounts():
    """CTO B5: accounts that signed recently and have not had time to finish a step are not drop-offs."""
    recent = pd.Timestamp(D.AS_OF) - pd.Timedelta(days=5)
    df = pd.DataFrame(index=[1, 2, 3, 4], columns=D.ONBOARDING_STEPS, dtype="datetime64[ns]")
    for a in (1, 2):  # old accounts, both completed the step in 2 days
        df.loc[a, "contract_signed"] = T0
        df.loc[a, "platform_account_created"] = T0 + pd.Timedelta(days=2)
    for a in (3, 4):  # signed 5 days ago, still in flight
        df.loc[a, "contract_signed"] = recent
    st = {s["step"]: s for s in F.step_stats(df)}["platform_account_created"]
    assert st["conv_all"] == 0.5 and st["n_mature"] == 2 and st["conv_from_prev"] == 1.0


def test_severity_buckets():
    assert F.severity_of(1.3, 8) == "critical"      # broad KYC-loop leak
    assert F.severity_of(1.0, 6) == "high"
    assert F.severity_of(0.5, 6) == "medium"
    assert F.severity_of(0.2, 5) == "low"


def test_friction_detects_planted_segment_gap():
    rows, acc = {}, []
    for i in range(40):
        seg = "UTILITY" if i < 10 else "REP"
        slow = seg == "UTILITY"
        rows[i] = {"contract_signed": 0, "platform_account_created": 1, "first_login": 2, "kyc_submitted": 3}
        if not slow or i < 4:  # UTILITY converts 4/10 at KYC approval vs 30/30 for REP
            rows[i]["kyc_approved"] = 4 + (8 if slow else 1)
        acc.append({"id": i, "segment": seg, "is_liquidity_partner": False, "p_active": 0.5, "exp_adv": 40.0})
    p = pivot(rows)
    a = pd.DataFrame(acc).set_index("id")
    cards = F.detect_friction(a, p, p.index, pd.Series(dtype=float), min_affected=1)
    util = [c for c in cards if c["segment"] == "UTILITY" and c["step"] == "kyc_approved"]
    assert len(util) == 1
    c = util[0]
    conv = next(m for m in c["metrics"] if m["metric"] == "conversion")
    assert conv["value"] == pytest.approx(0.4) and conv["benchmark"] == pytest.approx(34 / 40)
    assert c["accounts_affected"] == 6 and c["adv_at_stake"] == pytest.approx(6 * 0.5 * 40)
    assert "Ask:" in c["roadmap_ask"] and c["severity"] in {"low", "medium", "high", "critical"}
    assert c["step_label"] == "KYC approved" and c["from_step_label"] == "KYC submitted"
    # cards with fewer than 5 accounts affected are dropped by default
    assert F.detect_friction(a, p, p.index, pd.Series(dtype=float))[0]["accounts_affected"] >= 5
    assert not any(c["segment"] == "REP" for c in cards)
