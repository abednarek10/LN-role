"""Market Overview endpoint — the workbench's landing view."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Event, HistoricalPricing, Venue
from ..schemas import EventOverviewRow, OverviewResponse, OverviewSummary
from ..services.elasticity import fit_log_log, revenue_maximizing_price
from ..services.metrics import (
    avg_ticket_price,
    contribution_margin,
    gross_revenue,
    opportunity_score,
    sell_through,
    summarise_events,
)

router = APIRouter(prefix="/api/events", tags=["events"])


def _row_for_event(event: Event) -> dict:
    tickets = list(event.tickets)
    revenue = gross_revenue(tickets)
    margin = contribution_margin(tickets)
    st = sell_through(tickets)
    price = avg_ticket_price(tickets)
    capacity = event.venue.capacity if event.venue else sum(t.quantity_available for t in tickets)
    total_available = sum(t.quantity_available for t in tickets)
    total_sold = sum(t.quantity_sold for t in tickets)

    # Recommended price is a lightweight pass through the elasticity fit so the
    # opportunity score can incorporate under-/over-pricing. Small-sample events
    # (n<3) return a trivial fit and the recommendation collapses to the
    # current price.
    prices = [h.avg_price for h in event.historical_pricing]
    qtys = [h.tickets_sold for h in event.historical_pricing]
    fit = fit_log_log(prices, qtys)
    vc_sold = sum(t.variable_cost_per_ticket * t.quantity_sold for t in tickets)
    avg_vc = vc_sold / total_sold if total_sold else 0.0
    recommended_price, _ = revenue_maximizing_price(
        fit,
        current_price=price,
        variable_cost_per_ticket=avg_vc,
        quantity_available=total_available,
    )
    score, momentum = opportunity_score(tickets, list(event.demand_signals), recommended_price)

    return {
        "event_id": event.id,
        "event_name": event.event_name,
        "artist_name": event.artist_name,
        "tour_name": event.tour_name,
        "city": event.venue.city if event.venue else "?",
        "state": event.venue.state if event.venue else "?",
        "venue_name": event.venue.venue_name if event.venue else "?",
        "event_date": event.event_date,
        "category": event.category,
        "capacity": capacity,
        "avg_ticket_price": round(price, 2),
        "tickets_available": total_available,
        "tickets_sold": total_sold,
        "tickets_remaining": total_available - total_sold,
        "sell_through": round(st, 4),
        "gross_revenue": round(revenue, 2),
        "contribution_margin": round(margin, 2),
        "contribution_margin_pct": round(margin / revenue, 4) if revenue > 0 else 0.0,
        "market_opportunity_score": score,
        "demand_momentum": round(momentum, 3),
        "recommended_price": round(recommended_price, 2),
    }


@router.get("/overview", response_model=OverviewResponse)
def events_overview(
    db: Session = Depends(get_db),
    city: Optional[str] = Query(None, description="Case-insensitive substring match"),
    artist_name: Optional[str] = Query(None, description="Case-insensitive substring match"),
    tour_name: Optional[str] = Query(None, description="Case-insensitive substring match"),
    category: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
) -> OverviewResponse:
    q = (
        select(Event)
        .join(Event.venue)
        .options(
            selectinload(Event.venue),
            selectinload(Event.tickets),
            selectinload(Event.demand_signals),
            selectinload(Event.historical_pricing),
        )
    )
    if city:
        q = q.where(Venue.city.ilike(f"%{city}%"))
    if artist_name:
        q = q.where(Event.artist_name.ilike(f"%{artist_name}%"))
    if tour_name:
        q = q.where(Event.tour_name.ilike(f"%{tour_name}%"))
    if category:
        q = q.where(Event.category == category)
    if date_from:
        q = q.where(Event.event_date >= date_from)
    if date_to:
        q = q.where(Event.event_date <= date_to)
    q = q.order_by(Event.event_date.asc())

    events = list(db.execute(q).scalars().unique().all())
    rows = [_row_for_event(e) for e in events]
    summary = summarise_events(rows)
    return OverviewResponse(
        summary=OverviewSummary(**summary),
        events=[EventOverviewRow(**r) for r in rows],
    )


@router.get("/{event_id}", response_model=EventOverviewRow)
def get_event(event_id: str, db: Session = Depends(get_db)) -> EventOverviewRow:
    event = (
        db.query(Event)
        .options(
            selectinload(Event.venue),
            selectinload(Event.tickets),
            selectinload(Event.demand_signals),
            selectinload(Event.historical_pricing),
        )
        .filter(Event.id == event_id)
        .first()
    )
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    return EventOverviewRow(**_row_for_event(event))
