"""Point-in-time features and account health — leakage-safe by construction.

``features_as_of(frames, t)`` reads only:

* static account attributes known at signing (segment, ISO, hub, size, tier,
  lead source, other-exchange flag, redlines) and contacts;
* ``onboarding_events``, ``activities``, ``trades`` and ``market_prices`` rows
  with ``ts < t``.

It never reads ``accounts.stage``/``*_at`` columns or ``latent_propensity``, so
deleting every row with ``ts >= t`` leaves the output unchanged (tested).
"""
from __future__ import annotations


import numpy as np
import pandas as pd

from .. import definitions as D

STATIC_FEATURES = (
    [f"seg_{s}" for s in D.SEGMENT_CODES]
    + [f"iso_{i}" for i in D.ISO_CODES]
    + [
        "log_size_mw",
        "tier_a",
        "lead_partner",
        "lead_inbound",
        "lead_paid_social",
        "other_exchange",
        "kyc_redlines",
        "n_contacts",
        "has_champion",
        "has_trader_or_risk",
    ]
)
DYNAMIC_FEATURES = [
    "days_since_signed",
    "steps_completed",
    "kyc_approved",
    "funded",
    "traded",
    "days_in_step",
    "first_login_lag",
    "kyc_info_requests",
    "api_key",
    "ticket_opened",
    "order_rejected",
    "days_funded_no_trade",
    "trading_days_30",
    "touches_14d",
    "touches_30d",
    "meetings",
    "demo",
    "no_shows",
    "reply_rate",
    "days_since_reply",
    "walkthrough",
    "triggered_14d",
    "webinar",
    "hub_vol_30d",
]
FEATURES: list[str] = STATIC_FEATURES + DYNAMIC_FEATURES
# v1.1 (X11): the served propensity model excludes days_funded_no_trade. It is not
# leakage (deletion tests pass; its within-state effect is negative), but coded 0
# outside "funded, not traded" it absorbs that state's base rate under L2 and showed
# a misleading positive weight. It stays in the feature matrix for display/rules.
MODEL_FEATURES: list[str] = [f for f in FEATURES if f != "days_funded_no_trade"]

_LEAD_PARTNER = {"Partner Referrals", "Liquidity Partner Intros"}
_LEAD_INBOUND = {"Industry Conferences", "Webinars & Education", "Content & SEO"}
_OUTBOUND_KINDS = {"email", "call", "linkedin", "triggered_email"}
_TOUCH_KINDS = {"email", "call", "meeting", "demo", "linkedin", "triggered_email", "walkthrough", "qbr"}


def _ts(t) -> pd.Timestamp:
    return pd.Timestamp(t)


def _days(delta: pd.Series) -> pd.Series:
    return delta.dt.total_seconds() / 86400.0


def static_features(frames, account_ids=None) -> pd.DataFrame:
    acc = frames.accounts.set_index("id")
    if account_ids is not None:
        acc = acc.loc[list(account_ids)]
    X = pd.DataFrame(index=acc.index)
    X.index.name = "account_id"
    for s in D.SEGMENT_CODES:
        X[f"seg_{s}"] = (acc["segment"] == s).astype(float)
    for i in D.ISO_CODES:
        X[f"iso_{i}"] = (acc["primary_iso"] == i).astype(float)
    X["log_size_mw"] = np.log1p(acc["size_mw"].astype(float))
    X["tier_a"] = (acc["tam_tier"] == "A").astype(float)
    X["lead_partner"] = acc["lead_source"].isin(_LEAD_PARTNER).astype(float)
    X["lead_inbound"] = acc["lead_source"].isin(_LEAD_INBOUND).astype(float)
    X["lead_paid_social"] = (acc["lead_source"] == "LinkedIn Paid").astype(float)
    X["other_exchange"] = acc["has_other_exchange_account"].astype(float)
    X["kyc_redlines"] = acc["kyc_redlines"].astype(float)
    c = frames.contacts
    grp = c.groupby("account_id")
    X["n_contacts"] = grp.size().reindex(X.index).fillna(0).astype(float)
    X["has_champion"] = grp["is_champion"].any().reindex(X.index).fillna(False).astype(float)
    tr_risk = c[c["persona"].isin(["TRADER", "RISK"])].groupby("account_id").size()
    X["has_trader_or_risk"] = (tr_risk.reindex(X.index).fillna(0) > 0).astype(float)
    return X


def _hub_vol(prices: pd.DataFrame, t: pd.Timestamp) -> pd.Series:
    w = prices[(prices["ts"] < t) & (prices["ts"] >= t - pd.Timedelta(days=30))]
    if w.empty:
        return pd.Series(dtype=float)
    w = w.sort_values(["hub", "ts"])
    x = np.arcsinh(w["lmp"].to_numpy() / 10.0)
    d = pd.Series(x, index=w.index).groupby(w["hub"].to_numpy()).diff()
    return d.groupby(w["hub"].to_numpy()).std()


def features_as_of(frames, t, account_ids=None) -> pd.DataFrame:
    """Feature matrix (index ``account_id``, columns :data:`FEATURES`) at time ``t``.

    Strictly uses event rows with ``ts < t``.
    """
    t = _ts(t)
    X = static_features(frames, account_ids)
    ids = X.index

    # --- onboarding -------------------------------------------------------
    ob = frames.onboarding_events
    ob = ob[(ob["ts"] < t) & ob["account_id"].isin(ids)]
    first = ob.groupby(["account_id", "step"])["ts"].min().unstack()
    first = first.reindex(index=ids, columns=D.ONBOARDING_STEPS)
    signed = first["contract_signed"]
    is_signed = signed.notna()
    X["days_since_signed"] = _days(t - signed).fillna(0).clip(0, 365)
    X["steps_completed"] = first[D.MAIN_PATH_STEPS].notna().sum(axis=1).astype(float)
    X["kyc_approved"] = first["kyc_approved"].notna().astype(float)
    X["funded"] = first["funded"].notna().astype(float)
    X["traded"] = first["first_trade"].notna().astype(float)
    last_ob = ob.groupby("account_id")["ts"].max().reindex(ids)
    created = frames.accounts.set_index("id").loc[ids, "created_at"]
    last_ob = last_ob.fillna(created.where(created < t))  # pre-sign: time in pipeline
    # v1.1: pre-funding stall only (0 once funded) — post-funding dwell lives in
    # days_funded_no_trade, which is collinear with this column (r≈0.98) otherwise.
    X["days_in_step"] = _days(t - last_ob).where(first["funded"].isna(), 0).fillna(0).clip(0, 180)
    login_lag = _days(first["first_login"] - signed)
    waiting = _days(t - signed)
    X["first_login_lag"] = login_lag.fillna(waiting).where(is_signed, 0).fillna(0).clip(0, 60)
    X["kyc_info_requests"] = (
        ob[ob["step"] == "kyc_info_requested"].groupby("account_id").size().reindex(ids).fillna(0).astype(float)
    )
    X["api_key"] = first["api_key_created"].notna().astype(float)
    X["ticket_opened"] = first["order_ticket_opened"].notna().astype(float)
    X["order_rejected"] = first["order_rejected"].notna().astype(float)
    fnt = _days(t - first["funded"]).where(first["first_trade"].isna(), 0)
    X["days_funded_no_trade"] = fnt.fillna(0).clip(0, 180)

    # --- trades -----------------------------------------------------------
    tr = frames.trades
    tr = tr[(tr["ts"] < t) & (tr["ts"] >= t - pd.Timedelta(days=D.ACTIVE_LOOKBACK_D)) & tr["account_id"].isin(ids)]
    X["trading_days_30"] = (
        tr.assign(d=tr["ts"].dt.normalize()).groupby("account_id")["d"].nunique().reindex(ids).fillna(0).astype(float)
    )

    # --- activities -------------------------------------------------------
    ac = frames.activities
    ac = ac[(ac["ts"] < t) & ac["account_id"].isin(ids)]
    touch = ac[ac["kind"].isin(_TOUCH_KINDS)]
    X["touches_14d"] = touch[touch["ts"] >= t - pd.Timedelta(days=14)].groupby("account_id").size().reindex(ids).fillna(0).astype(float)
    X["touches_30d"] = touch[touch["ts"] >= t - pd.Timedelta(days=30)].groupby("account_id").size().reindex(ids).fillna(0).astype(float)
    held = ac[ac["kind"].isin(["meeting", "demo"]) & (ac["outcome"] != "no_show")]
    X["meetings"] = held.groupby("account_id").size().reindex(ids).fillna(0).astype(float)
    X["demo"] = (ac[ac["kind"] == "demo"].groupby("account_id").size().reindex(ids).fillna(0) > 0).astype(float)
    X["no_shows"] = ac[ac["outcome"] == "no_show"].groupby("account_id").size().reindex(ids).fillna(0).astype(float)
    out = ac[ac["kind"].isin(_OUTBOUND_KINDS)]
    n_out = out.groupby("account_id").size().reindex(ids).fillna(0)
    n_rep = out[out["outcome"].isin(["reply", "meeting_booked"])].groupby("account_id").size().reindex(ids).fillna(0)
    X["reply_rate"] = ((n_rep + 1.0) / (n_out + 4.0)).astype(float)
    last_reply = ac[ac["outcome"].isin(["reply", "meeting_booked"])].groupby("account_id")["ts"].max().reindex(ids)
    X["days_since_reply"] = _days(t - last_reply).fillna(120).clip(0, 120)
    X["walkthrough"] = (ac[ac["kind"] == "walkthrough"].groupby("account_id").size().reindex(ids).fillna(0) > 0).astype(float)
    trig = ac[(ac["kind"] == "triggered_email") & (ac["ts"] >= t - pd.Timedelta(days=14))]
    X["triggered_14d"] = (trig.groupby("account_id").size().reindex(ids).fillna(0) > 0).astype(float)
    X["webinar"] = (ac[ac["kind"] == "webinar"].groupby("account_id").size().reindex(ids).fillna(0) > 0).astype(float)

    # --- market -----------------------------------------------------------
    vol = _hub_vol(frames.market_prices, t)
    hubs = frames.accounts.set_index("id").loc[ids, "hub"]
    X["hub_vol_30d"] = hubs.map(vol).fillna(0.0).astype(float).to_numpy()

    return X[FEATURES].astype(float)


# ---------------------------------------------------------------------------
# Activity / health
# ---------------------------------------------------------------------------
def trading_days(trades: pd.DataFrame, t, lookback_days: int = D.ACTIVE_LOOKBACK_D) -> pd.Series:
    """Distinct trading days per account in ``[t - lookback, t)``."""
    t = _ts(t)
    w = trades[(trades["ts"] < t) & (trades["ts"] >= t - pd.Timedelta(days=lookback_days))]
    return w.assign(d=w["ts"].dt.normalize()).groupby("account_id")["d"].nunique()


def first_active_at(trades: pd.DataFrame) -> pd.Series:
    """Timestamp each account first became Active (≥4 distinct days within 30).

    The account becomes Active on the day of its 4th distinct trading day that
    falls within ``ACTIVE_LOOKBACK_D`` days of the 1st of those four; the value
    is the first trade timestamp on that day.
    """
    if trades.empty:
        return pd.Series(dtype="datetime64[ns]")
    day_first = trades.assign(d=trades["ts"].dt.normalize()).groupby(["account_id", "d"])["ts"].min().reset_index()
    day_first = day_first.sort_values(["account_id", "d"])
    k = D.ACTIVE_MIN_DAYS - 1
    prev = day_first.groupby("account_id")["d"].shift(k)
    ok = (day_first["d"] - prev) <= pd.Timedelta(days=D.ACTIVE_LOOKBACK_D - 1)
    hits = day_first[ok.fillna(False)]
    return hits.groupby("account_id")["ts"].min()


def activation_labels(frames, t, horizon_days: int = D.ACTIVATION_WINDOW_D, account_ids=None) -> pd.Series:
    """1 if the account first becomes Active in ``(t, t + horizon]``."""
    t = _ts(t)
    fa = first_active_at(frames.trades)
    ids = frames.accounts["id"] if account_ids is None else pd.Index(account_ids)
    fa = fa.reindex(ids)
    lab = (fa > t) & (fa <= t + pd.Timedelta(days=horizon_days))
    lab.index.name = "account_id"
    return lab.astype(int)


def account_health(frames, t=D.AS_OF) -> pd.DataFrame:
    """Per-account activity snapshot at ``t`` (index ``account_id``).

    Columns: trading_days_30, contracts_30d, adv_30d (contracts / weekdays in
    window), adv_prior_30d, ever_traded, first_active_at,
    ``health_state`` / ``health_label`` / ``days_funded`` / ``days_since_first_trade``
    (v1.1 X2 vocabulary — use these), and legacy ``state``
    (active|at_risk|dormant|not_funded|funded_new, the v1 D2 literal; deprecated).
    """
    t = _ts(t)
    acc = frames.accounts.set_index("id")
    tr = frames.trades[frames.trades["ts"] < t]
    lo = t - pd.Timedelta(days=30)
    lo2 = t - pd.Timedelta(days=60)
    wd = np.busday_count(lo.date(), t.date())
    out = pd.DataFrame(index=acc.index)
    out.index.name = "account_id"
    out["trading_days_30"] = trading_days(tr, t).reindex(acc.index).fillna(0).astype(int)
    c30 = tr[tr["ts"] >= lo].groupby("account_id")["contracts"].sum()
    c60 = tr[(tr["ts"] >= lo2) & (tr["ts"] < lo)].groupby("account_id")["contracts"].sum()
    out["contracts_30d"] = c30.reindex(acc.index).fillna(0).astype(int)
    out["adv_30d"] = (out["contracts_30d"] / max(wd, 1)).round(1)
    out["adv_prior_30d"] = (c60.reindex(acc.index).fillna(0) / max(wd, 1)).round(1)
    out["ever_traded"] = tr.groupby("account_id").size().reindex(acc.index).fillna(0) > 0
    out["first_active_at"] = first_active_at(tr).reindex(acc.index)
    funded_at = acc["funded_at"]
    state = np.where(out["trading_days_30"] >= D.ACTIVE_MIN_DAYS, "active",
                     np.where(out["trading_days_30"] >= D.AT_RISK_DAYS[0], "at_risk", "dormant"))
    state = pd.Series(state, index=acc.index)
    funded_mask = funded_at.notna() & (funded_at < t)
    young = funded_mask & (funded_at > t - pd.Timedelta(days=D.DORMANT_MIN_FUNDED_D)) & (state == "dormant")
    state = state.where(funded_mask | (out["trading_days_30"] > 0), "not_funded")
    state = state.where(~young, "funded_new")
    out["state"] = state  # legacy (v1) vocabulary — prefer health_state
    hs = health_state(frames, t, _trading_days_30=out["trading_days_30"])
    for c in ("health_state", "health_label", "days_funded", "days_since_first_trade"):
        out[c] = hs[c]
    return out


def health_state(frames, t=D.AS_OF, account_ids=None, _trading_days_30: pd.Series | None = None) -> pd.DataFrame:
    """X2 health state per account at ``t`` (index ``account_id``).

    Columns: ``health_state`` (``definitions.HEALTH_STATES``), ``health_label``
    (display text, e.g. "No trades yet · funded 34 d"), ``days_funded``,
    ``days_since_first_trade``, ``trading_days_30``. Uses only trades/onboarding
    before ``t``; funded = a ``funded`` onboarding event before ``t``.
    """
    t = _ts(t)
    ids = frames.accounts["id"] if account_ids is None else pd.Index(account_ids)
    ids = pd.Index(ids, name="account_id")
    ob = frames.onboarding_events
    funded_ts = ob[(ob["step"] == "funded") & (ob["ts"] < t)].groupby("account_id")["ts"].min().reindex(ids)
    tr = frames.trades[frames.trades["ts"] < t]
    first_tr = tr.groupby("account_id")["ts"].min().reindex(ids)
    td = _trading_days_30 if _trading_days_30 is not None else trading_days(tr, t)
    td = td.reindex(ids).fillna(0).astype(int)
    days_funded = np.floor(_days(t - funded_ts))
    days_ft = _days(t - first_tr)
    states = [
        D.classify_health(funded=bool(f), ever_traded=bool(e), trading_days_30=int(n),
                          days_since_first_trade=None if np.isnan(d) else float(d))
        for f, e, n, d in zip(funded_ts.notna(), first_tr.notna(), td, days_ft.to_numpy())
    ]
    out = pd.DataFrame({"health_state": states, "trading_days_30": td.to_numpy(),
                        "days_funded": days_funded.to_numpy(), "days_since_first_trade": np.floor(days_ft).to_numpy()},
                       index=ids)
    labels = {
        "pre_funding": "Not funded yet",
        "ramping": "Ramping · first trade {ft:.0f} d ago",
        "active": "Active · {n} trading days in 30",
        "at_risk": "At risk · {n} trading days in 30",
        "dormant": "Dormant · no trades in 30 d",
    }
    out["health_label"] = [
        f"No trades yet · funded {df:.0f} d" if st == "not_started"
        else labels[st].format(ft=ft if not np.isnan(ft) else 0, n=n)
        for st, df, ft, n in zip(out["health_state"], out["days_funded"], out["days_since_first_trade"],
                                 out["trading_days_30"])
    ]
    return out
