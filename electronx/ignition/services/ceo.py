"""CEO Weekly (CEO memo §1, spec D2/D9/D11, v1.1 X1/X10, CEO review P0-1..4, P1-7).

Point-in-time at the close of ``week_end`` (Sunday, X1): ``Tc = week_end + 1 day 00:00``
(the default week_end 2026-10-04 makes Tc = AS_OF, the one snapshot every view uses).
Only rows with ``ts < Tc`` count. ADV windows count weekday trading days.

* ADV (contracts) — Σ contracts over the 20 trading days ending ``week_end`` ÷ 20;
  LP volume reported separately; organic = non-LP. (The book has no self-matches.)
* ADV notional — **median daily notional** over the same 20 trading days (X10), with
  a note giving the mean and the largest (event) day.
* Fee revenue — Σ fees over 20 td vs a target derived from the ADV target
  (25,000 × $0.25 × 20 = $125k).
* Pacing (P0-3) — ``signed_cum`` / ``funded_cum`` with ``pace``: needed per week to hit
  the EOY target, 4-week run rate and the projected EOY at that run rate.
* Cohort activation — accounts funded in the last 8 matured weeks whose first
  qualifying trade came within 30 d. Bars are 4-week funding cohorts; n < 20 greyed.
* Active rate — Active (≥4 trading days in trailing 30) ÷ funded accounts older than 20 d.
* Balance (X10) — hedger share of Active, hedger ADV, LP share of ADV, speculator share
  of organic ADV (2026 band 55–75%), top-5 share, HHI.
* Spreads — mean of the last 5 weekday snapshots at each ISO's main hub.
* Net ADV retention — trailing-90-d ADV of the top-20 non-LP accounts by prior-90-d ADV ÷ prior.
* ``prior`` is always the same metric one week earlier (``prior_label`` "prior week").
* ``lever`` (P0-1) — the top live event from ``pulse.events``: ``n`` = funded-not-trading
  accounts exposed to it (distinct across hubs, unsuppressed), the same number the Pulse
  banner shows, plus outreach progress from ``outreach_drafts``.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from .. import definitions as D
from . import activation
from .common import as_int, num

T26 = D.TARGETS_2026
FIRST_WEEK = D.snap_week_end(D.HISTORY_START.date())  # 2026-01-11 (first Sunday close)
YEAR_END = date(2026, 12, 31)
BOARD_KEYS = ("funded_cum", "active_rate", "adv_contracts", "cohort_activation", "hedger_share_active", "ercot_spread")


class WeekEndError(ValueError):
    pass


def parse_week_end(v: str | date | None) -> date:
    if v in (None, ""):
        return D.WEEK_END
    try:
        d = pd.Timestamp(v).date()
    except Exception as exc:  # noqa: BLE001
        raise WeekEndError(f"week_end must be YYYY-MM-DD, got {v!r}") from exc
    d = D.snap_week_end(d)  # Mon–Sun weeks: snap to the Sunday that closes d's week
    lo = FIRST_WEEK + timedelta(days=28)
    if d > D.WEEK_END or d < lo:
        raise WeekEndError(f"week_end must be between {lo} and {D.WEEK_END}")
    return d


def week_ends(end: date, n: int) -> list[date]:
    """The ``n`` week closes ending at ``end`` (oldest first)."""
    return [end - timedelta(days=7 * k) for k in range(n - 1, -1, -1)]


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


def _weeks_left(we: date) -> float:
    return max(1.0, (YEAR_END - we).days / 7.0)


def snapshot(b: Base, we: date) -> dict:
    """Raw KPI values at the close of ``we``."""
    tc = pd.Timestamp(we) + pd.Timedelta(days=1)
    acc = b.acc
    win = b.window(we)
    d0, d1 = D.adv_window(we, inclusive=True)
    prior_win = b.window(d0 - timedelta(days=1))
    adv = win["contracts"].sum() / D.ADV_WINDOW_TD
    adv_prior = prior_win["contracts"].sum() / D.ADV_WINDOW_TD
    adv_5d = b.window(we, 5)["contracts"].sum() / 5
    adv_lp = win.loc[win["is_lp"], "contracts"].sum() / D.ADV_WINDOW_TD
    tdays = pd.bdate_range(d0, d1)
    daily_notional = win.groupby("d")["notional_usd"].sum().reindex(tdays, fill_value=0.0)
    notional_median = float(daily_notional.median())
    notional_mean = float(daily_notional.mean())
    max_day = daily_notional.idxmax() if len(daily_notional) else None
    notional_by_iso = (win.groupby("iso")["notional_usd"].sum() / D.ADV_WINDOW_TD).round(0).to_dict()
    fees_20 = win["fee_usd"].sum()
    wk = b.tr[(b.tr["d"] >= pd.Timestamp(we) - pd.Timedelta(days=6)) & (b.tr["d"] < tc)]
    fees_week = wk["fee_usd"].sum()

    funded = acc[acc["funded_at"].notna() & (acc["funded_at"] < tc)]
    signed = acc[acc["signed_at"].notna() & (acc["signed_at"] < tc)]
    new_funded_4w = int((funded["funded_at"] >= tc - pd.Timedelta(days=28)).sum())
    new_signed_4w = int((signed["signed_at"] >= tc - pd.Timedelta(days=28)).sum())
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

    weeks_left = _weeks_left(we)

    def pace(cum: int, flow_4w: int, target: int) -> dict:
        rr = flow_4w / 4.0
        return {"ytd": cum, "target": target, "needed_weekly": round(max(0.0, (target - cum) / weeks_left), 2),
                "run_rate_4w": round(rr, 2), "projected_eoy": int(round(cum + rr * weeks_left)), "weeks_left": round(weeks_left, 1)}

    return {
        "week_end": we, "adv": adv, "adv_prior": adv_prior, "adv_5d": adv_5d, "adv_lp": adv_lp,
        "adv_organic": adv - adv_lp, "lp_share": adv_lp / adv if adv else None,
        "notional_median": notional_median, "notional_mean": notional_mean,
        "notional_max": float(daily_notional.max()) if len(daily_notional) else None,
        "notional_max_day": max_day.date().isoformat() if max_day is not None else None,
        "notional_by_iso": notional_by_iso,
        "fees_20": fees_20, "fees_week": fees_week,
        "signed_cum": len(signed), "funded_cum": len(funded), "funded_velocity": new_funded_4w / 4.0,
        "signed_pace": pace(len(signed), new_signed_4w, T26["signed_cum"]),
        "funded_pace": pace(len(funded), new_funded_4w, T26["funded_cum"]),
        "median_sign_to_fund": None if pd.isna(sign_to_fund) else float(sign_to_fund),
        "active_rate": active_rate, "active_n": n_active_funded, "funded_mature_n": int(len(mature)),
        "active_total": int(len(act_acc)),
        "cohort_rate": cohort_rate, "cohort_n": int(len(coh)),
        "median_days_ft": float(dd.median()) if len(dd) else None, "p75_days_ft": float(dd.quantile(0.75)) if len(dd) else None,
        "days_ft_n": int(len(dd)),
        "by_side_accounts": by_side_accounts, "by_side_adv": by_side_adv, "hedger_adv": by_side_adv["hedger"],
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


def band_status(value, lo: float, hi: float, slack: float = 0.05) -> str:
    if value is None:
        return "watch"
    if lo <= value <= hi:
        return "on_track"
    return "watch" if lo - slack <= value <= hi + slack else "off_track"


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
# key, label, unit, snapshot field, target (or "band"/None), higher_is_better
KPI_DEFS = [
    ("funded_cum", "Funded accounts (cumulative)", "accounts", "funded_cum", T26["funded_cum"], True),
    ("active_rate", "Active rate", "rate", "active_rate", T26["active_rate"], True),
    ("adv_contracts", "ADV (20-td, contracts)", "contracts", "adv", T26["adv_contracts"], True),
    ("cohort_activation", "30-day cohort activation", "rate", "cohort_rate", T26["cohort_activation_30d_start"], True),
    ("hedger_share_active", "Hedger share of Active", "share", "hedger_share", T26["hedger_share_active"], True),
    ("ercot_spread", "ERCOT North spread (hourly)", "usd_mwh", "ercot_spread", T26["spread_usd_mwh"]["ERCOT"], False),
    ("signed_cum", "Signed accounts (cumulative)", "accounts", "signed_cum", T26["signed_cum"], True),
    ("adv_notional_usd", "Median daily notional (20-td)", "usd", "notional_median", T26["adv_notional_usd"], True),
    ("fee_revenue_20d", "Fee revenue (20-td)", "usd", "fees_20", T26["fee_revenue_20td"], True),
    ("adv_organic", "Organic ADV (ex-LP)", "contracts", "adv_organic", None, True),
    ("hedger_adv", "Hedger ADV", "contracts", "hedger_adv", T26["hedger_adv_contracts"], True),
    ("lp_share_adv", "LP share of ADV", "share", "lp_share", T26["lp_share_adv"], False),
    ("speculator_share_adv_organic", "Speculator share of organic ADV", "share", "spec_share_adv", "band", True),
    ("top5_adv_share", "Top-5 ADV share", "share", "top5", T26["top5_adv_share"], False),
    ("funded_velocity", "Funded per week (4-wk avg)", "accounts", "funded_velocity", "pace", True),
    ("median_days_funded_to_first_trade", "Median days funded → first trade", "days", "median_days_ft", T26["median_days_funded_to_first_trade"], False),
    ("net_adv_retention", "Net ADV retention (top-20)", "ratio", "nrr", T26["net_adv_retention"], True),
    ("stalled_accounts", "Stalled funded accounts (>21 d)", "accounts", "stalled_n", None, False),
]


def _field(s: dict, f: str):
    if f == "ercot_spread":
        return s["spreads"][("ERCOT", "HB_NORTH", "HOURLY")]["spread"]
    return s[f]


def build_kpis(state, we: date) -> list[dict]:
    weeks = week_ends(we, 12)
    snaps = {w: _snap(state, w) for w in weeks}
    cur, prev = snaps[we], snaps[weeks[-2]]
    band = T26["speculator_share_adv_organic"]
    out = []
    for key, label, unit, fld, target, higher in KPI_DEFS:
        v = _field(cur, fld)
        prior = _field(prev, fld)
        delta = (v - prior) if (v is not None and prior is not None) else None
        k = {"key": key, "label": label, "unit": unit, "value": num(v, 4), "prior": num(prior, 4), "delta": num(delta, 4),
             "prior_label": "prior week", "board": key in BOARD_KEYS, "target_direction": "min" if higher else "max",
             "spark": [num(_field(snaps[w], fld), 4) for w in weeks]}
        if target == "band":
            k.update(target=band[1], target_band=list(band), target_direction="band", status=band_status(v, *band))
        elif target == "pace":
            t = cur["funded_pace"]["needed_weekly"]
            k.update(target=num(t, 2), status=status_for(v, t, True))
        elif target is None:
            k.update(target=None, status="info")
        else:
            k.update(target=num(target, 4), status=status_for(v, target, higher))
        if key == "funded_cum":
            k["pace"] = cur["funded_pace"]
            k["status"] = status_for(cur["funded_pace"]["projected_eoy"], target, True, band=0.1)
        elif key == "signed_cum":
            k["pace"] = cur["signed_pace"]
            k["status"] = status_for(cur["signed_pace"]["projected_eoy"], target, True, band=0.1)
        elif key == "adv_contracts":
            k["detail"] = {"adv_prior_20td": round(cur["adv_prior"], 1), "adv_5d": round(cur["adv_5d"], 1),
                           "adv_lp": round(cur["adv_lp"], 1), "adv_organic": round(cur["adv_organic"], 1)}
        elif key == "adv_notional_usd":
            k["note"] = (f"Median of daily notional over 20 trading days. Mean incl. event days ${cur['notional_mean'] / 1e6:.2f}M; "
                         f"largest day ${cur['notional_max'] / 1e6:.1f}M on {pd.Timestamp(cur['notional_max_day']).strftime('%b')} "
                         f"{pd.Timestamp(cur['notional_max_day']).day}.")
            k["detail"] = {"mean_20td": round(cur["notional_mean"], 0), "max_day": cur["notional_max_day"],
                           "max_day_notional": round(cur["notional_max"] or 0, 0), "by_iso_mean": cur["notional_by_iso"]}
        elif key == "fee_revenue_20d":
            k["detail"] = {"fees_week": round(cur["fees_week"], 2),
                           "per_active_account_20d": num(cur["fees_20"] / cur["active_total"] if cur["active_total"] else None, 2)}
        elif key == "funded_velocity":
            k["detail"] = {"median_days_signed_to_funded": num(cur["median_sign_to_fund"], 1)}
        elif key == "active_rate":
            k["detail"] = {"active_funded_20d": cur["active_n"], "funded_older_than_20d": cur["funded_mature_n"],
                           "active_total": cur["active_total"]}
        elif key == "cohort_activation":
            k["detail"] = {"n": cur["cohort_n"], "greyed": cur["cohort_n"] < D.SMALL_COHORT_N,
                           "window": "accounts funded in the last 8 matured weeks"}
        elif key == "median_days_funded_to_first_trade":
            k["detail"] = {"p75": num(cur["p75_days_ft"], 1), "n": cur["days_ft_n"],
                           "window": "first qualifying trades in the trailing 90 days"}
        elif key == "ercot_spread":
            k["detail"] = {"uptime_pct": num(cur["spreads"][("ERCOT", "HB_NORTH", "HOURLY")]["uptime"], 2),
                           "target_uptime_pct": T26["uptime_pct"]["ERCOT"]}
        elif key == "top5_adv_share":
            k["detail"] = {"hhi": num(cur["hhi"], 4)}
        out.append(k)
    return out


def weekly_series(state, we: date) -> list[dict]:
    b = _base(state)
    acc = b.acc
    out = []
    for w in week_ends(we, max(1, (we - FIRST_WEEK).days // 7 + 1)):
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
            "signed_cum": s["signed_cum"],
            "funded_cum": s["funded_cum"],
            "active_accounts": s["active_total"],
            "adv_contracts": round(float(s["adv"]), 1),
            "adv_lp": round(float(s["adv_lp"]), 1),
            "fee_revenue": round(float(s["fees_week"]), 2),
        })
    return out


def activation_cohorts(state, we: date, block_weeks: int = 4) -> list[dict]:
    """4-week funding cohorts starting on or after HISTORY_START (weekly cohorts are n≈5)."""
    b = _base(state)
    tc = pd.Timestamp(we) + pd.Timedelta(days=1)
    f = b.acc[b.acc["funded_at"].notna() & ~b.acc["is_liquidity_partner"]]
    last_matured = tc - pd.Timedelta(days=D.COHORT_FIRST_TRADE_D)
    end = pd.Timestamp(we - timedelta(days=we.weekday())) + pd.Timedelta(days=7)  # Monday after the week
    while end > last_matured:
        end -= pd.Timedelta(days=7)
    out = []
    start = end - pd.Timedelta(days=7 * block_weeks)
    while start >= pd.Timestamp(D.HISTORY_START):
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
            "health_state": r["health_state"], "iso": r["primary_iso"], "rep_name": r["rep_name"],
            "days_stalled": round((tc - pd.Timestamp(r["funded_at"])).total_seconds() / 86400, 1),
            "p_active": num(r["p_active"]), "p_display": r["p_display"], "exp_adv": num(r["exp_adv"], 1),
            "expected_adv": round(float(r["ev"]), 1),
            "next_action": activation.account_next_action(state, int(r["id"])),
        })
    return out


# ---------------------------------------------------------------------------
# Lever (P0-1) and narrative
# ---------------------------------------------------------------------------
def _fmt_c(v) -> str:
    return f"{v / 1000:.1f}k" if abs(v) >= 10_000 else f"{v:,.0f}"


def _day(ts) -> str:
    t = pd.Timestamp(ts)
    return f"{t.strftime('%b')} {t.day}"


def lever(state) -> dict | None:
    """The top live event with funded-not-trading exposure; numbers come from ``pulse.events``."""
    from . import pulse

    evs = [e for e in pulse.events(state)["events"] if e["funded_not_trading"] > 0]
    if not evs:
        return None
    e = evs[0]
    hubs = set(e["hubs"])
    dr = state.frames.outreach_drafts
    dr = dr[dr["trigger_id"].isin(hubs)] if len(dr) else dr
    st = dr["status"] if len(dr) else pd.Series(dtype=str)
    rows = activation._rows(state)
    acc = state.accounts
    ids = e["funded_not_trading_ids"]
    start = pd.Timestamp(e["start_ts"])
    sla_h = next((r.get("sla_hours") for r in activation.rules() if r["condition_code"] == "VOL_TRIGGER_EXPOSED"), 4) or 4
    past = 0
    for i in ids:
        lt = acc.loc[i, "last_touch_ts"]
        touched = pd.notna(lt) and pd.Timestamp(lt) >= start
        if not touched and pd.Timestamp(D.AS_OF) > start + pd.Timedelta(hours=float(sla_h)):
            past += 1
    rules_of = {}
    for i in ids:
        if i in rows.index:
            rid = rows.loc[i, "next_action"]["rule_id"]
            rules_of[rid] = rules_of.get(rid, 0) + 1
    return {
        "event_id": e["event_id"], "iso": e["iso"], "isos": {e["iso"]: e["funded_not_trading"]},
        "regime": e["regime"], "regime_label": e["regime_label"], "top_hub": e["top_hub"], "hubs": e["hubs"],
        "peak_lmp": e["peak_lmp"], "peak_ratio": e["peak_ratio"], "start_ts": e["start_ts"], "event_day": _day(e["start_ts"]),
        "n": e["funded_not_trading"], "funded_not_trading": e["funded_not_trading"], "exposed": e["exposed"],
        "actionable": e["actionable"], "adv_at_stake": e["adv_at_stake"],
        "drafted": int(st.isin(["pending_review", "approved", "queued", "sent"]).sum()) if len(st) else 0,
        "approved": int(st.isin(["approved", "queued", "sent"]).sum()) if len(st) else 0,
        "queued": int(st.isin(["queued", "sent"]).sum()) if len(st) else 0,
        "past_sla": past, "sla_hours": int(sla_h),
        "next_actions": dict(sorted(rules_of.items(), key=lambda kv: -kv[1])),
        "action": "Work the funded-not-trading accounts exposed to the event (Pulse “Act now”), compliance-approved before send",
    }


def headline(state, s: dict, prev8: dict, lv: dict | None) -> list[str]:
    sp = s["spreads"][("ERCOT", "HB_NORTH", "HOURLY")]
    d_adv = (s["adv"] / s["adv_prior"] - 1) if s["adv_prior"] else 0.0
    sp_then = sp["spread_8w_ago"]
    tightening = sp_then is not None and sp["spread"] is not None and sp["spread"] < sp_then
    d_active = s["active_total"] - prev8["active_total"]
    liq = (f"Liquidity: ADV is {_fmt_c(s['adv'])} contracts/day ({d_adv:+.1%} vs the prior 20 trading days; liquidity partners "
           f"{_fmt_c(s['adv_lp'])}, {s['lp_share']:.0%} of the total), with ERCOT North spreads at ${sp['spread']:.2f}/MWh and two-sided "
           f"uptime {sp['uptime']:.1f}%. The flywheel is {'tightening' if tightening else 'stalling'}: "
           f"{abs(d_active)} {'more' if d_active >= 0 else 'fewer'} Active accounts than eight weeks ago and the spread "
           f"{'down' if tightening else 'up'} ${abs((sp['spread'] or 0) - (sp_then or 0)):.2f}.")
    conc = s["top5"] or 0
    bal = (f"Balance: {s['active_total']} accounts are Active; {s['active_n']} of our {s['funded_mature_n']} funded accounts older than "
           f"20 days are actively trading ({(s['active_rate'] or 0):.0%}). Hedgers are {(s['hedger_share'] or 0):.0%} of Active accounts but "
           f"{s['hedger_adv']:,.0f} contracts/day of ADV (target 3,000), and the top-5 firms hold {conc:.0%} of volume — "
           + ("growth is broad-based, not borrowed." if conc <= T26["top5_adv_share"]
              else f"above the {T26['top5_adv_share']:.0%} ceiling, so one departure is a board event."))
    if lv:
        act = (f"Action: This week's biggest lever is the {lv['iso']} {lv['regime_label'].lower()} event on {lv['event_day']} "
               f"({lv['top_hub']} peaked at ${lv['peak_lmp']:,.0f}/MWh, ×{lv['peak_ratio']:.0f} its 30-day p99): {lv['n']} funded-not-trading "
               f"accounts are exposed (~{lv['adv_at_stake']:,.0f} contracts/day expected ADV); {lv['drafted']} drafted, "
               f"{lv['queued']} queued, {lv['past_sla']} past the {lv['sla_hours']}h SLA.")
    else:
        act = "Action: No live event this week; the team is working the stage rules in the Activation Queue."
    return [liq, bal, act]


def _friction_decision(state) -> str | None:
    from . import funnel as funnel_svc

    fr = funnel_svc.funnel(state)["friction"]
    if not fr:
        return None
    f0 = fr[0]
    seg = D.SEGMENTS.get(f0["segment"], {}).get("label", f0["segment"])
    return (f"Fund the top onboarding fix: {seg} accounts stall at {f0['from_step_label']} → {f0['step_label']} "
            f"({f0['accounts_affected']} accounts, ~{f0['adv_at_stake']:,.0f} contracts/day at stake). {f0['ask']}")


def decisions(state, s: dict, lv: dict | None) -> list[str]:
    out = []
    if lv:
        out.append(f"Work the {lv['n']} funded-not-trading {lv['iso']} accounts exposed to the {lv['event_day']} event through the "
                   f"compliance-approved volatility sequence and their stage rules (Pulse “Act now”): {lv['queued']} queued so far, "
                   f"{lv['past_sla']} past SLA, ~{lv['adv_at_stake']:,.0f} contracts/day at stake.")
    if s["top5"] is not None and s["top5"] > T26["top5_adv_share"] or (s["hedger_share"] or 0) < T26["hedger_share_active"]:
        out.append(f"Balance the book: hedgers are {(s['hedger_share'] or 0):.0%} of Active (floor {T26['hedger_share_active']:.0%}) and "
                   f"{s['hedger_adv']:,.0f} contracts/day (target {T26['hedger_adv_contracts']:,}), top-5 share {(s['top5'] or 0):.0%} "
                   f"(ceiling {T26['top5_adv_share']:.0%}): keep the ×{D.BALANCE_WEIGHT_HEDGER:g} hedger weight and hedger slots on, and "
                   "review LP quoting obligations rather than adding partner volume.")
    try:
        fd = _friction_decision(state)
        if fd:
            out.append(fd)
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
    lv = lever(state)
    return {
        "as_of": D.AS_OF_DATE.isoformat(),
        "week_end": we.isoformat(),
        "synthetic": True,
        "headline": headline(state, s, prev8, lv),
        "kpis": build_kpis(state, we),
        "weekly_series": weekly_series(state, we),
        "mix": {
            "by_side_accounts": s["by_side_accounts"],
            "by_side_adv": s["by_side_adv"],
            "top5_adv_share": num(s["top5"]),
            "hhi": num(s["hhi"]),
            "hedger_share_active": num(s["hedger_share"]),
            "hedger_adv": num(s["hedger_adv"], 1),
            "lp_share_adv": num(s["lp_share"]),
            "speculator_share_adv_organic": num(s["spec_share_adv"]),
            "top5_accounts": [{"account_id": i, "name": state.accounts.loc[i, "name"],
                               "is_liquidity_partner": bool(state.accounts.loc[i, "is_liquidity_partner"])} for i in s["top5_ids"]],
        },
        "spreads": spreads_rows(s),
        "activation_cohorts": activation_cohorts(state, we),
        "stalled": stalled_list(state, we),
        "stalled_total": s["stalled_n"],
        "active_accounts": s["active_total"],
        "decisions": decisions(state, s, lv),
        "lever": lv,
    }
