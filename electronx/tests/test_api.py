"""API contract tests (spec §E + FRONTEND_CONTRACT_NOTES). Every endpoint → 200 + shape,
plus 404 / 409 / 422 paths. Write tests clean up the rows they create so the
Data agent's seed assertions (no drafts, no events at/after AS_OF) still hold."""
from __future__ import annotations

import re

import pytest

AS_OF = "2026-10-05"
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
HOUSTON = "ERCOT-HB_HOUSTON-20261002"


@pytest.fixture(scope="module", autouse=True)
def _load_frames_first(frames):
    """Load the shared ``frames`` fixture before any write test runs."""
    return frames


@pytest.fixture()
def cleanup(client):
    """Delete drafts/activities created by a test and refresh app state."""
    from sqlalchemy import delete, select, func

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


# ---------------------------------------------------------------- meta / health
def test_health(client):
    d = get(client, "/api/health")
    assert d["status"] == "ok" and d["warmed"] is True


def test_meta(client):
    d = get(client, "/api/meta")
    assert d["as_of"] == AS_OF and d["week_end"] == "2026-10-02" and d["synthetic"] is True
    assert {s["code"] for s in d["segments"]} == {"IPP", "STORAGE", "REP", "CI_LOAD", "UTILITY", "DATACENTER", "PROP", "FUND"}
    assert all({"code", "label", "side"} <= set(s) for s in d["segments"])
    assert d["isos"]["ERCOT"] == ["HB_NORTH", "HB_HOUSTON", "HB_WEST"]
    assert "FUNDED" in d["stages"] and d["steps"][0] == "contract_signed"
    assert len(d["channels"]) == 7 and all({"id", "name", "role"} <= set(r) for r in d["reps"])
    assert d["targets"]["adv_contracts"] == 25000


def test_frontend_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Ignition" in r.text
    assert client.get("/static/app.js").status_code == 200


# ---------------------------------------------------------------- CEO
def test_ceo_weekly_shape(client):
    d = get(client, "/api/ceo/weekly")
    assert d["as_of"] == AS_OF and d["week_end"] == "2026-10-02"
    assert len(d["headline"]) == 3 and d["headline"][0].startswith("Liquidity:")
    assert d["headline"][1].startswith("Balance:") and d["headline"][2].startswith("Action:")
    assert len(d["decisions"]) == 3 and all(isinstance(x, str) and x for x in d["decisions"])
    units = {"contracts", "usd", "usd_mwh", "rate", "share", "pct", "days", "accounts", "ratio"}
    keys = {k["key"] for k in d["kpis"]}
    assert {"adv_contracts", "active_rate", "top5_adv_share", "ercot_north_spread", "fee_revenue_20d"} <= keys
    for k in d["kpis"]:
        assert {"key", "label", "value", "unit", "prior", "delta", "target", "status", "spark"} <= set(k)
        assert k["unit"] in units and k["status"] in {"on_track", "watch", "off_track"} and len(k["spark"]) == 12
    ws = d["weekly_series"]
    assert len(ws) >= 30 and {"week_end", "signed", "funded", "first_trades", "active_accounts", "adv_contracts", "fee_revenue"} <= set(ws[-1])
    m = d["mix"]
    assert set(m["by_side_accounts"]) == {"hedger", "speculator", "liquidity_partner"} == set(m["by_side_adv"])
    assert 0 < m["top5_adv_share"] < 1 and 0 < m["hhi"] < 1
    for s in d["spreads"]:
        assert {"iso", "hub", "tenor", "spread_usd_mwh", "uptime_pct", "target_spread", "target_uptime", "status"} <= set(s)
        assert 50 < s["uptime_pct"] <= 100 and s["target_uptime"] > 50  # *_pct fields are 0–100
    assert all({"cohort_week", "n", "activated_30d_rate", "greyed"} <= set(c) for c in d["activation_cohorts"])
    assert any(not c["greyed"] for c in d["activation_cohorts"])
    for r in d["stalled"]:
        assert {"account_id", "name", "segment", "stage", "days_stalled", "exp_adv", "next_action"} <= set(r)
        assert r["days_stalled"] > 21 and set(r["next_action"]) >= {"rule_id", "action", "owner", "sla", "sequence"}


def test_ceo_weekly_calibration(client):
    d = get(client, "/api/ceo/weekly")
    k = {x["key"]: x for x in d["kpis"]}
    assert 13_000 < k["adv_contracts"]["value"] < 18_000
    assert 0.5 < k["active_rate"]["value"] < 0.7
    assert 0.45 < k["top5_adv_share"]["value"] < 0.56
    assert k["adv_contracts"]["prior"] < k["adv_contracts"]["value"]  # rising


def test_ceo_week_end_param(client):
    d = get(client, "/api/ceo/weekly?week_end=2026-09-25")
    assert d["week_end"] == "2026-09-25"
    assert get(client, "/api/ceo/weekly?week_end=2026-09-23")["week_end"] == "2026-09-18"  # snaps to Friday
    get(client, "/api/ceo/weekly?week_end=2027-01-01", 422)
    get(client, "/api/ceo/weekly?week_end=notadate", 422)


def test_ceo_memo_md(client):
    r = client.get("/api/ceo/weekly.md")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    assert "Synthetic data — illustrative" in r.text and r.text.startswith("# ElectronX — CEO Weekly")
    assert "nan" not in r.text.lower().replace("financ", "")


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
    ids = [t["trigger_id"] for t in d["triggers"]]
    assert ids[0] == HOUSTON and "ERCOT-HB_NORTH-20261002" in ids
    t = d["triggers"][0]
    assert {"trigger_id", "hub", "iso", "regime", "severity", "spike_hours", "vol_z", "peak_lmp", "peak_ts", "start_ts",
            "end_ts", "forward_risk", "exposed_count", "funded_not_trading", "adv_at_stake"} <= set(t)
    assert t["peak_lmp"] == 4800 and t["forward_risk"] is True and 0 < t["severity"] <= 100
    assert t["exposed_count"] >= 14 and t["funded_not_trading"] > 0 and t["adv_at_stake"] > 0


def test_pulse_trigger_accounts(client):
    d = get(client, f"/api/pulse/triggers/{HOUSTON}/accounts")
    assert d["trigger"]["trigger_id"] == HOUSTON
    accts = d["accounts"]
    assert len(accts) == d["trigger"]["exposed_count"]
    dirs = {a["direction"] for a in accts}
    assert dirs == {"hurt", "opportunity"}
    for a in accts[:20]:
        assert {"account_id", "name", "segment", "stage", "direction", "exposure_line", "exposure_score", "p_active", "exp_adv",
                "last_touch_days", "suppressed", "suppressed_reason"} <= set(a)
        assert "$" not in a["exposure_line"]
    assert any(a["segment"] == "REP" and a["direction"] == "hurt" for a in accts)
    assert any(a["segment"] in ("STORAGE", "PROP") and a["direction"] == "opportunity" for a in accts)
    get(client, "/api/pulse/triggers/NOPE-123/accounts", 404)


def test_pulse_history(client):
    d = get(client, "/api/pulse/history")
    assert len(d["events"]) >= 20 and {"trigger_id", "hub", "regime", "peak_lmp", "start_ts"} <= set(d["events"][0])
    lift = d["lift"]
    assert lift["triggered"]["n"] > 50 and 2.0 <= lift["lift_x"] <= 3.0


# ---------------------------------------------------------------- Queue / scoring
def test_activation_queue(client):
    d = get(client, "/api/activation/queue?limit=50")
    assert d["as_of"] == AS_OF
    assert {"accounts_in_queue", "stalled", "sla_breaches", "adv_at_stake"} <= set(d["summary"])
    items = d["items"]
    assert len(items) == 50 and [i["rank"] for i in items] == list(range(1, 51))
    pr = [i["priority"] for i in items]
    assert pr == sorted(pr, reverse=True)
    for it in items:
        assert {"rank", "account_id", "name", "segment", "side", "iso", "stage", "days_in_stage", "stall", "p_active", "exp_adv",
                "k_stage", "urgency", "balance_weight", "priority", "trigger_id", "next_action", "reasons"} <= set(it)
        assert it["side"] != "liquidity_partner" and it["urgency"] <= 2.0
        assert abs(it["p_active"] * it["exp_adv"] * it["k_stage"] * it["urgency"] * it["balance_weight"] - it["priority"]) < 0.05 * max(it["priority"], 1)
        assert set(it["next_action"]) >= {"rule_id", "action", "owner", "sla", "sequence"}
        assert all({"label", "direction", "weight"} <= set(r) and r["direction"] in "+-" for r in it["reasons"])
    assert any(i["balance_weight"] == 1.15 for i in items if i["side"] == "hedger")


def test_activation_queue_filters(client):
    d = get(client, "/api/activation/queue?segment=REP&iso=ERCOT&limit=10")
    assert all(i["segment"] == "REP" and i["iso"] == "ERCOT" for i in d["items"])
    d = get(client, "/api/activation/queue?stage=FUNDED&limit=200")
    assert d["items"] and all(i["stage"] == "FUNDED" for i in d["items"])
    d = get(client, "/api/activation/queue?rep_id=1&limit=5")
    assert all(i["rep_id"] == 1 for i in d["items"])
    get(client, "/api/activation/queue?segment=BOGUS", 422)
    get(client, "/api/activation/queue?stage=BOGUS", 422)


def test_scoring_model(client):
    d = get(client, "/api/scoring/model")
    assert d["as_of"] == AS_OF
    assert {"target", "train_n", "test_n", "auc", "pr_auc", "brier", "base_rate", "lift_top_decile", "gain_curve",
            "calibration", "coefficients", "challenger"} <= set(d)
    assert 0.72 <= d["auc"] <= 0.9 and d["lift_top_decile"] >= 2
    assert {"pct_accounts", "pct_positives"} <= set(d["gain_curve"][0])
    assert {"bin", "predicted", "observed", "n"} <= set(d["calibration"][0])
    assert {"name", "auc", "lift_top_decile"} <= set(d["challenger"])


# ---------------------------------------------------------------- Funnel / segments / liquidity
def test_funnel(client):
    d = get(client, "/api/funnel")
    steps = d["steps"]
    assert steps[0]["step"] == "contract_signed" and steps[0]["conv_from_prev"] is None
    for s in steps[1:]:
        assert {"step", "label", "n", "conv_from_prev", "median_days_from_prev", "p75_days"} <= set(s)
        assert 0 <= s["conv_from_prev"] <= 1
    assert set(d["states"]) >= {"active", "at_risk", "dormant"}
    assert len(d["by_segment"]) == 8 and {"segment", "steps"} <= set(d["by_segment"][0])
    fr = d["friction"]
    assert fr
    for f in fr:
        assert {"step", "segment", "metric", "value", "benchmark", "accounts_affected", "adv_at_stake", "roadmap_ask", "severity"} <= set(f)
        assert f["severity"] in {"low", "medium", "high", "critical"}
    advs = [f["adv_at_stake"] for f in fr]
    assert advs == sorted(advs, reverse=True)
    # planted friction is found: DATACENTER bank_linked→funded dwell, UTILITY/CI_LOAD KYC loops, FUND rejections
    found = {(f["segment"], f["step"], f["metric"]) for f in fr}
    assert ("DATACENTER", "funded", "median_days") in found
    assert any(s in ("UTILITY", "CI_LOAD") and m == "kyc_info_requests_per_account" for s, _, m in found)
    assert ("FUND", "first_trade", "order_rejection_rate") in found


def test_funnel_filters_and_ticket(client):
    d = get(client, "/api/funnel?segment=UTILITY&iso=PJM")
    assert all(f["segment"] == "UTILITY" for f in d["friction"])
    assert len(d["by_segment"]) == 1
    md = get(client, "/api/funnel/friction/0.md")
    assert md.startswith("# Roadmap ticket") and "Synthetic data — illustrative" in md
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
    assert len(reps) == 5 and {r["role"] for r in reps} == {"AE", "STRATEGIC"}
    for r in reps:
        assert {"rep_id", "name", "role", "funded_ytd", "quota_ytd", "attainment", "activation_rate", "book_adv",
                "median_days_sign_to_trade", "pipeline_coverage", "sla_adherence", "score", "components"} <= set(r)
        assert 0 <= r["score"] <= 150
        assert abs(sum(r["components"].values()) - r["score"]) < 0.5


def test_comp_plans(client):
    d = get(client, "/api/team/comp-plans")
    ids = [p["plan_id"] for p in d["plans"]]
    assert ids == ["pay_on_signature", "pay_on_funded", "activation_adv"]
    assert all(p["name"] and p["formula"] for p in d["plans"])


def test_comp_sim(client):
    r = client.post("/api/team/comp-sim", json={"plan_id": "activation_adv"})
    assert r.status_code == 200
    d = r.json()
    assert d["plan"]["plan_id"] == "activation_adv" and len(d["reps"]) == 5
    assert {"rep_id", "name", "payout_variable", "payout_breakdown"} <= set(d["reps"][0])
    assert {"variable_cost", "per_active_account", "per_1k_contracts"} <= set(d["totals"])
    cmp = {c["plan_id"]: c for c in d["comparison"]}
    assert set(cmp) == {"pay_on_signature", "pay_on_funded", "activation_adv"}
    assert all(c["behavior"] for c in cmp.values())
    # the recommended plan buys Active accounts cheapest
    assert cmp["activation_adv"]["per_active_account"] < cmp["pay_on_funded"]["per_active_account"] < cmp["pay_on_signature"]["per_active_account"]
    # partial params merge (contract note #9): CEO's $2,500 unit raises cost
    r2 = client.post("/api/team/comp-sim", json={"plan_id": "activation_adv", "params": {"per_account_unit": 2500, "multipliers": {"funded": 0.5}}})
    assert r2.status_code == 200 and r2.json()["totals"]["variable_cost"] > d["totals"]["variable_cost"]
    assert r2.json()["plan"]["multipliers"]["active_60d"] == 1.0
    assert client.post("/api/team/comp-sim", json={}).json()["plan"]["plan_id"] == "activation_adv"
    assert client.post("/api/team/comp-sim", json={"plan_id": "nope"}).status_code == 404
    assert client.post("/api/team/comp-sim", json={"plan_id": "activation_adv", "params": {"accelerator": "fast"}}).status_code == 422


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
    assert {"id", "name", "segment", "iso", "stage", "rep", "p_active", "adv_30d"} <= set(d["items"][0])
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
            "rep_name", "is_liquidity_partner", "funded_amount_usd", "size_mw", "p_active", "signed_at", "funded_at",
            "first_trade_at"} <= set(a)
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


def test_account_360_lp_and_404(client):
    lp = get(client, "/api/accounts?limit=600")["items"]
    lp_id = next(i["id"] for i in lp if i["is_liquidity_partner"])
    d = get(client, f"/api/accounts/{lp_id}")
    assert d["account"]["is_liquidity_partner"] is True and d["account"]["side"] == "liquidity_partner"
    get(client, "/api/accounts/999999", 404)


# ---------------------------------------------------------------- Outreach workflow
def _first_exposed_rep(client):
    accts = get(client, f"/api/pulse/triggers/{HOUSTON}/accounts")["accounts"]
    return next(a for a in accts if a["segment"] == "REP" and not a["suppressed"] and a["stage"] != "TARGET")


def test_outreach_volatility_flow(client, cleanup):
    acct = _first_exposed_rep(client)
    before = get(client, "/api/activation/queue?limit=1000")
    prev = next((i for i in before["items"] if i["account_id"] == acct["account_id"]), None)

    r = client.post("/api/outreach/draft", json={"account_id": acct["account_id"], "trigger_id": HOUSTON, "kind": "volatility"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["engine"] == "template" and d["status"] == "pending_review"
    assert d["compliance"]["passed"] is True
    assert "{" not in d["subject"] + d["body"] and "$4,800" in d["body"]
    assert d["facts"]["event_peak_price"] == "$4,800" and d["facts"]["regime_label"] == "scarcity pricing"
    assert d["body"].rstrip().endswith(d["facts"].get("disclaimer", "") or "CFTC approval or endorsement of any product or communication.")

    did = d["draft_id"]
    assert client.post(f"/api/outreach/{did}/queue").status_code == 409  # queue before approve
    a = client.post(f"/api/outreach/{did}/approve")
    assert a.status_code == 200 and a.json() == {"draft_id": did, "status": "approved", "activity_id": None,
                                                    "account_id": None, "trigger_id": None, "logged_at": None}
    q = client.post(f"/api/outreach/{did}/queue")
    assert q.status_code == 200 and q.json()["status"] == "queued"
    assert client.post(f"/api/outreach/{did}/queue").status_code == 409  # no double-logging
    assert client.post(f"/api/outreach/{did}/approve").status_code == 409

    # Queue reflects the touch: last_touch_days 0, trigger urgency gone, volatility rule suppressed
    after = get(client, "/api/activation/queue?limit=1000")
    it = next(i for i in after["items"] if i["account_id"] == acct["account_id"])
    assert it["last_touch_days"] == 0 and it["trigger_id"] is None
    assert it["next_action"]["condition_code"] != "VOL_TRIGGER_EXPOSED"
    if prev is not None:
        assert it["urgency"] < prev["urgency"] and it["priority"] < prev["priority"]
    pulse = get(client, f"/api/pulse/triggers/{HOUSTON}/accounts")["accounts"]
    pa = next(x for x in pulse if x["account_id"] == acct["account_id"])
    assert pa["suppressed"] is True and pa["last_touch_days"] == 0 and pa["suppressed_reason"]
    tl = get(client, f"/api/accounts/{acct['account_id']}")["timeline"]
    assert tl[0]["type"] == "triggered_email" and HOUSTON in tl[0]["label"]

    # a second volatility draft within 14 days is blocked (R14) → approve 409
    r2 = client.post("/api/outreach/draft", json={"account_id": acct["account_id"], "trigger_id": HOUSTON, "kind": "volatility"})
    assert r2.status_code == 200 and r2.json()["compliance"]["passed"] is False
    assert any(f["rule"] == "R14_CADENCE_LIMITS" and f["level"] == "block" for f in r2.json()["compliance"]["flags"])
    assert client.post(f"/api/outreach/{r2.json()['draft_id']}/approve").status_code == 409


def test_outreach_activation_and_qbr(client, cleanup):
    funded = get(client, "/api/accounts?stage=FUNDED&limit=1")["items"][0]
    r = client.post("/api/outreach/draft", json={"account_id": funded["id"], "kind": "activation"})
    assert r.status_code == 200
    d = r.json()
    assert d["kind"] == "activation" and d["trigger_id"] is None and d["template_id"].startswith("ACT_")
    assert "{" not in d["body"] and d["compliance"]["passed"]
    assert client.post(f"/api/outreach/{d['draft_id']}/approve").status_code == 200
    q = client.post(f"/api/outreach/{d['draft_id']}/queue")
    assert q.status_code == 200
    tl = get(client, f"/api/accounts/{funded['id']}")["timeline"]
    assert tl[0]["type"] == "email"
    aid = _active_account_id(client)
    r = client.post("/api/outreach/draft", json={"account_id": aid, "kind": "qbr"})
    assert r.status_code == 200 and r.json()["template_id"] == "QBR_GENERIC" and "{" not in r.json()["body"]


def test_outreach_errors(client):
    assert client.post("/api/outreach/draft", json={"account_id": 999999, "kind": "activation"}).status_code == 404
    assert client.post("/api/outreach/draft", json={"account_id": 1, "kind": "spam"}).status_code == 422
    assert client.post("/api/outreach/draft", json={"account_id": 1, "kind": "volatility", "trigger_id": "NOPE"}).status_code == 404
    assert client.post("/api/outreach/999999/approve").status_code == 404
    assert client.post("/api/outreach/999999/queue").status_code == 404
