"""SQLAlchemy ORM models mirroring the workbench data model.

Mirrors the PRD's Postgres schema — UUIDs are stored as strings for SQLite
portability, and every FK column carries an index so the analytical joins
(events → venues, tickets → events, demand_signals → events) stay cheap.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import List

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    venue_name: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(60), nullable=False)
    country: Mapped[str] = mapped_column(String(60), nullable=False, default="USA")
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)

    events: Mapped[List["Event"]] = relationship(back_populates="venue")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    artist_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    tour_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    event_name: Mapped[str] = mapped_column(String(240), nullable=False)
    venue_id: Mapped[str] = mapped_column(String(36), ForeignKey("venues.id"), index=True)
    event_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(60), nullable=False, default="Concert")

    venue: Mapped[Venue] = relationship(back_populates="events")
    tickets: Mapped[List["Ticket"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    demand_signals: Mapped[List["DemandSignal"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    historical_pricing: Mapped[List["HistoricalPricing"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class Ticket(Base):
    """A price tier within an event (one row per Standard / VIP / Pit / etc.)."""

    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("events.id"), index=True)
    price_tier: Mapped[str] = mapped_column(String(60), nullable=False)
    face_value: Mapped[float] = mapped_column(Float, nullable=False)
    quantity_available: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_sold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    variable_cost_per_ticket: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    fixed_cost_per_event: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    event: Mapped[Event] = relationship(back_populates="tickets")


class DemandSignal(Base):
    __tablename__ = "demand_signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("events.id"), index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    page_views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_visitors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    add_to_cart_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    search_interest_index: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    event: Mapped[Event] = relationship(back_populates="demand_signals")


class HistoricalPricing(Base):
    """Panel of (price, tickets_sold) observations used for elasticity."""

    __tablename__ = "historical_pricing"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("events.id"), index=True)
    observation_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    avg_price: Mapped[float] = mapped_column(Float, nullable=False)
    tickets_sold: Mapped[int] = mapped_column(Integer, nullable=False)
    promo_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    event: Mapped[Event] = relationship(back_populates="historical_pricing")


class OkrTarget(Base):
    __tablename__ = "okr_targets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    segment: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    annual_revenue_target: Mapped[float] = mapped_column(Float, nullable=False)
    annual_margin_target: Mapped[float] = mapped_column(Float, nullable=False)
