"""Elasticity endpoint — powers the Price & Demand view."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Event
from ..schemas import ElasticityPoint, ElasticityResponse, PricePrediction
from ..services.elasticity import (
    build_narrative,
    elasticity_verdict,
    fit_log_log,
    revenue_maximizing_price,
)
from ..services.metrics import avg_ticket_price, contribution_margin, gross_revenue

router = APIRouter(prefix="/api/events", tags=["elasticity"])


@router.get("/{event_id}/elasticity", response_model=ElasticityResponse)
def event_elasticity(event_id: str, db: Session = Depends(get_db)) -> ElasticityResponse:
    event = (
        db.query(Event)
        .options(
            selectinload(Event.tickets),
            selectinload(Event.historical_pricing),
            selectinload(Event.venue),
        )
        .filter(Event.id == event_id)
        .first()
    )
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    hist = list(event.historical_pricing)
    prices = [h.avg_price for h in hist]
    qtys = [h.tickets_sold for h in hist]
    fit = fit_log_log(prices, qtys)

    tickets = list(event.tickets)
    current_price = avg_ticket_price(tickets)
    total_sold = sum(t.quantity_sold for t in tickets)
    total_available = sum(t.quantity_available for t in tickets)
    total_vc_sold = sum(t.variable_cost_per_ticket * t.quantity_sold for t in tickets)
    avg_vc = total_vc_sold / total_sold if total_sold else 0.0

    recommended_price, grid = revenue_maximizing_price(
        fit,
        current_price=current_price,
        variable_cost_per_ticket=avg_vc,
    )
    # Model-basis revenue at the current price — used inside the narrative
    # so the "revenue Δ" is a like-for-like comparison. The event-level
    # gross_revenue below is the actual all-tier tour revenue reported on
    # the API response for the KPI card.
    predicted_qty_current = fit.predict_qty(current_price)
    model_revenue_current = current_price * predicted_qty_current
    revenue_at_current_actual = gross_revenue(tickets)

    # Pick the grid row closest to the argmax price — an exact float compare
    # is fragile once we round for the API response.
    best_row = min(grid, key=lambda r: abs(r["price"] - recommended_price))
    revenue_at_recommended = best_row["predicted_revenue"]
    margin_at_recommended = best_row["predicted_contribution_margin"]

    # ±10% band around the argmax gets us the "recommended price range"
    # the PRD calls for in View 2 without invoking a full confidence interval
    # — a reasonable, defensible heuristic for the workbench.
    low = round(recommended_price * 0.95, 2)
    high = round(recommended_price * 1.05, 2)

    narrative = build_narrative(
        fit=fit,
        current_price=current_price,
        recommended_price=recommended_price,
        rev_at_current=model_revenue_current,
        rev_at_recommended=revenue_at_recommended,
    )

    return ElasticityResponse(
        event_id=event.id,
        event_name=event.event_name,
        beta_0=round(fit.beta_0, 6),
        beta_1=round(fit.beta_1, 6),
        r_squared=round(fit.r_squared, 4),
        sample_size=fit.sample_size,
        current_price=round(current_price, 2),
        current_tickets_sold=total_sold,
        recommended_price=round(recommended_price, 2),
        recommended_price_low=low,
        recommended_price_high=high,
        revenue_at_recommended=round(revenue_at_recommended, 2),
        margin_at_recommended=round(margin_at_recommended, 2),
        revenue_at_current=round(revenue_at_current_actual, 2),
        elasticity_verdict=elasticity_verdict(fit.beta_1),
        narrative=narrative,
        data_points=[
            ElasticityPoint(avg_price=h.avg_price, tickets_sold=h.tickets_sold) for h in hist
        ],
        price_grid_predictions=[PricePrediction(**r) for r in grid],
    )
