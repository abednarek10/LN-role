"""DB → pandas loaders. The only SQL touchpoint for services.

Every ``load_<table>(session)`` returns a DataFrame whose columns are exactly
the table's columns (spec §D), with:

* ``DateTime`` **and** ``Date`` columns as ``datetime64[us]`` (naive UTC; dates at
  midnight) — compare with ``pd.Timestamp``/``datetime``;
* nullable integer FKs (``rep_id``) as pandas ``Int64``;
* booleans as ``bool``.

``load_all(session)`` returns a :class:`Frames` bundle and caches it in-process
per database. Call :func:`invalidate_cache` after writes (e.g. a queued
outreach draft adds an ``activities`` row): ``invalidate_cache("activities",
"outreach_drafts")`` reloads only those tables on the next ``load_all``.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, fields
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, select
from sqlalchemy.orm import Session

from .models import (
    Account,
    Activity,
    Contact,
    MarketingSpend,
    MarketPrice,
    OnboardingEvent,
    OutreachDraft,
    PriceForecast,
    Rep,
    SpreadSnapshot,
    Trade,
    VolatilityEvent,
)

MODELS = {
    "reps": Rep,
    "accounts": Account,
    "contacts": Contact,
    "activities": Activity,
    "onboarding_events": OnboardingEvent,
    "trades": Trade,
    "market_prices": MarketPrice,
    "price_forecasts": PriceForecast,
    "spread_snapshots": SpreadSnapshot,
    "marketing_spend": MarketingSpend,
    "volatility_events": VolatilityEvent,
    "outreach_drafts": OutreachDraft,
}
_ORDER_BY = {
    "activities": ("ts", "id"),
    "onboarding_events": ("ts", "id"),
    "trades": ("ts", "id"),
    "market_prices": ("hub", "ts"),
    "spread_snapshots": ("hub", "tenor", "date"),
    "marketing_spend": ("month", "channel"),
    "volatility_events": ("start_ts", "hub"),
    "price_forecasts": ("hub", "date"),
}


@dataclass(frozen=True)
class Frames:
    """Every table as a DataFrame. Treat as read-only (copy before mutating)."""

    reps: pd.DataFrame
    accounts: pd.DataFrame
    contacts: pd.DataFrame
    activities: pd.DataFrame
    onboarding_events: pd.DataFrame
    trades: pd.DataFrame
    market_prices: pd.DataFrame
    price_forecasts: pd.DataFrame
    spread_snapshots: pd.DataFrame
    marketing_spend: pd.DataFrame
    volatility_events: pd.DataFrame
    outreach_drafts: pd.DataFrame
    loaded_at: datetime

    @property
    def tables(self) -> dict[str, pd.DataFrame]:
        return {f.name: getattr(self, f.name) for f in fields(self) if f.name != "loaded_at"}


def frames_from_tables(tables: dict[str, pd.DataFrame]) -> Frames:
    """Build a :class:`Frames` from in-memory DataFrames (e.g. ``seed.generate``)."""
    out = {}
    for name, model in MODELS.items():
        df = tables.get(name)
        if df is None:
            df = pd.DataFrame(columns=[c.name for c in model.__table__.columns])
        out[name] = _coerce(df.copy(), model)
    return Frames(**out, loaded_at=_now())


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def _coerce(df: pd.DataFrame, model) -> pd.DataFrame:
    for col in model.__table__.columns:
        if col.name not in df.columns:
            continue
        if isinstance(col.type, (DateTime, Date)):
            df[col.name] = pd.to_datetime(df[col.name]).astype("datetime64[us]")
        elif isinstance(col.type, Boolean):
            df[col.name] = df[col.name].fillna(False).astype(bool)
        elif isinstance(col.type, Integer) and col.nullable and not col.primary_key:
            df[col.name] = pd.array(df[col.name], dtype="Int64")
        elif isinstance(col.type, Integer):
            df[col.name] = df[col.name].astype("int64")
        elif isinstance(col.type, Float):
            df[col.name] = df[col.name].astype("float64")
    return df


def _load(session: Session, name: str) -> pd.DataFrame:
    model = MODELS[name]
    table = model.__table__
    cols = [c.name for c in table.columns]
    stmt = select(table)
    order = _ORDER_BY.get(name, ("id",) if "id" in cols else ())
    if order:
        stmt = stmt.order_by(*[table.c[c] for c in order])
    rows = session.execute(stmt).all()
    df = pd.DataFrame.from_records([tuple(r) for r in rows], columns=cols)
    return _coerce(df, model)


def load_reps(session: Session) -> pd.DataFrame:
    return _load(session, "reps")


def load_accounts(session: Session) -> pd.DataFrame:
    return _load(session, "accounts")


def load_contacts(session: Session) -> pd.DataFrame:
    return _load(session, "contacts")


def load_activities(session: Session) -> pd.DataFrame:
    return _load(session, "activities")


def load_onboarding_events(session: Session) -> pd.DataFrame:
    return _load(session, "onboarding_events")


def load_trades(session: Session) -> pd.DataFrame:
    return _load(session, "trades")


def load_market_prices(session: Session) -> pd.DataFrame:
    return _load(session, "market_prices")


def load_price_forecasts(session: Session) -> pd.DataFrame:
    return _load(session, "price_forecasts")


def load_spread_snapshots(session: Session) -> pd.DataFrame:
    return _load(session, "spread_snapshots")


def load_marketing_spend(session: Session) -> pd.DataFrame:
    return _load(session, "marketing_spend")


def load_volatility_events(session: Session) -> pd.DataFrame:
    return _load(session, "volatility_events")


def load_outreach_drafts(session: Session) -> pd.DataFrame:
    return _load(session, "outreach_drafts")


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
_CACHE: dict[str, dict[str, pd.DataFrame]] = {}
_LOCK = threading.RLock()


def _cache_key(session: Session) -> str:
    bind = session.get_bind()
    return f"{bind.url}#{id(bind)}"


def load_all(session: Session, refresh: bool = False) -> Frames:
    """All tables as a :class:`Frames`, cached in-process per database."""
    key = _cache_key(session)
    with _LOCK:
        cached = {} if refresh else dict(_CACHE.get(key, {}))
        for name in MODELS:
            if name not in cached:
                cached[name] = _load(session, name)
        _CACHE[key] = cached
        return Frames(**cached, loaded_at=_now())


def invalidate_cache(*tables: str) -> None:
    """Drop cached tables (all when called without arguments)."""
    with _LOCK:
        if not tables:
            _CACHE.clear()
            return
        for entry in _CACHE.values():
            for t in tables:
                entry.pop(t, None)
