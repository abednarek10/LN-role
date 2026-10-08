"""Market Pulse (spec D6, CTO §5, v1.1 X6/X7/X8): hubs, live triggers, exposed accounts, events, history.

* Exposure is hub-specific first (X6): ``volatility.exposure_table`` — accounts whose
  own hub is the trigger hub score in full (``hub_match``), other accounts with the
  trigger ISO in ``exposure_isos`` score × 0.6; accounts without the ISO are never listed.
* Listed population: non-LP accounts in QUALIFIED → FIRST_TRADE plus AT_RISK / DORMANT.
* ``funded_not_trading`` (one definition, shared with the CEO lever): stage FUNDED
  (funded > 7 d, no qualifying trade), FIRST_TRADE or AT_RISK, not suppressed.
* ``view=actionable`` (default, X7): top 15 funded-not-trading + top 5 SIGNED/KYC_APPROVED
  by ``touch_value``; QUALIFIED/TARGET and suppressed accounts excluded. ``view=all``: everything.
* ``touch_value = exposure_score/100 × P(Active) × E[ADV]`` (expected value of a touch, D4).
* Events (X6): triggers grouped by ``event_id``; counts are distinct accounts per event
  (best-scoring hub kept), the single source for the CEO lever and the Pulse banner.
* Suppression (CRO §5): a triggered sequence in the last 14 days, or this event already worked.
"""
from __future__ import annotations

import pandas as pd

from .. import definitions as D
from . import volatility
from .activation import TRIGGER_STAGES, trigger_event_id
from .common import AS_OF_TS, account_fact, as_int, date_str, num, ts_str

FNT_STAGES = frozenset({"FUNDED", "FIRST_TRADE", "AT_RISK"})
PRE_FUNDING_ACT = frozenset({"SIGNED", "KYC_APPROVED"})
ACT_FNT, ACT_PRE = 15, 5
FNT_MIN_FUNDED_D = 7


def _trigger_public(t: dict) -> dict:
    return {
        "trigger_id": t["trigger_id"],
        "event_id": trigger_event_id(t),
        "hub": t["hub"],
        "iso": t["iso"],
        "regime": t["regime"],
        "regime_label": t["regime_label"],
        "severity": num(t["severity"], 1),
        "spike_hours": int(t["spike_hours"]),
        "neg_hours": int(t.get("neg_hours") or 0),
        "event_hours": int(t.get("neg_hours") or 0) if t["regime"] == "negative_price" else int(t["spike_hours"]),
        "vol_z": num(t["vol_z"], 2),
        "peak_lmp": num(t["peak_lmp"], 2),
        "peak_ratio": num(t.get("peak_ratio"), 2),
        "peak_ratio_basis": t.get("peak_ratio_basis"),
        "p99_30d": num(t.get("p99_30d"), 2),
        "peak_ts": ts_str(t["peak_ts"]),
        "start_ts": ts_str(t["start_ts"]),
        "end_ts": ts_str(t["end_ts"]),
        "forward_risk": bool(t["forward_risk"]),
        "forecast_peak_lmp": num(t.get("forecast_peak_lmp"), 2),
        "forecast_date": t.get("forecast_date"),
    }


def find_trigger(state, trigger_id: str) -> dict | None:
    return next((t for t in state.triggers if t["trigger_id"] == trigger_id), None)


def is_suppressed(r: dict, event_id: str) -> tuple[bool, str | None]:
    lt = r.get("last_trig_ts")
    if lt is not None and pd.notna(lt) and (AS_OF_TS - pd.Timestamp(lt)).total_seconds() / 86400.0 < D.TRIGGER_COOLDOWN_D:
        return True, (f"Triggered sequence sent {pd.Timestamp(lt).date().isoformat()} — max 1 per account per "
                      f"{D.TRIGGER_COOLDOWN_D} days")
    if event_id in (r.get("sequenced_events") or []):
        return True, f"Already worked for event {event_id} (one sequence per account per ISO event)"
    return False, None


def is_funded_not_trading(r: dict, suppressed: bool) -> bool:
    """The one funded-not-trading definition (CEO decision 4 / X7)."""
    if suppressed or r["stage"] not in FNT_STAGES:
        return False
    if r["stage"] == "FUNDED":
        f = r.get("funded_at")
        return pd.notna(f) and (AS_OF_TS - pd.Timestamp(f)).days > FNT_MIN_FUNDED_D and pd.isna(r.get("first_qualifying_trade_at"))
    return r.get("health_state") in ("not_started", "ramping", "at_risk")


def _rows_for(state, trig: dict) -> list[dict]:
    """Exposed rows for one trigger (hub-specific scoring), ranked by touch value."""
    acc = state.accounts
    ev = trigger_event_id(trig)
    tab = volatility.exposure_table(acc, trig)
    out = []
    for x in tab.itertuples(index=False):
        r = acc.loc[int(x.account_id)]
        if bool(r["is_liquidity_partner"]) or r["stage"] not in TRIGGER_STAGES:
            continue
        rd = r.to_dict()
        sup, why = is_suppressed(rd, ev)
        p = float(r["p_active"]) if pd.notna(r["p_active"]) else 0.0
        out.append({
            "account_id": int(x.account_id),
            "name": r["name"],
            "segment": r["segment"],
            "side": r["side"],
            "stage": r["stage"],
            "health_state": r["health_state"],
            "health_label": r["health_label"],
            "hub": x.hub,
            "hub_match": bool(x.hub_match),
            "iso": r["primary_iso"],
            "direction": x.direction,
            "exposure_line": x.exposure_line,
            "exposure_score": float(x.exposure_score),
            "p_active": num(r["p_active"]),
            "p_display": r["p_display"],
            "exp_adv": num(r["exp_adv"], 1),
            "touch_value": round(float(x.exposure_score) / 100.0 * p * float(r["exp_adv"]), 2),
            "last_touch_days": as_int(r["last_touch_days"]),
            "account_fact": account_fact(rd),
            "funded_not_trading": is_funded_not_trading(rd, sup),
            "suppressed": sup,
            "suppressed_reason": why,
        })
    out.sort(key=lambda a: (a["suppressed"], -a["touch_value"], -a["exposure_score"], a["account_id"]))
    return out


def actionable(rows: list[dict]) -> list[dict]:
    """X7 "Act now": top 15 funded-not-trading + top 5 SIGNED/KYC_APPROVED by touch value."""
    live = [a for a in rows if not a["suppressed"]]
    fnt = [a for a in live if a["funded_not_trading"]][:ACT_FNT]
    pre = [a for a in live if a["stage"] in PRE_FUNDING_ACT][:ACT_PRE]
    return sorted(fnt + pre, key=lambda a: (-a["touch_value"], a["account_id"]))


def _counts(rows: list[dict]) -> dict:
    fnt = [a for a in rows if a["funded_not_trading"]]
    return {
        "exposed": len(rows),
        "funded_not_trading": len(fnt),
        "actionable": len(actionable(rows)),
        "adv_at_stake": round(sum((a["p_active"] or 0) * (a["exp_adv"] or 0) for a in fnt), 1),
        "hurt": sum(1 for a in rows if a["direction"] == "hurt"),
        "opportunity": sum(1 for a in rows if a["direction"] == "opportunity"),
        "suppressed": sum(1 for a in rows if a["suppressed"]),
        "own_hub": sum(1 for a in rows if a["hub_match"]),
    }


def _trigger_rows(state, t: dict) -> list[dict]:
    return state.cached(("pulse_rows", t["trigger_id"]), lambda: _rows_for(state, t))


def _trigger_summary(state, t: dict) -> dict:
    c = _counts(_trigger_rows(state, t))
    return _trigger_public(t) | {
        "exposed_count": c["exposed"], "funded_not_trading": c["funded_not_trading"],
        "actionable_count": c["actionable"], "adv_at_stake": c["adv_at_stake"],
        "hurt": c["hurt"], "opportunity": c["opportunity"], "suppressed": c["suppressed"], "own_hub": c["own_hub"],
    }


def triggers_payload(state) -> dict:
    return state.cached(("pulse_triggers",), lambda: {
        "as_of": D.AS_OF_DATE.isoformat(), "triggers": [_trigger_summary(state, t) for t in state.triggers]})


def trigger_accounts(state, trigger_id: str, view: str = "actionable") -> dict | None:
    t = find_trigger(state, trigger_id)
    if t is None:
        return None

    def build():
        rows = _trigger_rows(state, t)
        c = _counts(rows)
        shown = actionable(rows) if view == "actionable" else rows
        shown = [dict(a, rank=i) for i, a in enumerate(shown, start=1)]
        return {"as_of": D.AS_OF_DATE.isoformat(), "view": view,
                "trigger": _trigger_summary(state, t),
                "counts": {"exposed": c["exposed"], "funded_not_trading": c["funded_not_trading"], "actionable": c["actionable"]},
                "accounts": shown}
    return state.cached(("pulse_accounts", trigger_id, view), build)


def events(state) -> dict:
    """Distinct accounts per ISO event (best-scoring hub kept) — the one source of event numbers."""
    def build():
        groups: dict[str, list[dict]] = {}
        for t in state.triggers:
            groups.setdefault(trigger_event_id(t), []).append(t)
        out = []
        for ev, ts in groups.items():
            best: dict[int, dict] = {}
            for t in ts:
                for a in _trigger_rows(state, t):
                    cur = best.get(a["account_id"])
                    if cur is None or a["exposure_score"] > cur["exposure_score"]:
                        best[a["account_id"]] = dict(a, trigger_id=t["trigger_id"])
            rows = sorted(best.values(), key=lambda a: (a["suppressed"], -a["touch_value"], a["account_id"]))
            c = _counts(rows)
            top = max(ts, key=lambda t: t["severity"])
            out.append({
                "event_id": ev, "iso": top["iso"], "regime": top["regime"], "regime_label": top["regime_label"],
                "hubs": [t["trigger_id"] for t in sorted(ts, key=lambda t: -t["severity"])],
                "top_trigger_id": top["trigger_id"], "top_hub": top["hub"],
                "severity": num(top["severity"], 1), "peak_lmp": num(top["peak_lmp"], 2), "peak_ratio": num(top.get("peak_ratio"), 2),
                "peak_ratio_basis": top.get("peak_ratio_basis"),
                "start_ts": ts_str(min(pd.Timestamp(t["start_ts"]) for t in ts)), "peak_ts": ts_str(top["peak_ts"]),
                "event_hours": int(top.get("neg_hours") or 0) if top["regime"] == "negative_price" else int(top["spike_hours"]),
                "forward_risk": any(t["forward_risk"] for t in ts),
                "exposed": c["exposed"], "funded_not_trading": c["funded_not_trading"], "actionable": c["actionable"],
                "adv_at_stake": c["adv_at_stake"], "suppressed": c["suppressed"],
                "funded_not_trading_ids": sorted(a["account_id"] for a in rows if a["funded_not_trading"]),
            })
        out.sort(key=lambda e: -(e["severity"] or 0))
        return {"as_of": D.AS_OF_DATE.isoformat(), "events": out}
    return state.cached(("pulse_events",), build)


def hubs(state, iso: str | None = None, hours: int = 168) -> dict:
    hours = int(max(24, min(hours, 24 * 60)))

    def build():
        f = state.frames
        hub_list = D.ISOS.get(iso, []) if iso else D.HUBS
        prices = f.market_prices
        fc = f.price_forecasts
        lo = AS_OF_TS - pd.Timedelta(hours=hours)
        out = []
        for hub in hub_list:
            s = prices[(prices["hub"] == hub) & (prices["ts"] >= lo) & (prices["ts"] < AS_OF_TS)]
            series = [{"ts": ts.strftime("%Y-%m-%dT%H:%M:%S"), "lmp": round(float(v), 2)} for ts, v in zip(s["ts"], s["lmp"])]
            fh = fc[fc["hub"] == hub].sort_values("date")
            forecast = [{"date": date_str(d), "forecast_peak_lmp": round(float(p), 2), "forecast_avg_lmp": round(float(a), 2)}
                        for d, p, a in zip(fh["date"], fh["forecast_peak_lmp"], fh["forecast_avg_lmp"])]
            out.append({"hub": hub, "iso": D.HUB_ISO[hub], "series": series,
                        "stats": volatility.hub_stats(prices, hub, D.AS_OF), "forecast": forecast})
        return {"as_of": D.AS_OF_DATE.isoformat(), "iso": iso, "hours": hours, "hubs": out}
    return state.cached(("pulse_hubs", iso, hours), build)


def history(state) -> dict:
    def build():
        f = state.frames
        ev = f.volatility_events.sort_values("start_ts")
        events_ = [{
            "trigger_id": r.trigger_id, "event_id": D.event_id_for(r.iso, pd.Timestamp(r.start_ts)), "hub": r.hub, "iso": r.iso,
            "regime": r.regime, "peak_lmp": num(r.peak_lmp, 2), "spike_hours": int(r.spike_hours), "severity": num(r.severity, 1),
            "start_ts": ts_str(r.start_ts), "end_ts": ts_str(r.end_ts),
        } for r in ev.itertuples(index=False)]
        lift = volatility.trigger_cohort_lift(f.accounts, f.activities, f.trades, f.volatility_events, D.AS_OF)
        return {"as_of": D.AS_OF_DATE.isoformat(), "events": events_, "lift": lift,
                "note": "Cohort: funded-not-trading accounts exposed to each past event; converted = first trade within 14 days."}
    return state.cached(("pulse_history",), build)
