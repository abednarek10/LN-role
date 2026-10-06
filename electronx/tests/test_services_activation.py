"""Queue formula and NBA rule matching on hand-built account rows (no DB)."""
from __future__ import annotations

import pandas as pd
import pytest

from ignition import definitions as D
from ignition.services import activation as A

AS_OF = pd.Timestamp(D.AS_OF)
NaT = pd.NaT


def days_ago(n: float) -> pd.Timestamp:
    return AS_OF - pd.Timedelta(days=n)


def row(id_, **kw) -> dict:
    base = dict(
        id=id_, name=f"Acct {id_}", segment="REP", side="hedger", is_liquidity_partner=False, stage="FUNDED",
        primary_iso="ERCOT", hub="HB_HOUSTON", isos=["ERCOT"], p_active=0.5, exp_adv=100.0, trading_days_30=0,
        td_prior30=0, adv_20td=0.0, created_at=days_ago(120), n_touches=3, stage_entry_ts=days_ago(10),
        signed_at=days_ago(40), ob_kyc_submitted=days_ago(35), kyc_approved_at=days_ago(20), funded_at=days_ago(10),
        first_trade_at=NaT, first_qualifying_trade_at=NaT, ob_api_key_created=NaT, last_trig_ts=NaT,
        last_touch_ts=days_ago(9), trade_days_total=0, active_since=NaT, isos_traded_90d=[], tenors_traded_90d=[],
        last_qbr_ts=NaT, last_trade_ts=NaT, days_in_stage=10, rep_id=1, rep_name="Rep", reasons=[],
    )
    base.update(kw)
    return base


TRIG = {"trigger_id": "ERCOT-HB_HOUSTON-20261002", "iso": "ERCOT", "hub": "HB_HOUSTON", "severity": 92.0,
        "start_ts": AS_OF - pd.Timedelta(days=2, hours=9), "forward_risk": True}


def table(*rows) -> pd.DataFrame:
    return pd.DataFrame(list(rows)).set_index("id", drop=False)


def test_rules_sorted_and_vocabulary():
    rl = A.rules()
    assert rl[0]["rule_id"] == "R09" and rl[-1]["condition_code"] == "DEFAULT"
    assert all(r["condition_code"] in A.CONDITION_CODES for r in rl)


def test_priority_formula_and_caps():
    # an Active speculator keeps hedger share of Active at 0% → B = 1.15 for hedgers
    acc = table(row(1), row(2, segment="PROP", side="speculator", stage="ACTIVE", trading_days_30=10, isos=["PJM"],
                            primary_iso="PJM", hub="PJM_WESTERN_HUB"))
    out = A.score_rows(acc, [TRIG])
    r = out.loc[1]
    # U = 1.5 (trigger) × 1.25 (stalled: funded >7 d) × 1.2 (forecast, not touched in 5 d) = 2.25 → capped 2.0
    assert r["stall"] and r["urgency"] == pytest.approx(2.0)
    assert r["balance_weight"] == pytest.approx(1.15) and r["k_stage"] == pytest.approx(0.35)
    assert r["priority"] == pytest.approx(0.5 * 100 * 0.35 * 2.0 * 1.15, rel=1e-6)
    assert r["trigger_id"] == TRIG["trigger_id"] and r["next_action"]["rule_id"] == "R09"
    assert out.loc[2, "balance_weight"] == 1.0


def test_balance_weight_off_when_hedgers_at_target():
    acc = table(row(1), row(2, stage="ACTIVE", trading_days_30=8))  # active hedger → share 100%
    assert A.score_rows(acc, []).loc[1, "balance_weight"] == 1.0


def test_touch_suppresses_trigger_and_forecast_urgency():
    acc = table(row(1, last_trig_ts=AS_OF, last_touch_ts=AS_OF))
    r = A.score_rows(acc, [TRIG]).loc[1]
    assert r["urgency"] == pytest.approx(1.25)  # stall only
    assert r["trigger_id"] is None
    assert r["next_action"]["rule_id"] == "R06"  # funded >7 d, volatility rule suppressed (14-day cooldown)


def test_liquidity_partners_excluded():
    acc = table(row(1), row(2, is_liquidity_partner=True, side="liquidity_partner", segment="PROP"))
    assert list(A.score_rows(acc, []).index) == [1]


@pytest.mark.parametrize("kw, expected", [
    (dict(stage="FUNDED", funded_at=days_ago(25)), "R07"),                                   # 21 d beats 7 d
    (dict(stage="FUNDED", funded_at=days_ago(10)), "R06"),
    (dict(stage="FUNDED", funded_at=days_ago(10), segment="PROP", side="speculator"), "R08"),  # segments honored
    (dict(stage="FUNDED", funded_at=days_ago(3)), "R99"),
    (dict(stage="SIGNED", signed_at=days_ago(5), ob_kyc_submitted=NaT, kyc_approved_at=NaT, funded_at=NaT), "R03"),
    (dict(stage="SIGNED", signed_at=days_ago(12), ob_kyc_submitted=days_ago(7), kyc_approved_at=NaT, funded_at=NaT), "R04"),
    (dict(stage="KYC_APPROVED", kyc_approved_at=days_ago(6), funded_at=NaT), "R05"),
    (dict(stage="QUALIFIED", stage_entry_ts=days_ago(15), signed_at=NaT, funded_at=NaT), "R02"),
    (dict(stage="QUALIFIED", stage_entry_ts=days_ago(3), signed_at=NaT, funded_at=NaT), "R99"),
    (dict(stage="FIRST_TRADE", first_trade_at=days_ago(15), first_qualifying_trade_at=days_ago(15), trade_days_total=1,
          trading_days_30=1, last_trade_ts=days_ago(15)), "R10"),
    (dict(stage="ACTIVE", trading_days_30=4, td_prior30=10, active_since=days_ago(90)), "R11"),
    (dict(stage="ACTIVE", trading_days_30=10, td_prior30=10, active_since=days_ago(90), isos=["ERCOT", "PJM"],
          isos_traded_90d=["ERCOT"], tenors_traded_90d=["HOURLY", "DAILY_PEAK"]), "R12"),
    (dict(stage="DORMANT", funded_at=days_ago(120), trading_days_30=0, last_trade_ts=days_ago(45)), "R14"),
])
def test_nba_first_match(kw, expected):
    ctx = A.NBAContext(as_of=AS_OF, triggers=[], top_decile_p=0.9)
    assert A.next_best_action(row(1, **kw), ctx)["rule_id"] == expected


def test_nba_trigger_rules_by_stage_and_top20():
    ctx = A.NBAContext(as_of=AS_OF, triggers=[TRIG], top20_ids=frozenset({7}))
    assert A.next_best_action(row(1, stage="SIGNED"), ctx)["rule_id"] == "R09"
    active = row(7, stage="ACTIVE", trading_days_30=10, td_prior30=10, active_since=days_ago(30))
    assert A.next_best_action(active, ctx)["rule_id"] == "R15"  # active → market note, not a sequence
    ctx2 = A.NBAContext(as_of=AS_OF, triggers=[], top20_ids=frozenset({7}))
    assert A.next_best_action(active, ctx2)["rule_id"] == "R13"
    # exposure is by ISO: a PJM-only account is not hit by an ERCOT trigger
    assert A.next_best_action(row(1, isos=["PJM"]), ctx)["rule_id"] == "R06"


def test_top_decile_untouched_and_sla_breach():
    ctx = A.NBAContext(as_of=AS_OF, triggers=[], top_decile_p=0.6)
    tgt = row(1, stage="TARGET", p_active=0.7, n_touches=0, created_at=days_ago(4), signed_at=NaT, funded_at=NaT,
              last_touch_ts=NaT)
    na = A.next_best_action(tgt, ctx)
    assert na["rule_id"] == "R01" and na["sla"] == "24h" and na["sla_breached"] is True
    assert A.next_best_action(dict(tgt, p_active=0.4), ctx)["rule_id"] == "R99"
    # SLA not breached when a touch landed after the condition started
    funded = row(1, funded_at=days_ago(10), last_touch_ts=days_ago(1))
    assert A.next_best_action(funded, ctx)["sla_breached"] is False
