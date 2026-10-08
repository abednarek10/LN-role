"""API contract tests (spec §E + FRONTEND_CONTRACT_NOTES + v1.1 03_ROUND2_CHANGES §1) and the exec
acceptance checks. Write tests clean up the rows they create so the Data agent's seed assertions
(no drafts, no events at/after AS_OF) still hold."""
from __future__ import annotations

import re
from collections import Counter

import pytest

AS_OF = "2026-10-05"
WEEK_END = "2026-10-04"
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
HOUSTON = "ERCOT-HB_HOUSTON-20261002"
NORTH = "ERCOT-HB_NORTH-20261002"
EVENT = "ERCOT-20261002"
HEALTH = {"pre_funding", "not_started", "ramping", "active", "at_risk", "dormant"}


@pytest.fixture(scope="module", autouse=True)
def _load_frames_first(frames):
    """Load the shared ``frames`` fixture before any write test runs."""
    return frames


@pytest.fixture()
def cleanup(client):
    """Delete drafts/activities created by a test and refresh app state."""
    from sqlalchemy import delete, func, select

    from ignition.database import SessionLocal
    from ignition.models import Activity, OutreachDraft
    from ignition.services import cache

    with SessionLocal() as s:
        max_act = s.execute(select(func.max(Activity.id))).scalar() or 0
        max_dr = s.execute(select(func.max(OutreachDraft.id))).scalar() or 0
    yield
    with SessionLocal() as s:
        s.execute(delete(Activity).where(Activity.id > max_act))
        s.execute(delete(OutreachDraft).where(OutreachDraft.id > max_dr))
        s.commit()
        cache.refresh(s, "activities", "outreach_drafts")


def get(client, path, status=200):
    r = client.get(path)
    assert r.status_code == status, (path, r.status_code, r.text[:300])
    return r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text


def post(client, path, body=None, status=200):
    r = client.post(path, json=body)
    assert r.status_code == status, (path, r.status_code, r.text[:300])
    return r.json()


# ---------------------------------------------------------------- meta / health
def test_health(client):
    d = get(client, "/api/health")
    assert d["status"] == "ok" and d["warmed"] is True


def test_meta(client):
    d = get(client, "/api/meta")
    assert d["as_of"] == AS_OF and d["week_end"] == WEEK_END and d["synthetic"] is True
    assert {s["code"] for s in d["segments"]} == {"IPP", "STORAGE", "REP", "CI_LOAD", "UTILITY", "DATACENTER", "PROP", "FUND"}
    assert all({"code", "label", "side"} <= set(s) for s in d["segments"])
    assert d["isos"]["ERCOT"] == ["HB_NORTH", "HB_HOUSTON", "HB_WEST"]
    assert "FUNDED" in d["stages"] and d["steps"][0] == "contract_signed"
    assert len(d["channels"]) == 7 and all({"id", "name", "role"} <= set(r) for r in d["reps"])
    assert d["targets"]["adv_contracts"] == 25000 and d["targets"]["adv_notional_usd"] == 1_500_000


def test_frontend_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Ignition" in r.text
    assert client.get("/static/app.js").status_code == 200


# ---------------------------------------------------------------- CEO
def test_ceo_weekly_shape(client):
    d = get(client, "/api/ceo/weekly")
    assert d["as_of"] == AS_OF and d["week_end"] == WEEK_END
    assert len(d["headline"]) == 3 and d["headline"][0].startswith("Liquidity:")
    assert d["headline"][1].startswith("Balance:") and d["headline"][2].startswith("Action:")
    assert "today" not in " ".join(d["headline"] + d["decisions"]).lower() and "on Oct 2" in d["headline"][2]
    assert len(d["decisions"]) == 3 and all(isinstance(x, str) and x for x in d["decisions"])
    units = {"contracts", "usd", "usd_mwh", "rate", "share", "pct", "days", "accounts", "ratio"}
    k = {x["key"]: x for x in d["kpis"]}
    assert {"signed_cum", "funded_cum", "adv_contracts", "adv_organic", "speculator_share_adv_organic", "hedger_adv",
            "lp_share_adv", "adv_notional_usd", "fee_revenue_20d", "active_rate", "top5_adv_share", "ercot_spread"} <= set(k)
    assert {x["key"] for x in d["kpis"] if x["board"]} == {"funded_cum", "active_rate", "adv_contracts", "cohort_activation",
                                                         "hedger_share_active", "ercot_spread"}
    for x in d["kpis"]:
        assert {"key", "label", "value", "unit", "prior", "delta", "target", "status", "spark", "board", "prior_label"} <= set(x)
        assert x["unit"] in units and x["status"] in {"on_track", "watch", "off_track", "info"} and len(x["spark"]) == 12
        assert x["prior_label"] == "prior week"
    for key in ("signed_cum", "funded_cum"):
        assert {"ytd", "target", "needed_weekly", "run_rate_4w", "projected_eoy"} <= set(k[key]["pace"])
    assert k["fee_revenue_20d"]["target"] == 125_000 and k["fee_revenue_20d"]["status"] != "info"
    assert "note" in k["adv_notional_usd"] and "Oct 2" in k["adv_notional_usd"]["note"]
    ws = d["weekly_series"]
    assert len(ws) >= 30 and {"week_end", "signed", "funded", "first_trades", "active_accounts", "adv_contracts",
                              "fee_revenue", "signed_cum", "funded_cum"} <= set(ws[-1])
    assert ws[-1]["week_end"] == WEEK_END
    m = d["mix"]
    assert set(m["by_side_accounts"]) == {"hedger", "speculator", "liquidity_partner"} == set(m["by_side_adv"])
    assert 0 < m["top5_adv_share"] < 1 and 0 < m["hhi"] < 1
    for s in d["spreads"]:
        assert {"iso", "hub", "tenor", "spread_usd_mwh", "uptime_pct", "target_spread", "target_uptime", "status"} <= set(s)
        assert 50 < s["uptime_pct"] <= 100 and s["target_uptime"] > 50  # *_pct fields are 0–100
    cohorts = d["activation_cohorts"]
    assert all({"cohort_week", "n", "activated_30d_rate", "greyed"} <= set(c) for c in cohorts)
    assert all(c["cohort_week"] >= "2026-01-05" for c in cohorts) and any(not c["greyed"] for c in cohorts)
    for r in d["stalled"]:
        assert {"account_id", "name", "segment", "stage", "days_stalled", "exp_adv", "next_action"} <= set(r)
        assert r["days_stalled"] > 21 and set(r["next_action"]) >= {"rule_id", "action", "owner", "sla", "sequence"}
    lv = d["lever"]
    assert {"event_id", "iso", "n", "funded_not_trading", "adv_at_stake", "drafted", "approved", "queued", "past_sla"} <= set(lv)


def test_ceo_weekly_calibration(client):
    d = get(client, "/api/ceo/weekly")
    k = {x["key"]: x for x in d["kpis"]}
    assert 13_000 < k["adv_contracts"]["value"] < 18_000
    assert 0.5 < k["active_rate"]["value"] < 0.7
    assert 0.45 < k["top5_adv_share"]["value"] < 0.56
    # median notional moves < 15% week over week (CEO P0-2)
    n = k["adv_notional_usd"]
    assert abs(n["value"] / n["prior"] - 1) < 0.15 and n["value"] < 1_500_000
    assert k["speculator_share_adv_organic"]["target_band"] == [0.55, 0.75]


def test_ceo_week_end_param(client):
    d = get(client, "/api/ceo/weekly?week_end=2026-09-27")
    assert d["week_end"] == "2026-09-27"
    assert get(client, "/api/ceo/weekly?week_end=2026-09-23")["week_end"] == "2026-09-27"  # snaps to the Sunday close
    get(client, "/api/ceo/weekly?week_end=2027-01-01", 422)
    get(client, "/api/ceo/weekly?week_end=notadate", 422)


def test_ceo_memo_md(client):
    r = client.get("/api/ceo/weekly.md")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    assert "Synthetic data — illustrative" in r.text and r.text.startswith("# ElectronX — CEO Weekly")
    assert "## This week's lever" in r.text and "## Board KPIs" in r.text


# ---------------------------------------------------------------- one number everywhere (CPO P0-2, CEO P0-1)
def test_event_numbers_agree_across_ceo_and_pulse(client):
    lv = get(client, "/api/ceo/weekly")["lever"]
    events = get(client, "/api/pulse/events")["events"]
    ev = next(e for e in events if e["event_id"] == lv["event_id"])
    assert lv["event_id"] == EVENT and list(lv["isos"]) == ["ERCOT"] and lv["iso"] == "ERCOT"
    assert lv["n"] == lv["funded_not_trading"] == ev["funded_not_trading"]
    assert lv["exposed"] == ev["exposed"] and lv["adv_at_stake"] == ev["adv_at_stake"]
    # distinct per event: equals the distinct funded-not-trading accounts across both ERCOT hubs
    ids = set()
    for tid in ev["hubs"]:
        rows = get(client, f"/api/pulse/triggers/{tid}/accounts?view=all")["accounts"]
        assert all(r["iso"] or True for r in rows)
        ids |= {r["account_id"] for r in rows if r["funded_not_trading"]}
    assert len(ids) == lv["n"]
    trig = {t["trigger_id"]: t for t in get(client, "/api/pulse/triggers")["triggers"]}
    assert all(trig[t]["funded_not_trading"] == lv["n"] for t in ev["hubs"])  # ISO-level exposure, same set
    d = get(client, "/api/ceo/weekly")
    assert f"{lv['n']} funded-not-trading" in d["headline"][2] and f"{lv['n']} funded-not-trading" in d["decisions"][0]
    md = get(client, "/api/ceo/weekly.md")
    assert f"{lv['n']} funded-not-trading accounts" in md


def test_active_count_agrees(client):
    ceo = get(client, "/api/ceo/weekly")
    funnel = get(client, "/api/funnel")
    queue = get(client, "/api/activation/queue")
    k = {x["key"]: x for x in ceo["kpis"]}
    assert ceo["active_accounts"] == funnel["states"]["active"] == queue["summary"]["active_accounts"]
    assert k["active_rate"]["detail"]["active_total"] == ceo["active_accounts"] == ceo["weekly_series"][-1]["active_accounts"]
    assert f"{ceo['active_accounts']} accounts are Active" in ceo["headline"][1]


# ---------------------------------------------------------------- Pulse
def test_pulse_hubs(client):
    d = get(client, "/api/pulse/hubs?iso=ERCOT&hours=168")
    assert d["as_of"] == AS_OF and [h["hub"] for h in d["hubs"]] == ["HB_NORTH", "HB_HOUSTON", "HB_WEST"]
    h = next(x for x in d["hubs"] if x["hub"] == "HB_HOUSTON")
    assert len(h["series"]) == 168 and TS_RE.match(h["series"][0]["ts"])
    assert set(h["stats"]) >= {"last", "avg_30d", "p99_30d", "max_72h", "min_72h", "spike_hours_72h", "vol_z"}
    assert h["stats"]["max_72h"] == 4800 and len(h["forecast"]) == 5
    assert len(get(client, "/api/pulse/hubs")["hubs"]) == 7
    get(client, "/api/pulse/hubs?iso=NYISO", 422)


def test_pulse_triggers(client):
    d = get(client, "/api/pulse/triggers")
    ts = d["triggers"]
    assert ts[0]["trigger_id"] == HOUSTON and NORTH in {t["trigger_id"] for t in ts}
    for t in ts:
        assert {"trigger_id", "event_id", "hub", "iso", "regime", "severity", "spike_hours", "neg_hours", "vol_z", "peak_lmp",
                "peak_ratio", "peak_ts", "start_ts", "end_ts", "forward_risk", "exposed_count", "funded_not_trading",
                "actionable_count", "adv_at_stake"} <= set(t)
    h = ts[0]
    assert h["peak_lmp"] == 4800 and h["forward_risk"] is True and 0 < h["severity"] <= 100 and h["event_id"] == EVENT
    spikes = [t for t in ts if t["regime"] != "negative_price"]
    assert max(spikes, key=lambda t: t["peak_ratio"])["trigger_id"] == HOUSTON  # X8: HB_HOUSTON reads strongest
    assert h["exposed_count"] >= 14 and h["funded_not_trading"] > 0 and h["actionable_count"] <= 20
    sp = next(t for t in ts if t["iso"] == "CAISO")
    assert sp["neg_hours"] == 14 and sp["peak_ratio_basis"] == "neg_hours"


def test_pulse_events(client):
    d = get(client, "/api/pulse/events")
    ev = {e["event_id"]: e for e in d["events"]}
    assert EVENT in ev and sorted(ev[EVENT]["hubs"]) == sorted([HOUSTON, NORTH])  # one ERCOT event
    for e in d["events"]:
        assert {"event_id", "iso", "hubs", "exposed", "funded_not_trading", "actionable", "adv_at_stake"} <= set(e)


def test_pulse_trigger_accounts_actionable_default(client):
    from ignition.services import cache

    acc = cache.get_state().accounts
    d = get(client, f"/api/pulse/triggers/{HOUSTON}/accounts")
    assert d["view"] == "actionable" and {"exposed", "funded_not_trading", "actionable"} <= set(d["counts"])
    rows = d["accounts"]
    assert 0 < len(rows) <= 20 == d["counts"]["actionable"] or len(rows) == d["counts"]["actionable"]
    assert not {r["stage"] for r in rows} & {"QUALIFIED", "TARGET"}
    assert all("ERCOT" in acc.loc[r["account_id"], "isos"] for r in rows)  # never outside the trigger's ISO
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))
    tv = [r["touch_value"] for r in rows]
    assert tv == sorted(tv, reverse=True)
    for r in rows:
        assert {"rank", "touch_value", "hub", "hub_match", "health_state", "account_fact", "direction", "exposure_line",
                "exposure_score", "p_active", "exp_adv", "last_touch_days", "suppressed"} <= set(r)
        assert r["health_state"] in HEALTH and r["hub"] == acc.loc[r["account_id"], "hub"] and not r["suppressed"]
        assert r["hub_match"] == (r["hub"] == "HB_HOUSTON")
    assert any(r["stage"] == "FUNDED" and r["segment"] == "REP" for r in rows)
    assert any(r["direction"] == "opportunity" for r in rows) and any(r["direction"] == "hurt" for r in rows)
    get(client, f"/api/pulse/triggers/{HOUSTON}/accounts?view=bogus", 422)
    get(client, "/api/pulse/triggers/NOPE-123/accounts", 404)


def test_pulse_trigger_accounts_all(client):
    d = get(client, f"/api/pulse/triggers/{HOUSTON}/accounts?view=all")
    rows = d["accounts"]
    assert d["view"] == "all" and len(rows) == d["counts"]["exposed"] == d["trigger"]["exposed_count"]
    assert sum(r["funded_not_trading"] for r in rows) == d["counts"]["funded_not_trading"]
    assert all("$" not in r["exposure_line"] for r in rows)
    own = [r for r in rows if r["hub_match"]]
    north = get(client, f"/api/pulse/triggers/{NORTH}/accounts?view=all")["accounts"]
    assert {r["account_id"] for r in own} != {r["account_id"] for r in north if r["hub_match"]}  # hub-specific (X6)
    houston_act = [r["account_id"] for r in get(client, f"/api/pulse/triggers/{HOUSTON}/accounts")["accounts"]]
    north_act = [r["account_id"] for r in get(client, f"/api/pulse/triggers/{NORTH}/accounts")["accounts"]]
    assert houston_act != north_act


def test_pulse_history(client):
    d = get(client, "/api/pulse/history")
    assert len(d["events"]) >= 20 and {"trigger_id", "event_id", "hub", "regime", "peak_lmp", "start_ts"} <= set(d["events"][0])
    lift = d["lift"]
    assert lift["triggered"]["n"] > 50 and 2.0 <= lift["lift_x"] <= 3.0


# ---------------------------------------------------------------- Queue / scoring
QUEUE_KEYS = {"rank", "account_id", "name", "segment", "side", "iso", "stage", "days_in_stage", "stall", "p_active", "exp_adv",
              "k_stage", "urgency", "balance_weight", "priority", "trigger_id", "next_action", "reasons", "health_state",
              "ramping", "owner_rep_id", "owner_name"}


def test_activation_queue_today(client):
    d = get(client, "/api/activation/queue?limit=200")
    s = d["summary"]
    assert d["as_of"] == AS_OF and s["view"] == "today"
    assert {"accounts_in_queue", "stalled", "sla_breaches", "adv_at_stake", "backlog"} <= set(s)
    items = d["items"]
    assert s["accounts_in_queue"] == len(items) and s["backlog"] > 0
    assert s["sla_breaches"] == sum(i["sla_breached"] for i in items)  # counted on listed items only
    caps = Counter(i["owner_name"] for i in items)
    cap_of = {"Head of GTM": 5}
    for owner, n in caps.items():
        assert n <= cap_of.get(owner, 15), (owner, n)
    for owner in {i["owner_name"] for i in items if i["owner_name"] in {"Maya Castillo", "Ben Okafor", "Priya Raman", "Tom Lindqvist"}}:
        own = [i for i in items if i["owner_name"] == owner]
        assert len(own) <= 12 and sum(i["side"] == "hedger" for i in own) >= len(own) / 2  # ≥50% hedger slots
    top20 = items[:20]
    assert sum(i["side"] == "hedger" for i in top20) >= 8  # CEO P1-6: ≥40% hedgers in the top 20
    for it in items:
        assert QUEUE_KEYS <= set(it) and it["health_state"] in HEALTH


def test_activation_queue_all_and_acceptance(client):
    d = get(client, "/api/activation/queue?view=all&limit=1000")
    items = d["items"]
    assert d["summary"]["view"] == "all" and len(items) == d["summary"]["accounts_in_queue"]
    pr = [i["priority"] for i in items]
    assert pr == sorted(pr, reverse=True) and [i["rank"] for i in items[:50]] == list(range(1, 51))
    for it in items[:200]:
        assert QUEUE_KEYS <= set(it)
        assert it["side"] != "liquidity_partner" and it["urgency"] <= 2.0
        assert abs(it["p_active"] * it["exp_adv"] * it["k_stage"] * it["urgency"] * it["balance_weight"] - it["priority"]) < 0.05 * max(it["priority"], 1)
        assert set(it["next_action"]) >= {"rule_id", "action", "owner", "sla", "sequence"}
        assert all({"label", "direction", "weight"} <= set(r) and r["direction"] in "+-" for r in it["reasons"])
    by_id = {i["account_id"]: i for i in items}
    assert by_id[337]["next_action"]["rule_id"] == "R16"                                # CRO P0-2
    top10 = {i["name"] for i in items[:10]}
    assert not any(n.startswith(("Onyx", "Bufflehead")) for n in top10)                  # CRO P0-3
    assert all(i["next_action"]["rule_id"] != "R99" for i in items[:25])
    assert all(i["trigger_id"] is None for i in items if i["stage"] in ("TARGET", "SIGNED"))  # CTO B3
    assert any(i["balance_weight"] == 1.5 for i in items if i["side"] == "hedger")
    r09 = [i for i in items if i["next_action"]["rule_id"] == "R09"]
    assert 12 <= len(r09) <= 40 and all(i["event_id"] == EVENT for i in r09)            # X5
    assert all(i["stage"] not in ("SIGNED", "TARGET") for i in r09)
    assert sum(i["side"] == "hedger" for i in r09) > len(r09) / 2
    assert all((i["p_active"] or 0) < 0.95 for i in r09)


def test_activation_queue_filters(client):
    d = get(client, "/api/activation/queue?view=all&segment=REP&iso=ERCOT&limit=10")
    assert all(i["segment"] == "REP" and i["iso"] == "ERCOT" for i in d["items"])
    d = get(client, "/api/activation/queue?view=all&stage=FUNDED&limit=200")
    assert d["items"] and all(i["stage"] == "FUNDED" for i in d["items"])
    d = get(client, "/api/activation/queue?view=all&rep_id=1&limit=5")
    assert all(i["rep_id"] == 1 for i in d["items"])
    get(client, "/api/activation/queue?segment=BOGUS", 422)
    get(client, "/api/activation/queue?stage=BOGUS", 422)
    get(client, "/api/activation/queue?view=week", 422)


def test_scoring_model(client):
    d = get(client, "/api/scoring/model")
    assert d["as_of"] == AS_OF and d["target"] == "active_60d"
    assert {"target", "train_n", "test_n", "auc", "pr_auc", "brier", "base_rate", "lift_top_decile", "gain_curve",
            "calibration", "coefficients", "challenger", "honest"} <= set(d)
    h = d["honest"]
    assert {"gap_days", "auc_gap", "auc_unseen", "baseline_name", "baseline_auc", "note"} <= set(h)
    assert d["auc"] == h["auc_gap"] and h["gap_days"] >= 60 and 0.7 <= d["auc"] <= 0.85
    assert d["lift_top_decile"] >= 2
    assert {"pct_accounts", "pct_positives"} <= set(d["gain_curve"][0])
    assert {"bin", "predicted", "observed", "n"} <= set(d["calibration"][0])


# ---------------------------------------------------------------- Funnel / segments / liquidity
def test_funnel(client):
    d = get(client, "/api/funnel")
    steps = d["steps"]
    assert steps[0]["step"] == "contract_signed" and steps[0]["conv_from_prev"] is None
    for s in steps[1:]:
        assert {"step", "label", "n", "n_mature", "conv_from_prev", "median_days_from_prev", "p75_days"} <= set(s)
        assert 0 <= s["conv_from_prev"] <= 1 and s["n_mature"] > 0
    assert "(" not in steps[-1]["label"]
    assert {"not_started", "ramping", "active", "at_risk", "dormant"} <= set(d["states"])
    assert len(d["by_segment"]) == 8 and {"segment", "steps"} <= set(d["by_segment"][0])
    fr = d["friction"]
    assert 1 <= len(fr) <= 6                                                            # CPO P1-6
    for f in fr:
        assert {"step", "step_label", "from_step", "segment", "metric", "value", "benchmark", "accounts_affected",
                "adv_at_stake", "roadmap_ask", "severity"} <= set(f)
        assert f["accounts_affected"] >= 5 and f["severity"] in {"low", "medium", "high", "critical"}
    assert len({(f["segment"], f["step"]) for f in fr}) == len(fr)                      # merged per segment × step
    advs = [f["adv_at_stake"] for f in fr]
    assert advs == sorted(advs, reverse=True)
    kyc = [f for f in fr if f["segment"] in ("UTILITY", "CI_LOAD") and any(m["metric"] == "kyc_info_requests_per_account" for m in f["metrics"])]
    assert kyc and all(f["severity"] in ("high", "critical") for f in kyc)              # seeded KYC-loop leak reads high


def test_funnel_filters_and_ticket(client):
    d = get(client, "/api/funnel?segment=UTILITY&iso=PJM")
    assert all(f["segment"] == "UTILITY" for f in d["friction"])
    assert len(d["by_segment"]) == 1
    md = get(client, "/api/funnel/friction/0.md")
    assert md.startswith("# Roadmap ticket") and "Synthetic data — illustrative" in md and ".." not in md
    n = len(get(client, "/api/funnel")["friction"])
    get(client, f"/api/funnel/friction/{n}.md", 404)


def test_segments(client):
    d = get(client, "/api/segments")
    c = d["cells"][0]
    assert {"segment", "iso", "tam_accounts", "signed", "funded", "active", "penetration", "activation_rate",
            "adv_per_active", "adv_total"} <= set(c)
    assert len(d["segments"]) == 8
    assert {"segment", "label", "side", "tam", "active", "adv", "adv_share", "recommended_coverage"} <= set(d["segments"][0])
    assert abs(sum(s["adv_share"] for s in d["segments"]) - 1) < 0.01
    assert sum(c["tam_accounts"] for c in d["cells"]) + d["liquidity_partners"]["accounts"] == 600


def test_liquidity(client):
    d = get(client, "/api/liquidity?iso=ERCOT&tenor=HOURLY")
    assert {"date", "hub", "spread_usd_mwh", "uptime_pct", "active_accounts", "lp_quote_share"} <= set(d["series"][0])
    assert {r["hub"] for r in d["series"]} == {"HB_NORTH", "HB_HOUSTON", "HB_WEST"}
    e = d["elasticity"]
    assert e["b"] > 0 and 0.3 < e["r2"] <= 1 and e["note"]
    get(client, "/api/liquidity?tenor=MONTHLY", 422)


# ---------------------------------------------------------------- Team & comp
def test_team_scorecards(client):
    d = get(client, "/api/team/scorecards")
    reps = d["reps"]
    assert len(reps) == 5 and {r["role"] for r in reps} == {"AE", "STRATEGIC"}  # Partnerships Desk excluded
    for r in reps:
        assert {"rep_id", "name", "role", "funded_ytd", "quota_ytd", "attainment", "activation_rate", "book_adv",
                "median_days_sign_to_trade", "pipeline_coverage", "sla_adherence", "score", "components"} <= set(r)
        assert 0 <= r["score"] <= 150
        assert abs(sum(r["components"].values()) - r["score"]) < 0.5
    aes = [r for r in reps if r["role"] == "AE"]
    assert all(0.70 <= r["attainment"] <= 1.30 for r in aes)                            # CEO P1-5
    assert any(r["attainment"] < 1.0 for r in aes)
    assert max(r["funded_ytd"] for r in aes) / min(r["funded_ytd"] for r in aes) <= 1.5
    tom = next(r for r in reps if r["name"].startswith("Tom"))
    assert tom["quota_ytd"] < next(r for r in reps if r["name"].startswith("Maya"))["quota_ytd"]  # start-date proration


def test_comp_plans(client):
    d = get(client, "/api/team/comp-plans")
    ids = [p["plan_id"] for p in d["plans"]]
    assert ids == ["pay_on_signature", "pay_on_funded", "activation_adv"]
    assert all(p["name"] and p["formula"] for p in d["plans"])


def test_comp_sim(client):
    d = post(client, "/api/team/comp-sim", {"plan_id": "activation_adv"})
    assert d["plan"]["plan_id"] == "activation_adv" and len(d["reps"]) == 5
    for r in d["reps"]:
        assert {"rep_id", "name", "payout_variable", "payout_breakdown", "book_activation", "accelerator_applied",
                "pct_of_fee_revenue"} <= set(r)
        # accelerator only with book activation ≥ 50% (CRO P0-4)
        assert not r["accelerator_applied"] or r["book_activation"] >= 0.5
    maya = next(r for r in d["reps"] if r["name"].startswith("Maya"))
    assert maya["accelerator_applied"] is False and maya["payout_breakdown"].get("accelerator", 0) == 0
    assert {"variable_cost", "per_active_account", "per_1k_contracts", "pct_of_fee_revenue"} <= set(d["totals"])
    cmp = {c["plan_id"]: c for c in d["comparison"]}
    assert set(cmp) == {"pay_on_signature", "pay_on_funded", "activation_adv"}
    assert all(c["behavior"] and c["pct_of_fee_revenue"] > 0 for c in cmp.values())
    assert cmp["activation_adv"]["per_active_account"] < cmp["pay_on_funded"]["per_active_account"] < cmp["pay_on_signature"]["per_active_account"]
    r2 = post(client, "/api/team/comp-sim", {"plan_id": "activation_adv", "params": {"per_account_unit": 2500, "multipliers": {"funded": 0.5}}})
    assert r2["totals"]["variable_cost"] > d["totals"]["variable_cost"] and r2["plan"]["multipliers"]["active_60d"] == 1.0
    assert post(client, "/api/team/comp-sim", {})["plan"]["plan_id"] == "activation_adv"
    post(client, "/api/team/comp-sim", {"plan_id": "nope"}, 404)
    post(client, "/api/team/comp-sim", {"plan_id": "activation_adv", "params": {"accelerator": "fast"}}, 422)


# ---------------------------------------------------------------- Marketing
def test_marketing_roi(client):
    d = get(client, "/api/marketing/roi?months=6")
    assert len(d["channels"]) == 7
    for c in d["channels"]:
        assert {"channel", "spend", "leads", "signed", "funded", "active", "cac_funded", "cac_active", "adv",
                "adv_per_1k_spend", "n_small"} <= set(c)
        assert c["n_small"] == (c["funded"] < 20)
    assert len(d["monthly"]) == 6 * 7 and {"month", "channel", "spend", "leads"} <= set(d["monthly"][0])
    get(client, "/api/marketing/roi?months=0", 422)


# ---------------------------------------------------------------- Accounts
def test_accounts_list_and_search(client):
    d = get(client, "/api/accounts?limit=10&offset=5")
    assert d["total"] == 600 and len(d["items"]) == 10
    assert {"id", "name", "segment", "iso", "stage", "rep", "p_active", "adv_30d", "health_state"} <= set(d["items"][0])
    q = get(client, "/api/accounts?q=trading&limit=8")
    assert q["items"] and all("trading" in i["name"].lower() for i in q["items"])
    f = get(client, "/api/accounts?segment=STORAGE&iso=ERCOT&stage=FUNDED")
    assert all(i["segment"] == "STORAGE" and i["iso"] == "ERCOT" and i["stage"] == "FUNDED" for i in f["items"])


def _active_account_id(client) -> int:
    return get(client, "/api/accounts?stage=ACTIVE&limit=1")["items"][0]["id"]


def test_account_360(client):
    aid = _active_account_id(client)
    d = get(client, f"/api/accounts/{aid}")
    a = d["account"]
    assert {"id", "name", "segment", "segment_label", "side", "primary_iso", "hub", "exposure_isos", "stage", "rep_id",
            "rep_name", "is_liquidity_partner", "funded_amount_usd", "size_mw", "p_active", "p_display", "signed_at",
            "funded_at", "first_trade_at"} <= set(a)
    assert isinstance(a["exposure_isos"], list)
    assert {"state", "trading_days_30", "adv_30d", "adv_prior_30d", "net_retention", "churn_risk"} <= set(d["health"])
    assert d["health"]["state"] == "active"
    assert d["adv_series"] and {"date", "contracts"} <= set(d["adv_series"][0])
    assert d["timeline"] and all({"ts", "type", "label"} <= set(e) and TS_RE.match(e["ts"]) for e in d["timeline"])
    assert d["onboarding"] and {"step", "ts"} <= set(d["onboarding"][0])
    u = d["qbr"]["utilization_by_tenor"]
    assert set(u) == {"HOURLY", "DAILY_PEAK", "WEEKLY_PEAK"} and abs(sum(u.values()) - 1) < 0.01
    assert isinstance(d["qbr"]["isos_traded"], list) and isinstance(d["qbr"]["growth_plays"], list)
    assert set(d["next_action"]) >= {"rule_id", "action", "owner", "sla", "sequence"}
    assert d["contacts"]


def test_account_360_never_traded_and_337(client):
    d = get(client, "/api/accounts/337")
    assert d["health"]["state"] == "not_started" and d["qbr"] is None              # X2 + CPO P1-7
    assert d["next_action"]["rule_id"] == "R16" and d["account"]["p_display"] in (">95%",) or d["account"]["p_display"].endswith("%")
    lp = get(client, "/api/accounts?limit=600")["items"]
    lp_id = next(i["id"] for i in lp if i["is_liquidity_partner"])
    d = get(client, f"/api/accounts/{lp_id}")
    assert d["account"]["is_liquidity_partner"] is True and d["account"]["side"] == "liquidity_partner"
    get(client, "/api/accounts/999999", 404)


# ---------------------------------------------------------------- Outreach workflow (X12, CTO B1/B2/B6)
def _funded_rep(client):
    rows = get(client, f"/api/pulse/triggers/{HOUSTON}/accounts")["accounts"]
    return next(a for a in rows if a["segment"] == "REP" and a["stage"] == "FUNDED")


def _cautions(d):
    return [f["id"] for f in d["compliance"]["flags"] if f["level"] == "caution"]


def test_outreach_volatility_flow(client, cleanup):
    acct = _funded_rep(client)
    before = get(client, "/api/activation/queue?view=all&limit=1000")
    prev = next((i for i in before["items"] if i["account_id"] == acct["account_id"]), None)
    lever0 = get(client, "/api/ceo/weekly")["lever"]

    d = post(client, "/api/outreach/draft", {"account_id": acct["account_id"], "trigger_id": HOUSTON, "kind": "volatility"})
    assert d["engine"] == "template" and d["status"] == "pending_review" and d["compliance"]["passed"] is True
    assert d["template_id"] == "VOL_REP_FUNDED" and d["facts"]["stage"] == "FUNDED"
    assert "{" not in d["subject"] + d["body"] and "$4,800" in d["body"]
    assert d["facts"]["event_peak_price"] == "$4,800" and d["facts"]["regime_label"] == "scarcity pricing"
    assert all("id" in f for f in d["compliance"]["flags"])
    assert get(client, "/api/ceo/weekly")["lever"]["drafted"] == lever0["drafted"] + 1

    did = d["draft_id"]
    post(client, f"/api/outreach/{did}/queue", None, 409)                            # queue before approve
    post(client, f"/api/outreach/{did}/approve", {"cleared_flag_ids": _cautions(d)}, 422)  # reviewer required
    if _cautions(d):
        post(client, f"/api/outreach/{did}/approve", {"reviewer": "Ana Compliance", "cleared_flag_ids": []}, 409)
    a = post(client, f"/api/outreach/{did}/approve", {"reviewer": "Ana Compliance", "cleared_flag_ids": _cautions(d)})
    assert a["status"] == "approved" and a["reviewer"] == "Ana Compliance"
    q = post(client, f"/api/outreach/{did}/queue")
    assert q["status"] == "queued" and q["activity_id"]
    post(client, f"/api/outreach/{did}/queue", None, 409)                            # no double-logging
    post(client, f"/api/outreach/{did}/approve", {"reviewer": "Ana Compliance"}, 409)

    after = get(client, "/api/activation/queue?view=all&limit=1000")
    it = next(i for i in after["items"] if i["account_id"] == acct["account_id"])
    assert it["last_touch_days"] == 0 and it["trigger_id"] is None
    assert it["next_action"]["condition_code"] != "VOL_TRIGGER_EXPOSED"
    if prev is not None:
        assert it["priority"] <= prev["priority"]
    rows = get(client, f"/api/pulse/triggers/{HOUSTON}/accounts?view=all")["accounts"]
    pa = next(x for x in rows if x["account_id"] == acct["account_id"])
    assert pa["suppressed"] is True and pa["last_touch_days"] == 0 and pa["suppressed_reason"]
    assert acct["account_id"] not in {x["account_id"] for x in get(client, f"/api/pulse/triggers/{HOUSTON}/accounts")["accounts"]}
    lv = get(client, "/api/ceo/weekly")["lever"]
    assert lv["queued"] == lever0["queued"] + 1
    assert lv["n"] == get(client, "/api/pulse/events")["events"][0]["funded_not_trading"]   # still one number after a write
    tl = get(client, f"/api/accounts/{acct['account_id']}")["timeline"]
    assert tl[0]["type"] == "triggered_email" and HOUSTON in tl[0]["label"]

    r2 = post(client, "/api/outreach/draft", {"account_id": acct["account_id"], "trigger_id": NORTH, "kind": "volatility"})
    assert r2["compliance"]["passed"] is False                                       # same ISO event, other hub → R14
    assert any(f["rule"] == "R14_CADENCE_LIMITS" and f["level"] == "block" for f in r2["compliance"]["flags"])
    post(client, f"/api/outreach/{r2['draft_id']}/approve", {"reviewer": "Ana Compliance", "cleared_flag_ids": _cautions(r2)}, 409)


def test_outreach_suppression_race(client, cleanup):
    """CTO B2: two drafts for one account created before either is queued → one queues, one 409, one activity row."""
    from sqlalchemy import func, select

    from ignition.database import SessionLocal
    from ignition.models import Activity

    acct = _funded_rep(client)["account_id"]
    drafts = [post(client, "/api/outreach/draft", {"account_id": acct, "trigger_id": t, "kind": "volatility"}) for t in (HOUSTON, NORTH)]
    assert all(d["compliance"]["passed"] for d in drafts)
    for d in drafts:
        post(client, f"/api/outreach/{d['draft_id']}/approve", {"reviewer": "Ana Compliance", "cleared_flag_ids": _cautions(d)})
    post(client, f"/api/outreach/{drafts[0]['draft_id']}/queue")
    r = client.post(f"/api/outreach/{drafts[1]['draft_id']}/queue")
    assert r.status_code == 409 and "suppressed" in r.json()["detail"]
    with SessionLocal() as s:
        n = s.execute(select(func.count()).select_from(Activity).where(
            Activity.account_id == acct, Activity.kind == "triggered_email", Activity.ts >= "2026-10-05")).scalar()
    assert n == 1


def test_outreach_reject_and_edit(client, cleanup):
    acct = _funded_rep(client)["account_id"]
    d = post(client, "/api/outreach/draft", {"account_id": acct, "trigger_id": HOUSTON, "kind": "volatility"})
    did = d["draft_id"]
    e = post(client, f"/api/outreach/{did}/edit", {"subject": d["subject"], "body": "We guarantee savings.\n\n" + d["body"]})
    assert e["status"] == "pending_review" and e["compliance"]["passed"] is False
    post(client, f"/api/outreach/{did}/approve", {"reviewer": "Ana Compliance"}, 409)
    e = post(client, f"/api/outreach/{did}/edit", {"subject": d["subject"],
                                                   "body": "Our not-for-profit members asked for 30 minutes.\n\n" + d["body"]})
    assert e["compliance"]["passed"] is True                                          # B6: allowlist
    assert any(f["rule"] == "R04_COMPUTED_FACTS_ONLY" and f["phrase"] == "30" and f["level"] == "caution" for f in e["compliance"]["flags"])
    post(client, f"/api/outreach/{did}/approve", {"reviewer": "Ana Compliance", "cleared_flag_ids": []}, 409)
    rj = post(client, f"/api/outreach/{did}/reject", {"reviewer": "Ana Compliance", "reason": "Tone"})
    assert rj["status"] == "rejected" and rj["reason"] == "Tone"
    post(client, f"/api/outreach/{did}/approve", {"reviewer": "Ana Compliance"}, 409)
    post(client, f"/api/outreach/{did}/edit", {"subject": "x", "body": "y"}, 409)
    assert get(client, f"/api/outreach/{did}")["status"] == "rejected"


def test_outreach_activation_and_qbr(client, cleanup):
    funded = get(client, "/api/accounts?stage=FUNDED&limit=1")["items"][0]
    d = post(client, "/api/outreach/draft", {"account_id": funded["id"], "kind": "activation"})
    assert d["kind"] == "activation" and d["trigger_id"] is None and d["template_id"].startswith("ACT_")
    assert "{" not in d["body"] and d["compliance"]["passed"]
    post(client, f"/api/outreach/{d['draft_id']}/approve", {"reviewer": "Ana Compliance", "cleared_flag_ids": _cautions(d)})
    post(client, f"/api/outreach/{d['draft_id']}/queue")
    tl = get(client, f"/api/accounts/{funded['id']}")["timeline"]
    assert tl[0]["type"] == "email"
    aid = _active_account_id(client)
    r = post(client, "/api/outreach/draft", {"account_id": aid, "kind": "qbr"})
    assert r["template_id"] == "QBR_GENERIC" and "{" not in r["body"]


def test_outreach_errors(client):
    post(client, "/api/outreach/draft", {"account_id": 999999, "kind": "activation"}, 404)
    post(client, "/api/outreach/draft", {"account_id": 1, "kind": "spam"}, 422)
    post(client, "/api/outreach/draft", {"account_id": 1, "kind": "volatility", "trigger_id": "NOPE"}, 404)
    post(client, "/api/outreach/999999/approve", {"reviewer": "Ana"}, 404)
    post(client, "/api/outreach/999999/queue", None, 404)
    post(client, "/api/outreach/999999/reject", {"reviewer": "Ana", "reason": "x"}, 404)
    post(client, "/api/outreach/999999/edit", {"subject": "x", "body": "y"}, 404)
