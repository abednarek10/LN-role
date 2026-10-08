"""Queue formula, X5 volatility narrowing, down-ranks and NBA rule matching on hand-built rows (no DB)."""
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
        primary_iso="ERCOT", hub="HB_HOUSTON", isos=["ERCOT"], size_mw=1000.0, p_active=0.5, exp_adv=100.0,
        trading_days_30=0, td_prior30=0, adv_20td=0.0, created_at=days_ago(120), n_touches=3, stage_entry_ts=days_ago(10),
        signed_at=days_ago(40), ob_kyc_submitted=days_ago(35), kyc_approved_at=days_ago(20), funded_at=days_ago(10),
        first_trade_at=NaT, first_qualifying_trade_at=NaT, ob_api_key_created=NaT, last_trig_ts=NaT,
        last_touch_ts=days_ago(9), trade_days_total=0, active_since=NaT, isos_traded_90d=[], tenors_traded_90d=[],
        last_qbr_ts=NaT, last_trade_ts=NaT, last_qual_trade_ts=NaT, last_rejection_ts=NaT, sequenced_events=[],
        health_state="not_started", days_in_stage=10, rep_id=1, rep_name="Rep", reasons=[],
    )
    base.update(kw)
    return base


TRIG = {"trigger_id": "ERCOT-HB_HOUSTON-20261002", "event_id": "ERCOT-20261002", "iso": "ERCOT", "hub": "HB_HOUSTON",
        "severity": 92.0, "start_ts": AS_OF - pd.Timedelta(days=2, hours=9), "forward_risk": True}


def table(*rows) -> pd.DataFrame:
    return pd.DataFrame(list(rows)).set_index("id", drop=False)


def test_rules_sorted_and_vocabulary():
    rl = A.rules()
    assert [r["rule_id"] for r in rl[:4]] == ["R16", "R07", "R04", "R09"]  # X5 precedence
    assert rl[-1]["condition_code"] == "DEFAULT"
    assert all(r["condition_code"] in A.CONDITION_CODES for r in rl)


def test_priority_formula_and_caps():
    # an Active speculator keeps hedger share of Active at 0% → B = 1.5 for hedgers (X9)
    acc = table(row(1), row(2, segment="PROP", side="speculator", stage="ACTIVE", trading_days_30=10, isos=["PJM"],
                            primary_iso="PJM", hub="PJM_WESTERN_HUB", health_state="active"))
    out = A.score_rows(acc, [TRIG])
    r = out.loc[1]
    # U = 1.5 (trigger) × 1.25 (stalled: funded >7 d) × 1.2 (forecast, not touched in 5 d) = 2.25 → capped 2.0
    assert r["stall"] and r["urgency"] == pytest.approx(2.0)
    assert r["balance_weight"] == pytest.approx(1.5) and r["k_stage"] == pytest.approx(0.35)
    assert r["priority"] == pytest.approx(0.5 * 100 * 0.35 * 2.0 * 1.5, rel=1e-6)
    assert r["trigger_id"] == TRIG["trigger_id"] and r["next_action"]["rule_id"] == "R09"
    assert out.loc[2, "balance_weight"] == 1.0


def test_balance_weight_off_when_hedgers_at_target():
    acc = table(row(1), row(2, stage="ACTIVE", trading_days_30=8, health_state="active"))  # active hedger → share 100%
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
    (dict(stage="FUNDED", funded_at=days_ago(25), last_rejection_ts=days_ago(4)), "R16"),    # R16 outranks R07
    (dict(stage="FIRST_TRADE", funded_at=days_ago(30), first_trade_at=days_ago(20), last_rejection_ts=days_ago(2),
          last_qual_trade_ts=days_ago(20), trade_days_total=1, trading_days_30=1, last_trade_ts=days_ago(20)), "R16"),
    (dict(stage="FUNDED", funded_at=days_ago(25), last_rejection_ts=days_ago(9)), "R07"),    # rejection > 7 d ago
    (dict(stage="FUNDED", funded_at=days_ago(25), last_rejection_ts=days_ago(4), last_qual_trade_ts=days_ago(2)), "R07"),
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


def test_x5_volatility_narrowing():
    ctx = A.NBAContext(as_of=AS_OF, triggers=[TRIG])
    nba = lambda **kw: A.next_best_action(row(1, **kw), ctx)["rule_id"]  # noqa: E731
    assert nba() == "R09"                                                   # FUNDED 10 d, exposure 100, P 0.5
    assert nba(funded_at=days_ago(25)) == "R07"                             # R07 outranks R09
    assert nba(stage="SIGNED", signed_at=days_ago(12), ob_kyc_submitted=days_ago(7), kyc_approved_at=NaT,
               funded_at=NaT) == "R04"                                      # SIGNED keeps its KYC rule
    assert nba(p_active=0.97) == "R06"                                      # P ≥ 0.95: will activate anyway
    assert nba(last_touch_ts=days_ago(2)) == "R06"                          # touched in the last 3 days
    assert nba(sequenced_events=["ERCOT-20261002"]) == "R06"                # one sequence per ISO event
    assert nba(size_mw=5.0) == "R06"                                        # exposure < 80 (small load)
    assert nba(hub="HB_WEST", size_mw=40.0) == "R06"                        # other hub ×0.6 → below 80
    assert nba(isos=["PJM"], primary_iso="PJM", hub="PJM_WESTERN_HUB") == "R06"  # not exposed to the ISO
    weak = dict(TRIG, severity=60.0)
    assert A.next_best_action(row(1), A.NBAContext(as_of=AS_OF, triggers=[weak]))["rule_id"] == "R06"  # severity < 70
    q = dict(stage="QUALIFIED", stage_entry_ts=days_ago(3), signed_at=NaT, funded_at=NaT, kyc_approved_at=NaT)
    assert nba(**q) == "R09"                                                # QUALIFIED at exposure ≥ 90
    assert nba(**q, size_mw=60.0) == "R99"                                  # QUALIFIED below 90
    active = dict(stage="ACTIVE", trading_days_30=10, td_prior30=10, active_since=days_ago(30), health_state="active")
    assert nba(**active) == "R15"                                           # Active → market note


def test_trigger_boost_only_for_x5_stages():
    acc = table(row(1, stage="TARGET", signed_at=NaT, funded_at=NaT, kyc_approved_at=NaT, health_state="pre_funding"),
                row(2, stage="SIGNED", funded_at=NaT, kyc_approved_at=NaT, health_state="pre_funding"),
                row(3, stage="AT_RISK", trading_days_30=2, td_prior30=6, first_trade_at=days_ago(60), health_state="at_risk"))
    out = A.score_rows(acc, [TRIG])
    assert out["trigger_id"].isna().all() or all(v is None for v in out["trigger_id"])
    assert all("trigger" not in " ".join(f) for f in out["urgency_factors"])


def test_downranks():
    acc = table(row(1, stage="FIRST_TRADE", health_state="ramping", first_trade_at=days_ago(5), trading_days_30=2,
                    trade_days_total=2, last_trade_ts=days_ago(1), p_active=0.6),
                row(2, stage="FUNDED", funded_at=days_ago(3), p_active=0.6),                 # DEFAULT rule
                row(3, stage="FIRST_TRADE", health_state="at_risk", first_trade_at=days_ago(20), trading_days_30=3,
                    trade_days_total=3, last_trade_ts=days_ago(1), p_active=0.99))          # will activate anyway
    out = A.score_rows(acc, [])
    d1 = A.DOWNRANK_DEFAULT if out.loc[1, "next_action"]["condition_code"] == "DEFAULT" else 1.0
    assert out.loc[1, "k_stage"] == pytest.approx(0.30 * A.DOWNRANK_RAMPING * d1)
    assert any("ramping" in f for f in out.loc[1, "downrank_factors"])
    assert out.loc[2, "next_action"]["rule_id"] == "R99" and out.loc[2, "k_stage"] == pytest.approx(0.35 * A.DOWNRANK_DEFAULT)
    d3 = A.DOWNRANK_DEFAULT if out.loc[3, "next_action"]["condition_code"] == "DEFAULT" else 1.0
    assert out.loc[3, "k_stage"] == pytest.approx(0.30 * A.DOWNRANK_WILL_ACTIVATE * d3)


def test_top_decile_untouched_and_sla_breach():
    ctx = A.NBAContext(as_of=AS_OF, triggers=[], top_decile_p=0.6)
    tgt = row(1, stage="TARGET", p_active=0.7, n_touches=0, created_at=days_ago(4), signed_at=NaT, funded_at=NaT,
              last_touch_ts=NaT)
    na = A.next_best_action(tgt, ctx)
    assert na["rule_id"] == "R01" and na["sla"] == "24h" and na["sla_breached"] is True
    assert A.next_best_action(dict(tgt, p_active=0.4), ctx)["rule_id"] == "R99"
    funded = row(1, funded_at=days_ago(10), last_touch_ts=days_ago(1))
    assert A.next_best_action(funded, ctx)["sla_breached"] is False


def test_today_lists_caps_and_hedger_slots():
    reps = pd.DataFrame([{"id": 1, "name": "AE One", "role": "AE"}, {"id": 6, "name": "Rev Ops", "role": "REVOPS"}])
    recs, subs = [], []
    for i in range(30):
        side = "speculator" if i < 20 else "hedger"  # speculators rank first
        recs.append({"id": i, "side": side, "rep_id": 1, "rep_name": "AE One"})
        subs.append({"next_action": {"owner": "AE"}, "priority": 100 - i})
    listed = A.today_lists(recs, subs, reps, hedger_short=True)
    assert len(listed) == A.OWNER_CAPS["AE"]
    assert sum(recs[i]["side"] == "hedger" for i in listed) >= A.OWNER_CAPS["AE"] / 2
    order = A.balance_order(listed, recs, subs, True)
    for n in range(1, len(order) + 1):  # every prefix keeps ≥50% hedgers while hedgers remain
        assert sum(recs[i]["side"] == "hedger" for i in order[:n]) >= n // 2
