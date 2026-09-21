"""OKR summary endpoint."""
from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload

from ..config import DEFAULT_OKR_SEGMENT
from ..database import get_db
from ..models import Event, OkrTarget
from ..schemas import OkrSummaryResponse, OkrSummaryRow
from ..services.metrics import contribution_margin, gross_revenue

router = APIRouter(prefix="/api/okr", tags=["okr"])


def _segment_for_event(event: Event) -> str:
    """Map an event to the OKR segment key used in the seed data.

    The convention is ``<Category>_<Country>_<Year>`` — e.g.
    ``Concerts_NA_2026``. If the event's country is unknown we fall through
    to ``Category_ALL_<year>``.
    """
    year = event.event_date.year
    country = event.venue.country if event.venue else "NA"
    region = "NA" if country in {"USA", "Canada"} else country
    return f"{event.category}s_{region}_{year}"


@router.get("/summary", response_model=OkrSummaryResponse)
def okr_summary(db: Session = Depends(get_db)) -> OkrSummaryResponse:
    events: List[Event] = (
        db.query(Event)
        .options(selectinload(Event.tickets), selectinload(Event.venue))
        .all()
    )

    revenue_by_segment: Dict[str, float] = {}
    margin_by_segment: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    for e in events:
        seg = _segment_for_event(e)
        revenue_by_segment[seg] = revenue_by_segment.get(seg, 0.0) + gross_revenue(e.tickets)
        margin_by_segment[seg] = margin_by_segment.get(seg, 0.0) + contribution_margin(e.tickets)
        counts[seg] = counts.get(seg, 0) + 1

    okrs: List[OkrTarget] = db.query(OkrTarget).all()
    rows: List[OkrSummaryRow] = []
    for okr in okrs:
        rev_actual = revenue_by_segment.get(okr.segment, 0.0)
        margin_actual = margin_by_segment.get(okr.segment, 0.0)
        rows.append(
            OkrSummaryRow(
                segment=okr.segment,
                annual_revenue_target=okr.annual_revenue_target,
                annual_margin_target=okr.annual_margin_target,
                actual_revenue_to_date=round(rev_actual, 2),
                actual_margin_to_date=round(margin_actual, 2),
                revenue_progress_pct=round(rev_actual / okr.annual_revenue_target, 4)
                if okr.annual_revenue_target
                else 0.0,
                margin_progress_pct=round(margin_actual / okr.annual_margin_target, 4)
                if okr.annual_margin_target
                else 0.0,
                events_counted=counts.get(okr.segment, 0),
            )
        )
    rows.sort(key=lambda r: r.segment)

    return OkrSummaryResponse(default_segment=DEFAULT_OKR_SEGMENT, segments=rows)
