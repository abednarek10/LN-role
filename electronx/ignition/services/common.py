"""Shared helpers for Engineering services: content loading, JSON-safe values,
and the per-account "context" table every view reads.

Services are pure: DataFrames in, dicts out. No Session here.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd

from .. import definitions as D
from ..config import CONTENT_DIR

AS_OF_TS = pd.Timestamp(D.AS_OF)
TOUCH_KINDS = frozenset({"email", "call", "meeting", "demo", "linkedin", "triggered_email", "walkthrough", "qbr"})


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------
@lru_cache(maxsize=None)
def content(name: str):
    """Parsed ``ignition/content/<name>.json`` (cached; treat as read-only)."""
    return json.loads((CONTENT_DIR / f"{name}.json").read_text())


# ---------------------------------------------------------------------------
# JSON-safe scalars
# ---------------------------------------------------------------------------
def num(v, nd: int | None = 4):
    """Float rounded, NaN/inf/None -> None."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, nd) if nd is not None else f


def as_int(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return int(v)


def ts_str(v) -> str | None:
    """Naive UTC ISO string ``YYYY-MM-DDTHH:MM:SS`` (contract note #11)."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return pd.Timestamp(v).strftime("%Y-%m-%dT%H:%M:%S")


def date_str(v) -> str | None:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return pd.Timestamp(v).date().isoformat()


def days_between(later, earlier) -> float | None:
    if earlier is None or later is None:
        return None
    try:
        if pd.isna(earlier) or pd.isna(later):
            return None
    except (TypeError, ValueError):
        pass
    return (pd.Timestamp(later) - pd.Timestamp(earlier)).total_seconds() / 86400.0


def fmt_price(v: float) -> str:
    """$4,800 / $36.47 / -$16.83 — whole dollars at or above $100."""
    a = abs(float(v))
    s = f"${a:,.0f}" if a >= 100 else f"${a:,.2f}"
    return ("-" if v < 0 else "") + s


def fmt_date_long(v) -> str:
    d = pd.Timestamp(v)
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def to_date(v) -> date:
    return pd.Timestamp(v).date()


# ---------------------------------------------------------------------------
# Expected ADV (CRO §2 segment prior, updated with sizing data)
# ---------------------------------------------------------------------------
def expected_adv(accounts: pd.DataFrame) -> pd.Series:
    """E[ADV] contracts/day once active: segment prior × size factor.

    size factor = clip((size_mw / segment median size)^0.25, 0.7, 1.5) — the
    "updated with sizing data from discovery" adjustment (CRO memo §2).
    """
    prior = accounts["segment"].map(D.EXPECTED_ADV_PRIOR).astype(float)
    med = accounts.groupby("segment")["size_mw"].transform("median").astype(float)
    ratio = (accounts["size_mw"].astype(float) / med.replace(0, np.nan)).fillna(1.0)
    factor = np.clip(ratio ** 0.25, 0.7, 1.5)
    out = (prior * factor).round(1)
    out.index = accounts["id"].to_numpy()
    return out


# ---------------------------------------------------------------------------
# Account context table (one row per account, everything "as of AS_OF")
# ---------------------------------------------------------------------------
def build_account_table(frames, scores: pd.DataFrame | None, health: pd.DataFrame, t=D.AS_OF) -> pd.DataFrame:
    """Per-account derived facts at ``t`` used by queue, pulse, CEO and 360.

    Index = account id. Activities with ``ts <= t`` count as touches (a touch
    queued "now" is stamped ``AS_OF`` and must register as last_touch_days 0).
    """
    t = pd.Timestamp(t)
    acc = frames.accounts.copy().set_index("id", drop=False)
    acc["side"] = [D.segment_side(s, bool(lp)) for s, lp in zip(acc["segment"], acc["is_liquidity_partner"])]
    acc["isos"] = acc["exposure_isos"].map(D.parse_isos)
    acc["exp_adv"] = expected_adv(frames.accounts)

    if scores is not None and len(scores):
        sc = scores.set_index("account_id")
        acc["p_active"] = sc["p_active"].reindex(acc.index)
        acc["reasons"] = sc["reasons"].reindex(acc.index)
        acc["already_active"] = sc["already_active"].reindex(acc.index)
    else:
        acc["p_active"] = np.nan
        acc["reasons"] = None
        acc["already_active"] = False
    acc["reasons"] = acc["reasons"].map(lambda r: r if isinstance(r, list) else [])

    h = health.reindex(acc.index)
    for c in ("trading_days_30", "adv_30d", "adv_prior_30d", "ever_traded", "first_active_at", "state"):
        acc[c] = h[c]
    acc["trading_days_30"] = acc["trading_days_30"].fillna(0).astype(int)

    tr = frames.trades[frames.trades["ts"] < t]
    days = tr.assign(d=tr["ts"].dt.normalize())
    prior = days[(days["ts"] >= t - pd.Timedelta(days=60)) & (days["ts"] < t - pd.Timedelta(days=30))]
    acc["td_prior30"] = prior.groupby("account_id")["d"].nunique().reindex(acc.index).fillna(0).astype(int)
    acc["trade_days_total"] = days.groupby("account_id")["d"].nunique().reindex(acc.index).fillna(0).astype(int)
    acc["last_trade_ts"] = tr.groupby("account_id")["ts"].max().reindex(acc.index)
    d0, d1 = D.adv_window(t.date())
    win = tr[(tr["ts"].dt.date >= d0) & (tr["ts"].dt.date <= d1)]
    acc["adv_20td"] = (win.groupby("account_id")["contracts"].sum() / D.ADV_WINDOW_TD).reindex(acc.index).fillna(0.0)
    recent = tr[tr["ts"] >= t - pd.Timedelta(days=90)]
    acc["isos_traded_90d"] = recent.groupby("account_id")["iso"].agg(lambda s: sorted(set(s))).reindex(acc.index)
    acc["tenors_traded_90d"] = recent.groupby("account_id")["tenor"].agg(lambda s: sorted(set(s))).reindex(acc.index)
    for c in ("isos_traded_90d", "tenors_traded_90d"):
        acc[c] = acc[c].map(lambda v: v if isinstance(v, list) else [])

    ob = frames.onboarding_events[frames.onboarding_events["ts"] < t]
    first = ob.groupby(["account_id", "step"])["ts"].min().unstack()
    for step in ("kyc_submitted", "api_key_created", "first_login", "bank_linked", "first_order"):
        acc[f"ob_{step}"] = first[step].reindex(acc.index) if step in first.columns else pd.NaT
    acc["last_kyc_event"] = (
        ob[ob["step"].isin(["kyc_submitted", "kyc_info_requested"])].groupby("account_id")["ts"].max().reindex(acc.index)
    )

    ac = frames.activities[frames.activities["ts"] <= t]
    touch = ac[ac["kind"].isin(TOUCH_KINDS)]
    acc["last_touch_ts"] = touch.groupby("account_id")["ts"].max().reindex(acc.index)
    acc["n_touches"] = touch.groupby("account_id").size().reindex(acc.index).fillna(0).astype(int)
    trig = ac[ac["kind"] == "triggered_email"]
    acc["last_trig_ts"] = trig.groupby("account_id")["ts"].max().reindex(acc.index)
    acc["last_qbr_ts"] = ac[ac["kind"] == "qbr"].groupby("account_id")["ts"].max().reindex(acc.index)
    meet = ac[ac["kind"].isin(["meeting", "demo"])]
    acc["first_meeting_ts"] = meet.groupby("account_id")["ts"].min().reindex(acc.index)
    ltd = (t - acc["last_touch_ts"]).dt.total_seconds() / 86400.0
    acc["last_touch_days"] = np.floor(ltd)

    reps = frames.reps.set_index("id")["name"]
    names = [reps.get(int(r)) if pd.notna(r) else None for r in acc["rep_id"]]
    acc["rep_name"] = pd.Series(names, index=acc.index, dtype=object)

    acc["stage_entry_ts"] = [_stage_entry(r, days, t) for r in acc.itertuples(index=False)]
    acc["days_in_stage"] = np.floor((t - pd.to_datetime(acc["stage_entry_ts"])).dt.total_seconds() / 86400.0).clip(lower=0)
    return acc


def _stage_entry(r, days: pd.DataFrame, t: pd.Timestamp):
    st = r.stage
    if st == "TARGET":
        return r.created_at
    if st == "QUALIFIED":
        return r.first_meeting_ts if pd.notna(r.first_meeting_ts) else r.created_at
    if st == "SIGNED":
        return r.signed_at
    if st == "KYC_APPROVED":
        return r.kyc_approved_at
    if st == "FUNDED":
        return r.funded_at
    if st == "FIRST_TRADE":
        return r.first_trade_at
    if st in ("ACTIVE", "EXPANDING"):
        return r.active_since if pd.notna(r.active_since) else r.first_trade_at
    if st == "AT_RISK":
        # the trailing-30 window lost its 4th trading day: (4th most recent day) + 30 d
        ds = days.loc[days["account_id"] == r.id, "d"].drop_duplicates().sort_values(ascending=False)
        if len(ds) >= D.ACTIVE_MIN_DAYS:
            return min(ds.iloc[D.ACTIVE_MIN_DAYS - 1] + pd.Timedelta(days=D.ACTIVE_LOOKBACK_D), t)
        return r.first_trade_at
    if st == "DORMANT":
        return min(r.last_trade_ts + pd.Timedelta(days=D.ACTIVE_LOOKBACK_D), t) if pd.notna(r.last_trade_ts) else r.funded_at
    return r.created_at


def week_fridays(end: date, n: int) -> list[date]:
    """The ``n`` Fridays ending at ``end`` (oldest first)."""
    out, d = [], end
    while len(out) < n:
        out.append(d)
        d = d - timedelta(days=7)
    return out[::-1]


def snap_friday(d: date) -> date:
    """Most recent Friday on or before ``d``."""
    return d - timedelta(days=(d.weekday() - 4) % 7)


def first_friday_after(d: date | datetime) -> date:
    d = pd.Timestamp(d).date()
    return d + timedelta(days=(4 - d.weekday()) % 7)
