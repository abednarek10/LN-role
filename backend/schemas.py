"""Pydantic response / request schemas for the API surface."""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class VenueOut(BaseModel):
    id: str
    venue_name: str
    city: str
    state: str
    country: str
    capacity: int


class TicketOut(BaseModel):
    id: str
    price_tier: str
    face_value: float
    quantity_available: int
    quantity_sold: int
    variable_cost_per_ticket: float
    fixed_cost_per_event: float


class EventOverviewRow(BaseModel):
    """One row of the Market Overview table."""

    event_id: str
    event_name: str
    artist_name: str
    tour_name: str
    city: str
    state: str
    venue_name: str
    event_date: datetime
    category: str
    capacity: int
    avg_ticket_price: float
    tickets_available: int
    tickets_sold: int
    tickets_remaining: int
    sell_through: float = Field(..., description="quantity_sold / quantity_available, 0-1")
    gross_revenue: float
    contribution_margin: float
    contribution_margin_pct: float
    market_opportunity_score: float = Field(..., description="0-100 heuristic")
    demand_momentum: float = Field(
        ..., description="Recent 7d pageviews / 30d avg pageviews (1.0 = flat)"
    )
    recommended_price: Optional[float] = None


class OverviewSummary(BaseModel):
    total_revenue: float
    avg_margin_pct: float
    avg_sell_through: float
    top_cities: List[dict]  # [{"city": str, "avg_opportunity": float, "event_count": int}]
    event_count: int


class OverviewResponse(BaseModel):
    summary: OverviewSummary
    events: List[EventOverviewRow]


class ElasticityPoint(BaseModel):
    avg_price: float
    tickets_sold: int


class PricePrediction(BaseModel):
    price: float
    predicted_tickets_sold: float
    predicted_revenue: float
    predicted_contribution_margin: float


class ElasticityResponse(BaseModel):
    # ``model_type`` collides with pydantic's protected ``model_`` namespace;
    # opt-out is safe here since we don't rely on those hooks.
    model_config = ConfigDict(protected_namespaces=())

    event_id: str
    event_name: str
    model_type: Literal["log-log"] = "log-log"
    beta_0: float
    beta_1: float = Field(..., description="Price elasticity of demand (log-log slope)")
    r_squared: float
    sample_size: int
    current_price: float
    current_tickets_sold: int
    recommended_price: float
    recommended_price_low: float
    recommended_price_high: float
    revenue_at_recommended: float
    margin_at_recommended: float
    revenue_at_current: float
    elasticity_verdict: str = Field(
        ..., description="Human-readable summary — 'inelastic', 'unit-elastic', 'elastic'"
    )
    narrative: str
    data_points: List[ElasticityPoint]
    price_grid_predictions: List[PricePrediction]


class ScenarioRequest(BaseModel):
    event_ids: List[str] = Field(..., min_length=1)
    price_adjustment_type: Literal["absolute", "percent"] = "percent"
    price_adjustment_value: float = 0.0
    add_extra_show: bool = False


class EventScenarioBreakdown(BaseModel):
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
    delta_revenue: float
    delta_margin: float


class ScenarioResponse(BaseModel):
    baseline_revenue: float
    scenario_revenue: float
    baseline_margin: float
    scenario_margin: float
    delta_revenue: float
    delta_margin: float
    delta_revenue_pct: float
    delta_margin_pct: float
    okr_segment: str
    okr_revenue_target: float
    okr_progress_baseline: float
    okr_progress_scenario: float
    okr_progress_delta_pts: float
    extra_show_events_added: int
    narrative: str
    per_event: List[EventScenarioBreakdown]


class OkrSummaryRow(BaseModel):
    segment: str
    annual_revenue_target: float
    annual_margin_target: float
    actual_revenue_to_date: float
    actual_margin_to_date: float
    revenue_progress_pct: float
    margin_progress_pct: float
    events_counted: int


class OkrSummaryResponse(BaseModel):
    default_segment: str
    segments: List[OkrSummaryRow]
