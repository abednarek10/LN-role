# API Reference

All endpoints return JSON. Live OpenAPI docs at
[http://localhost:8000/docs](http://localhost:8000/docs) when the server
is running.

## `GET /api/health`
Cheap liveness probe.
```json
{ "status": "ok" }
```

## `GET /api/events/overview`
Returns the Market Overview payload.

**Query params (all optional):**
- `city` — case-insensitive substring
- `artist_name` — case-insensitive substring
- `tour_name` — case-insensitive substring
- `category` — exact match (e.g. `Concert`)
- `date_from`, `date_to` — ISO 8601 timestamps

**Response shape:**
```json
{
  "summary": {
    "total_revenue": 24824520.0,
    "avg_margin_pct": 0.5162,
    "avg_sell_through": 0.6489,
    "top_cities": [
      { "city": "Los Angeles", "avg_opportunity": 90.3, "event_count": 1 },
      ...
    ],
    "event_count": 15
  },
  "events": [
    {
      "event_id": "...",
      "event_name": "Astra Vale — New York",
      "artist_name": "Astra Vale",
      "tour_name": "Neon Skyline World Tour",
      "city": "New York", "state": "NY", "venue_name": "Madison Square Garden",
      "event_date": "2026-03-05T20:00:00",
      "avg_ticket_price": 172.53,
      "tickets_available": 20000, "tickets_sold": 15490,
      "sell_through": 0.7745,
      "gross_revenue": 3191479.5,
      "contribution_margin": 2110452.1,
      "market_opportunity_score": 81.6,
      "demand_momentum": 1.043,
      "recommended_price": 224.29
    },
    ...
  ]
}
```

## `GET /api/events/{event_id}`
Single event row from the overview shape. Returns 404 if unknown.

## `GET /api/events/{event_id}/elasticity`
Fits `log(q) = β₀ + β₁·log(p)` on this event's `historical_pricing`
panel and returns:

```json
{
  "event_id": "...",
  "event_name": "Astra Vale — New York",
  "model_type": "log-log",
  "beta_0": 8.13, "beta_1": -0.9,
  "r_squared": 0.30, "sample_size": 90,
  "current_price": 172.53, "current_tickets_sold": 15490,
  "recommended_price": 224.29,
  "recommended_price_low": 213.08,
  "recommended_price_high": 235.50,
  "revenue_at_current": 3191479.5,
  "revenue_at_recommended": 39222.33,
  "margin_at_recommended": 34210.98,
  "elasticity_verdict": "unit-elastic",
  "narrative": "Demand for this event is unit-elastic (elasticity ≈ -0.90, R² = 0.30, n = 90). ...",
  "data_points": [{ "avg_price": 168.4, "tickets_sold": 47 }, ...],
  "price_grid_predictions": [
    { "price": 129.4, "predicted_tickets_sold": 63.5, "predicted_revenue": 8221, "predicted_contribution_margin": 6754 },
    ...
  ]
}
```

## `POST /api/scenario/simulate`

**Body:**
```json
{
  "event_ids": ["...", "..."],
  "price_adjustment_type": "percent",   // or "absolute"
  "price_adjustment_value": 10.0,        // interpret per the type
  "add_extra_show": true
}
```

**Response:**
```json
{
  "baseline_revenue": 8_500_000.0,
  "scenario_revenue": 9_320_000.0,
  "baseline_margin": 4_100_000.0,
  "scenario_margin": 4_760_000.0,
  "delta_revenue": 820_000.0,
  "delta_margin": 660_000.0,
  "delta_revenue_pct": 0.0964,
  "delta_margin_pct": 0.161,
  "okr_segment": "Concerts_NA_2026",
  "okr_revenue_target": 55_000_000.0,
  "okr_progress_baseline": 0.1545,
  "okr_progress_scenario": 0.1694,
  "okr_progress_delta_pts": 1.49,
  "extra_show_events_added": 3,
  "narrative": "Scenario applied +10.0% price move, +1 show per city ...",
  "per_event": [ ... ]
}
```

`per_event` includes a synthetic row per extra show (with `event_id`
prefixed `extra-`) so the frontend chart can display it beside real
events.

## `GET /api/okr/summary`
Segment-level rollup joined against `okr_targets`.

```json
{
  "default_segment": "Concerts_NA_2026",
  "segments": [
    {
      "segment": "Concerts_NA_2026",
      "annual_revenue_target": 55_000_000.0,
      "annual_margin_target": 18_000_000.0,
      "actual_revenue_to_date": 24_824_520.0,
      "actual_margin_to_date": 12_805_100.0,
      "revenue_progress_pct": 0.4514,
      "margin_progress_pct": 0.7114,
      "events_counted": 15
    },
    ...
  ]
}
```
