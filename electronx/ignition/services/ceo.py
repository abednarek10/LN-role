"""CEO Weekly (CEO memo §1 KPI definitions, spec D2/D9/D11).

Everything is computed point-in-time at the close of ``week_end`` (Friday):
``Tc = week_end + 1 day 00:00``. Only rows with ``ts < Tc`` count.

Definitions used (single source: ``ignition/definitions.py``):

* ADV (contracts) — Σ contracts over the 20 trading days ending ``week_end`` ÷ 20,
  shown vs the prior 20 td and the 5-day ADV. LP volume is reported as its own line.
  (The synthetic book has no self-matches, so "excludes self-matches" is a no-op.)
* ADV notional — Σ notional (contracts × MWh/contract × price) ÷ 20.
* Fee revenue — Σ fees, trailing 20 td (and the week).
* Funded velocity — new funded accounts/week, 4-week moving average.
* Cohort activation — accounts funded in the last 8 matured weeks (funded
  ≥30 d before close) whose first qualifying trade (≥10 contracts) came within 30 d.
  Cohort bars are 4-week funding cohorts; n < 20 is greyed.
* Active rate — Active (≥4 distinct trading days in trailing 30, D2) ÷ funded
  accounts older than 20 days.
* Days to first trade — median (and P75) days funded → first qualifying trade,
  for first qualifying trades in the trailing 90 days.
* Mix — Active accounts and ADV by side; LPs are their own side.
* Concentration — top-5 accounts' share of 20-td ADV, HHI of ADV by account.
* Spreads — mean of the last 5 weekday snapshots at each ISO's main hub, HOURLY
  (next-hour) and DAILY_PEAK (front daily).
* Net ADV retention — trailing 90 d ADV of the top-20 institutional (non-LP)
  accounts by prior-90-d ADV ÷ their prior-90-d ADV.
* Stalled — funded >21 d, no qualifying trade, non-LP; ranked by P × E[ADV].
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from .. import definitions as D
from . import activation
from .common import AS_OF_TS, as_int, first_friday_after, num, week_fridays

T26 = D.TARGETS_2026
FIRST_WEEK = first_friday_after(D.HISTORY_START)  # 2026-01-09


class WeekEndError(ValueError):
    pass


def parse_week_end(v: str | date | None) -> date:
    if v in (None, ""):
        return D.WEEK_END
    try:
        d = pd.Timestamp(v).date()
    except Exception as exc:  # noqa: BLE001
        raise WeekEndError(f"week_end must be YYYY-MM-DD, got {v!r}") from exc
    d = d - timedelta(days=(d.weekday() - 4) % 7)  # snap to Friday on/before
    if d > D.WEEK_END or d < FIRST_WEEK + timedelta(days=28):
        raise WeekEndError(f"week_end must be between {FIRST_WEEK + timedelta(days=28)} and {D.WEEK_END}")
    return d


# ---------------------------------------------------------------------------
# Base frames (built once per state version)
# ---------------------------------------------------------------------------
class Base:
    def __init__(self, frames):
        acc = frames.accounts.copy()
        acc["side"] = [D.segment_side(s, bool(lp)) for s, lp in zip(acc["segment"], acc["is_liquidity_partner"])]
        self.acc = acc.set_index("id", drop=False)
        tr = frames.trades.copy()
        tr["d"] = tr["ts"].dt.normalize()
        tr["is_lp"] = tr["account_id"].map(self.acc["is_liquidity_partner"]).astype(bool)
        tr["side"] = tr["account_id"].map(self.acc["side"])
        self.tr = tr
        self.days = tr[["account_id", "d"]].drop_duplicates()
        self.spreads = frames.spread_snapshots
        self.lp_ids = set(self.acc.index[self.acc["is_liquidity_partner"]])

    def window(self, end: date, n: int = D.ADV_WINDOW_TD) -> pd.DataFrame:
        d0, d1 = D.adv_window(end, n, inclusive=True)
        m = (self.tr["d"] >= pd.Timestamp(d0)) & (self.tr["d"] <= pd.Timestamp(d1))
        return self.tr[m]

    def active_ids(self, tc: pd.Timestamp) -> pd.Index:
        w = self.days[(self.days["d"] >= tc - pd.Timedelta(days=D.ACTIVE_LOOKBACK_D)) & (self.days["d"] < tc)]
        n = w.groupby("account_id").size()
        return n.index[n >= D.ACTIVE_MIN_DAYS]


def _base(state) -> Base:
    return state.cached(("ceo_base",), lambda: Base(state.frames))


def snapshot(b: Base, we: date) -> dict:
    """Raw KPI values at the close of ``we``."""
    tc = pd.Timestamp(we) + pd.Timedelta(days=1)
    acc = b.acc
    win = b.window(we)
    d0, _ = D.adv_window(we, inclusive=True)
    prior_win = b.window(d0 - timedelta(days=1))
    adv = win["contracts"].sum() / D.ADV_WINDOW_TD
    adv_prior = prior_win["contracts"].sum() / D.ADV_WINDOW_TD
    adv_5d = b.window(we, 5)["contracts"].sum() / 5
    adv_lp = win.loc[win["is_lp"], "contracts"].sum() / D.ADV_WINDOW_TD
    notional = win["notional_usd"].sum() / D.ADV_WINDOW_TD
    notional_by_iso = (win.groupby("iso")["notional_usd"].sum() / D.ADV_WINDOW_TD).round(0).to_dict()
    fees_20 = win["fee_usd"].sum()
    wk = b.tr[(b.tr["d"] >= pd.Timestamp(we) - pd.Timedelta(days=6)) & (b.tr["d"] < tc)]
    fees_week = wk["fee_usd"].sum()

    funded = acc[acc["funded_at"].notna() & (acc["funded_at"] < tc)]
    signed = acc[acc["signed_at"].notna() & (acc["signed_at"] < tc)]
    new_funded_4w = int((funded["funded_at"] >= tc - pd.Timedelta(days=28)).sum())
    recent_f = funded[funded["funded_at"] >= tc - pd.Timedelta(days=90)]
    sign_to_fund = ((recent_f["funded_at"] - recent_f["signed_at"]).dt.total_seconds() / 86400).median()

    active = b.active_ids(tc)
    mature = funded[funded["funded_at"] <= tc - pd.Timedelta(days=D.ACTIVE_RATE_MIN_AGE_D)]
    active_rate = float(mature.index.isin(active).mean()) if len(mature) else None
    n_active_funded = int(mature.index.isin(active).sum())

    nonlp_f = funded[~funded["is_liquidity_partner"]]
    coh = nonlp_f[(nonlp_f["funded_at"] <= tc - pd.Timedelta(days=D.COHORT_FIRST_TRADE_D))
                  & (nonlp_f["funded_at"] > tc - pd.Timedelta(days=D.COHORT_FIRST_TRADE_D + 56))]
    ok = coh["first_qualifying_trade_at"].notna() & (
        (coh["first_qualifying_trade_at"] - coh["funded_at"]) <= pd.Timedelta(days=D.COHORT_FIRST_TRADE_D))
    cohort_rate = float(ok.mean()) if len(coh) else None

    fq = acc[(~acc["is_liquidity_partner"]) & acc["first_qualifying_trade_at"].notna()
             & (acc["first_qualifying_trade_at"] < tc) & (acc["first_qualifying_trade_at"] >= tc - pd.Timedelta(days=90))]
    dd = (fq["first_qualifying_trade_at"] - fq["funded_at"]).dt.total_seconds() / 86400
    dd = dd[dd >= 0]

    act_acc = acc.loc[acc.index.intersection(active)]
    by_side_accounts = {s: int((act_acc["side"] == s).sum()) for s in D.SIDES}
    hedger_share = by_side_accounts["hedger"] / len(act_acc) if len(act_acc) else None
    by_side_adv = {s: round(float(win.loc[win["side"] == s, "contracts"].sum()) / D.ADV_WINDOW_TD, 1) for s in D.SIDES}
    organic = by_side_adv["hedger"] + by_side_adv["speculator"]
    spec_share = by_side_adv["speculator"] / organic if organic else None
    per_acct = win.groupby("account_id")["contracts"].sum().sort_values(ascending=False)
    tot = per_acct.sum()
    top5 = float(per_acct.head(5).sum() / tot) if tot else None
    hhi = float(((per_acct / tot) ** 2).sum()) if tot else None
    top5_ids = [int(i) for i in per_acct.head(5).index]

    sp = b.spreads
    sp = sp[(sp["date"] < tc) & (sp["date"].dt.dayofweek < 5)]  # trading days only
    spreads = {}
    for iso, hub in D.MAIN_HUB.items():
        for tenor in D.SPREAD_TENORS:
            s = sp[(sp["hub"] == hub) & (sp["tenor"] == tenor)].sort_values("date").tail(5)
            s_prev = sp[(sp["hub"] == hub) & (sp["tenor"] == tenor) & (sp["date"] < tc - pd.Timedelta(days=56))].sort_values("date").tail(10)
            spreads[(iso, hub, tenor)] = {
                "spread": float(s["spread_usd_mwh"].mean()) if len(s) else None,
                "uptime": float(s["two_sided_uptime_pct"].mean()) if len(s) else None,
                "lp_quote_share": float(s["lp_quote_share"].mean()) if len(s) else None,
                "active_accounts": float(s["active_accounts"].mean()) if len(s) else None,
                "spread_8w_ago": float(s_prev["spread_usd_mwh"].mean()) if len(s_prev) else None,
            }

    cur = b.tr[(b.tr["ts"] >= tc - pd.Timedelta(days=90)) & (b.tr["ts"] < tc) & ~b.tr["is_lp"]]
    prv = b.tr[(b.tr["ts"] >= tc - pd.Timedelta(days=180)) & (b.tr["ts"] < tc - pd.Timedelta(days=90)) & ~b.tr["is_lp"]]
    prv_by = prv.groupby("account_id")["contracts"].sum().sort_values(ascending=False).head(20)
    nrr = float(cur[cur["account_id"].isin(prv_by.index)]["contracts"].sum() / prv_by.sum()) if prv_by.sum() else None

    stalled_ids = nonlp_f[(nonlp_f["funded_at"] < tc - pd.Timedelta(days=D.STALL_FUNDED_NO_TRADE_D))
                          & ~(nonlp_f["first_qualifying_trade_at"].notna() & (nonlp_f["first_qualifying_trade_at"] < tc))].index

    return {
        "week_end": we, "adv": adv, "adv_prior": adv_prior, "adv_5d": adv_5d, "adv_lp": adv_lp,
        "adv_organic": adv - adv_lp, "notional": notional, "notional_by_iso": notional_by_iso,
        "fees_20": fees_20, "fees_week": fees_week,
        "signed_cum": len(signed), "funded_cum": len(funded), "funded_velocity": new_funded_4w / 4.0,
        "median_sign_to_fund": None if pd.isna(sign_to_fund) else float(sign_to_fund),
        "active_rate": active_rate, "active_n": n_active_funded, "funded_mature_n": int(len(mature)),
        "active_total": int(len(act_acc)),
        "cohort_rate": cohort_rate, "cohort_n": int(len(coh)),
        "median_days_ft": float(dd.median()) if len(dd) else None, "p75_days_ft": float(dd.quantile(0.75)) if len(dd) else None,
        "days_ft_n": int(len(dd)),
        "by_side_accounts": by_side_accounts, "by_side_adv": by_side_adv,
        "hedger_share": hedger_share, "spec_share_adv": spec_share, "top5": top5, "hhi": hhi, "top5_ids": top5_ids,
        "spreads": spreads, "nrr": nrr, "stalled_n": int(len(stalled_ids)),
    }


def _snap(state, we: date) -> dict:
    return state.cached(("ceo_snap", we), lambda: snapshot(_base(state), we))


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
def status_for(value, target, higher: bool = True, band: float = 0.15) -> str:
    """on_track if the target is met; watch within ``band`` (relative); else off_track."""
    if value is None or target is None:
        return "watch"
    if higher:
        if value >= target:
            return "on_track"
        return "watch" if value >= target * (1 - band) else "off_track"
    if value <= target:
        return "on_track"
    return "watch" if value <= target * (1 + band) else "off_track"


def trend_status(delta, higher: bool = True) -> str:
    if delta is None:
        return "watch"
    return "on_track" if (delta >= 0) == higher else "watch"


def spread_status(spread, uptime, t_spread, t_uptime) -> str:
    if spread is None or uptime is None:
        return "watch"
    if spread <= t_spread and uptime >= t_uptime:
        return "on_track"
    if spread <= t_spread * 1.25 and uptime >= t_uptime - 5:
        return "watch"
    return "off_track"


# ---------------------------------------------------------------------------
# KPI tiles
# ---------------------------------------------------------------------------
KPI_DEFS = [
    # key, label, unit, snapshot field, target, higher_is_better, prior_mode
    ("adv_contracts", "ADV (20-td, contracts)", "contracts", "adv", T26["adv_contracts"], True, "adv_prior"),
    ("adv_notional_usd", "ADV notional (20-td)", "usd", "notional", T26["adv_notional_usd"], True, "week"),
    ("fee_revenue_20d", "Fee revenue (20-td)", "usd", "fees_20", None, True, "week"),
    ("funded_velocity", "Funded velocity (4-wk MA)", "accounts", "funded_velocity", "pace", True, "week"),
    ("active_rate", "Active rate", "rate", "active_rate", T26["active_rate"], True, "week"),
    ("cohort_activation_30d", "30-day cohort activation", "rate", "cohort_rate", T26["cohort_activation_30d_start"], True, "week"),
    ("median_days_funded_to_first_trade", "Median days funded → first trade", "days", "median_days_ft", T26["median_days_funded_to_first_trade"], False, "week"),
    ("hedger_share_active", "Hedger share of Active", "share", "hedger_share", T26["hedger_share_active"], True, "week"),
    ("top5_adv_share", "Top-5 ADV share", "share", "top5", T26["top5_adv_share"], False, "week"),
    ("ercot_north_spread", "ERCOT North spread (hourly)", "usd_mwh", "ercot_spread", T26["spread_usd_mwh"]["ERCOT"], False, "week"),
    ("net_adv_retention", "Net ADV retention (top-20)", "ratio", "nrr", T26["net_adv_retention"], True, "week"),
    ("stalled_accounts", "Stalled funded accounts (>21 d)", "accounts", "stalled_n", None, False, "week"),
]


def _field(s: dict, f: str):
    if f == "ercot_spread":
        return s["spreads"][("ERCOT", "HB_NORTH", "HOURLY")]["spread"]
    return s[f]


def _weeks_left(we: date) -> float:
    return max(1.0, (date(2026, 12, 31) - we).days / 7.0)


def build_kpis(state, we: date) -> list[dict]:
    weeks = week_fridays(we, 12)
    snaps = {w: _snap(state, w) for w in weeks}
    cur, prev = snaps[we], snaps[weeks[-2]]
    out = []
    for key, label, unit, fld, target, higher, prior_mode in KPI_DEFS:
        v = _field(cur, fld)
        prior = cur["adv_prior"] if prior_mode == "adv_prior" else _field(prev, fld)
        if target == "pace":  # weekly run-rate needed to reach the EOY funded target
            target = max(0.0, (T26["funded_cum"] - cur["funded_cum"]) / _weeks_left(we))
        delta = (v - prior) if (v is not None and prior is not None) else None
        st = status_for(v, target, higher) if target is not None else trend_status(delta, higher)
        k = {
            "key": key, "label": label, "unit": unit,
            "value": num(v, 4), "prior": num(prior, 4), "delta": num(delta, 4),
            "prior_label": "prior 20 td" if prior_mode == "adv_prior" else "prior week",
            "target": num(target, 4), "target_direction": "min" if higher else "max",
            "status": st,
            "spark": [num(_field(snaps[w], fld), 4) for w in weeks],
        }
        if key == "adv_contracts":
            k["detail"] = {"adv_5d": round(cur["adv_5d"], 1), "adv_lp": round(cur["adv_lp"], 1),
                           "adv_organic": round(cur["adv_organic"], 1), "lp_share": num(cur["adv_lp"] / cur["adv"] if cur["adv"] else None)}
        elif key == "adv_notional_usd":
            k["detail"] = {"by_iso": cur["notional_by_iso"]}
        elif key == "fee_revenue_20d":
            k["detail"] = {"fees_week": round(cur["fees_week"], 2),
                           "per_active_account_20d": num(cur["fees_20"] / cur["active_total"] if cur["active_total"] else None, 2)}
        elif key == "funded_velocity":
            k["detail"] = {"funded_cum": cur["funded_cum"], "funded_target_eoy": T26["funded_cum"],
                           "median_days_signed_to_funded": num(cur["median_sign_to_fund"], 1)}
        elif key == "active_rate":
            k["detail"] = {"active": cur["active_n"], "funded_older_than_20d": cur["funded_mature_n"]}
        elif key == "cohort_activation_30d":
            k["detail"] = {"n": cur["cohort_n"], "greyed": cur["cohort_n"] < D.SMALL_COHORT_N,
                           "window": "accounts funded in the last 8 matured weeks"}
        elif key == "median_days_funded_to_first_trade":
            k["detail"] = {"p75": num(cur["p75_days_ft"], 1), "n": cur["days_ft_n"]}
        elif key == "ercot_north_spread":
            k["detail"] = {"uptime_pct": num(cur["spreads"][("ERCOT", "HB_NORTH", "HOURLY")]["uptime"], 2)}
        elif key == "top5_adv_share":
            k["detail"] = {"hhi": num(cur["hhi"], 4)}
        elif key == "hedger_share_active":
            k["detail"] = {"speculator_share_adv_organic": num(cur["spec_share_adv"]),
                           "speculator_band": list(T26["speculator_share_adv"])}
        out.append(k)
    return out


def weekly_series(state, we: date) -> list[dict]:
    b = _base(state)
    acc = b.acc
    out = []
    for w in week_fridays(we, max(1, (we - FIRST_WEEK).days // 7 + 1)):
        lo = pd.Timestamp(w) - pd.Timedelta(days=6)
        hi = pd.Timestamp(w) + pd.Timedelta(days=1)
        s = _snap(state, w)

        def cnt(col):
            c = acc[col]
            return int(((c >= lo) & (c < hi)).sum())
        out.append({
            "week_end": w.isoformat(),
            "signed": cnt("signed_at"),
            "funded": cnt("funded_at"),
            "first_trades": cnt("first_qualifying_trade_at"),
            "active_accounts": s["active_total"],
            "adv_contracts": round(float(s["adv"]), 1),
            "adv_lp": round(float(s["adv_lp"]), 1),
            "fee_revenue": round(float(s["fees_week"]), 2),
        })
    return out


def activation_cohorts(state, we: date, block_weeks: int = 4) -> list[dict]:
    """4-week funding cohorts (weekly cohorts here are n≈5: all small-n theatre)."""
    b = _base(state)
    tc = pd.Timestamp(we) + pd.Timedelta(days=1)
    f = b.acc[b.acc["funded_at"].notna() & ~b.acc["is_liquidity_partner"]]
    last_matured = tc - pd.Timedelta(days=D.COHORT_FIRST_TRADE_D)
    end = pd.Timestamp(we - timedelta(days=we.weekday())) + pd.Timedelta(days=7)  # next Monday after we's week
    while end > last_matured:
        end -= pd.Timedelta(days=7)
    out = []
    start = end - pd.Timedelta(days=7 * block_weeks)
    while start >= pd.Timestamp(D.HISTORY_START) - pd.Timedelta(days=7 * block_weeks):
        c = f[(f["funded_at"] >= start) & (f["funded_at"] < end)]
        if len(c):
            ok = c["first_qualifying_trade_at"].notna() & (
                (c["first_qualifying_trade_at"] - c["funded_at"]) <= pd.Timedelta(days=D.COHORT_FIRST_TRADE_D))
            out.append({"cohort_week": start.date().isoformat(), "weeks": block_weeks, "n": int(len(c)),
                        "activated_30d_rate": round(float(ok.mean()), 4), "greyed": bool(len(c) < D.SMALL_COHORT_N)})
        end, start = start, start - pd.Timedelta(days=7 * block_weeks)
    return out[::-1]


def spreads_rows(s: dict) -> list[dict]:
    rows = []
    for (iso, hub, tenor), v in s["spreads"].items():
        ts_, tu = T26["spread_usd_mwh"][iso], T26["uptime_pct"][iso]
        rows.append({"iso": iso, "hub": hub, "tenor": tenor,
                     "spread_usd_mwh": num(v["spread"], 3), "uptime_pct": num(v["uptime"], 2),
                     "target_spread": ts_, "target_uptime": tu,
                     "lp_quote_share": num(v["lp_quote_share"], 3),
                     "spread_8w_ago": num(v["spread_8w_ago"], 3),
                     "status": spread_status(v["spread"], v["uptime"], ts_, tu)})
    return rows


def stalled_list(state, we: date, limit: int = 10) -> list[dict]:
    tc = pd.Timestamp(we) + pd.Timedelta(days=1)
    acc = state.accounts
    m = (~acc["is_liquidity_partner"].astype(bool)) & acc["funded_at"].notna() & (
        acc["funded_at"] < tc - pd.Timedelta(days=D.STALL_FUNDED_NO_TRADE_D))
    m &= ~(acc["first_qualifying_trade_at"].notna() & (acc["first_qualifying_trade_at"] < tc))
    df = acc[m].copy()
    df["ev"] = df["p_active"].fillna(0) * df["exp_adv"]
    df = df.sort_values(["ev", "exp_adv"], ascending=False).head(limit)
    out = []
    for r in df.to_dict("records"):
        out.append({
            "account_id": int(r["id"]), "name": r["name"], "segment": r["segment"], "stage": r["stage"],
            "iso": r["primary_iso"], "rep_name": r["rep_name"],
            "days_stalled": round((tc - pd.Timestamp(r["funded_at"])).total_seconds() / 86400, 1),
            "p_active": num(r["p_active"]), "exp_adv": num(r["exp_adv"], 1), "expected_adv": round(float(r["ev"]), 1),
            "next_action": activation.account_next_action(state, int(r["id"])),
        })
    return out


# ---------------------------------------------------------------------------
# Narrative
# ---------------------------------------------------------------------------
def _fmt_c(v) -> str:
    return f"{v / 1000:.1f}k" if abs(v) >= 10_000 else f"{v:,.0f}"


def biggest_lever(state) -> dict:
    """Stalled queue items grouped by next-action rule; largest Σ P×E[ADV] wins."""
    q = activation.queue(state, limit=10_000)
    groups: dict[str, dict] = {}
    for it in q["items"]:
        if not it["stall"] and it["next_action"]["condition_code"] != "VOL_TRIGGER_EXPOSED":
            continue
        na = it["next_action"]
        g = groups.setdefault(na["rule_id"], {"rule_id": na["rule_id"], "action": na["action"], "owner": na["owner"],
                                               "sla": na["sla"], "condition_code": na["condition_code"],
                                               "condition_text": na["condition_text"], "sequence": na["sequence"],
                                               "n": 0, "adv": 0.0, "segments": {}, "isos": {}, "triggers": {}})
        g["n"] += 1
        g["adv"] += (it["p_active"] or 0) * (it["exp_adv"] or 0)
        g["segments"][it["segment"]] = g["segments"].get(it["segment"], 0) + 1
        g["isos"][it["iso"]] = g["isos"].get(it["iso"], 0) + 1
        if it["trigger_id"]:
            g["triggers"][it["trigger_id"]] = g["triggers"].get(it["trigger_id"], 0) + 1
    if not groups:
        return {}
    best = max(groups.values(), key=lambda g: g["adv"])
    best["adv"] = round(best["adv"], 1)
    return best


_PLAY = {
    "VOL_TRIGGER_EXPOSED": "the compliance-approved volatility sequence (NBA R09, 4h SLA)",
    "FUNDED_NO_TRADE_21D": "Head of GTM diagnostic calls (NBA R07)",
    "FUNDED_NO_TRADE_7D": "live hub walkthroughs with a sized DAILY_PEAK example (NBA R06)",
    "KYC_STALLED_5D": "named-document KYC chases (NBA R04)",
    "KYC_NOT_STARTED_3D": "prefilled KYC packets (NBA R03)",
    "KYC_APPROVED_UNFUNDED_5D": "funding steps + first-hedge sizing (NBA R05)",
    "QUALIFIED_NO_AGREEMENT_10D": "agreement + onboarding preview (NBA R02)",
}


def _lever_name(lv: dict, state) -> str:
    if lv.get("condition_code") == "VOL_TRIGGER_EXPOSED" and lv.get("triggers"):
        tid = max(lv["triggers"], key=lv["triggers"].get)
        t = next((x for x in state.triggers if x["trigger_id"] == tid), None)
        if t:
            return f"the {t['iso']} {t['regime_label'].lower()} event ({t['hub']} peaked at ${t['peak_lmp']:,.0f}/MWh)"
    seg = max(lv["segments"], key=lv["segments"].get) if lv.get("segments") else ""
    iso = max(lv["isos"], key=lv["isos"].get) if lv.get("isos") else ""
    return f"{(lv.get('condition_text') or lv.get('rule_id') or '').rstrip('.').lower()} (mostly {D.SEGMENTS.get(seg, {}).get('label', seg)} in {iso})"


def headline(state, s: dict, prev8: dict, lever: dict) -> list[str]:
    sp = s["spreads"][("ERCOT", "HB_NORTH", "HOURLY")]
    d_adv = (s["adv"] / s["adv_prior"] - 1) if s["adv_prior"] else 0.0
    sp_then = sp["spread_8w_ago"]
    tightening = sp_then is not None and sp["spread"] is not None and sp["spread"] < sp_then
    d_active = s["active_total"] - prev8["active_total"]
    liq = (f"Liquidity: ADV is {_fmt_c(s['adv'])} contracts/day ({d_adv:+.1%} vs prior 20 td; liquidity partners {_fmt_c(s['adv_lp'])}), "
           f"with ERCOT North spreads at ${sp['spread']:.2f}/MWh and two-sided uptime {sp['uptime']:.1f}%. "
           f"The flywheel is {'tightening' if tightening else 'stalling'}: "
           f"{abs(d_active)} {'more' if d_active >= 0 else 'fewer'} Active accounts than eight weeks ago and the spread "
           f"{'down' if tightening else 'up'} ${abs((sp['spread'] or 0) - (sp_then or 0)):.2f}.")
    conc = s["top5"] or 0
    bal = (f"Balance: {s['active_n']} of our {s['funded_mature_n']} funded accounts older than 20 days are actively trading "
           f"({(s['active_rate'] or 0):.0%}). Hedgers are {(s['hedger_share'] or 0):.0%} of Active accounts and the top-5 firms hold "
           f"{conc:.0%} of volume — " + ("growth is broad-based, not borrowed." if conc <= T26["top5_adv_share"]
                                        else f"above the {T26['top5_adv_share']:.0%} ceiling, so one departure is a board event."))
    if lever:
        act = (f"Action: This week's biggest lever is {_lever_name(lever, state)}: {lever['n']} accounts worth ~{lever['adv']:,.0f} "
               f"contracts/day expected ADV, and the team is working them through {_PLAY.get(lever['condition_code'], lever['action'].split(':')[0].lower())}.")
    else:
        act = "Action: No stalled accounts this week; the team is working the standard activation sequence."
    return [liq, bal, act]


def decisions(state, s: dict, lever: dict) -> list[str]:
    out = []
    if lever:
        out.append(f"Approve and staff {_PLAY.get(lever['condition_code'], 'the play')} for the {lever['n']} accounts in "
                   f"{_lever_name(lever, state)} today (~{lever['adv']:,.0f} contracts/day expected ADV; owner {lever['owner']}, SLA {lever['sla']}).")
    if s["top5"] is not None and s["top5"] > T26["top5_adv_share"]:
        out.append(f"Concentration is {s['top5']:.0%} top-5 vs a {T26['top5_adv_share']:.0%} ceiling and hedgers are "
                   f"{(s['hedger_share'] or 0):.0%} of Active vs a {T26['hedger_share_active']:.0%} floor: keep the ×{D.BALANCE_WEIGHT_HEDGER} hedger "
                   "balance weight on in the queue and review LP quoting obligations rather than adding partner volume.")
    elif s["hedger_share"] is not None and s["hedger_share"] < T26["hedger_share_active"]:
        out.append(f"Hedgers are {s['hedger_share']:.0%} of Active vs a {T26['hedger_share_active']:.0%} floor: keep the ×{D.BALANCE_WEIGHT_HEDGER} balance weight on.")
    try:
        from . import funnel as funnel_svc
        fr = funnel_svc.funnel(state)["friction"]
        if fr:
            f0 = fr[0]
            out.append(f"Fund the top roadmap ask — {D.SEGMENTS.get(f0['segment'], {}).get('label', f0['segment'])} at "
                       f"'{D.STEP_LABELS.get(f0['step'], f0['step'])}' ({f0['accounts_affected']} accounts, ~{f0['adv_at_stake']:,.0f} contracts/day at stake): "
                       f"{f0['roadmap_ask']}")
    except Exception:  # noqa: BLE001 - decisions are best-effort narrative
        pass
    sp = s["spreads"][("ERCOT", "HB_NORTH", "HOURLY")]
    if len(out) < 3 and sp["spread"] is not None:
        out.append(f"ERCOT North spread ${sp['spread']:.2f} vs ${T26['spread_usd_mwh']['ERCOT']:.2f} target: tighten market-maker "
                   "two-sided obligations on HB_NORTH hourly.")
    return out[:3]


def weekly(state, week_end: date | None = None) -> dict:
    we = week_end or D.WEEK_END
    return state.cached(("ceo_weekly", we), lambda: _weekly(state, we))


def _weekly(state, we: date) -> dict:
    s = _snap(state, we)
    prev8 = _snap(state, we - timedelta(days=56))
    lever = biggest_lever(state)
    return {
        "as_of": D.AS_OF_DATE.isoformat(),
        "week_end": we.isoformat(),
        "synthetic": True,
        "headline": headline(state, s, prev8, lever),
        "kpis": build_kpis(state, we),
        "weekly_series": weekly_series(state, we),
        "mix": {
            "by_side_accounts": s["by_side_accounts"],
            "by_side_adv": s["by_side_adv"],
            "top5_adv_share": num(s["top5"]),
            "hhi": num(s["hhi"]),
            "hedger_share_active": num(s["hedger_share"]),
            "speculator_share_adv_organic": num(s["spec_share_adv"]),
            "top5_accounts": [{"account_id": i, "name": state.accounts.loc[i, "name"],
                               "is_liquidity_partner": bool(state.accounts.loc[i, "is_liquidity_partner"])} for i in s["top5_ids"]],
        },
        "spreads": spreads_rows(s),
        "activation_cohorts": activation_cohorts(state, we),
        "stalled": stalled_list(state, we),
        "stalled_total": s["stalled_n"],
        "decisions": decisions(state, s, lever),
        "lever": lever,
    }
