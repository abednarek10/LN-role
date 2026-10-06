"""Accounts list/search and Account 360 (incl. QBR block and health).

Health: ``state``/``trading_days_30``/``adv_30d``/``adv_prior_30d`` from
``features.account_health``; ``net_retention`` = adv_30d ÷ adv_prior_30d;
``churn_risk`` (0–1, traded accounts only) = 0.5 × inactivity (1 − min(td30, 8)/8)
+ 0.3 × decline (1 − retention, clipped 0–1) + 0.2 × recency (days since last
trade ÷ 30, capped). A transparent heuristic, not a model.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import definitions as D
from . import activation
from .common import AS_OF_TS, as_int, content, date_str, num, ts_str


def _item(r: dict) -> dict:
    return {"id": int(r["id"]), "name": r["name"], "segment": r["segment"], "iso": r["primary_iso"], "hub": r["hub"],
            "stage": r["stage"], "rep": r["rep_name"], "rep_id": as_int(r["rep_id"]),
            "is_liquidity_partner": bool(r["is_liquidity_partner"]),
            "p_active": num(r["p_active"]), "adv_30d": num(r["adv_30d"], 1)}


def list_accounts(state, segment=None, iso=None, stage=None, rep_id=None, q=None, limit: int = 50, offset: int = 0) -> dict:
    key = ("accounts", segment, iso, stage, rep_id, (q or "").strip().lower(), limit, offset)
    return state.cached(key, lambda: _list(state, segment, iso, stage, rep_id, q, limit, offset))


def _list(state, segment, iso, stage, rep_id, q, limit, offset) -> dict:
    acc = state.accounts
    m = pd.Series(True, index=acc.index)
    if segment:
        m &= acc["segment"] == segment
    if iso:
        m &= acc["primary_iso"] == iso
    if stage:
        m &= acc["stage"] == stage
    if rep_id is not None:
        m &= acc["rep_id"] == rep_id
    df = acc[m]
    if q and q.strip():
        qs = q.strip().lower()
        nm = df["name"].str.lower()
        df = df[nm.str.contains(qs, regex=False)]
        # prefix matches first, then alphabetical
        df = df.assign(_pre=~df["name"].str.lower().str.startswith(qs)).sort_values(["_pre", "name"])
    else:
        df = df.sort_values("name")
    total = int(len(df))
    page = df.iloc[offset: offset + limit]
    return {"as_of": D.AS_OF_DATE.isoformat(), "total": total, "limit": limit, "offset": offset,
            "items": [_item(r) for r in page.to_dict("records")]}


def _health(r: dict) -> dict:
    td = int(r["trading_days_30"] or 0)
    adv, prior = float(r["adv_30d"] or 0), float(r["adv_prior_30d"] or 0)
    nr = adv / prior if prior > 0 else None
    churn = None
    if bool(r["ever_traded"]):
        inactivity = 1 - min(td, 8) / 8
        decline = float(np.clip(1 - nr, 0, 1)) if nr is not None else 0.5
        lt = r["last_trade_ts"]
        rec = min(((AS_OF_TS - pd.Timestamp(lt)).total_seconds() / 86400) / 30, 1.0) if pd.notna(lt) else 1.0
        churn = round(0.5 * inactivity + 0.3 * decline + 0.2 * rec, 3)
    return {"state": r["state"], "trading_days_30": td, "adv_30d": round(adv, 1), "adv_prior_30d": round(prior, 1),
            "net_retention": num(nr, 3), "churn_risk": churn,
            "last_trade_ts": ts_str(r["last_trade_ts"]), "first_active_at": ts_str(r["first_active_at"])}


def _growth_plays(r: dict, util: dict, isos_traded: list[str], has_api: bool) -> list[str]:
    msg = content("segment_messaging")["segments"].get(r["segment"], {})
    plays = []
    if not r["ever_traded"]:
        prod = msg.get("first_product", "DAILY_PEAK")
        plays.append(f"First position: walk through the {r['hub']} {prod} contract against the exposure the team described.")
    missing = [i for i in r["isos"] if i not in isos_traded]
    if r["ever_traded"] and missing:
        plays.append(f"Second ISO: exposure in {', '.join(missing)} but trades only {', '.join(isos_traded) or r['primary_iso']} — "
                     f"offer the {D.MAIN_HUB[missing[0]]} contract set.")
    if r["ever_traded"] and util.get("HOURLY", 0) < 0.2:
        plays.append("Hourly shape: under 20% of volume in HOURLY contracts — show ramp-hour and evening-peak coverage.")
    if r["ever_traded"] and util.get("WEEKLY_PEAK", 0) == 0 and r["side"] == "hedger":
        plays.append("WEEKLY_PEAK for baseload weeks: a 5-day on-peak strip reduces ticket count for steady load.")
    if r["segment"] in ("PROP", "FUND") and not has_api:
        plays.append("API onboarding: sandbox certification and historical hub data for backtesting (Solutions Eng).")
    if r["ever_traded"] and r["trading_days_30"] < D.ACTIVE_MIN_DAYS:
        plays.append("Re-establish a weekly routine (e.g. Monday peak ladder) before the next forecast peak at their hub.")
    return plays[:4]


def account_360(state, account_id: int) -> dict | None:
    acc = state.accounts
    if account_id not in acc.index:
        return None
    return state.cached(("acct360", account_id), lambda: _a360(state, account_id))


def _a360(state, account_id: int) -> dict:
    f = state.frames
    r = state.accounts.loc[account_id].to_dict()
    account = {
        "id": int(r["id"]), "name": r["name"], "segment": r["segment"], "segment_label": D.SEGMENTS[r["segment"]]["label"],
        "side": r["side"], "primary_iso": r["primary_iso"], "iso": r["primary_iso"], "hub": r["hub"],
        "exposure_isos": list(r["isos"]), "hq_state": r["hq_state"], "stage": r["stage"],
        "rep_id": as_int(r["rep_id"]), "rep_name": r["rep_name"], "is_liquidity_partner": bool(r["is_liquidity_partner"]),
        "has_other_exchange_account": bool(r["has_other_exchange_account"]), "kyc_redlines": int(r["kyc_redlines"]),
        "funded_amount_usd": num(r["funded_amount_usd"], 2), "size_mw": num(r["size_mw"], 1),
        "est_annual_mwh": num(r["est_annual_mwh"], 0), "tam_tier": r["tam_tier"], "lead_source": r["lead_source"],
        "p_active": num(r["p_active"]), "exp_adv": num(r["exp_adv"], 1),
        "days_in_stage": as_int(r["days_in_stage"]), "last_touch_days": as_int(r["last_touch_days"]),
        "created_at": ts_str(r["created_at"]), "signed_at": ts_str(r["signed_at"]), "kyc_approved_at": ts_str(r["kyc_approved_at"]),
        "funded_at": ts_str(r["funded_at"]), "first_trade_at": ts_str(r["first_trade_at"]),
        "first_qualifying_trade_at": ts_str(r["first_qualifying_trade_at"]), "active_since": ts_str(r["active_since"]),
    }
    c = f.contacts[f.contacts["account_id"] == account_id].sort_values(["is_champion", "id"], ascending=[False, True])
    contacts = [{"id": int(x.id), "name": x.name, "title": x.title, "persona": x.persona, "email": x.email,
                 "is_champion": bool(x.is_champion)} for x in c.itertuples(index=False)]

    ob = f.onboarding_events[(f.onboarding_events["account_id"] == account_id) & (f.onboarding_events["ts"] < AS_OF_TS)]
    first = ob.groupby("step")["ts"].min()
    onboarding = [{"step": s, "label": D.STEP_LABELS[s], "ts": ts_str(first[s])} for s in D.ONBOARDING_STEPS if s in first.index]

    timeline = []
    reps = f.reps.set_index("id")["name"]
    acts = f.activities[(f.activities["account_id"] == account_id) & (f.activities["ts"] <= AS_OF_TS)]
    for a in acts.itertuples(index=False):
        who = reps.get(int(a.rep_id)) if pd.notna(a.rep_id) else None
        bits = [a.kind.replace("_", " ").capitalize()]
        if a.outcome and a.outcome != "none":
            bits.append(a.outcome.replace("_", " "))
        if isinstance(a.sequence, str) and a.sequence:
            bits.append(f"{a.sequence} sequence")
        if isinstance(a.trigger_id, str) and a.trigger_id:
            bits.append(a.trigger_id)
        if who:
            bits.append(who)
        timeline.append({"ts": ts_str(a.ts), "type": a.kind, "label": " · ".join(bits)})
    for o in ob.itertuples(index=False):
        timeline.append({"ts": ts_str(o.ts), "type": "onboarding", "label": D.STEP_LABELS.get(o.step, o.step)})
    dr = f.outreach_drafts[f.outreach_drafts["account_id"] == account_id]
    for d in dr.itertuples(index=False):
        timeline.append({"ts": ts_str(d.created_at), "type": "outreach_draft", "label": f"Outreach draft ({d.engine}, {d.status}): {d.subject}"})
    tr = f.trades[(f.trades["account_id"] == account_id) & (f.trades["ts"] < AS_OF_TS)]
    if len(tr):
        daily = tr.assign(d=tr["ts"].dt.normalize()).groupby("d").agg(contracts=("contracts", "sum"), fills=("id", "size"),
                                                                         hubs=("hub", lambda s: ", ".join(sorted(set(s)))))
        for d, x in daily.tail(8).iterrows():
            timeline.append({"ts": ts_str(d + pd.Timedelta(hours=21)), "type": "trade",
                             "label": f"Traded {int(x.contracts):,} contracts in {int(x.fills)} fills ({x.hubs})"})
    rank = {"outreach_draft": 0, "onboarding": 1, "trade": 2}
    timeline.sort(key=lambda e: (e["ts"] or "", rank.get(e["type"], 3)), reverse=True)

    adv_series = []
    if len(tr):
        start = max(tr["ts"].min().normalize(), AS_OF_TS - pd.Timedelta(days=120))
        days = pd.bdate_range(start, AS_OF_TS - pd.Timedelta(days=1))
        by_day = tr.groupby(tr["ts"].dt.normalize())["contracts"].sum()
        adv_series = [{"date": d.date().isoformat(), "contracts": int(by_day.get(d, 0))} for d in days]

    recent = tr[tr["ts"] >= AS_OF_TS - pd.Timedelta(days=90)]
    base = recent if len(recent) else tr
    tot = float(base["contracts"].sum())
    util = {t: (round(float(base.loc[base["tenor"] == t, "contracts"].sum()) / tot, 4) if tot else 0.0) for t in D.TENORS}
    isos_traded = sorted(set(tr["iso"])) if len(tr) else []
    has_api = "api_key_created" in first.index

    na = activation.account_next_action(state, account_id)
    qrow = activation.row_for(state, account_id)
    return {
        "as_of": D.AS_OF_DATE.isoformat(),
        "account": account,
        "contacts": contacts,
        "timeline": timeline,
        "onboarding": onboarding,
        "adv_series": adv_series,
        "health": _health(r),
        "reasons": list(r["reasons"]),
        "next_action": na,
        "queue": ({"priority": num(qrow["priority"], 2), "urgency": num(qrow["urgency"], 3), "k_stage": qrow["k_stage"],
                   "balance_weight": qrow["balance_weight"], "stall": bool(qrow["stall"]),
                   "trigger_id": qrow["trigger_id"] if isinstance(qrow["trigger_id"], str) else None} if qrow else None),
        "qbr": {
            "utilization_by_tenor": util,
            "isos_traded": isos_traded,
            "contracts_90d": int(recent["contracts"].sum()) if len(recent) else 0,
            "fees_90d": round(float(recent["fee_usd"].sum()), 2) if len(recent) else 0.0,
            "last_qbr": date_str(r["last_qbr_ts"]),
            "growth_plays": _growth_plays(r, util, isos_traded, has_api),
        },
    }
