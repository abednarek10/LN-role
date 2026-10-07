"""Seed: determinism, calibration (spec §C) and embedded causal structure (§D)."""
from __future__ import annotations

import os
import re
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from ignition import definitions as D
from ignition import seed as S
from ignition.services import features as F
from ignition.services import volatility as V


@pytest.fixture(scope="module")
def report(seeded_tables):
    return S.calibration_report(seeded_tables)


# ---------------------------------------------------------------------------
# Shape & determinism
# ---------------------------------------------------------------------------
def test_row_counts(frames):
    assert len(frames.accounts) == S.N_ACCOUNTS
    assert frames.accounts["is_liquidity_partner"].sum() == S.N_LP
    roles = frames.reps["role"].value_counts().to_dict()
    assert roles == {"AE": 4, "STRATEGIC": 1, "REVOPS": 2, "MARKETING": 1, "PARTNERSHIPS": 1}
    hours = int((D.AS_OF - D.HISTORY_START).total_seconds() // 3600)
    assert len(frames.market_prices) == hours * len(D.HUBS)
    assert frames.market_prices["ts"].min() == pd.Timestamp(D.HISTORY_START)
    assert frames.market_prices["ts"].max() == pd.Timestamp(D.AS_OF - timedelta(hours=1))
    assert len(frames.price_forecasts) == D.FORECAST_DAYS * len(D.HUBS)
    assert set(frames.spread_snapshots["tenor"]) == set(D.SPREAD_TENORS)
    assert len(frames.marketing_spend) == 12 * len(D.CHANNELS)
    assert len(frames.trades) > 10_000
    assert len(frames.activities) > 5_000
    assert len(frames.outreach_drafts) == 0


def test_db_roundtrip_and_determinism(frames, seeded_tables):
    """Same seed → same data: a fresh generation matches what is in the DB."""
    again = S.generate(S.SEED)
    assert S.checksum(again) == S.checksum(frames.tables) == S.checksum(seeded_tables)
    pd.testing.assert_series_equal(
        again["accounts"]["stage"].reset_index(drop=True), frames.accounts["stage"].reset_index(drop=True),
        check_names=False, check_dtype=False,
    )


def test_db_size(engine):
    url = str(engine.url)
    if url.startswith("sqlite:///"):
        path = url.removeprefix("sqlite:///")
        assert os.path.getsize(path) < 60 * 1024 * 1024


def test_no_events_after_as_of(frames):
    created = frames.accounts.set_index("id")["created_at"]
    for name in ("activities", "onboarding_events", "trades"):
        df = frames.tables[name]
        assert df["ts"].max() < pd.Timestamp(D.AS_OF), name
        assert (df["ts"] >= df["account_id"].map(created)).all(), name
    assert frames.trades["ts"].min() >= pd.Timestamp(D.HISTORY_START)
    assert (frames.trades["ts"].dt.dayofweek < 5).all(), "trades only on weekdays"


def test_names_fictional_and_unique(frames):
    names = frames.accounts["name"]
    assert names.is_unique
    banned = ["Vistra", "NRG", "Calpine", "Constellation", "Tenaska", "Citadel", "Jane Street", "Vitol",
              "Shell", "BP ", "Exelon", "Duke", "Oncor", "Reliant", "TXU", "Bluebonnet Electric", "Pedernales"]
    for b in banned:
        assert not names.str.contains(b, regex=False).any(), b
    assert frames.contacts["email"].str.endswith(".example").all()
    counts = frames.contacts.groupby("account_id").size()
    assert counts.min() >= 1 and counts.max() <= 5
    assert set(frames.contacts["persona"]) <= set(D.PERSONAS)


def test_enums_respected(frames):
    a, ac, ob, tr = frames.accounts, frames.activities, frames.onboarding_events, frames.trades
    assert set(a["segment"]) == set(D.SEGMENT_CODES)
    assert set(a["stage"]) <= set(D.STAGES)
    assert set(a["lead_source"]) <= set(D.CHANNELS)
    assert set(a["tam_tier"]) <= {"A", "B", "C"}
    assert set(ac["kind"]) <= set(D.ACTIVITY_KINDS)
    assert set(ac["outcome"]) <= set(D.ACTIVITY_OUTCOMES)
    assert set(ob["step"]) <= set(D.ONBOARDING_STEPS)
    assert set(tr["tenor"]) == set(D.TENORS)
    assert set(tr["side"]) == {"BUY", "SELL"}
    assert (tr["hub"].map(D.HUB_ISO) == tr["iso"]).all()
    assert (a["hub"].map(D.HUB_ISO) == a["primary_iso"]).all()
    for csv, primary in zip(a["exposure_isos"], a["primary_iso"]):
        isos = D.parse_isos(csv)
        assert primary in isos and set(isos) <= set(D.ISO_CODES)
    owner_reps = set(frames.reps.loc[frames.reps["role"].isin(D.QUOTA_ROLES | {"PARTNERSHIPS"}), "id"])
    assert set(a["rep_id"].dropna().astype(int)) <= owner_reps


def test_trade_economics(frames):
    tr = frames.trades
    fee = np.where(tr["is_maker"], D.FEE_MAKER_PER_CONTRACT, D.FEE_TAKER_PER_CONTRACT) * tr["contracts"]
    assert np.allclose(tr["fee_usd"], fee, atol=0.011)
    mwh = tr["tenor"].map(D.TENORS)
    assert np.allclose(tr["notional_usd"], tr["contracts"] * mwh * tr["price"], rtol=1e-6, atol=0.05)
    # heavy-tailed sizes: top 10% of accounts carry most of the volume
    by = tr.groupby("account_id")["contracts"].sum().sort_values(ascending=False)
    assert by.head(max(1, len(by) // 10)).sum() / by.sum() > 0.5
    lp = set(frames.accounts.loc[frames.accounts["is_liquidity_partner"], "id"])
    lp_share = tr[tr["account_id"].isin(lp)]["contracts"].sum() / tr["contracts"].sum()
    assert 0.3 < lp_share < 0.75


# ---------------------------------------------------------------------------
# Calibration vs spec §C ("the synthetic now")
# ---------------------------------------------------------------------------
def test_calibration_funnel(report):
    assert 300 <= report["signed"] <= 360  # ≈330
    assert 180 <= report["funded"] <= 230  # ≈205
    assert 0.55 <= report["active_rate"] <= 0.70  # ≈62%


def test_calibration_volume(report):
    assert 13_000 <= report["adv_20td"] <= 18_000  # ≈14–17k
    months = report["monthly_adv"]
    assert months["2026-09"] > months["2026-06"] > months["2026-03"]  # rising
    assert 0.38 <= report["hedger_share_active"] <= 0.50  # ≈44%, below the 50% target
    assert 0.45 <= report["top5_adv_share"] <= 0.58  # ≈50%, above the 45% ceiling


def test_calibration_spreads(report):
    assert 0.75 <= report["ercot_north_spread_now"] <= 1.10  # ≈$0.9/MWh
    assert report["ercot_north_spread_q1"] > report["ercot_north_spread_now"]  # tightening
    assert report["ercot_north_uptime_now"] < D.TARGETS_2026["uptime_pct"]["ERCOT"]


def test_calibration_cohort_activation(report):
    assert 0.40 <= report["cohort_activation_30d_last8w"] <= 0.65  # ≈50%
    q = report["cohort_activation_30d_by_quarter"]
    assert q["2026Q3"]["rate"] > q["2026Q1"]["rate"]  # trending up


def test_spreads_follow_active_accounts(frames):
    """Liquidity flywheel: spread = a + b/sqrt(active) ⇒ strongly negative corr."""
    sp = frames.spread_snapshots
    for (hub, tenor), g in sp.groupby(["hub", "tenor"]):
        r = np.corrcoef(g["spread_usd_mwh"], g["active_accounts"])[0, 1]
        assert r < -0.6, (hub, tenor, r)
    hn = sp[(sp["hub"] == "HB_NORTH") & (sp["tenor"] == "HOURLY")]
    x = 1 / np.sqrt(hn["active_accounts"] + 3)
    b, a = np.polyfit(x, hn["spread_usd_mwh"], 1)
    assert b > 0 and 0.2 < a < 1.0


# ---------------------------------------------------------------------------
# Stage consistency with events / trades
# ---------------------------------------------------------------------------
def test_active_definition_consistency(frames):
    """stage ∈ {ACTIVE, EXPANDING} ⇔ ≥4 distinct trading days in trailing 30."""
    td = F.trading_days(frames.trades, D.AS_OF).reindex(frames.accounts["id"]).fillna(0)
    acc = frames.accounts.set_index("id")
    is_active_stage = acc["stage"].isin(D.ACTIVE_STAGES)
    assert ((td >= D.ACTIVE_MIN_DAYS) == is_active_stage).all()
    fa = F.first_active_at(frames.trades)
    ever = acc.index.isin(fa.index)
    at_risk = acc["stage"] == "AT_RISK"
    assert td[at_risk].between(1, 3).all() and ever[at_risk.to_numpy()].all()
    ft = acc["stage"] == "FIRST_TRADE"
    assert td[ft].between(1, 3).all() and not ever[ft.to_numpy()].any()
    dormant = acc["stage"] == "DORMANT"
    assert (td[dormant] == 0).all() and acc.loc[dormant, "first_trade_at"].notna().all()


def test_stage_matches_onboarding(frames):
    acc = frames.accounts.set_index("id")
    ob = frames.onboarding_events
    first = ob.groupby(["account_id", "step"])["ts"].min().unstack()
    first = first.reindex(acc.index)
    pd.testing.assert_series_equal(acc["signed_at"], first["contract_signed"], check_names=False)
    pd.testing.assert_series_equal(acc["funded_at"], first["funded"], check_names=False)
    pd.testing.assert_series_equal(acc["kyc_approved_at"], first["kyc_approved"], check_names=False)
    trade_first = frames.trades.groupby("account_id")["ts"].min().reindex(acc.index)
    pd.testing.assert_series_equal(acc["first_trade_at"], trade_first, check_names=False)
    pd.testing.assert_series_equal(acc["first_trade_at"], first["first_trade"], check_names=False)
    q = frames.trades[frames.trades["contracts"] >= D.QUALIFYING_CONTRACTS].groupby("account_id")["ts"].min()
    pd.testing.assert_series_equal(acc["first_qualifying_trade_at"], q.reindex(acc.index), check_names=False)
    fa = F.first_active_at(frames.trades).reindex(acc.index)
    act_ev = first["activated"]
    assert (fa.notna() == act_ev.notna()).all()
    assert ((act_ev - fa).dropna() == pd.Timedelta(minutes=1)).all()
    # stage ordering
    assert acc.loc[acc["stage"].isin(D.PRE_SIGN_STAGES), "signed_at"].isna().all()
    assert acc.loc[acc["stage"] == "SIGNED", "kyc_approved_at"].isna().all()
    assert acc.loc[acc["stage"] == "KYC_APPROVED", "funded_at"].isna().all()
    funded_stage = acc["stage"] == "FUNDED"
    assert acc.loc[funded_stage, "funded_at"].notna().all() and acc.loc[funded_stage, "first_trade_at"].isna().all()
    # ordered timestamps
    m = acc["first_trade_at"].notna()
    assert (acc.loc[m, "first_trade_at"] > acc.loc[m, "funded_at"]).all()
    assert (acc.loc[m, "funded_at"] > acc.loc[m, "signed_at"]).all()
    assert (acc["created_at"] <= acc["signed_at"].fillna(pd.Timestamp(D.AS_OF))).all()
    # EXPANDING only for accounts active >= 60 d
    exp = acc["stage"] == "EXPANDING"
    assert (acc.loc[exp, "active_since"] <= pd.Timestamp(D.AS_OF - timedelta(days=60))).all()
    assert acc.loc[acc["stage"].isin(D.ACTIVE_STAGES), "active_since"].notna().all()


def test_liquidity_partners(frames):
    lp = frames.accounts[frames.accounts["is_liquidity_partner"]]
    assert set(lp["stage"]) <= D.ACTIVE_STAGES
    assert set(lp["segment"]) <= {"PROP", "FUND"}
    desk = frames.reps[frames.reps["role"] == "PARTNERSHIPS"]
    assert len(desk) == 1 and desk.iloc[0]["name"] == D.PARTNERSHIPS_REP_NAME
    assert desk.iloc[0]["quota_funded_annual"] == 0
    assert (lp["rep_id"] == int(desk.iloc[0]["id"])).all()
    non_lp = frames.accounts[~frames.accounts["is_liquidity_partner"]]
    assert not (non_lp["rep_id"] == int(desk.iloc[0]["id"])).any()


# ---------------------------------------------------------------------------
# v1.1 X4: book & quota
# ---------------------------------------------------------------------------
def _ytd_attainment(frames) -> pd.DataFrame:
    """Same arithmetic as services.team: funded in 2026 (LP credit 0.25) ÷ quota
    prorated from max(Jan 1, start_date) to AS_OF."""
    acc, reps = frames.accounts, frames.reps
    start = pd.Timestamp("2026-01-01")
    as_of = pd.Timestamp(D.AS_OF)
    rows = []
    for r in reps[reps["role"].isin(D.QUOTA_ROLES)].itertuples():
        b = acc[acc["rep_id"] == r.id]
        fy = b[b["funded_at"].notna() & (b["funded_at"] >= start) & (b["funded_at"] < as_of)]
        credit = float(np.where(fy["is_liquidity_partner"], 0.25, 1.0).sum())
        q = r.quota_funded_annual * (as_of - max(start, pd.Timestamp(r.start_date))).days / 365
        pf = b[b["funded_at"].notna() & b["segment"].isin(["PROP", "FUND"])]
        rows.append({"rep_id": r.id, "role": r.role, "funded_ytd": credit, "funded_total": int(b["funded_at"].notna().sum()),
                     "quota_ytd": q, "attainment": credit / q, "pf_funded": len(pf), "book": len(b)})
    return pd.DataFrame(rows).set_index("rep_id")


def test_quota_fields(frames):
    reps = frames.reps.set_index("id")
    assert (reps.loc[reps["role"] == "AE", "quota_funded_annual"] == D.AE_QUOTA_FUNDED_ANNUAL).all()
    assert (reps.loc[reps["role"] == "STRATEGIC", "quota_funded_annual"] == D.STRATEGIC_QUOTA_FUNDED_ANNUAL).all()
    assert (reps.loc[reps["role"] == "STRATEGIC", "quota_adv"] > 0).all()


def test_ae_attainment_balanced(frames):
    att = _ytd_attainment(frames)
    ae = att[att["role"] == "AE"]
    assert ae["attainment"].between(0.70, 1.30).all(), ae["attainment"].round(3).to_dict()
    assert (ae["attainment"] < 1.0).any()
    assert ae["funded_ytd"].max() / ae["funded_ytd"].min() <= 1.5
    assert ae["funded_total"].max() / ae["funded_total"].min() <= 1.5
    assert ae["pf_funded"].between(2, 4).all()
    assert ae["book"].max() / ae["book"].min() <= 1.5


def test_activity_reps_follow_book(frames):
    ac = frames.activities.merge(frames.accounts[["id", "rep_id"]], left_on="account_id", right_on="id",
                                 suffixes=("", "_owner"))
    reps = frames.reps.set_index("id")["role"]
    owner_role = ac["rep_id"].map(reps)
    sales_touch = owner_role.isin(["AE", "STRATEGIC", "PARTNERSHIPS"]) & (ac["kind"] != "qbr")
    assert (ac.loc[sales_touch, "rep_id"] == ac.loc[sales_touch, "rep_id_owner"]).all()


# ---------------------------------------------------------------------------
# v1.1 X2: health state
# ---------------------------------------------------------------------------
def test_health_state_vocabulary(frames):
    h = F.health_state(frames, D.AS_OF).join(frames.accounts.set_index("id")[["stage", "first_trade_at"]])
    assert set(h["health_state"]) <= set(D.HEALTH_STATES)
    assert (h.loc[h["stage"] == "FUNDED", "health_state"] == "not_started").all()
    assert (h.loc[h["stage"].isin(D.ACTIVE_STAGES), "health_state"] == "active").all()
    assert (h.loc[h["stage"].isin(["TARGET", "QUALIFIED", "SIGNED", "KYC_APPROVED"]), "health_state"] == "pre_funding").all()
    dormant = h["health_state"] == "dormant"
    assert h.loc[dormant, "first_trade_at"].notna().all() and (h.loc[dormant, "trading_days_30"] == 0).all()
    ramp = h[h["health_state"] == "ramping"]
    assert ramp["days_since_first_trade"].le(D.RAMPING_MAX_DAYS).all() and ramp["trading_days_30"].between(2, 3).all()
    ns = h[h["health_state"] == "not_started"]
    assert ns["health_label"].str.match(r"^No trades yet · funded \d+ d$").all()
    ah = F.account_health(frames, D.AS_OF)
    pd.testing.assert_series_equal(ah["health_state"], h["health_state"])
    assert "state" in ah.columns  # legacy column kept for v1 callers


@pytest.mark.parametrize("kw,expected", [
    (dict(funded=False, ever_traded=False, trading_days_30=0), "pre_funding"),
    (dict(funded=True, ever_traded=False, trading_days_30=0), "not_started"),
    (dict(funded=True, ever_traded=True, trading_days_30=2, days_since_first_trade=10), "ramping"),
    (dict(funded=True, ever_traded=True, trading_days_30=1, days_since_first_trade=3), "at_risk"),
    (dict(funded=True, ever_traded=True, trading_days_30=3, days_since_first_trade=40), "at_risk"),
    (dict(funded=True, ever_traded=True, trading_days_30=4, days_since_first_trade=5), "active"),
    (dict(funded=True, ever_traded=True, trading_days_30=0, days_since_first_trade=60), "dormant"),
])
def test_classify_health(kw, expected):
    assert D.classify_health(**kw) == expected


def test_v11_definitions():
    assert D.WEEK_END == D.snap_week_end(D.LAST_TRADING_DAY) and D.WEEK_END.weekday() == 6
    assert D.week_bounds() == (D.WEEK_END - timedelta(days=6), D.WEEK_END)
    assert D.adv_window(D.WEEK_END, inclusive=True) == D.adv_window(D.AS_OF_DATE)  # same 20 weekdays
    assert D.BALANCE_WEIGHT_HEDGER == 1.5
    t = D.TARGETS_2026
    assert t["adv_notional_usd"] == 1_500_000 and t["speculator_share_adv_organic"] == (0.55, 0.75)
    assert t["hedger_adv_contracts"] == 3_000 and t["lp_share_adv"] == 0.50


# ---------------------------------------------------------------------------
# Causal structure
# ---------------------------------------------------------------------------
def test_latent_propensity_drives_funnel(frames):
    from sklearn.metrics import roc_auc_score

    acc = frames.accounts[~frames.accounts["is_liquidity_partner"]]
    signed = acc["signed_at"].notna()
    assert roc_auc_score(signed, acc["latent_propensity"]) > 0.7
    s = acc[signed]
    ever_active = s["id"].isin(F.first_active_at(frames.trades).index)
    assert roc_auc_score(ever_active, s["latent_propensity"]) > 0.65


def test_triggered_outreach_lift(report):
    lift = report["trigger_lift"]
    assert lift["triggered"]["n"] >= 60 and lift["untriggered"]["n"] >= 60
    assert 1.8 <= lift["lift_x"] <= 3.0  # ≈2–2.5×


def test_trigger_ids_tie_to_events(frames):
    ac = frames.activities
    trig = ac[ac["trigger_id"].notna()]
    assert len(trig) > 100
    assert (trig["sequence"] == "volatility").all()
    pat = re.compile(r"^(ERCOT|PJM|CAISO|MISO)-[A-Z0-9_]+-\d{8}$")
    assert trig["trigger_id"].map(lambda x: bool(pat.match(x))).all()
    assert set(trig["trigger_id"]) <= set(frames.volatility_events["trigger_id"])
    assert "ERCOT-HB_HOUSTON-20260702" in set(trig["trigger_id"])
    # the live demo event is untouched — that's the AE's job today
    assert not trig["trigger_id"].str.endswith("20261002").any()


def test_friction_points(frames):
    acc = frames.accounts.set_index("id")
    ob = frames.onboarding_events
    signed = acc[acc["signed_at"].notna()]
    loops = ob[ob["step"] == "kyc_info_requested"].groupby("account_id").size().reindex(signed.index).fillna(0)
    by_seg = loops.groupby(signed["segment"]).mean()
    assert by_seg[["UTILITY", "CI_LOAD"]].min() > by_seg.drop(["UTILITY", "CI_LOAD"]).max()
    first = ob.groupby(["account_id", "step"])["ts"].min().unstack()
    bf = ((first["funded"] - first["bank_linked"]).dt.total_seconds() / 86400).dropna()
    med = bf.groupby(acc.loc[bf.index, "segment"]).median()
    assert med["DATACENTER"] > 2.5 * med.drop("DATACENTER").max()
    fo = first["first_order"].dropna().index
    rej = acc.loc[fo, "segment"].to_frame().assign(r=lambda d: d.index.isin(ob.loc[ob["step"] == "order_rejected", "account_id"]))
    rate = rej.groupby("segment")["r"].mean()
    assert rate.idxmax() == "FUND" and rate["FUND"] > 0.3


def test_marketing_channel_profiles(frames):
    acc = frames.accounts
    spend = frames.marketing_spend.groupby("channel")["spend_usd"].sum()
    funded = acc[acc["funded_at"].notna()].groupby("lead_source").size()
    cac = spend / funded
    assert cac["Partner Referrals"] < cac["LinkedIn Paid"] / 2
    assert spend["Industry Conferences"] == spend.max()
    tr = frames.trades
    adv = tr[tr["ts"] >= pd.Timestamp(D.AS_OF - timedelta(days=30))].groupby("account_id")["contracts"].sum()
    active = acc[acc["stage"].isin(D.ACTIVE_STAGES) & ~acc["is_liquidity_partner"]].assign(adv=lambda d: d["id"].map(adv))
    per = active.groupby("lead_source")["adv"].mean()
    assert per["Industry Conferences"] > per["LinkedIn Paid"]


def test_seeded_demo_event(frames):
    p = frames.market_prices
    win = p[(p["ts"] >= pd.Timestamp("2026-10-02 15:00")) & (p["ts"] < pd.Timestamp("2026-10-03 00:00"))]
    hou = win[win["hub"] == "HB_HOUSTON"].sort_values("ts")
    nor = win[win["hub"] == "HB_NORTH"].sort_values("ts")
    assert hou["lmp"].max() == 4800.0
    assert hou.iloc[0]["ts"] == pd.Timestamp("2026-10-02 15:00") and hou.iloc[0]["lmp"] >= 2200
    for g in (hou, nor):
        run = (g["lmp"] >= 2200).astype(int)
        assert 6 <= run.sum() <= 9
        assert g["lmp"].max() <= 4800
    assert nor["lmp"].max() < hou["lmp"].max()
    last_week = p[(p["ts"] >= pd.Timestamp(D.AS_OF - timedelta(days=7))) & (p["iso"] == "CAISO")]
    neg = last_week[last_week["lmp"] < 0]
    assert len(neg) >= 12 and neg["lmp"].min() > -50  # mild
    f = frames.price_forecasts
    ercot = f[(f["iso"] == "ERCOT")]
    assert ercot["forecast_peak_lmp"].max() >= V.ISO_FLOOR["ERCOT"]
    assert (ercot["date"] < pd.Timestamp(D.AS_OF + timedelta(days=5))).all()


def test_ercot_exposed_accounts_not_yet_trading(frames):
    acc = frames.accounts
    pre = acc[(~acc["is_liquidity_partner"]) & acc["stage"].isin(D.PRE_TRADE_STAGES)
              & acc["exposure_isos"].str.contains("ERCOT")]
    assert len(pre) >= 14
    segs = set(pre["segment"])
    assert "REP" in segs and ({"STORAGE", "PROP"} & segs)
    funded_not_trading = pre[pre["stage"] == "FUNDED"]
    assert len(funded_not_trading) >= 5


def test_historical_events_table(frames):
    ev = frames.volatility_events
    assert ev["trigger_id"].is_unique
    assert set(ev["regime"]) <= set(D.REGIMES)
    assert {"scarcity", "negative_price", "winter_peak"} <= set(ev["regime"])
    for tid in ("ERCOT-HB_HOUSTON-20260702", "ERCOT-HB_HOUSTON-20261002", "ERCOT-HB_NORTH-20261002"):
        assert tid in set(ev["trigger_id"])
    assert (ev["end_ts"] >= ev["start_ts"]).all()
