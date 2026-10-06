# CTO Memo — Round 1: Ignition Technical Design

**To:** CEO, CRO, CPO · **From:** CTO · **Re:** Architecture, data, ML, API for Ignition v1

## 1. Module layout

```
electronx/
  ignition/
    config.py      # IGNITION_DB_URL, SEED, AS_OF, ANTHROPIC_API_KEY
    database.py    # Base, engine, get_db, create_all
    models.py
    seed.py        # python -m ignition.seed --reset
    services/      # PURE: DataFrames in, dicts out. No Session.
      prices.py volatility.py propensity.py activation.py funnel.py
      segments.py liquidity.py comp.py marketing.py memo.py outreach.py
    repo.py        # DB -> DataFrame loaders (only SQL touchpoint)
    routers/       # accounts, activation, pulse, scoring, funnel, segments, team, marketing, ceo, outreach
    content/       # outreach templates, playbooks, NBA catalog
    main.py        # lifespan: create_all, seed-if-empty, warm caches
  frontend/        # index.html, app.js, styles.css, chart.umd.js
  tests/           # test_services_*, test_api_*, test_seed, test_perf
```

Routers: `repo` load → service → Pydantic response.

## 2. Data model

| Table | Columns (type) | Indexes |
|---|---|---|
| reps | id int PK, name str, role str (AE/Strategic/SE), quota_adv float, start_date date | — |
| accounts | id int PK, name str, segment str, primary_iso str, exposure_isos str (CSV), hub str, est_annual_mwh float, tam_tier str(A/B/C), lead_source str, rep_id FK, stage str, signed_at/funded_at/first_trade_at datetime null, latent_propensity float (seed-only, never exposed to features) | segment, primary_iso, stage, rep_id |
| contacts | id, account_id FK, name, title, persona str (trader/risk/CFO/ops), email | account_id |
| activities | id, account_id FK, rep_id FK, ts datetime, kind str (email/call/meeting/demo/triggered_email), outcome str (none/reply/meeting), trigger_id str null | (account_id, ts), rep_id |
| onboarding_events | id, account_id FK, ts datetime, step str (signed/kyc_started/kyc_approved/funded/first_login/api_key/first_order/first_trade) | (account_id, step), (step, ts) |
| trades | id, account_id FK, ts datetime, iso str, hub str, tenor str (hourly/daily/weekly), side str, mw float, price float, notional float, fee float | (account_id, ts), (iso, ts), ts |
| market_prices | iso str, hub str, ts datetime (hour-ending, UTC), lmp float — composite PK (hub, ts) | (iso, ts) |
| spread_snapshots | date date, iso str, hub str, tenor str, bid_ask_bps float, top_depth_mw float, active_accounts int | (hub, date) |
| marketing_spend | id, month date, channel str, spend float, leads int | (channel, month) |

~45k price rows, ~60k trades, ~25k activities.

## 3. Synthetic data realism

All from `numpy.random.default_rng(SEED)`; `AS_OF` fixed (2026-10-05) so the demo never drifts.

- **Accounts (600)** across the 8 segments, weighted (C&I 20%, IPP 15%, REP 12%, Utility 12%, Storage 10%, DC Dev 8%, Prop 12%, Fund 11%). ISO by segment realism (storage/DC heavy ERCOT; utilities PJM/MISO; IPP solar CAISO). Size lognormal by segment.
- **Hubs:** ERCOT HB_NORTH, HB_HOUSTON, HB_WEST; PJM WESTERN HUB; CAISO SP15, NP15; MISO INDIANA HUB.
- **Prices (270 days hourly):** base = ISO level × daily shape × season × AR(1) noise (lognormal). ERCOT: summer 16–20h scarcity draws (Poisson) to $1,000–5,000 with $5,000 cap; CAISO: duck curve with midday solar trough, P≈0.25 of spring midday hours negative (−$5 to −$40), steep 18–20h ramp; PJM/MISO: winter dual peaks (7–9h, 17–20h) and a cold-snap week to $300–900. Hubs within an ISO share 85% of the shock plus basis noise. **Injected event:** ERCOT HB_NORTH/HB_HOUSTON, `AS_OF−3d`, 6–9 consecutive hours at $2,200–4,800.
- **Funnel:** latent `z = segment_effect + 0.6·log(size) + rep_skill + persona_fit + N(0,1)`; propensity = sigmoid(z). Each step's pass probability and dwell time (gamma) depend on propensity and segment (prop/funds fast to trade, utilities slow KYC). Observable proxies (meetings, first_login lag, api_key creation, contacts count) correlate with z so the model can recover it (target AUC ≈ 0.75–0.82, not 0.99).
- **Trades:** per active account, Poisson arrivals scaled by propensity; size Pareto(α≈1.6) clipped, so top 10% of accounts ≈ 60% of ADV. Speculators trade more around spikes.
- **Spreads:** `bps = a + b / sqrt(active_accounts_t)` + noise, widened on spike days — the flywheel is visible on a chart.
- **Activities/marketing:** triggered touches lift reply rate ~1.8×; channels have distinct CAC.

## 4. ML: propensity model

- **Target:** first trade within 45 days of `funded_at` (or of signing for pre-funded scoring).
- **Features (as of snapshot t):** segment/ISO one-hot, log size, days since signed, steps completed, days in step, touches 14/30d, meetings, reply rate, contacts, trader persona, api_key, first-login lag, ISO 30d vol.
- **Model:** `StandardScaler` + `LogisticRegression(C=1.0, class_weight="balanced")` as production; `HistGradientBoostingClassifier` as challenger shown side-by-side. **Reasons:** per-account contribution = coef_j × standardized x_j; top 3 positive/negative mapped to plain-English labels from `content/`.
- **Split by time:** train on accounts with snapshot t ≤ AS_OF−105d whose 45d label is fully observed; test on t in (AS_OF−105d, AS_OF−45d]. Score live on all open accounts.
- **Leakage controls:** features computed by a single `features_as_of(t)` function filtering every event `ts < t`; label window strictly after t; `latent_propensity` and future stages never read; unit test asserts feature values unchanged when post-t rows are deleted.
- **Metrics:** ROC-AUC, PR-AUC, Brier, lift@decile + gain curve, calibration.
- **Activation EV** = P(activate) × expected ADV (segment-size regression) × urgency (stall age, active trigger).

## 5. Volatility trigger

Per hub, on hourly LMP at evaluation time T (default latest hour):

1. **Spike hours** `S = #{h ∈ (T−72h, T] : lmp_h > max(P99 of trailing 30d, ISO floor)}`; ISO floors: ERCOT $1,000, others $250. CAISO also counts **negative** hours `N` (lmp < 0).
2. **Realized vol** `RV72 = std(Δ asinh(lmp/10))` over 72h (asinh handles negatives/spikes). `z = (RV72 − mean RV72_rolling_30d) / std(...)`.
3. **Fire** if `S ≥ 3` or `z ≥ 2.5` (or `N ≥ 12` in CAISO). Severity = `min(100, 20·S + 15·max(z,0))`; regime label: scarcity / negative-price / winter-peak / elevated-vol.
4. **Exposure mapping:** accounts with the hub's ISO in `exposure_isos`; exposure score = severity × segment sensitivity (REP, DC, C&I, storage high; prop/fund high on opportunity) × size; exclude accounts touched in the last 5 days. Output feeds the Activation Queue urgency and Outreach drafts (event facts: peak $, hours, hub).

## 6. API surface (all GET unless noted, JSON, prefix `/api`)

| Path | Params | Response sketch |
|---|---|---|
| /health | — | `{status}` |
| /accounts | segment, iso, stage, rep_id, q, limit, offset | `{total, items:[{id,name,segment,iso,stage,score,adv_30d}]}` |
| /accounts/{id} | — | Account 360: `{account, contacts, timeline, adv_series, health, reasons, plays}` |
| /activation/queue | segment, iso, rep_id, limit | `[{account, p_activate, exp_adv, urgency, ev, stall_step, next_action, reasons}]` |
| /pulse/hubs | iso, hours=168 | `{hubs:[{hub, series:[{ts,lmp}], stats}]}` |
| /pulse/triggers | as_of | `[{hub, regime, severity, spike_hours, vol_z, peak_price, exposed_count}]` |
| /pulse/triggers/{hub}/accounts | limit | `[{account, exposure_score, segment, last_touch}]` |
| /scoring/model | — | `{auc, pr_auc, brier, lift_top_decile, gain_curve, calibration, coefs, challenger:{...}}` |
| /funnel | segment, iso | `{steps:[{step, n, conv, median_days}], friction:[{step, segment, delta, ask}]}` |
| /segments | — | `[{segment, iso, tam, accounts, penetration, activation_rate, adv_per_acct}]` |
| /liquidity | iso, tenor | `{series:[{date, bps, depth, active_accounts}], elasticity}` |
| /team/scorecards | period | `[{rep, funded, activated, adv, touches, attainment}]` |
| POST /team/comp-sim | body `{plan:{w_sign,w_fund,w_activate,w_adv}}` | `[{rep, payout, mix}]` |
| /marketing/roi | months | `[{channel, spend, leads, funded, active, cac_funded, cac_active, adv_per_dollar}]` |
| /ceo/weekly | week_end | `{kpis, deltas, mix, spreads, risks}` |
| /ceo/weekly.md | week_end | text/markdown memo |
| POST /outreach/draft | body `{account_id, trigger_hub?, tone}` | `{subject, body, engine:"claude"|"template", facts}` |

## 7. Testing & quality bar

- **Seed:** deterministic checksums; ERCOT event in last 7 days; CAISO negatives; corr(spread, active) < −0.6.
- **Services:** trigger fires/doesn't on hand-built series; holdout AUC ≥ 0.70, lift@decile ≥ 2.0, leakage test, reasons sum ≈ logit; funnel and comp math; outreach falls back to template without key or on API error/timeout.
- **API:** every endpoint 200 + shape on temp SQLite; 404s.
- **Performance:** every endpoint < 300ms on seed data (test_perf), via startup caching of model and price frames.

## 8. Risks

1. **Too-clean synthetic data** → add noise, outliers, honest AUC.
2. **Leakage** makes the model look magic → time split + leakage test.
3. **Domain credibility** — traders spot wrong hubs/shapes instantly; CRO reviews.
4. **Claude** latency/hallucinated prices → pass computed facts only; fallback.
5. **Scope creep** → ship W2, W3, W4, W1 first; others thin.
6. **SQLite→Postgres drift** → naive UTC datetimes, portable types.
