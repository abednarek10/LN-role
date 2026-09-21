# Strategic Angle & Hypothesis

**Working title:** Ticketmaster Market & Pricing Strategy Workbench

## Hypothesis

If Ticketmaster strategy managers have a unified tool that
- ingests structured event and market data,
- runs simple but explicit demand and profitability models, and
- visualizes trade-offs across markets and price points,

then they can allocate dates, marketing, and pricing much more efficiently —
improving revenue and contribution margin per tour, and giving leaders a
clean view of OKR impact.

## The business problem

The strategy team continuously answers three questions:

1. **In which markets should we add or prioritize shows?**
2. **At what price levels do we maximize contribution margin without killing demand?**
3. **How do these choices roll up to company-level OKRs — revenue growth,
   EBITDA margin, market share, engagement?**

Today those answers live in SQL queries, XLS models, BI dashboards, and
ad-hoc decks. That slows decisions, makes experiments hard to compare, and
obscures the trade-offs.

## The product

A single-page workbench with four connected views:

- **Market Overview** — table + KPIs for every event on a tour, ranked by
  a 0–100 opportunity score.
- **Price & Demand** — a per-event log-log elasticity fit with a
  contribution-margin-maximizing recommended price range and a plain-English
  narrative.
- **Scenario Simulator** — pick events, adjust price (%) or ($), optionally
  add a show per city, and see revenue, margin, and OKR-progress deltas
  against baseline.
- **OKR Alignment** — every segment's actual vs annual revenue and margin
  target.

## Users

- **Primary:** Manager, Strategy — Ticketmaster
- **Secondary:** FP&A analyst, PM for ticketing / pricing
- **Executive read-out:** leaders reviewing tour-level performance and
  progress against annual OKRs.

## What "success" looks like

- A strategy manager can go from "which cities on this tour are
  under-performing?" to a defensible, numbered recommendation in **under
  five minutes**.
- Every number on every screen traces back to a **named formula** in one
  service file — no undocumented Excel column, no hidden BI calculation.
- The same analytical logic exists **twice**: as Python for the API, and
  as SQL for the warehouse. A finance analyst can rebuild every metric in
  Tableau/Power BI without asking engineering.

## Why the log-log elasticity model, and not something fancier?

Because the audience is a strategy leadership team, not a data-science
review. Log-log OLS is:

- **Transparent**: β₁ is *the* number every economist and every strategy
  team already talks about (own-price elasticity of demand).
- **Cheap enough** to fit per event on demand — no offline pipeline,
  no model store.
- **Directly interpretable** into a decision: is this market inelastic
  (raise price), elastic (protect volume), or unit-elastic (hold)?

The architecture doesn't preclude a heavier estimator — the elasticity
service is a single module, and both the scenario engine and the UI
consume its interface. Swap it for a Bayesian hierarchical model or a DML
setup without touching the rest of the stack.

## Why now / why this posting

Live Nation Entertainment's core moat is the primary ticketing marketplace,
and Ticketmaster's ability to price and place dates well against a
capacity-constrained supply of arena-nights is one of the most direct
levers on EBITDA. A strategy manager who can operationalize that lever —
turn multi-tool analysis into a repeatable workbench a team can trust —
compounds over every tour cycle.
