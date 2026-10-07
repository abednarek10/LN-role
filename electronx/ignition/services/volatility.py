"""Volatility trigger engine (CTO memo §5, spec D6) — pure functions.

Inputs are DataFrames shaped like the ``market_prices`` (hub, ts, iso, lmp) and
``price_forecasts`` (hub, iso, date, forecast_peak_lmp, forecast_avg_lmp,
issued_at) tables. No DB access.

Rule per hub at evaluation hour ``T`` (latest hour strictly before ``as_of``):

1. Spike hour: ``lmp > max(P99 of the 30 d before the hour's 72 h window, ISO floor)``
   (floors: ERCOT $1,000, others $250). ``S`` = spike hours in ``(T-72h, T]``.
   CAISO also counts negative hours ``N``.
2. ``RV72 = std(Δ asinh(lmp/10))`` over 72 h; ``vol_z`` = RV72 vs its own
   trailing-30 d distribution (lagged 72 h so the event does not mask itself).
   The baseline std is floored at 0.5 × baseline mean so a calm month does
   not turn a few negative CAISO hours into a 50σ event.
3. Fire if ``S >= 3`` or (``vol_z >= 2.5`` and the 72 h max is at least half
   the ISO floor) or (CAISO and ``N >= 12``) or a forecast peak above the ISO
   floor within 5 days (``forward_risk``).
4. ``raw = 20·S + 15·clip(z,0,3) + 2·N + 10·log2(peak/floor)⁺ + 15·forward_risk``;
   ``severity = 100·(1 − e^(−raw/100))`` — a soft cap so the strongest hub
   still ranks first when several saturate (spec deviation from a hard
   ``min(100, …)``; documented in docs/DATA_MODEL.md).
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Iterable

import numpy as np
import pandas as pd

from ..definitions import AS_OF, FORECAST_DAYS, HUB_ISO, REGIME_LABELS, event_id_for, trigger_id_for

ISO_FLOOR: dict[str, float] = {"ERCOT": 1000.0, "PJM": 250.0, "CAISO": 250.0, "MISO": 250.0}
WINDOW_H = 72
BASELINE_H = 720  # 30 days
SPIKE_MIN_HOURS = 3
VOL_Z_FIRE = 2.5
NEG_MIN_HOURS = 12  # CAISO only
NEG_ISOS = frozenset({"CAISO"})
WINTER_MONTHS = frozenset({12, 1, 2})
MERGE_GAP_H = 24  # historical events: merge firing runs separated by <= 24 h
VOL_SD_FLOOR = 0.5  # baseline std floored at 0.5 × baseline mean RV
VOL_Z_SEVERITY_CAP = 3.0  # vol_z contributes at most 45 severity points
ELEVATED_MIN_FRAC = 0.5  # vol-only trigger also needs max72 >= 0.5 × ISO floor

# Segment sensitivity to a price event (used for exposure scoring).
SEGMENT_SENSITIVITY: dict[str, float] = {
    "REP": 1.0,
    "DATACENTER": 0.9,
    "CI_LOAD": 0.85,
    "STORAGE": 0.9,
    "PROP": 0.8,
    "FUND": 0.7,
    "UTILITY": 0.6,
    "IPP": 0.7,
}

_HURT_ON_SPIKE = frozenset({"REP", "CI_LOAD", "DATACENTER", "UTILITY"})
_HURT_ON_NEGATIVE = frozenset({"IPP"})


# ---------------------------------------------------------------------------
# Indicator frame
# ---------------------------------------------------------------------------
def _hub_series(prices_df: pd.DataFrame, hub: str, as_of: datetime | None = None) -> pd.Series:
    df = prices_df[prices_df["hub"] == hub]
    if as_of is not None:
        df = df[df["ts"] < pd.Timestamp(as_of)]
    s = df.set_index("ts")["lmp"].astype(float).sort_index()
    s.index = pd.DatetimeIndex(s.index)
    return s


def hub_indicators(lmp: pd.Series, iso: str) -> pd.DataFrame:
    """Hourly indicator frame for one hub (index = ts).

    Columns: lmp, thr, spike, neg, S72, N72, max72, min72, rv72, vol_z, raw, severity.
    Every value at hour T uses only hours <= T (no look-ahead).
    """
    floor = ISO_FLOOR.get(iso, 250.0)
    out = pd.DataFrame({"lmp": lmp.astype(float)})
    p99 = lmp.rolling(BASELINE_H, min_periods=24).quantile(0.99).shift(WINDOW_H)
    thr = p99.fillna(floor).clip(lower=floor)
    out["p99_base"] = p99  # unclipped baseline P99 (30 d before the 72 h window)
    out["p1_base"] = lmp.rolling(BASELINE_H, min_periods=24).quantile(0.01).shift(WINDOW_H)
    out["thr"] = thr
    out["spike"] = (lmp > thr).astype(int)
    out["neg"] = (lmp < 0).astype(int) if iso in NEG_ISOS else 0
    out["S72"] = out["spike"].rolling(WINDOW_H, min_periods=1).sum().astype(int)
    out["N72"] = pd.Series(out["neg"], index=out.index).rolling(WINDOW_H, min_periods=1).sum().astype(int)
    out["max72"] = lmp.rolling(WINDOW_H, min_periods=1).max()
    out["min72"] = lmp.rolling(WINDOW_H, min_periods=1).min()
    x = np.arcsinh(lmp / 10.0)
    rv = x.diff().rolling(WINDOW_H, min_periods=24).std()
    out["rv72"] = rv
    base = rv.shift(WINDOW_H).rolling(BASELINE_H, min_periods=168)
    mu = base.mean()
    sd = np.maximum(base.std(), VOL_SD_FLOOR * mu)  # floor: calm baselines don't explode z
    z = (rv - mu) / sd
    z = z.where(sd > 1e-9, 0.0).fillna(0.0)
    z = z.where(rv.notna(), 0.0)
    out["vol_z"] = z.clip(-5, 20)
    peak_term = 10.0 * np.log2(np.maximum(out["max72"] / floor, 1.0))
    neg_term = 2.0 * out["N72"] if iso in NEG_ISOS else 0.0
    out["raw"] = 20.0 * out["S72"] + 15.0 * out["vol_z"].clip(0, VOL_Z_SEVERITY_CAP) + neg_term + peak_term
    out["severity"] = _soft_severity(out["raw"])
    return out


def _soft_severity(raw):
    return np.round(100.0 * (1.0 - np.exp(-np.asarray(raw, dtype=float) / 100.0)), 1)


def _regime(iso: str, ts: datetime, S: int, N: int, z: float) -> str:
    if S >= SPIKE_MIN_HOURS:
        return "winter_peak" if ts.month in WINTER_MONTHS else "scarcity"
    if iso in NEG_ISOS and N >= NEG_MIN_HOURS:
        return "negative_price"
    return "elevated_vol"


# ---------------------------------------------------------------------------
# Hub stats (Market Pulse cards)
# ---------------------------------------------------------------------------
def hub_stats(prices_df: pd.DataFrame, hub: str, as_of: datetime = AS_OF) -> dict:
    """``{last, avg_30d, p99_30d, max_72h, min_72h, spike_hours_72h, vol_z}`` at ``as_of``."""
    iso = HUB_ISO[hub]
    s = _hub_series(prices_df, hub, as_of)
    if s.empty:
        return {k: None for k in ("last", "avg_30d", "p99_30d", "max_72h", "min_72h")} | {
            "spike_hours_72h": 0,
            "vol_z": 0.0,
        }
    ind = hub_indicators(s, iso)
    last = ind.iloc[-1]
    t_end = s.index[-1]
    w30 = s[s.index > t_end - pd.Timedelta(days=30)]
    return {
        "last": round(float(last["lmp"]), 2),
        "avg_30d": round(float(w30.mean()), 2),
        "p99_30d": round(float(w30.quantile(0.99)), 2),
        "max_72h": round(float(last["max72"]), 2),
        "min_72h": round(float(last["min72"]), 2),
        "spike_hours_72h": int(last["S72"]),
        "neg_hours_72h": int(last["N72"]),
        "vol_z": round(float(last["vol_z"]), 2),
    }


def _peak_ratio(regime: str, peak: float, neg_hours: int, last: pd.Series) -> tuple[float | None, str]:
    """X8 headline multiple. Spikes: peak ÷ baseline P99 (30 d before the 72 h
    window). Negative regime: |min| ÷ |baseline P1| when the baseline P1 is
    itself negative, otherwise the negative-hour count (basis ``neg_hours``)."""
    if regime == "negative_price":
        p1 = last.get("p1_base")
        if p1 is not None and not pd.isna(p1) and p1 < 0:
            return round(abs(peak) / abs(float(p1)), 2), "p1_30d"
        return float(neg_hours), "neg_hours"
    p99 = last.get("p99_base")
    if p99 is None or pd.isna(p99) or p99 <= 0:
        return None, "p99_30d"
    return round(peak / float(p99), 2), "p99_30d"


# ---------------------------------------------------------------------------
# Live triggers
# ---------------------------------------------------------------------------
def _forward_risk(forecasts_df: pd.DataFrame | None, hub: str, as_of: datetime) -> dict | None:
    if forecasts_df is None or forecasts_df.empty:
        return None
    f = forecasts_df[forecasts_df["hub"] == hub].copy()
    if f.empty:
        return None
    d0 = as_of.date() if isinstance(as_of, datetime) else as_of
    dates = pd.to_datetime(f["date"]).dt.date
    f = f[(dates >= d0) & (dates < d0 + timedelta(days=FORECAST_DAYS))]
    if f.empty:
        return None
    top = f.sort_values("forecast_peak_lmp", ascending=False).iloc[0]
    floor = ISO_FLOOR.get(HUB_ISO[hub], 250.0)
    return {
        "forward_risk": bool(top["forecast_peak_lmp"] >= floor),
        "forecast_peak_lmp": round(float(top["forecast_peak_lmp"]), 2),
        "forecast_date": pd.Timestamp(top["date"]).date().isoformat(),
    }


def detect_triggers(
    prices_df: pd.DataFrame,
    as_of: datetime = AS_OF,
    forecasts_df: pd.DataFrame | None = None,
    hubs: Iterable[str] | None = None,
) -> list[dict]:
    """Triggers firing at ``as_of`` (evaluated on the last hour < ``as_of``).

    Returns dicts sorted by severity desc with keys: trigger_id, hub, iso,
    regime, regime_label, severity, spike_hours, neg_hours, vol_z, peak_lmp,
    peak_ts, start_ts, end_ts, forward_risk, forecast_peak_lmp, forecast_date.
    ``peak_lmp`` is the most negative price for ``negative_price`` regimes.
    """
    as_of = pd.Timestamp(as_of).to_pydatetime()
    hubs = list(hubs) if hubs is not None else sorted(prices_df["hub"].unique())
    out: list[dict] = []
    for hub in hubs:
        iso = HUB_ISO[hub]
        s = _hub_series(prices_df, hub, as_of)
        if len(s) < 2:
            continue
        ind = hub_indicators(s, iso)
        last = ind.iloc[-1]
        T = ind.index[-1]
        S, N, z = int(last["S72"]), int(last["N72"]), float(last["vol_z"])
        fwd = _forward_risk(forecasts_df, hub, as_of) or {
            "forward_risk": False,
            "forecast_peak_lmp": None,
            "forecast_date": None,
        }
        floor = ISO_FLOOR.get(iso, 250.0)
        vol_fire = z >= VOL_Z_FIRE and float(last["max72"]) >= ELEVATED_MIN_FRAC * floor
        fires_realized = S >= SPIKE_MIN_HOURS or vol_fire or (iso in NEG_ISOS and N >= NEG_MIN_HOURS)
        if not (fires_realized or fwd["forward_risk"]):
            continue
        win = ind[ind.index > T - pd.Timedelta(hours=WINDOW_H)]
        if fires_realized:
            regime = _regime(iso, T.to_pydatetime(), S, N, z)
        else:
            regime = "winter_peak" if as_of.month in WINTER_MONTHS else "scarcity"
        if regime == "negative_price":
            ev = win[win["neg"] == 1]
            peak_ts = win["lmp"].idxmin()
            peak = float(win["lmp"].min())
        else:
            ev = win[win["spike"] == 1]
            peak_ts = win["lmp"].idxmax()
            peak = float(win["lmp"].max())
        if not ev.empty:
            start_ts, end_ts = ev.index[0], ev.index[-1]
        elif fires_realized:
            start_ts, end_ts = win.index[0], T
        else:  # forward-only trigger
            fd = pd.Timestamp(fwd["forecast_date"])
            start_ts, end_ts = fd, fd + pd.Timedelta(hours=23)
            peak = float(fwd["forecast_peak_lmp"])
            peak_ts = fd
        raw = float(last["raw"]) + (15.0 if fwd["forward_risk"] else 0.0)
        if not fires_realized:
            raw = 15.0 + 10.0 * math.log2(max(peak / floor, 1.0))
        peak_ratio, basis = _peak_ratio(regime, peak, N, last)
        out.append(
            {
                "trigger_id": trigger_id_for(iso, hub, start_ts),
                "event_id": event_id_for(iso, start_ts),
                "hub": hub,
                "iso": iso,
                "regime": regime,
                "regime_label": REGIME_LABELS[regime],
                "severity": float(_soft_severity(raw)),
                "peak_ratio": peak_ratio,
                "peak_ratio_basis": basis,
                "p99_30d": None if pd.isna(last["p99_base"]) else round(float(last["p99_base"]), 2),
                "spike_hours": S,
                "neg_hours": N,
                "vol_z": round(z, 2),
                "peak_lmp": round(peak, 2),
                "peak_ts": pd.Timestamp(peak_ts).to_pydatetime(),
                "start_ts": pd.Timestamp(start_ts).to_pydatetime(),
                "end_ts": pd.Timestamp(end_ts).to_pydatetime(),
                "forward_risk": bool(fwd["forward_risk"]),
                "forecast_peak_lmp": fwd["forecast_peak_lmp"],
                "forecast_date": fwd["forecast_date"],
            }
        )
    out.sort(key=lambda d: (-d["severity"], d["hub"]))
    return out


# ---------------------------------------------------------------------------
# Historical events (seed -> volatility_events)
# ---------------------------------------------------------------------------
def detect_historical_events(prices_df: pd.DataFrame, until: datetime | None = None) -> list[dict]:
    """Scan full history and return discrete events (realized spikes / negatives).

    Runs the live rule at every hour (excluding vol_z-only firings, which are
    too noisy to log as named events), merges firing runs separated by <= 24 h
    and summarises each run. ``trigger_id`` matches what :func:`detect_triggers`
    would emit for the same event.
    """
    events: list[dict] = []
    for hub in sorted(prices_df["hub"].unique()):
        iso = HUB_ISO[hub]
        s = _hub_series(prices_df, hub, until)
        if s.empty:
            continue
        ind = hub_indicators(s, iso)
        fire = ind["S72"] >= SPIKE_MIN_HOURS
        if iso in NEG_ISOS:
            fire = fire | (ind["N72"] >= NEG_MIN_HOURS)
        fire_ts = ind.index[fire.to_numpy()]
        if len(fire_ts) == 0:
            continue
        runs: list[list[pd.Timestamp]] = [[fire_ts[0], fire_ts[0]]]
        for ts in fire_ts[1:]:
            if ts - runs[-1][1] <= pd.Timedelta(hours=MERGE_GAP_H):
                runs[-1][1] = ts
            else:
                runs.append([ts, ts])
        for r0, r1 in runs:
            win = ind[(ind.index > r0 - pd.Timedelta(hours=WINDOW_H)) & (ind.index <= r1)]
            run = ind[(ind.index >= r0) & (ind.index <= r1)]
            S_max = int(run["S72"].max())
            N_max = int(run["N72"].max())
            regime = _regime(iso, r0.to_pydatetime(), S_max, N_max, 0.0)
            if regime == "negative_price":
                ev = win[win["neg"] == 1]
                peak = float(win["lmp"].min())
                hours = int(len(ev))
            else:
                ev = win[win["spike"] == 1]
                peak = float(win["lmp"].max())
                hours = int(len(ev))
            if ev.empty:
                continue
            start_ts = ev.index[0].to_pydatetime()
            events.append(
                {
                    "trigger_id": trigger_id_for(iso, hub, start_ts),
                    "event_id": event_id_for(iso, start_ts),
                    "hub": hub,
                    "iso": iso,
                    "start_ts": start_ts,
                    "end_ts": ev.index[-1].to_pydatetime(),
                    "regime": regime,
                    "peak_lmp": round(peak, 2),
                    "spike_hours": hours,
                    "severity": float(run["severity"].max()),
                }
            )
    events.sort(key=lambda e: (e["start_ts"], e["hub"]))
    # De-duplicate ids (two runs starting the same day on one hub).
    seen: set[str] = set()
    unique = []
    for e in events:
        if e["trigger_id"] in seen:
            continue
        seen.add(e["trigger_id"])
        unique.append(e)
    return unique


# ---------------------------------------------------------------------------
# Exposure (D6)
# ---------------------------------------------------------------------------
def exposure_direction(segment: str, regime: str, is_liquidity_partner: bool = False) -> str:
    """'hurt' (short the move) or 'opportunity' (long the move)."""
    if is_liquidity_partner:
        return "opportunity"
    if regime == "negative_price":
        return "hurt" if segment in _HURT_ON_NEGATIVE else "opportunity"
    return "hurt" if segment in _HURT_ON_SPIKE else "opportunity"


# Neutral exposure descriptions (no advice, no promissory verbs). Checked against
# content/compliance_rules.json banned + caution phrases in tests/test_volatility.py.
_LINES: dict[tuple[str, str], str] = {
    ("REP", "hurt"): "Serves fixed-price retail load settled at {hub}; {regime_lc} hours raise the real-time cost of serving that load.",
    ("CI_LOAD", "hurt"): "Index-priced industrial load at {hub}; {regime_lc} hours feed directly into its monthly power bill.",
    ("DATACENTER", "hurt"): "Flat 24x7 data-center load priced off {hub}; it cannot curtail, so {regime_lc} hours pass straight through to its power cost.",
    ("UTILITY", "hurt"): "Load-serving obligation in {iso} with purchases indexed to {hub}; {regime_lc} raises its replacement-power cost.",
    ("STORAGE", "opportunity"): "Battery fleet whose revenue depends on {hub} price swings; {regime_lc} widens the intraday price range it operates in.",
    ("PROP", "opportunity"): "Trades {iso} power volatility; {regime_lc} at {hub} moves the short-dated prices its desk follows.",
    ("FUND", "opportunity"): "Runs power-price strategies in {iso}; {regime_lc} at {hub} changes the volatility its book is positioned around.",
    ("IPP", "opportunity"): "Merchant generation selling at {hub}; {regime_lc} raises its realized price and the variability of its revenue.",
    ("IPP", "hurt"): "Solar output settling at {hub}; negative midday prices and the evening ramp affect its realized revenue and curtailment.",
    ("STORAGE", "opportunity_neg"): "Battery fleet at {hub}; negative midday prices and the evening ramp widen its charge-to-discharge price range.",
    ("REP", "opportunity"): "Retail load settled at {hub}; negative midday prices and the evening ramp change the shape of its purchase costs.",
    ("CI_LOAD", "opportunity"): "Flexible industrial load at {hub}; negative-price hours and the evening ramp change its hourly cost profile.",
    ("DATACENTER", "opportunity"): "Round-the-clock load at {hub}; negative midday prices and the evening ramp change its hourly cost profile.",
    ("UTILITY", "opportunity"): "Load-serving utility in {iso}; negative prices at {hub} and the evening ramp change its purchase-cost profile.",
}
_LP_LINE = "Liquidity partner quoting {hub}; {regime_lc} changes its quoting obligations and order flow."
_DEFAULT_LINE = "Has physical or financial exposure to {hub} in {iso}; {regime_lc} moves the value of that position."


def exposure_line(segment: str, hub: str, regime: str, is_liquidity_partner: bool = False) -> str:
    """One plain-English sentence on *why* this account is exposed (no prices)."""
    iso = HUB_ISO.get(hub, "")
    if is_liquidity_partner:
        return _LP_LINE.format(hub=hub, regime_lc=REGIME_LABELS.get(regime, regime).lower())
    direction = exposure_direction(segment, regime)
    key = (segment, direction)
    if regime == "negative_price" and segment == "STORAGE":
        key = ("STORAGE", "opportunity_neg")
    tmpl = _LINES.get(key) or _DEFAULT_LINE
    return tmpl.format(hub=hub, iso=iso, regime_lc=REGIME_LABELS.get(regime, regime).lower())


def is_exposed(exposure_isos: str | Iterable[str], iso: str) -> bool:
    isos = exposure_isos.split(",") if isinstance(exposure_isos, str) else list(exposure_isos)
    return iso in {i.strip() for i in isos}


HUB_MISMATCH_FACTOR = 0.6  # X6: exposed via ISO only (not the account's own hub)


def exposure_score(segment: str, size_mw: float, severity: float, hub_match: bool = True) -> float:
    """0–100. ``severity × segment sensitivity × size factor``, × 0.6 when the
    account is exposed to the trigger's ISO but its own hub is a different hub
    (v1.1 X6; v1 used × 1.2 for a hub match). Size factor = 0.5 + 0.25·log10(MW)."""
    size_factor = 0.5 + 0.25 * math.log10(max(float(size_mw), 1.0))
    score = severity * SEGMENT_SENSITIVITY.get(segment, 0.5) * size_factor * (1.0 if hub_match else HUB_MISMATCH_FACTOR)
    return round(min(100.0, score), 1)


def exposure_table(accounts: pd.DataFrame, trigger: dict) -> pd.DataFrame:
    """Accounts exposed to one trigger (X6): own hub == trigger hub → ``hub_match``
    True (full score); trigger ISO in ``exposure_isos`` otherwise → False (× 0.6).
    Accounts without the ISO are never returned. Columns: account_id, hub (the
    account's own), hub_match, exposure_score, direction, exposure_line."""
    iso, hub = trigger["iso"], trigger["hub"]
    exp = accounts[accounts["exposure_isos"].fillna("").map(lambda c: is_exposed(c, iso))]
    rows = []
    for r in exp.itertuples(index=False):
        match = r.hub == hub
        lp = bool(getattr(r, "is_liquidity_partner", False))
        rows.append({
            "account_id": int(r.id), "hub": r.hub, "hub_match": bool(match),
            "exposure_score": exposure_score(r.segment, r.size_mw, trigger["severity"], hub_match=match),
            "direction": exposure_direction(r.segment, trigger["regime"], lp),
            "exposure_line": exposure_line(r.segment, r.hub, trigger["regime"], lp),
        })
    cols = ["account_id", "hub", "hub_match", "exposure_score", "direction", "exposure_line"]
    return pd.DataFrame(rows, columns=cols)


def event_exposure(accounts: pd.DataFrame, triggers: list[dict]) -> pd.DataFrame:
    """Distinct accounts per ``event_id`` (no double count across hubs): one row
    per (event_id, account_id) keeping the best-scoring hub's row."""
    parts = []
    for t in triggers:
        tab = exposure_table(accounts, t)
        if not tab.empty:
            parts.append(tab.assign(event_id=t.get("event_id") or event_id_for(t["iso"], t["start_ts"]),
                                    trigger_id=t["trigger_id"]))
    if not parts:
        return pd.DataFrame(columns=["event_id", "account_id", "trigger_id", "hub", "hub_match", "exposure_score",
                                     "direction", "exposure_line"])
    allx = pd.concat(parts, ignore_index=True).sort_values(["event_id", "account_id", "exposure_score"],
                                                            ascending=[True, True, False])
    return allx.drop_duplicates(["event_id", "account_id"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Triggered-outreach lift (Pulse history)
# ---------------------------------------------------------------------------
LIFT_WINDOW_D = 14


def trigger_cohort_lift(
    accounts: pd.DataFrame,
    activities: pd.DataFrame,
    trades: pd.DataFrame,
    events: pd.DataFrame,
    as_of: datetime = AS_OF,
) -> dict:
    """Past triggered vs untriggered 14-day activation.

    Cohort per historical event = non-LP accounts exposed to the event ISO that
    were funded-not-trading at ``start_ts`` (funded before, no trade before),
    for events whose 14-day window closed before ``as_of``. *Triggered* = got a
    ``triggered_email`` carrying that ``trigger_id``. *Activated* = first trade
    within 14 days of ``start_ts``. One row per (account, ISO-day) cohort;
    accounts still inside a previous sequence's 14-day window are excluded.
    """
    if events.empty:
        return {"triggered": {"n": 0, "activated_14d_rate": 0.0}, "untriggered": {"n": 0, "activated_14d_rate": 0.0}, "lift_x": None}
    acc = accounts[~accounts["is_liquidity_partner"].astype(bool)]
    first_trade = trades.groupby("account_id")["ts"].min()
    trig = activities[(activities["kind"] == "triggered_email") & activities["trigger_id"].notna()]
    trig_pairs = set(zip(trig["account_id"], trig["trigger_id"]))
    trig_by_acc: dict[int, list[str]] = {}
    for a, t in trig_pairs:
        trig_by_acc.setdefault(int(a), []).append(t)
    trig_ts = trig.groupby("account_id")["ts"].apply(lambda s: sorted(pd.to_datetime(s))).to_dict()
    rows = []
    seen = set()
    ev = events.sort_values(["start_ts", "severity"], ascending=[True, False])
    for e in ev.itertuples(index=False):
        start = pd.Timestamp(e.start_ts)
        if start + pd.Timedelta(days=LIFT_WINDOW_D) > pd.Timestamp(as_of):
            continue
        day_key = (e.iso, start.date())
        exposed = acc[acc["exposure_isos"].fillna("").str.contains(e.iso, regex=False)]
        funded = exposed["funded_at"].notna() & (exposed["funded_at"] < start)
        exposed = exposed[funded]
        for a in exposed.itertuples(index=False):
            ft = first_trade.get(a.id)
            if ft is not None and pd.Timestamp(ft) < start:
                continue
            key = (a.id, day_key)
            if key in seen:
                continue
            seen.add(key)
            # in cooldown from an earlier sequence -> not a clean comparison
            prior = [x for x in trig_ts.get(a.id, []) if start - pd.Timedelta(days=LIFT_WINDOW_D) <= x < start]
            if prior:
                continue
            same_day_ids = [t for t in trig_by_acc.get(int(a.id), []) if t.startswith(e.iso + "-") and t.endswith(f"{start:%Y%m%d}")]
            activated = ft is not None and pd.Timestamp(ft) <= start + pd.Timedelta(days=LIFT_WINDOW_D)
            rows.append((bool(same_day_ids), bool(activated)))
    if not rows:
        return {"triggered": {"n": 0, "activated_14d_rate": 0.0}, "untriggered": {"n": 0, "activated_14d_rate": 0.0}, "lift_x": None}
    arr = np.array(rows, dtype=bool)
    t_mask = arr[:, 0]
    nt, nu = int(t_mask.sum()), int((~t_mask).sum())
    rt = float(arr[t_mask, 1].mean()) if nt else 0.0
    ru = float(arr[~t_mask, 1].mean()) if nu else 0.0
    return {
        "triggered": {"n": nt, "activated_14d_rate": round(rt, 4)},
        "untriggered": {"n": nu, "activated_14d_rate": round(ru, 4)},
        "lift_x": round(rt / ru, 2) if ru > 0 else None,
    }
