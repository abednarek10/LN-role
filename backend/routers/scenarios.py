"""Scenario Simulator endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from ..config import DEFAULT_OKR_SEGMENT
from ..database import get_db
from ..models import Event, OkrTarget
from ..schemas import EventScenarioBreakdown, ScenarioRequest, ScenarioResponse
from ..services.scenarios import build_narrative, simulate

router = APIRouter(prefix="/api/scenario", tags=["scenarios"])


@router.post("/simulate", response_model=ScenarioResponse)
def simulate_scenario(req: ScenarioRequest, db: Session = Depends(get_db)) -> ScenarioResponse:
    events = (
        db.query(Event)
        .options(
            selectinload(Event.venue),
            selectinload(Event.tickets),
            selectinload(Event.historical_pricing),
        )
        .filter(Event.id.in_(req.event_ids))
        .all()
    )
    if not events:
        raise HTTPException(status_code=404, detail="No events matched the supplied ids.")
    missing = set(req.event_ids) - {e.id for e in events}
    if missing:
        raise HTTPException(
            status_code=404, detail=f"Unknown event ids: {sorted(missing)}"
        )

    rows, extra_shows_added = simulate(
        db=db,
        events=events,
        price_adjustment_type=req.price_adjustment_type,
        price_adjustment_value=req.price_adjustment_value,
        add_extra_show=req.add_extra_show,
    )

    baseline_rev = sum(r.baseline_revenue for r in rows)
    scenario_rev = sum(r.scenario_revenue for r in rows)
    baseline_margin = sum(r.baseline_margin for r in rows)
    scenario_margin = sum(r.scenario_margin for r in rows)
    delta_rev = scenario_rev - baseline_rev
    delta_margin = scenario_margin - baseline_margin

    okr = (
        db.query(OkrTarget).filter(OkrTarget.segment == DEFAULT_OKR_SEGMENT).first()
    )
    revenue_target = okr.annual_revenue_target if okr else max(baseline_rev * 4, 1.0)
    okr_progress_baseline = baseline_rev / revenue_target
    okr_progress_scenario = scenario_rev / revenue_target
    okr_progress_delta_pts = (okr_progress_scenario - okr_progress_baseline) * 100

    narrative = build_narrative(
        rows=rows,
        price_adjustment_type=req.price_adjustment_type,
        price_adjustment_value=req.price_adjustment_value,
        add_extra_show=req.add_extra_show,
        okr_progress_delta_pts=okr_progress_delta_pts,
        okr_segment=DEFAULT_OKR_SEGMENT,
    )

    per_event = [
        EventScenarioBreakdown(
            event_id=r.event_id,
            event_name=r.event_name,
            city=r.city,
            baseline_price=r.baseline_price,
            scenario_price=r.scenario_price,
            baseline_tickets_sold=r.baseline_tickets_sold,
            scenario_tickets_sold=r.scenario_tickets_sold,
            baseline_revenue=r.baseline_revenue,
            scenario_revenue=r.scenario_revenue,
            baseline_margin=r.baseline_margin,
            scenario_margin=r.scenario_margin,
            delta_revenue=round(r.delta_revenue, 2),
            delta_margin=round(r.delta_margin, 2),
        )
        for r in rows
    ]

    return ScenarioResponse(
        baseline_revenue=round(baseline_rev, 2),
        scenario_revenue=round(scenario_rev, 2),
        baseline_margin=round(baseline_margin, 2),
        scenario_margin=round(scenario_margin, 2),
        delta_revenue=round(delta_rev, 2),
        delta_margin=round(delta_margin, 2),
        delta_revenue_pct=round(delta_rev / baseline_rev, 4) if baseline_rev > 0 else 0.0,
        delta_margin_pct=round(delta_margin / baseline_margin, 4) if baseline_margin > 0 else 0.0,
        okr_segment=DEFAULT_OKR_SEGMENT,
        okr_revenue_target=round(revenue_target, 2),
        okr_progress_baseline=round(okr_progress_baseline, 4),
        okr_progress_scenario=round(okr_progress_scenario, 4),
        okr_progress_delta_pts=round(okr_progress_delta_pts, 3),
        extra_show_events_added=extra_shows_added,
        narrative=narrative,
        per_event=per_event,
    )
