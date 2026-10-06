"""SQLAlchemy ORM models — table and column names are a contract (spec §D).

All datetimes are naive UTC. Integer PKs. Every FK column is indexed.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Rep(Base):
    __tablename__ = "reps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # AE|STRATEGIC|REVOPS|MARKETING
    region: Mapped[str] = mapped_column(String(40), nullable=False)
    quota_funded_annual: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quota_adv: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    segment: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    primary_iso: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    exposure_isos: Mapped[str] = mapped_column(String(60), nullable=False)  # CSV
    hub: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    hq_state: Mapped[str] = mapped_column(String(4), nullable=False)
    size_mw: Mapped[float] = mapped_column(Float, nullable=False)
    est_annual_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    tam_tier: Mapped[str] = mapped_column(String(1), nullable=False)  # A|B|C
    lead_source: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    rep_id: Mapped[int | None] = mapped_column(ForeignKey("reps.id"), nullable=True, index=True)
    stage: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    is_liquidity_partner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_other_exchange_account: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    kyc_redlines: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    kyc_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    funded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    funded_amount_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_trade_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_qualifying_trade_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active_since: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # SEED-ONLY ground truth. Never read by features/services (tests only).
    latent_propensity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    persona: Mapped[str] = mapped_column(String(10), nullable=False)  # TRADER|RISK|CFO|OPS|EXEC
    email: Mapped[str] = mapped_column(String(200), nullable=False)
    is_champion: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (Index("ix_activities_account_ts", "account_id", "ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    rep_id: Mapped[int | None] = mapped_column(ForeignKey("reps.id"), nullable=True, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    trigger_id: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    sequence: Mapped[str | None] = mapped_column(String(30), nullable=True)


class OnboardingEvent(Base):
    __tablename__ = "onboarding_events"
    __table_args__ = (
        Index("ix_onboarding_account_step", "account_id", "step"),
        Index("ix_onboarding_step_ts", "step", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    step: Mapped[str] = mapped_column(String(30), nullable=False)


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        Index("ix_trades_account_ts", "account_id", "ts"),
        Index("ix_trades_iso_ts", "iso", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    iso: Mapped[str] = mapped_column(String(10), nullable=False)
    hub: Mapped[str] = mapped_column(String(30), nullable=False)
    tenor: Mapped[str] = mapped_column(String(12), nullable=False)  # HOURLY|DAILY_PEAK|WEEKLY_PEAK
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # BUY|SELL
    contracts: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    notional_usd: Mapped[float] = mapped_column(Float, nullable=False)
    fee_usd: Mapped[float] = mapped_column(Float, nullable=False)
    is_maker: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class MarketPrice(Base):
    __tablename__ = "market_prices"
    __table_args__ = (Index("ix_market_prices_iso_ts", "iso", "ts"),)

    hub: Mapped[str] = mapped_column(String(30), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, primary_key=True)  # hour-beginning, naive UTC
    iso: Mapped[str] = mapped_column(String(10), nullable=False)
    lmp: Mapped[float] = mapped_column(Float, nullable=False)


class PriceForecast(Base):
    __tablename__ = "price_forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hub: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    iso: Mapped[str] = mapped_column(String(10), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_peak_lmp: Mapped[float] = mapped_column(Float, nullable=False)
    forecast_avg_lmp: Mapped[float] = mapped_column(Float, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class SpreadSnapshot(Base):
    __tablename__ = "spread_snapshots"
    __table_args__ = (Index("ix_spread_hub_date", "hub", "date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    iso: Mapped[str] = mapped_column(String(10), nullable=False)
    hub: Mapped[str] = mapped_column(String(30), nullable=False)
    tenor: Mapped[str] = mapped_column(String(12), nullable=False)
    spread_usd_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    two_sided_uptime_pct: Mapped[float] = mapped_column(Float, nullable=False)
    top_depth_contracts: Mapped[int] = mapped_column(Integer, nullable=False)
    active_accounts: Mapped[int] = mapped_column(Integer, nullable=False)
    lp_quote_share: Mapped[float] = mapped_column(Float, nullable=False)


class MarketingSpend(Base):
    __tablename__ = "marketing_spend"
    __table_args__ = (Index("ix_marketing_channel_month", "channel", "month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[date] = mapped_column(Date, nullable=False)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    spend_usd: Mapped[float] = mapped_column(Float, nullable=False)
    leads: Mapped[int] = mapped_column(Integer, nullable=False)
    campaign: Mapped[str] = mapped_column(String(160), nullable=False)


class VolatilityEvent(Base):
    __tablename__ = "volatility_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trigger_id: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    hub: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    iso: Mapped[str] = mapped_column(String(10), nullable=False)
    start_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    regime: Mapped[str] = mapped_column(String(20), nullable=False)
    peak_lmp: Mapped[float] = mapped_column(Float, nullable=False)
    spike_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[float] = mapped_column(Float, nullable=False)


class OutreachDraft(Base):
    __tablename__ = "outreach_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    rep_id: Mapped[int | None] = mapped_column(ForeignKey("reps.id"), nullable=True, index=True)
    trigger_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    engine: Mapped[str] = mapped_column(String(20), nullable=False)  # claude|template
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending_review")
    compliance_flags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON


ALL_MODELS = [
    Rep,
    Account,
    Contact,
    Activity,
    OnboardingEvent,
    Trade,
    MarketPrice,
    PriceForecast,
    SpreadSnapshot,
    MarketingSpend,
    VolatilityEvent,
    OutreachDraft,
]
