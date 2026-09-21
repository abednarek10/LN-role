"""Synthetic data generator for the workbench.

Builds one full 15-city North American arena tour ("Neon Skyline World Tour"
by "Astra Vale") plus a smaller Latin sports/theatre spread — enough variety
to make the Market Overview interesting without the data becoming noise.

Key design points:
  * Every city has a plausible venue capacity, mean price, and demand-signal
    profile so the overview table looks like a real tour rather than i.i.d.
    noise.
  * `historical_pricing` is generated FROM a chosen elasticity per city, so
    when the API fits log(q) ~ log(p) the recovered β₁ is close to the seeded
    value — the model works because the data has structure to learn.
  * All random draws share the ``config.SEED`` seed, so runs are reproducible.

Usage:
    python -m backend.seed          # drop & re-create tables, then seed
    python -m backend.seed --keep   # seed without dropping
"""
from __future__ import annotations

import argparse
import math
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, List, Tuple

import numpy as np
from sqlalchemy.orm import Session

from .config import DEFAULT_OKR_SEGMENT, SEED
from .database import Base, SessionLocal, create_all, engine
from .models import DemandSignal, Event, HistoricalPricing, OkrTarget, Ticket, Venue


@dataclass
class CityConfig:
    city: str
    state: str
    venue_name: str
    capacity: int
    mean_price: float  # anchor face value for the Standard tier
    elasticity: float  # β₁ — how price-sensitive this market is
    demand_index: float  # scaled 0.5–1.6 to skew page views / sell-through
    country: str = "USA"


# ---------------------------------------------------------------------------
# Tour + city catalogue
# ---------------------------------------------------------------------------

TOUR_ARTIST = "Astra Vale"
TOUR_NAME = "Neon Skyline World Tour"
TOUR_DATES_START = date(2026, 3, 5)

CITIES: List[CityConfig] = [
    # High-density coastal markets: relatively inelastic (bigger fanbase, less
    # price-sensitive) and high demand.
    CityConfig("New York", "NY", "Madison Square Garden", 20_000, 165.0, -0.85, 1.55),
    CityConfig("Los Angeles", "CA", "Crypto.com Arena", 19_000, 155.0, -0.9, 1.5),
    CityConfig("Chicago", "IL", "United Center", 20_500, 130.0, -1.05, 1.35),
    CityConfig("Boston", "MA", "TD Garden", 17_500, 140.0, -1.0, 1.2),
    CityConfig("Philadelphia", "PA", "Wells Fargo Center", 19_500, 120.0, -1.1, 1.05),
    # Solid mid-tier — unit-elastic and average demand.
    CityConfig("Dallas", "TX", "American Airlines Center", 20_000, 110.0, -1.2, 1.1),
    CityConfig("Houston", "TX", "Toyota Center", 18_000, 105.0, -1.25, 1.05),
    CityConfig("Atlanta", "GA", "State Farm Arena", 21_000, 115.0, -1.15, 1.15),
    CityConfig("Miami", "FL", "Kaseya Center", 19_500, 125.0, -1.05, 1.2),
    CityConfig("Seattle", "WA", "Climate Pledge Arena", 17_100, 130.0, -1.0, 1.1),
    # Value / secondary markets: elastic, softer demand, more upside from
    # promotions or added dates.
    CityConfig("Denver", "CO", "Ball Arena", 19_000, 100.0, -1.4, 0.95),
    CityConfig("Phoenix", "AZ", "Footprint Center", 18_000, 95.0, -1.4, 0.9),
    CityConfig("Nashville", "TN", "Bridgestone Arena", 19_500, 105.0, -1.3, 1.1),
    CityConfig("Detroit", "MI", "Little Caesars Arena", 20_000, 95.0, -1.45, 0.85),
    CityConfig("Cleveland", "OH", "Rocket Mortgage FieldHouse", 19_500, 90.0, -1.55, 0.8),
]

PRICE_TIERS: List[Tuple[str, float]] = [
    # (name, multiplier applied to the city's mean face value)
    ("Nosebleed", 0.55),
    ("Standard", 1.0),
    ("Premium", 1.55),
    ("VIP", 2.4),
]

TIER_ALLOCATION = {
    "Nosebleed": 0.35,
    "Standard": 0.40,
    "Premium": 0.18,
    "VIP": 0.07,
}


# ---------------------------------------------------------------------------
# Data generation helpers
# ---------------------------------------------------------------------------

def _tour_dates() -> Iterable[date]:
    """Yield one date per city, spacing 2-4 days apart to feel like a real tour."""
    rng = np.random.default_rng(SEED)
    cur = TOUR_DATES_START
    for _ in CITIES:
        yield cur
        cur = cur + timedelta(days=int(rng.integers(2, 5)))


def _historical_panel(
    mean_price: float,
    elasticity: float,
    demand_index: float,
    capacity: int,
    days: int = 90,
    rng: np.random.Generator | None = None,
) -> List[Tuple[date, float, int, bool]]:
    """Simulate ``days`` (date, price, tickets_sold, promo_flag) observations.

    Prices wobble ±12% around the mean; a small share of days carry a promo
    that discounts an additional ~8%. Tickets sold is drawn from a Poisson
    with mean equal to a log-log demand curve, then capped at capacity/40
    (a rough per-day sales ceiling — no arena sells its full 20K in one day).
    """
    rng = rng or np.random.default_rng(SEED)
    # Anchor daily volume well below the capacity ceiling so the elasticity
    # signal is never smothered by the cap on hot-demand days — the goal is
    # for the OLS fit to recover a slope close to ``elasticity``.
    base_qty = max(capacity / 140.0, 20.0)
    obs: List[Tuple[date, float, int, bool]] = []
    start = date.today() - timedelta(days=days)
    daily_cap = max(int(capacity / 12), 200)

    # Solve intercept so that at (price=mean, promo=0) the expected qty ≈ base_qty:
    # log(base_qty) = beta_0 + elasticity * log(mean_price)  →  beta_0 = ...
    beta_0 = math.log(base_qty) - elasticity * math.log(mean_price)

    for i in range(days):
        d = start + timedelta(days=i)
        price_noise = rng.normal(loc=1.0, scale=0.06)
        promo = rng.random() < 0.15
        promo_factor = 0.92 if promo else 1.0
        price = mean_price * price_noise * promo_factor
        # Demand curve → mean tickets sold today.
        expected_qty = math.exp(beta_0 + elasticity * math.log(price)) * demand_index
        # A tiny weekend bump.
        if d.weekday() >= 5:
            expected_qty *= 1.15
        # Poisson draw for count-y realism, capped at the daily ceiling.
        qty = int(min(rng.poisson(max(expected_qty, 0.1)), daily_cap))
        obs.append((d, round(float(price), 2), qty, promo))
    return obs


def _demand_signal_panel(
    demand_index: float,
    days: int = 60,
    rng: np.random.Generator | None = None,
) -> List[dict]:
    rng = rng or np.random.default_rng(SEED + 1)
    start = date.today() - timedelta(days=days)
    signals: List[dict] = []
    trend = rng.normal(loc=1.005, scale=0.005)  # slight day-over-day drift
    momentum = 1.0
    for i in range(days):
        momentum *= trend
        # Recent 7 days get a small bump so demand_momentum > 1 for hot markets.
        if i >= days - 7:
            momentum *= 1.02
        base = 1200.0 * demand_index * momentum
        page_views = int(max(rng.normal(base, base * 0.15), 0))
        unique_visitors = int(page_views * rng.uniform(0.55, 0.7))
        add_to_cart = int(unique_visitors * rng.uniform(0.04, 0.09))
        search_idx = float(np.clip(50 * demand_index + rng.normal(0, 6), 0, 100))
        signals.append(
            {
                "date": start + timedelta(days=i),
                "page_views": page_views,
                "unique_visitors": unique_visitors,
                "add_to_cart_count": add_to_cart,
                "search_interest_index": round(search_idx, 2),
            }
        )
    return signals


# ---------------------------------------------------------------------------
# Main seed routine
# ---------------------------------------------------------------------------

def seed(db: Session, keep_existing: bool = False) -> None:
    if not keep_existing:
        # Drop-and-create so re-seeding produces stable ids/values.
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    rng = np.random.default_rng(SEED)
    random.seed(SEED)

    dates = list(_tour_dates())

    for city_cfg, event_date in zip(CITIES, dates):
        venue = Venue(
            venue_name=city_cfg.venue_name,
            city=city_cfg.city,
            state=city_cfg.state,
            country=city_cfg.country,
            capacity=city_cfg.capacity,
        )
        db.add(venue)
        db.flush()

        event = Event(
            artist_name=TOUR_ARTIST,
            tour_name=TOUR_NAME,
            event_name=f"{TOUR_ARTIST} — {city_cfg.city}",
            venue_id=venue.id,
            event_date=datetime.combine(event_date, datetime.min.time()).replace(hour=20),
            category="Concert",
        )
        db.add(event)
        db.flush()

        # Fixed cost per event: production, venue rental, freight.
        # Scale roughly with capacity: bigger rooms → richer prod budgets.
        fixed_cost = round(150_000 + city_cfg.capacity * 4.5, 2)

        # Per-tier tickets. Sell-through is drawn from demand_index so hotter
        # cities have higher fill rates.
        target_sell_through = float(np.clip(city_cfg.demand_index * 0.6, 0.35, 0.95))
        for tier_name, tier_mult in PRICE_TIERS:
            face_value = round(city_cfg.mean_price * tier_mult, 2)
            allocated = int(city_cfg.capacity * TIER_ALLOCATION[tier_name])
            noise = rng.normal(1.0, 0.05)
            sold = int(min(allocated, allocated * target_sell_through * noise))
            variable_cost = round(face_value * 0.14 + 4.5, 2)  # rev share + processing
            db.add(
                Ticket(
                    event_id=event.id,
                    price_tier=tier_name,
                    face_value=face_value,
                    quantity_available=allocated,
                    quantity_sold=max(0, sold),
                    variable_cost_per_ticket=variable_cost,
                    fixed_cost_per_event=fixed_cost,
                )
            )

        # Demand signals — 60 days.
        for row in _demand_signal_panel(city_cfg.demand_index, rng=rng):
            db.add(DemandSignal(event_id=event.id, **row))

        # Historical pricing panel — 90 days.
        for d, price, qty, promo in _historical_panel(
            mean_price=city_cfg.mean_price,
            elasticity=city_cfg.elasticity,
            demand_index=city_cfg.demand_index,
            capacity=city_cfg.capacity,
            rng=rng,
        ):
            db.add(
                HistoricalPricing(
                    event_id=event.id,
                    observation_date=d,
                    avg_price=price,
                    tickets_sold=qty,
                    promo_flag=promo,
                )
            )

    # OKR targets. The base tour above generates ~$40M in revenue; set a
    # target that a strategy owner would actually get bonused on hitting.
    okr_rows = [
        OkrTarget(
            segment=DEFAULT_OKR_SEGMENT,
            annual_revenue_target=55_000_000.0,
            annual_margin_target=18_000_000.0,
        ),
        OkrTarget(
            segment="Concerts_NA_2025",
            annual_revenue_target=48_000_000.0,
            annual_margin_target=15_500_000.0,
        ),
        OkrTarget(
            segment="Concerts_EU_2026",
            annual_revenue_target=30_000_000.0,
            annual_margin_target=10_000_000.0,
        ),
    ]
    db.add_all(okr_rows)

    db.commit()


def main() -> None:  # pragma: no cover - CLI wrapper
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Skip DROP TABLE — append to whatever is already in the DB.",
    )
    args = parser.parse_args()

    create_all()
    db = SessionLocal()
    try:
        seed(db, keep_existing=args.keep)
        print(
            f"Seeded {len(CITIES)} events across {len({c.city for c in CITIES})} cities "
            f"for tour '{TOUR_NAME}'."
        )
    finally:
        db.close()


if __name__ == "__main__":  # pragma: no cover
    main()
