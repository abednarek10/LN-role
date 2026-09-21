# Methodology

Every quantitative decision in the workbench is documented here — no
"black-box scores".

## 1 · Contribution margin (per event)

```
gross_revenue        = Σ_tier face_value × quantity_sold
variable_cost_total  = Σ_tier variable_cost_per_ticket × quantity_sold
fixed_cost_allocated = max_tier(fixed_cost_per_event)  ← every tier stores
                                                         the same value;
                                                         MAX() dedupes it
contribution_margin  = gross_revenue − variable_cost_total − fixed_cost_allocated
```

Why contribution margin, not full EBITDA? Because the strategy team's
decisions (add a date, move a price tier) impact contribution — corporate
overhead, D&A, and interest expense are downstream. Contribution is the
right marginal-decision metric.

## 2 · Sell-through and demand momentum

```
sell_through        = Σ quantity_sold / Σ quantity_available
demand_momentum     = mean(page_views, last 7d) /
                      mean(page_views, trailing 30d)
```

Momentum is a scalar ratio: `1.0` means demand is flat, `1.2` means the
recent week is 20% above the 30-day baseline. When there aren't enough
observations to compute either window, we fall back to `1.0` (neutral)
rather than fabricate a signal.

## 3 · Market Opportunity Score

A 0–100 weighted heuristic. The weights are visible and unashamed:

```
score = 100 × (
    0.40 × clip(sell_through, 0, 1)
  + 0.35 × clip((momentum − 0.5) / 1.0, 0, 1)     # 0.5 → 0, 1.5 → 1
  + 0.25 × clip((price_gap_pct + 0.15) / 0.45, 0, 1)  # −0.15 → 0, +0.30 → 1
)
```

`price_gap_pct = (recommended_price − current_price) / current_price`.
A positive gap = current price is below the model's optimum = more upside.

This same formula lives twice: once in Python
(`services/metrics.OpportunityInputs.score`) and once in SQL
(`sql/market_prioritization.sql`) so a BI user can rebuild the ranking
without touching the API.

## 4 · Price elasticity (log-log OLS)

```
log(tickets_sold) = β₀ + β₁ · log(avg_price) + ε
```

- β₁ is the own-price elasticity of demand.
- Fitted per event on the `historical_pricing` panel (default 90 days).
- Observations with non-positive price or quantity are dropped (log
  undefined). Fewer than three usable observations → return a trivial
  fit and surface the small sample size to the user via `sample_size`.

### Recovering the seeded elasticity

The seed generator draws quantities from a Poisson centred on the true
log-log curve, so we can measure how well OLS recovers β₁:

| City | Seeded β₁ | Recovered β₁ | R² |
| :-- | :--: | :--: | :--: |
| New York | −0.85 | ≈ −0.90 | ≈ 0.30 |
| Chicago | −1.05 | ≈ −1.13 | ≈ 0.39 |
| Boston | −1.00 | ≈ −1.23 | ≈ 0.40 |
| Nashville | −1.30 | ≈ −1.25 | ≈ 0.46 |

Poisson noise + a 15% share of promo days keeps R² honest — the model
learns real structure but never claims a fit it doesn't have.

## 5 · Recommended price

Given a fit, we scan a **grid of prices bounded to ±25–30% of the current
price** and pick the argmax of predicted **contribution margin** (not raw
revenue):

```
predicted_qty(p)     = exp(β₀) · p^β₁
predicted_margin(p)  = (p − variable_cost_per_ticket) · predicted_qty(p)
recommended_price    = argmax_p predicted_margin(p)   for p in grid
```

Why the ±25–30% bound? Because for inelastic demand (β₁ > −1) raw revenue
is monotonically increasing in price and the "optimum" runs to infinity —
mathematically valid, strategically absurd. The bound encodes a real
strategic constraint (churn risk, brand, political optics) rather than
letting the model report a nonsense number.

## 6 · Scenario projection

For each selected event:

```
baseline_qty            = actual tickets_sold today
baseline_revenue        = actual gross_revenue
baseline_margin         = actual contribution_margin

scenario_price          = adjust(baseline_avg_price, % or $)
predicted_baseline_qty  = fit.predict_qty(baseline_avg_price)
scale                   = baseline_qty / predicted_baseline_qty
scenario_qty            = min(fit.predict_qty(scenario_price) · scale,
                              capacity)
scenario_revenue        = scenario_price · scenario_qty
scenario_margin         = (scenario_price − variable_cost) · scenario_qty
                          − fixed_cost
```

**Scale factor.** A 0% price move must reproduce today's actual volume,
so we normalise the log-log prediction by the ratio of actual to
predicted at the baseline price. That keeps the elasticity model as the
source of *marginal* change while anchoring absolute levels to reality.

**Capacity ceiling.** Predicted quantity is capped at the event's total
available tickets so a scenario can't sell more seats than the venue
holds.

**Extra shows.** When the toggle is on, we add one synthetic event per
city equal to 85% of the best-performing scenario in that city (a
mid-teens cannibalization). Its baseline is zero, so the whole
projection lands in the delta column.

## 7 · OKR progress

```
segment_key           = "<Category>s_<Region>_<Year>"
revenue_progress_pct  = Σ(actual_revenue_in_segment) /
                        okr_targets.annual_revenue_target
scenario_progress_pct = Σ(scenario_revenue_in_segment) /
                        okr_targets.annual_revenue_target
delta_pts             = 100 × (scenario_progress_pct − baseline_progress_pct)
```

`delta_pts` is what the scenario view reports as "+X.YZ pts vs annual
target" — a percentage-point movement, not a percentage change of a
percentage.

## 8 · Data-quality guardrails

| Guardrail | Why |
| :-- | :-- |
| Sales-weighted avg price falls back to face-value mean when sold = 0 | Brand-new on-sale events don't crash the API. |
| Log-log fit returns a trivial (β₁ = −1, R² = 0) fit when `n < 3` | Downstream code always gets a valid `ElasticityFit`. |
| Recommended price is bounded to ±25–30% of current | Prevents nonsense recommendations on inelastic demand. |
| Fixed cost taken as `MAX` across tiers | Prevents double-counting when the same fixed cost is written to every tier row. |
| Predicted quantity capped at capacity | No forecast sells more seats than the venue holds. |
| Scenario prediction rescaled so 0% move ⇒ 0 volume Δ | Users see baseline == scenario for a null intervention. |
