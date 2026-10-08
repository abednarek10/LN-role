"""CEO KPI math on a tiny hand-built fixture (CEO memo §1 definitions)."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from ignition import definitions as D
from ignition import repo
from ignition.services import ceo

WE = date(2026, 10, 4)  # Sunday close (X1)


def _frames():
    acc = pd.DataFrame([
        # id, segment, LP, signed, funded, first qualifying trade
        dict(id=1, segment="PROP", is_liquidity_partner=True, signed_at="2025-12-01", funded_at="2026-06-01", first_qualifying_trade_at="2026-06-02"),
        dict(id=2, segment="PROP", is_liquidity_partner=False, signed_at="2026-05-01", funded_at="2026-06-01", first_qualifying_trade_at="2026-06-05"),
        dict(id=3, segment="REP", is_liquidity_partner=False, signed_at="2026-07-01", funded_at="2026-08-15", first_qualifying_trade_at="2026-09-20"),
        dict(id=4, segment="REP", is_liquidity_partner=False, signed_at="2026-07-01", funded_at="2026-08-01", first_qualifying_trade_at="2026-08-20"),
        dict(id=5, segment="STORAGE", is_liquidity_partner=False, signed_at="2026-09-01", funded_at="2026-09-25", first_qualifying_trade_at=None),
        dict(id=6, segment="FUND", is_liquidity_partner=False, signed_at="2026-09-10", funded_at=None, first_qualifying_trade_at=None),
    ])
    window = pd.bdate_range("2026-09-07", "2026-10-02")  # the 20 trading days ending WE
    assert len(window) == 20
    rows = []

    def trade(aid, d, n):
        rows.append(dict(id=len(rows) + 1, account_id=aid, ts=d + pd.Timedelta(hours=15), iso="ERCOT", hub="HB_NORTH",
                         tenor="HOURLY", side="BUY", contracts=n, price=50.0, notional_usd=n * 50.0, fee_usd=n * 0.25, is_maker=False))
    for d in window:
        trade(1, d, 100)          # LP: 20 days × 100
    for d in window[-5:]:
        trade(2, d, 50)           # speculator: 5 days × 50 → Active
    for d in window[-4:]:
        trade(3, d, 10)           # hedger: 4 days → Active
    for d in window[-2:]:
        trade(4, d, 10)           # hedger: 2 days → not Active
    trades = pd.DataFrame(rows)
    sp = pd.DataFrame([dict(id=i, date=d, iso="ERCOT", hub="HB_NORTH", tenor="HOURLY", spread_usd_mwh=0.8 + 0.01 * i,
                            two_sided_uptime_pct=94.0, top_depth_contracts=30, active_accounts=80, lp_quote_share=0.4)
                       for i, d in enumerate(pd.bdate_range("2026-09-28", "2026-10-02"))])
    return repo.frames_from_tables({"accounts": acc, "trades": trades, "spread_snapshots": sp})


@pytest.fixture(scope="module")
def snap():
    return ceo.snapshot(ceo.Base(_frames()), WE)


def test_adv_lp_line_and_notional(snap):
    assert snap["adv"] == pytest.approx((2000 + 250 + 40 + 20) / 20)
    assert snap["adv_lp"] == pytest.approx(100.0) and snap["adv_organic"] == pytest.approx(15.5)
    assert snap["adv_5d"] == pytest.approx((500 + 250 + 40 + 20) / 5)
    # median daily notional (X10): 15 days at $5,000, the busier last five days above → median $5,000
    assert snap["notional_median"] == pytest.approx(5000.0)
    assert snap["notional_mean"] == pytest.approx(snap["adv"] * 50.0)
    assert snap["notional_max"] == pytest.approx(8500.0)
    assert snap["lp_share"] == pytest.approx(100 / 115.5) and snap["hedger_adv"] == pytest.approx(3.0)
    assert snap["fees_20"] == pytest.approx(2310 * 0.25)


def test_active_rate_mix_and_concentration(snap):
    # funded >20 d before close: 1,2,3,4 → Active: 1 (LP), 2, 3
    assert snap["active_rate"] == pytest.approx(0.75)
    assert snap["by_side_accounts"] == {"hedger": 1, "speculator": 1, "liquidity_partner": 1}
    assert snap["hedger_share"] == pytest.approx(1 / 3)
    assert snap["by_side_adv"] == {"hedger": 3.0, "speculator": 12.5, "liquidity_partner": 100.0}
    shares = pd.Series([2000, 250, 40, 20]) / 2310
    assert snap["top5"] == pytest.approx(1.0)
    assert snap["hhi"] == pytest.approx(float((shares ** 2).sum()))


def test_cohort_and_days_to_first_trade(snap):
    # matured last-8-week cohort (funded Jul 9 – Sep 3): #4 traded in 19 d (ok), #3 in 36 d (not)
    assert snap["cohort_n"] == 2 and snap["cohort_rate"] == pytest.approx(0.5)
    # first qualifying trades in trailing 90 d: #3 (36 d), #4 (19 d)
    assert snap["median_days_ft"] == pytest.approx(27.5)
    assert snap["stalled_n"] == 0  # #5 funded only 8 d ago
    assert snap["funded_cum"] == 5 and snap["signed_cum"] == 6
    p = snap["funded_pace"]
    assert p["ytd"] == 5 and p["target"] == 260 and p["run_rate_4w"] == pytest.approx(0.25)  # one funding in 4 weeks
    assert p["needed_weekly"] == pytest.approx((260 - 5) / p["weeks_left"], abs=0.1)
    assert p["projected_eoy"] == round(5 + 0.25 * p["weeks_left"])


def test_spread_snapshot(snap):
    s = snap["spreads"][("ERCOT", "HB_NORTH", "HOURLY")]
    assert s["spread"] == pytest.approx(0.82) and s["uptime"] == pytest.approx(94.0)
    assert snap["spreads"][("PJM", "PJM_WESTERN_HUB", "HOURLY")]["spread"] is None


def test_status_rules():
    assert ceo.status_for(0.71, 0.70) == "on_track"
    assert ceo.status_for(0.61, 0.70) == "watch"
    assert ceo.status_for(0.50, 0.70) == "off_track"
    assert ceo.status_for(0.44, 0.45, higher=False) == "on_track"
    assert ceo.status_for(0.50, 0.45, higher=False) == "watch"
    assert ceo.band_status(0.65, 0.55, 0.75) == "on_track" and ceo.band_status(0.81, 0.55, 0.75) == "off_track"
    assert ceo.spread_status(0.70, 96, 0.75, 95) == "on_track"
    assert ceo.spread_status(0.90, 93, 0.75, 95) == "watch"
    assert ceo.spread_status(1.20, 80, 0.75, 95) == "off_track"


def test_parse_week_end():
    assert ceo.parse_week_end(None) == D.WEEK_END == date(2026, 10, 4)
    assert ceo.parse_week_end("2026-09-30") == date(2026, 10, 4)   # snaps to the Sunday closing its week
    assert ceo.parse_week_end("2026-09-27") == date(2026, 9, 27)
    with pytest.raises(ceo.WeekEndError):
        ceo.parse_week_end("2026-10-09")
