"""Comp simulator: each plan's v1.1 ``formula`` on the COMP_PLAN.md §3 worked example (AE A, one full year)."""
from __future__ import annotations

import pandas as pd
import pytest

from ignition.services import team

START = pd.Timestamp("2026-01-01")
AS_OF = pd.Timestamp("2027-01-01")  # exactly 365 days → frac = 1, Q = 48 (full plan year as in COMP_PLAN.md)


def approx(v, tol=1.0):
    return pytest.approx(v, abs=tol)  # unit $2,083.33 rounds; the doc quotes whole dollars


def plan(pid: str, **params) -> dict:
    p = next(p for p in team.plans() if p["plan_id"] == pid)
    return team.merge_params(p, params)


def ae_a_book(lp_first: bool = False, start_date="2025-06-01"):
    """52 funded (48 + 4 above quota), 64 signed; 14 Active ≤21 d, 23 at 22–60 d, 6 trade-only, 9 no trade.
    Above quota (k=49..52): 1 fast, 2 slow, 1 no-trade. 1,208k contracts: PROP 450k (capped 400k), PROP 250k, FUND 90k,
    40 hedger traders × 10,450."""
    within = ["fast"] * 13 + ["slow"] * 21 + ["trade"] * 6 + ["none"] * 8
    above = ["fast", "slow", "slow", "none"]
    kinds = within + above
    accs, trades, fa = [], [], {}
    hedger_traders = 0
    for k, kind in enumerate(kinds, start=1):
        fat = START + pd.Timedelta(days=1 + 5 * (k - 1))
        aid = k
        fq = None if kind == "none" else fat + pd.Timedelta(days=3)
        accs.append({"id": aid, "rep_id": 1, "signed_at": fat - pd.Timedelta(hours=12), "funded_at": fat,
                     "first_qualifying_trade_at": fq, "is_liquidity_partner": bool(lp_first and k == 1)})
        if kind == "fast":
            fa[aid] = fat + pd.Timedelta(days=14)
        elif kind == "slow":
            fa[aid] = fat + pd.Timedelta(days=40)
        if kind != "none":
            n = {1: 450_000, 2: 250_000, 3: 90_000}.get(k)
            if n is None:
                n = 10_450
                hedger_traders += 1
            trades.append({"account_id": aid, "ts": fat + pd.Timedelta(days=5), "contracts": n, "fee_usd": n * 0.25})
    assert hedger_traders == 40 and kinds[:3] == ["fast"] * 3
    for j in range(12):  # 12 signatures that never fund
        accs.append({"id": 100 + j, "rep_id": 1, "signed_at": START + pd.Timedelta(days=30 + j), "funded_at": None,
                     "first_qualifying_trade_at": None, "is_liquidity_partner": False})
    acc = pd.DataFrame(accs)
    for c in ("signed_at", "funded_at", "first_qualifying_trade_at"):
        acc[c] = pd.to_datetime(acc[c])
    acc = acc.set_index("id")
    reps = pd.DataFrame([{"id": 1, "name": "AE A", "role": "AE", "quota_funded_annual": 48,
                          "start_date": pd.Timestamp(start_date)}])
    return reps, acc, pd.DataFrame(trades), pd.Series(fa)


def run(p, book, as_of=AS_OF):
    reps, acc, trades, fa = book
    return team.compute_payouts(p, reps, acc, trades, fa, as_of=as_of, period_start=START)[0]


@pytest.fixture(scope="module")
def book():
    return ae_a_book()


def test_worked_example_plan_c(book):
    r = run(plan("activation_adv"), book)
    b = r["payout_breakdown"]
    assert b["funded"] == approx(32_500)                       # 52 × $625, never accelerated
    assert b["activation"] == approx(46_250)                   # 37 × $1,250
    assert b["speed_bonus"] == approx(4_375)                   # 14 × $312.50
    assert b["accelerator"] == approx(2_031.25)                # 0.5 × Active milestones of the 3 Active above-Q accounts
    assert b["clawback"] == approx(-5_625)                     # 9 × $625
    assert b["adv_kicker"] == approx(28_950)                   # 1,158k credited × $25/1k (PROP #1 capped)
    assert b["kicker_accelerator"] == approx(475)              # 0.5 × $25 × (1,158k − 1,120k)/1k
    assert r["payout_variable"] == approx(108_956)
    assert r["book_activation"] == pytest.approx(37 / 52, abs=1e-3) and r["accelerator_applied"] is True
    assert r["fees_ytd"] == approx(302_000) and r["pct_of_fee_revenue"] == pytest.approx(0.361, abs=0.001)


def test_worked_example_plans_a_and_b(book):
    a = run(plan("pay_on_signature"), book)
    assert a["payout_variable"] == approx(150_000) and a["signed_ytd"] == 64     # 48 × $2,083 + 16 × $2,083 × 1.5
    b = run(plan("pay_on_funded"), book)
    assert b["payout_breakdown"]["clawback"] == approx(-9_896)                  # 8 × $1,042 + 1 above-Q × $1,563
    assert b["payout_variable"] == approx(102_604)
    assert b["accelerator_applied"] is True                                      # not gated for (b)
    assert a["pct_of_fee_revenue"] == pytest.approx(0.497, abs=0.001)
    assert b["pct_of_fee_revenue"] == pytest.approx(0.340, abs=0.001)


def test_accelerator_gate_closes_below_book_activation(book):
    r = run(plan("activation_adv", accelerator_min_book_activation=0.8), book)   # 71% < 80% → gate shut
    assert r["accelerator_applied"] is False and r["payout_breakdown"].get("accelerator", 0) == 0
    assert r["payout_variable"] == approx(108_956.25 - 2_031.25)


def test_lp_credit_on_milestones_and_kicker():
    lp = run(plan("activation_adv"), ae_a_book(lp_first=True))
    base = run(plan("activation_adv"), ae_a_book())
    # account 1 (fast Active, 450k): milestones × 0.25; kicker on 112.5k credited contracts instead of the capped 400k,
    # which drops the book below the 1.12M volume target, so the $475 uplift disappears too
    assert base["payout_variable"] - lp["payout_variable"] == approx(
        0.75 * (625 + 1250 + 312.5) + (10_000 - 25 * 112.5) + 475)


def test_proration_from_rep_start_date():
    late = ae_a_book(start_date="2026-07-02")  # 183 days in plan → Q = 48 × 183/365
    r = run(plan("pay_on_funded"), late)
    assert r["quota_ytd"] == pytest.approx(48 * 183 / 365, abs=0.01)
    over = run(plan("pay_on_funded", quota_funded_annual=24), ae_a_book())  # params override every rep's quota
    assert over["quota_ytd"] == pytest.approx(24.0)


def test_merge_params_partial_and_validation():
    p = plan("activation_adv", per_account_unit=2500, multipliers={"funded": 0.6})
    assert p["per_account_unit"] == 2500 and p["multipliers"] == {"signed": 0.0, "funded": 0.6, "active_60d": 1.0, "active_21d_bonus": 0.25}
    assert p["quota_override"] is False
    for bad in (dict(clawback_pct=50), dict(multipliers={"bogus": 1}), dict(accelerator=-1),
                dict(accelerator_min_book_activation=2), dict(lp_milestone_credit="x")):
        with pytest.raises(team.CompParamError):
            plan("activation_adv", **bad)
