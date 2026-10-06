"""Market Pulse (spec D6, CTO §5): hub series, live triggers, exposed accounts, history.

Exposed accounts for a trigger = non-LP accounts whose ``exposure_isos``
include the trigger ISO, in stages QUALIFIED → FIRST_TRADE plus AT_RISK /
DORMANT (Active accounts get a market note via NBA R15, not this list).
Suppression (CRO §5): a triggered sequence already sent in the last 14 days.
Order: expected value of a touch, ``touch_value = exposure_score/100 × P × E[ADV]``
(spec D4), suppressed accounts last.
"""
from __future__ import annotations

import pandas as pd

from .. import definitions as D
from . import volatility
from .activation import TRIGGER_STAGES
from .common import AS_OF_TS, as_int, date_str, num, ts_str


def _trigger_public(t: dict) -> dict:
    return {
        "trigger_id": t["trigger_id"],
        "hub": t["hub"],
        "iso": t["iso"],
        "regime": t["regime"],
        "regime_label": t["regime_label"],
        "severity": num(t["severity"], 1),
        "spike_hours": int(t["spike_hours"]),
        "neg_hours": int(t.get("neg_hours") or 0),
        "vol_z": num(t["vol_z"], 2),
        "peak_lmp": num(t["peak_lmp"], 2),
        "peak_ts": ts_str(t["peak_ts"]),
        "start_ts": ts_str(t["start_ts"]),
        "end_ts": ts_str(t["end_ts"]),
        "forward_risk": bool(t["forward_risk"]),
        "forecast_peak_lmp": num(t.get("forecast_peak_lmp"), 2),
        "forecast_date": t.get("forecast_date"),
    }


def find_trigger(state, trigger_id: str) -> dict | None:
    return next((t for t in state.triggers if t["trigger_id"] == trigger_id), None)


def _exposed_rows(state, trig: dict) -> list[dict]:
    acc = state.accounts
    m = (~acc["is_liquidity_partner"].astype(bool)) & acc["stage"].isin(TRIGGER_STAGES)
    m &= acc["isos"].map(lambda xs: trig["iso"] in xs)
    out = []
    for r in acc[m].to_dict("records"):
        direction = volatility.exposure_direction(r["segment"], trig["regime"])
        score = volatility.exposure_score(r["segment"], r["size_mw"], trig["severity"], hub_match=(r["hub"] == trig["hub"]))
        lt = r["last_trig_ts"]
        cool = pd.notna(lt) and (AS_OF_TS - pd.Timestamp(lt)).total_seconds() / 86400.0 < D.TRIGGER_COOLDOWN_D
        out.append({
            "account_id": int(r["id"]),
            "name": r["name"],
            "segment": r["segment"],
            "side": r["side"],
            "stage": r["stage"],
            "hub": r["hub"],
            "iso": r["primary_iso"],
            "direction": direction,
            "exposure_line": volatility.exposure_line(r["segment"], trig["hub"], trig["regime"]),
            "exposure_score": score,
            "p_active": num(r["p_active"]),
            "exp_adv": num(r["exp_adv"], 1),
            "last_touch_days": as_int(r["last_touch_days"]),
            "touch_value": round(score / 100.0 * float(r["p_active"] if pd.notna(r["p_active"]) else 0) * float(r["exp_adv"]), 2),
            "suppressed": bool(cool),
            "suppressed_reason": (f"Triggered sequence sent {pd.Timestamp(lt).date().isoformat()} — max 1 per account per {D.TRIGGER_COOLDOWN_D} days"
                                  if cool else None),
        })
    # rank on the expected value of a touch (D4): exposure × P(Active) × E[ADV]; suppressed last
    out.sort(key=lambda a: (a["suppressed"], -a["touch_value"], -a["exposure_score"]))
    return out


def _summary(rows: list[dict]) -> dict:
    live = [a for a in rows if not a["suppressed"]]
    return {
        "exposed_count": len(rows),
        "funded_not_trading": sum(1 for a in rows if a["stage"] == "FUNDED"),
        "adv_at_stake": round(sum((a["p_active"] or 0) * (a["exp_adv"] or 0) for a in live), 1),
        "hurt": sum(1 for a in rows if a["direction"] == "hurt"),
        "opportunity": sum(1 for a in rows if a["direction"] == "opportunity"),
        "suppressed": len(rows) - len(live),
    }


def triggers_payload(state) -> dict:
    def build():
        out = []
        for t in state.triggers:
            rows = _exposed_rows(state, t)
            out.append(_trigger_public(t) | _summary(rows))
        return {"as_of": D.AS_OF_DATE.isoformat(), "triggers": out}
    return state.cached(("pulse_triggers",), build)


def trigger_accounts(state, trigger_id: str) -> dict | None:
    t = find_trigger(state, trigger_id)
    if t is None:
        return None

    def build():
        rows = _exposed_rows(state, t)
        return {"as_of": D.AS_OF_DATE.isoformat(), "trigger": _trigger_public(t) | _summary(rows), "accounts": rows}
    return state.cached(("pulse_accounts", trigger_id), build)


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
        events = [{
            "trigger_id": r.trigger_id, "hub": r.hub, "iso": r.iso, "regime": r.regime,
            "peak_lmp": num(r.peak_lmp, 2), "spike_hours": int(r.spike_hours), "severity": num(r.severity, 1),
            "start_ts": ts_str(r.start_ts), "end_ts": ts_str(r.end_ts),
        } for r in ev.itertuples(index=False)]
        lift = volatility.trigger_cohort_lift(f.accounts, f.activities, f.trades, f.volatility_events, D.AS_OF)
        return {"as_of": D.AS_OF_DATE.isoformat(), "events": events, "lift": lift,
                "note": "Cohort: funded-not-trading accounts exposed to each past event; activated = first trade within 14 days."}
    return state.cached(("pulse_history",), build)
