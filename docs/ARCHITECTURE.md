# Architecture

The workbench is deliberately monolithic and local-first: one FastAPI
process serving one SQLite database and one static frontend. That
constraint is a feature — reviewers should be able to `git clone`, install,
seed, and click through the tool inside 60 seconds.

## Layers

```
┌─────────── Frontend ────────────┐
│ Vanilla JS SPA, Chart.js via CDN │
│  ▸ Market Overview               │
│  ▸ Price & Demand                │
│  ▸ Scenario Simulator            │
│  ▸ OKR Alignment                 │
└──────────────┬───────────────────┘
               │  JSON HTTP
               ▼
┌────────── FastAPI ──────────────┐
│  routers/events, elasticity,     │
│  scenarios, okr                  │
│  → thin controllers, all         │
│    analytics live in services/    │
└──────────────┬───────────────────┘
               │
               ▼
┌────────── Services ─────────────┐
│  metrics.py     revenue, margin,  │
│                 opportunity score │
│  elasticity.py  log-log OLS,      │
│                 recommended price │
│  scenarios.py   baseline vs       │
│                 scenario + OKR    │
└──────────────┬───────────────────┘
               │
               ▼
┌────────── SQLAlchemy 2.0 ───────┐
│  events, venues, tickets,        │
│  demand_signals,                 │
│  historical_pricing, okr_targets │
└──────────────┬───────────────────┘
               │
               ▼
        SQLite (default) or Postgres
        (swap via WORKBENCH_DB_URL)
```

## Why these choices

- **FastAPI** gives us typed routes with automatic OpenAPI docs at
  `/docs`, which is the right primitive for an "API-first" strategy tool.
- **SQLAlchemy 2.0** models are close enough to Postgres DDL that a
  warehouse migration is a change of URL, not a rewrite.
- **SQLite** keeps the demo dead-simple; nothing in the schema or the
  service code assumes a Postgres-only feature.
- **Vanilla JS + Chart.js from CDN** avoids npm entirely. The tradeoff:
  no component reuse, no type system. The gain: any strategy analyst can
  read `frontend/app.js` end-to-end in ten minutes.
- **No caching layer.** Elasticities re-fit on request. Deliberate: the
  data volume is small, request latency is <100ms, and cache invalidation
  would obscure the "every number traces back to a formula" property.

## Request flow — a scenario run

```
UI clicks "Run Scenario"
   └─ POST /api/scenario/simulate {event_ids, price_adj, extra_show}
        └─ scenarios.router loads Events (+tickets, +historical_pricing)
             └─ for each Event:
                  services.scenarios.simulate
                     ├─ services.metrics.avg_ticket_price / gross_revenue / contribution_margin  (baseline)
                     ├─ services.elasticity.fit_log_log        (recover β₀, β₁)
                     └─ scale-and-project to scenario price     (respecting capacity)
             └─ rollup baseline / scenario / delta
             └─ join OkrTarget → OKR progress delta
             └─ services.scenarios.build_narrative
        └─ ScenarioResponse
```

## Extensibility

- **Swap the estimator** by adding a new service (e.g. `elasticity_bayes.py`)
  that returns the same interface: an `ElasticityFit`-shaped object plus
  a `predict_qty(price)` method. Nothing else changes.
- **Add a data source** by creating a new SQLAlchemy model plus a router.
  The frontend picks it up as another view.
- **Wire a warehouse** by setting `WORKBENCH_DB_URL` to a Postgres or
  Redshift DSN and re-running `python -m backend.seed --keep` (or your
  own ETL).
