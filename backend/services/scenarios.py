"""Scenario simulation engine.

Given a set of events, a price adjustment, and an optional 'add-a-show'
toggle, project revenue and contribution margin against baseline. Uses the
per-event log-log elasticity fit as the demand curve, so scenario math is
consistent with the Price & Demand view.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from sqlalchemy.orm import Session

from ..models import Event, HistoricalPricing, Ticket
from .elasticity import ElasticityFit, fit_log_log
from .metrics import (
    avg_ticket_price,
    contribution_margin,
    fixed_cost_total,
    gross_revenue,
)


@dataclass
class EventScenario:
    event_id: str
    event_name: str
    city: str
    baseline_price: float
    scenario_price: float
    baseline_tickets_sold: float
    scenario_tickets_sold: float
    baseline_revenue: float
    scenario_revenue: float
    baseline_margin: float
    scenario_margin: float

    @property
    def delta_revenue(self) -> float:
        return self.scenario_revenue - self.baseline_revenue

    @property
    def delta_margin(self) -> float:
        return self.scenario_margin - self.baseline_margin


def _event_variable_cost_per_ticket(event: Event) -> float:
    """Sold-weighted average variable cost across price tiers."""
    total_sold = sum(t.quantity_sold for t in event.tickets)
    if total_sold == 0:
        return float(
            sum(t.variable_cost_per_ticket for t in event.tickets) / max(len(event.tickets), 1)
        )
    return float(
        sum(t.variable_cost_per_ticket * t.quantity_sold for t in event.tickets) / total_sold
    )


def _fit_for_event(event: Event) -> ElasticityFit:
    prices = [h.avg_price for h in event.historical_pricing]
    qtys = [h.tickets_sold for h in event.historical_pricing]
    return fit_log_log(prices, qtys)


def _adjust_price(baseline: float, adj_type: str, adj_value: float) -> float:
    if adj_type == "percent":
        return max(0.0, baseline * (1.0 + adj_value / 100.0))
    if adj_type == "absolute":
        return max(0.0, baseline + adj_value)
    raise ValueError(f"Unknown price_adjustment_type: {adj_type}")


def simulate(
    db: Session,
    events: Sequence[Event],
    price_adjustment_type: str,
    price_adjustment_value: float,
    add_extra_show: bool,
) -> tuple[List[EventScenario], int]:
    """Return per-event scenario rows plus the count of synthetic extra shows."""
    per_event: List[EventScenario] = []
    extra_shows_added = 0

    # First pass: build baseline + scenario for each real event.
    per_city_lift: dict[str, EventScenario] = {}  # for the "add extra show" pass
    for event in events:
        tickets = list(event.tickets)
        baseline_price = avg_ticket_price(tickets)
        baseline_qty = float(sum(t.quantity_sold for t in tickets))
        baseline_rev = gross_revenue(tickets)
        baseline_margin = contribution_margin(tickets)

        fit = _fit_for_event(event)
        vc = _event_variable_cost_per_ticket(event)
        fc = fixed_cost_total(tickets)
        capacity = sum(t.quantity_available for t in tickets)

        scenario_price = _adjust_price(
            baseline_price, price_adjustment_type, price_adjustment_value
        )
        # Rescale predicted quantity so a 0% price move exactly reproduces the
        # observed sold count. This keeps the scenario intuitive: no price
        # change, no volume change — the elasticity only kicks in on movement.
        predicted_baseline_qty = fit.predict_qty(baseline_price)
        scale = 1.0 if predicted_baseline_qty <= 0 else baseline_qty / predicted_baseline_qty
        scenario_qty = min(fit.predict_qty(scenario_price) * scale, float(capacity))
        scenario_rev = scenario_price * scenario_qty
        scenario_margin = (scenario_price - vc) * scenario_qty - fc

        row = EventScenario(
            event_id=event.id,
            event_name=event.event_name,
            city=event.venue.city if event.venue else "?",
            baseline_price=round(baseline_price, 2),
            scenario_price=round(scenario_price, 2),
            baseline_tickets_sold=round(baseline_qty, 2),
            scenario_tickets_sold=round(scenario_qty, 2),
            baseline_revenue=round(baseline_rev, 2),
            scenario_revenue=round(scenario_rev, 2),
            baseline_margin=round(baseline_margin, 2),
            scenario_margin=round(scenario_margin, 2),
        )
        per_event.append(row)
        # Track the strongest scenario per city so an extra show can piggy-back
        # on the best-performing event in that market.
        if event.venue:
            prior = per_city_lift.get(event.venue.city)
            if prior is None or row.scenario_revenue > prior.scenario_revenue:
                per_city_lift[event.venue.city] = row

    # Second pass: 'add an extra show' proxy. We assume the incremental show
    # sells at ~85% of the best-performing scenario in that city (mid-teens
    # cannibalization). Baseline has no such show, so the whole thing lands
    # in the delta column.
    if add_extra_show:
        CANNIBAL = 0.85
        for city, ref in per_city_lift.items():
            per_event.append(
                EventScenario(
                    event_id=f"extra-{ref.event_id}",
                    event_name=f"Additional show in {city}",
                    city=city,
                    baseline_price=0.0,
                    scenario_price=ref.scenario_price,
                    baseline_tickets_sold=0.0,
                    scenario_tickets_sold=round(ref.scenario_tickets_sold * CANNIBAL, 2),
                    baseline_revenue=0.0,
                    scenario_revenue=round(ref.scenario_revenue * CANNIBAL, 2),
                    baseline_margin=0.0,
                    # Assume the additional show reuses the same fixed cost as the reference.
                    scenario_margin=round(ref.scenario_margin * CANNIBAL, 2),
                )
            )
            extra_shows_added += 1

    return per_event, extra_shows_added


def build_narrative(
    rows: Sequence[EventScenario],
    price_adjustment_type: str,
    price_adjustment_value: float,
    add_extra_show: bool,
    okr_progress_delta_pts: float,
    okr_segment: str,
) -> str:
    delta_revenue = sum(r.delta_revenue for r in rows)
    delta_margin = sum(r.delta_margin for r in rows)
    cities = sorted({r.city for r in rows if r.city and r.city != "?"})
    cities_str = ", ".join(cities[:3]) + ("…" if len(cities) > 3 else "")

    if price_adjustment_type == "percent":
        price_label = f"{price_adjustment_value:+.1f}% price move"
    else:
        price_label = f"{price_adjustment_value:+.2f} absolute price move"
    if add_extra_show:
        price_label += ", +1 show per city"
    if price_adjustment_value == 0 and not add_extra_show:
        price_label = "hold-and-observe (no price move, no added show)"

    return (
        f"Scenario applied {price_label} across {len(rows)} event rows "
        f"({cities_str}). Projected impact: ${delta_revenue:,.0f} revenue, "
        f"${delta_margin:,.0f} contribution margin, "
        f"{okr_progress_delta_pts:+.2f} pts toward {okr_segment} annual revenue target."
    )
