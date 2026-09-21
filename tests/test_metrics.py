"""Tests for the core economic metrics."""
from __future__ import annotations

from types import SimpleNamespace

from backend.services.metrics import (
    OpportunityInputs,
    avg_ticket_price,
    contribution_margin,
    gross_revenue,
    sell_through,
)


def make_ticket(face_value, sold, available=100, variable=5.0, fixed=1000.0):
    return SimpleNamespace(
        face_value=face_value,
        quantity_sold=sold,
        quantity_available=available,
        variable_cost_per_ticket=variable,
        fixed_cost_per_event=fixed,
    )


def test_gross_revenue_simple():
    tix = [make_ticket(100, 10), make_ticket(200, 5)]
    assert gross_revenue(tix) == 100 * 10 + 200 * 5


def test_contribution_margin_deducts_fixed_once():
    tix = [make_ticket(100, 10, fixed=1000), make_ticket(200, 5, fixed=1000)]
    # revenue = 2000, variable = 5 * 15 = 75, fixed = 1000 (max, not sum)
    assert contribution_margin(tix) == 2000 - 75 - 1000


def test_sell_through_zero_available_returns_zero():
    tix = [make_ticket(100, 0, available=0)]
    assert sell_through(tix) == 0.0


def test_avg_ticket_price_falls_back_when_no_sales():
    tix = [make_ticket(100, 0), make_ticket(200, 0)]
    assert avg_ticket_price(tix) == 150.0


def test_opportunity_score_bounds():
    hot = OpportunityInputs(sell_through=1.0, demand_momentum=1.4, price_gap_pct=0.2).score()
    cold = OpportunityInputs(sell_through=0.2, demand_momentum=0.6, price_gap_pct=-0.1).score()
    assert 0.0 <= cold < hot <= 100.0
