"""Price elasticity of demand — log-log OLS regression.

Model:  log(tickets_sold) = β₀ + β₁ · log(avg_price) + ε

β₁ is the standard economist's own-price elasticity — a value of -1.5 means a
1% price hike reduces quantity demanded by ~1.5%. We deliberately keep the
spec simple: transparent, cheap to run per request, and easy to reason about
in a strategy meeting.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

try:  # statsmodels gives us OLS + R² in one call; fall back to numpy if missing.
    import statsmodels.api as sm  # type: ignore

    _HAS_SM = True
except Exception:  # pragma: no cover - defensive; statsmodels is in requirements
    _HAS_SM = False


@dataclass
class ElasticityFit:
    beta_0: float
    beta_1: float
    r_squared: float
    sample_size: int
    price_min: float
    price_max: float

    def predict_qty(self, price: float) -> float:
        """log(q) = β₀ + β₁ · log(p) → q = exp(β₀) · p^β₁."""
        if price <= 0:
            return 0.0
        return float(np.exp(self.beta_0) * (price ** self.beta_1))


def fit_log_log(prices: Sequence[float], quantities: Sequence[float]) -> ElasticityFit:
    """Fit log(q) = β₀ + β₁ log(p) via OLS.

    Filters out any (price ≤ 0, quantity ≤ 0) rows because log of a
    non-positive is undefined. With fewer than 3 usable observations we short
    circuit to a trivial fit (β₁ = -1, R² = 0) so downstream callers keep
    receiving structurally valid results instead of an exception, and can
    surface the low sample size to the user via `sample_size`.
    """
    p = np.array(prices, dtype=float)
    q = np.array(quantities, dtype=float)
    mask = (p > 0) & (q > 0)
    p, q = p[mask], q[mask]
    n = int(len(p))
    if n < 3:
        return ElasticityFit(
            beta_0=float(np.log(q.mean())) if n else 0.0,
            beta_1=-1.0,
            r_squared=0.0,
            sample_size=n,
            price_min=float(p.min()) if n else 0.0,
            price_max=float(p.max()) if n else 0.0,
        )

    log_p = np.log(p)
    log_q = np.log(q)

    if _HAS_SM:
        X = sm.add_constant(log_p)
        model = sm.OLS(log_q, X).fit()
        beta_0 = float(model.params[0])
        beta_1 = float(model.params[1])
        r_squared = float(model.rsquared)
    else:  # pragma: no cover
        slope, intercept = np.polyfit(log_p, log_q, 1)
        beta_0, beta_1 = float(intercept), float(slope)
        pred = beta_0 + beta_1 * log_p
        ss_res = float(np.sum((log_q - pred) ** 2))
        ss_tot = float(np.sum((log_q - log_q.mean()) ** 2))
        r_squared = 0.0 if ss_tot == 0 else 1 - ss_res / ss_tot

    return ElasticityFit(
        beta_0=beta_0,
        beta_1=beta_1,
        r_squared=r_squared,
        sample_size=n,
        price_min=float(p.min()),
        price_max=float(p.max()),
    )


def revenue_maximizing_price(
    fit: ElasticityFit,
    current_price: float,
    variable_cost_per_ticket: float = 0.0,
    quantity_available: int | None = None,
    search_low_mult: float = 0.75,
    search_high_mult: float = 1.3,
    grid_points: int = 41,
) -> tuple[float, list[dict]]:
    """Scan a price grid and return the (contribution-margin-maximizing) price.

    Why margin, not raw revenue? Because a strategy owner cares about
    profitability. When ``variable_cost_per_ticket`` is 0 this reduces to
    revenue maximization; feeding real per-ticket variable cost gets us to
    contribution.
    The search band is deliberately tight — ±25–30% of the current price —
    because for inelastic goods (β₁ > -1) a raw log-log fit will run price
    to infinity, which is a mathematically valid but strategically absurd
    recommendation. Widening the band is a config choice, not a fix to the
    model.
    Predicted ``tickets_sold`` is also capped at capacity so the projection
    can never forecast more seats than the room holds.
    """
    if current_price <= 0:
        current_price = max(fit.price_min, 1.0)
    lo = current_price * search_low_mult
    hi = current_price * search_high_mult
    if hi <= lo:
        hi = lo * 1.5

    prices = np.linspace(lo, hi, grid_points)
    grid: list[dict] = []
    best_margin = -float("inf")
    best_price = current_price
    for p in prices:
        q = fit.predict_qty(float(p))
        if quantity_available is not None:
            q = min(q, float(quantity_available))
        rev = float(p) * q
        margin = (float(p) - variable_cost_per_ticket) * q
        grid.append(
            {
                "price": round(float(p), 2),
                "predicted_tickets_sold": round(q, 2),
                "predicted_revenue": round(rev, 2),
                "predicted_contribution_margin": round(margin, 2),
            }
        )
        if margin > best_margin:
            best_margin = margin
            best_price = float(p)

    return best_price, grid


def elasticity_verdict(beta_1: float) -> str:
    """Textbook labels — we treat the small band around -1 as unit-elastic."""
    magnitude = abs(beta_1)
    if magnitude < 0.9:
        return "inelastic"
    if magnitude <= 1.1:
        return "unit-elastic"
    return "elastic"


def build_narrative(
    fit: ElasticityFit,
    current_price: float,
    recommended_price: float,
    rev_at_current: float,
    rev_at_recommended: float,
) -> str:
    """One-paragraph strategy summary — the kind a manager would paste into a deck."""
    verdict = elasticity_verdict(fit.beta_1)
    if current_price <= 0:
        pct_move = 0.0
    else:
        pct_move = (recommended_price - current_price) / current_price * 100
    direction = "increase" if pct_move > 0 else "decrease" if pct_move < 0 else "hold"
    rev_delta_pct = (
        0.0 if rev_at_current == 0 else (rev_at_recommended - rev_at_current) / rev_at_current * 100
    )
    expected_qty_pct = fit.beta_1 * pct_move  # elasticity × price % change ≈ quantity %

    return (
        f"Demand for this event is {verdict} (elasticity ≈ {fit.beta_1:.2f}, "
        f"R² = {fit.r_squared:.2f}, n = {fit.sample_size}). "
        f"A {abs(pct_move):.1f}% price {direction} to ~${recommended_price:.2f} "
        f"is projected to move volume by {expected_qty_pct:+.1f}% and revenue by "
        f"{rev_delta_pct:+.1f}%."
    )
