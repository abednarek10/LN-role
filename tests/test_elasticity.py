"""Tests for the log-log elasticity fit."""
from __future__ import annotations

import math

import numpy as np

from backend.services.elasticity import (
    ElasticityFit,
    elasticity_verdict,
    fit_log_log,
    revenue_maximizing_price,
)


def _synthetic_panel(elasticity: float, n: int = 60, seed: int = 7):
    """Generate (price, qty) pairs from a known elasticity so we can invert it."""
    rng = np.random.default_rng(seed)
    prices = rng.uniform(80, 180, size=n)
    # log(q) = 8 + elasticity * log(p) + noise
    log_q = 8.0 + elasticity * np.log(prices) + rng.normal(0, 0.05, size=n)
    return prices.tolist(), np.exp(log_q).tolist()


def test_fit_recovers_known_elasticity():
    prices, qty = _synthetic_panel(elasticity=-1.3)
    fit = fit_log_log(prices, qty)
    assert fit.sample_size == 60
    assert fit.r_squared > 0.9  # noise is tiny
    assert math.isclose(fit.beta_1, -1.3, abs_tol=0.05)


def test_fit_handles_tiny_sample():
    fit = fit_log_log([100.0], [50.0])
    assert fit.sample_size == 1
    assert fit.r_squared == 0.0
    assert fit.beta_1 == -1.0  # sentinel fallback


def test_verdict_labels():
    assert elasticity_verdict(-0.5) == "inelastic"
    assert elasticity_verdict(-1.0) == "unit-elastic"
    assert elasticity_verdict(-1.5) == "elastic"


def test_revenue_maximizing_price_returns_valid_grid():
    prices, qty = _synthetic_panel(elasticity=-1.2)
    fit = fit_log_log(prices, qty)
    best, grid = revenue_maximizing_price(fit, current_price=120.0, variable_cost_per_ticket=10.0)
    assert len(grid) > 0
    assert all("price" in row and "predicted_tickets_sold" in row for row in grid)
    assert best > 0
    # The margin at the best price should be at least as high as at the ends of the grid.
    best_row = max(grid, key=lambda r: r["predicted_contribution_margin"])
    assert math.isclose(best_row["price"], best, abs_tol=1e-6)
