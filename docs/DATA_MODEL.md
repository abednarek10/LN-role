# Data Model

The schema mirrors the PRD in `STRATEGY.md`. UUIDs are stored as `CHAR(36)`
strings so SQLite and Postgres share the same DDL.

## Entity-relationship

```
   venues 1 ───────< events 1 ────< tickets
                       │
                       ├─────< demand_signals
                       └─────< historical_pricing

   okr_targets  (independent; joined at query-time via segment key)
```

## Tables

### `venues`
| column | type | notes |
| :-- | :-- | :-- |
| id | uuid PK | |
| venue_name | text | e.g. "Madison Square Garden" |
| city | text, indexed | analysis rolls up on this |
| state | text | |
| country | text | default `USA` |
| capacity | int | seat count (ceiling for total tickets) |

### `events`
| column | type | notes |
| :-- | :-- | :-- |
| id | uuid PK | |
| artist_name | text, indexed | |
| tour_name | text, indexed | logical grouping |
| event_name | text | display label |
| venue_id | uuid FK | → venues.id |
| event_date | timestamp, indexed | |
| category | text | `Concert` / `Sports` / `Theatre` |

### `tickets`
One row per price tier per event (Nosebleed, Standard, Premium, VIP by
default).

| column | type | notes |
| :-- | :-- | :-- |
| id | uuid PK | |
| event_id | uuid FK | → events.id |
| price_tier | text | |
| face_value | numeric | printed face value |
| quantity_available | int | allocation of the venue capacity |
| quantity_sold | int | |
| variable_cost_per_ticket | numeric | rev share + processing (~14% + $4.50 in seed) |
| fixed_cost_per_event | numeric | allocated equally across tiers so any single tier row carries the whole event fixed cost — see `services/metrics.fixed_cost_total` |

**Convention:** `fixed_cost_per_event` is written identically to every
tier row for the same event so a SQL rollup can safely use
`MAX(fixed_cost_per_event)` to avoid double-counting. Python code uses
the same pattern (`services/metrics.fixed_cost_total`).

### `demand_signals`
Daily panel per event.

| column | type | notes |
| :-- | :-- | :-- |
| id | uuid PK | |
| event_id | uuid FK | → events.id |
| date | date, indexed | |
| page_views | int | |
| unique_visitors | int | |
| add_to_cart_count | int | |
| search_interest_index | numeric | 0–100 scaled |

### `historical_pricing`
The (price, tickets sold) panel that the elasticity model fits.

| column | type | notes |
| :-- | :-- | :-- |
| id | uuid PK | |
| event_id | uuid FK | → events.id |
| observation_date | date, indexed | |
| avg_price | numeric | sales-weighted avg for the day |
| tickets_sold | int | that day's volume |
| promo_flag | boolean | `true` on the ~15% of days with a promo discount |

### `okr_targets`
| column | type | notes |
| :-- | :-- | :-- |
| id | uuid PK | |
| segment | text UNIQUE | `<Category>s_<Region>_<Year>` |
| annual_revenue_target | numeric | |
| annual_margin_target | numeric | contribution margin, not accounting EBITDA |

Segment key mapping is derived in `backend/routers/okr._segment_for_event`
and matched verbatim in `backend/sql/okr_progress.sql`.

## Derived fields — one canonical definition each

| Field | Definition | Home |
| :-- | :-- | :-- |
| Gross revenue | Σ face_value × quantity_sold across tiers | `services/metrics.gross_revenue` and `sql/event_economics.sql` |
| Contribution margin | revenue − Σ variable_cost×sold − fixed_cost (once) | same as above |
| Sell-through | Σ sold / Σ available | same |
| Avg ticket price | Sales-weighted average across tiers; falls back to face-value mean when nothing sold | `services/metrics.avg_ticket_price` |
| Demand momentum | Mean(page_views last 7d) / Mean(page_views trailing 30d) | `services/metrics.demand_momentum` and `sql/market_prioritization.sql` |
| Market Opportunity Score (0–100) | 0.40 × sell-through + 0.35 × momentum-clip + 0.25 × price-gap-clip | `services/metrics.OpportunityInputs.score` |
| Elasticity β₁ | Slope of `log(qty) = β₀ + β₁·log(price) + ε` | `services/elasticity.fit_log_log` |
| Recommended price | argmax_p contribution_margin(p) on ±25–30% grid | `services/elasticity.revenue_maximizing_price` |
