"""Comp simulator: each plan's ``formula`` on a hand-built rep and book."""
from __future__ import annotations

import pandas as pd
import pytest

from ignition.services import team

AS_OF = pd.Timestamp("2026-10-05")
START = pd.Timestamp("2026-01-01")
FRAC = (AS_OF - START).days / 365.0


def approx(v):
    return pytest.approx(v, abs=0.02)  # payouts are rounded to cents


def plan(pid: str, **params) -> dict:
    p = next(p for p in team.plans() if p["plan_id"] == pid)
    return team.merge_params(p, params)


@pytest.fixture()
def book():
    reps = pd.DataFrame([{"id": 1, "name": "Test Rep", "role": "AE", "quota_funded_annual": 24}])
    acc = pd.DataFrame([
        # A1: active in 14 d (60-d + 21-d bonus), 300k contracts → kicker capped at $10k
        {"id": 1, "rep_id": 1, "signed_at": "2026-02-01", "funded_at": "2026-03-01", "first_qualifying_trade_at": "2026-03-02", "is_liquidity_partner": False},
        # A2: active in 45 d (60-d only), 40k contracts → $2,000 kicker
        {"id": 2, "rep_id": 1, "signed_at": "2026-04-01", "funded_at": "2026-05-01", "first_qualifying_trade_at": "2026-05-10", "is_liquidity_partner": False},
        # A3: never trades → clawback
        {"id": 3, "rep_id": 1, "signed_at": "2026-05-01", "funded_at": "2026-06-01", "first_qualifying_trade_at": None, "is_liquidity_partner": False},
        # another rep's account is ignored
        {"id": 4, "rep_id": 2, "signed_at": "2026-05-01", "funded_at": "2026-06-01", "first_qualifying_trade_at": None, "is_liquidity_partner": False},
    ])
    for c in ("signed_at", "funded_at", "first_qualifying_trade_at"):
        acc[c] = pd.to_datetime(acc[c])
    acc = acc.set_index("id")
    trades = pd.DataFrame([
        {"account_id": 1, "ts": pd.Timestamp("2026-04-01"), "contracts": 300_000},
        {"account_id": 2, "ts": pd.Timestamp("2026-06-01"), "contracts": 40_000},
    ])
    fa = pd.Series({1: pd.Timestamp("2026-03-15"), 2: pd.Timestamp("2026-06-15")})
    return reps, acc, trades, fa


def run(p, book):
    reps, acc, trades, fa = book
    return team.compute_payouts(p, reps, acc, trades, fa, as_of=AS_OF, period_start=START)[0]


def test_activation_adv_formula(book):
    r = run(plan("activation_adv"), book)
    b = r["payout_breakdown"]
    # milestones: A1 2000×(0.5+1+0.25) + A2 2000×(0.5+1) + A3 2000×0.5 = 7,500
    assert b["funded"] == approx(3 * 1000)
    assert b["activation"] == approx(2 * 2000)
    assert b["speed_bonus"] == approx(500)
    assert b["clawback"] == approx(-1000)          # 100% of A3's funding payment
    assert b["adv_kicker"] == approx(10_000 + 2_000)  # capped at $10k for A1
    assert b.get("kicker_accelerator", 0) == 0             # 240k capped contracts < prorated 560k target
    assert r["payout_variable"] == approx(7_500 - 1_000 + 12_000)
    assert r["funded_ytd"] == 3 and r["active_60d"] == 2


def test_kicker_accelerator_and_lp_credit(book):
    reps, acc, trades, fa = book
    p = plan("activation_adv", volume_target_contracts_annual=100_000)  # V = 100k × FRAC
    r = run(p, book)
    V = 100_000 * FRAC
    assert r["payout_breakdown"]["kicker_accelerator"] == approx(0.5 * 50 * (240_000 - V) / 1000)
    acc2 = acc.copy()
    acc2.loc[1, "is_liquidity_partner"] = True
    r2 = team.compute_payouts(plan("activation_adv"), reps, acc2, trades, fa, as_of=AS_OF, period_start=START)[0]
    assert r2["payout_breakdown"]["adv_kicker"] == approx(50 * 300_000 * 0.25 / 1000 + 2_000)


def test_pay_on_funded_formula(book):
    r = run(plan("pay_on_funded"), book)
    unit = 4166.67
    assert r["payout_breakdown"]["funded"] == approx(3 * unit)
    assert r["payout_breakdown"]["clawback"] == approx(-0.5 * unit)  # A3: no qualifying trade in 60 d
    assert r["payout_variable"] == approx(2.5 * unit)


def test_accelerator_applies_above_prorated_quota(book):
    p = plan("pay_on_funded", quota_funded_annual=2)  # Q = 2 × FRAC ≈ 1.52 → k = 2, 3 accelerate
    r = run(p, book)
    unit = 4166.67
    assert r["payout_variable"] == approx(unit * (1 + 1.5 + 1.5) - 0.5 * unit * 1.5)
    assert r["payout_breakdown"]["accelerator"] == approx(unit * 0.5 * 2)


def test_pay_on_signature_formula(book):
    r = run(plan("pay_on_signature"), book)
    assert r["payout_variable"] == approx(3 * 4166.67)
    assert "clawback" not in r["payout_breakdown"] or r["payout_breakdown"]["clawback"] == 0
    q = run(plan("pay_on_signature", quota_funded_annual=2), book)
    Q = 2 * FRAC
    assert q["payout_variable"] == approx(4166.67 * Q + 4166.67 * 1.5 * (3 - Q))


def test_merge_params_partial_and_validation():
    p = plan("activation_adv", per_account_unit=2500, multipliers={"funded": 0.6})
    assert p["per_account_unit"] == 2500 and p["multipliers"] == {"signed": 0.0, "funded": 0.6, "active_60d": 1.0, "active_21d_bonus": 0.25}
    with pytest.raises(team.CompParamError):
        plan("activation_adv", clawback_pct=50)  # must be a 0–1 fraction
    with pytest.raises(team.CompParamError):
        plan("activation_adv", multipliers={"bogus": 1})
    with pytest.raises(team.CompParamError):
        plan("activation_adv", accelerator=-1)
