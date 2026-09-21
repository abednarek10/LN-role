"""Core economic metrics: revenue, contribution margin, opportunity score.

Every formula in this module is intentionally explicit — a strategy reviewer
should be able to trace any dashboard number to a single named function.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, List, Sequence

from ..models import DemandSignal, Event, HistoricalPricing, Ticket


# ---------------------------------------------------------------------------
# Per-event economics
# ---------------------------------------------------------------------------

def gross_revenue(tickets: Sequence[Ticket]) -> float:
    """Σ face_value * quantity_sold across every price tier."""
    return float(sum(t.face_value * t.quantity_sold for t in tickets))


def variable_cost_total(tickets: Sequence[Ticket]) -> float:
    return float(sum(t.variable_cost_per_ticket * t.quantity_sold for t in tickets))


def fixed_cost_total(tickets: Sequence[Ticket]) -> float:
    """Allocated fixed cost per event.

    The PRD stores ``fixed_cost_per_event`` on every ticket row for that event
    (so each tier can carry its allocation share). We take the *max* across the
    tier rows — which equals the event-level total when the seed writes an
    identical value to every tier — instead of summing, so we never
    double-count the same fixed cost.
    """
    if not tickets:
        return 0.0
    return float(max(t.fixed_cost_per_event for t in tickets))


def contribution_margin(tickets: Sequence[Ticket]) -> float:
    """Revenue – variable costs – allocated fixed costs."""
    return gross_revenue(tickets) - variable_cost_total(tickets) - fixed_cost_total(tickets)


def avg_ticket_price(tickets: Sequence[Ticket]) -> float:
    """Sales-weighted average ticket price. Falls back to a face-value mean
    when no tickets are sold yet, so a brand new on-sale still returns a
    meaningful price signal instead of a divide-by-zero NaN."""
    sold = sum(t.quantity_sold for t in tickets)
    if sold == 0:
        return float(sum(t.face_value for t in tickets) / max(len(tickets), 1))
    return float(sum(t.face_value * t.quantity_sold for t in tickets) / sold)


def sell_through(tickets: Sequence[Ticket]) -> float:
    available = sum(t.quantity_available for t in tickets)
    if available == 0:
        return 0.0
    sold = sum(t.quantity_sold for t in tickets)
    return float(sold / available)


# ---------------------------------------------------------------------------
# Demand momentum
# ---------------------------------------------------------------------------

def demand_momentum(signals: Sequence[DemandSignal], as_of: date | None = None) -> float:
    """Ratio of the last 7 days of page_views to the trailing 30-day mean.

    A value of 1.0 means demand is flat, >1 is accelerating. Falls back to
    1.0 when we lack enough observations to be meaningful — better to score
    a thin-data event as "neutral" than to hallucinate momentum from one point.
    """
    if not signals:
        return 1.0
    if as_of is None:
        as_of = max(s.date for s in signals)
    window_recent = [s for s in signals if (as_of - s.date).days < 7]
    window_baseline = [s for s in signals if 0 <= (as_of - s.date).days < 30]
    if not window_baseline:
        return 1.0
    baseline_mean = sum(s.page_views for s in window_baseline) / len(window_baseline)
    if baseline_mean <= 0:
        return 1.0
    recent_mean = (
        sum(s.page_views for s in window_recent) / len(window_recent) if window_recent else baseline_mean
    )
    return float(recent_mean / baseline_mean)


# ---------------------------------------------------------------------------
# Market Opportunity Score (0–100)
# ---------------------------------------------------------------------------

@dataclass
class OpportunityInputs:
    sell_through: float
    demand_momentum: float
    price_gap_pct: float  # (recommended - current) / current; positive = room to raise

    @staticmethod
    def _clip01(x: float) -> float:
        return max(0.0, min(1.0, x))

    def score(
        self,
        w_sellthrough: float = 0.4,
        w_momentum: float = 0.35,
        w_price_gap: float = 0.25,
    ) -> float:
        # Sell-through is treated as a *hot market* signal: closer to 1.0 sold
        # ⇒ higher opportunity to lean in (add dates, hold price).
        s_sell = self._clip01(self.sell_through)
        # Momentum is centred on 1.0; anything above 1.5 is treated as saturated.
        s_mom = self._clip01((self.demand_momentum - 0.5) / 1.0)
        # Bigger positive price gap ⇒ under-priced ⇒ more upside.
        s_gap = self._clip01((self.price_gap_pct + 0.15) / 0.45)
        score = 100.0 * (w_sellthrough * s_sell + w_momentum * s_mom + w_price_gap * s_gap)
        return round(score, 1)


def opportunity_score(
    tickets: Sequence[Ticket],
    signals: Sequence[DemandSignal],
    recommended_price: float | None,
) -> tuple[float, float]:
    """Returns (score, demand_momentum)."""
    st = sell_through(tickets)
    momentum = demand_momentum(signals)
    current_price = avg_ticket_price(tickets)
    if recommended_price is None or current_price <= 0:
        price_gap = 0.0
    else:
        price_gap = (recommended_price - current_price) / current_price
    inputs = OpportunityInputs(
        sell_through=st, demand_momentum=momentum, price_gap_pct=price_gap
    )
    return inputs.score(), momentum


# ---------------------------------------------------------------------------
# Helpers to package an Event into a metrics dict
# ---------------------------------------------------------------------------

def event_capacity(event: Event) -> int:
    return int(event.venue.capacity) if event.venue else int(
        sum(t.quantity_available for t in event.tickets)
    )


def summarise_events(rows: Iterable[dict]) -> dict:
    """Compute the top-of-view rollups (used by the overview endpoint)."""
    rows = list(rows)
    if not rows:
        return {
            "total_revenue": 0.0,
            "avg_margin_pct": 0.0,
            "avg_sell_through": 0.0,
            "top_cities": [],
            "event_count": 0,
        }
    total_revenue = sum(r["gross_revenue"] for r in rows)
    margin_pcts = [r["contribution_margin_pct"] for r in rows if r["gross_revenue"] > 0]
    avg_margin_pct = sum(margin_pcts) / len(margin_pcts) if margin_pcts else 0.0
    sell_throughs = [r["sell_through"] for r in rows]
    avg_st = sum(sell_throughs) / len(sell_throughs) if sell_throughs else 0.0

    by_city: dict[str, list[float]] = {}
    for r in rows:
        by_city.setdefault(r["city"], []).append(r["market_opportunity_score"])
    top_cities = sorted(
        (
            {
                "city": city,
                "avg_opportunity": round(sum(scores) / len(scores), 1),
                "event_count": len(scores),
            }
            for city, scores in by_city.items()
        ),
        key=lambda x: x["avg_opportunity"],
        reverse=True,
    )[:3]

    return {
        "total_revenue": round(total_revenue, 2),
        "avg_margin_pct": round(avg_margin_pct, 4),
        "avg_sell_through": round(avg_st, 4),
        "top_cities": top_cities,
        "event_count": len(rows),
    }
