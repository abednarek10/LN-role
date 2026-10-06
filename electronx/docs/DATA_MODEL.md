# Ignition — Data Model, Generators & Calibration

**Owner:** Data agent · **Status:** matches `ignition/models.py`, `ignition/seed.py`,
`ignition/services/{features,propensity,volatility}.py` at seed `IGNITION_SEED=42`.
All data is **synthetic and illustrative**. Company and person names are invented,
e-mails use the reserved `.example` TLD, and no row describes a real firm.

```
python -m ignition.seed --reset            # rebuild electronx/data/ignition.db (~6 s, ~16 MB)
python -m ignition.seed --report           # calibration report (no DB writes)
python -m pytest -q                        # seed / model / trigger tests
```

---

## 1. Tables (spec §D; names are a contract)

All datetimes are naive UTC and all PKs are integers. Every FK column has an index.
Row counts are for seed 42.

| Table | Rows | Columns (beyond spec in *italics*) | Notes |
|---|---:|---|---|
| `reps` | 8 | id, name, role, region, quota_funded_annual, quota_adv, start_date | 4 AE (ERCOT, PJM, CAISO, MISO), 1 STRATEGIC, 2 REVOPS, 1 MARKETING. Only AE and STRATEGIC carry a book or quota. The MISO AE started 2026-03-02 and is ramping. |
| `accounts` | 600 | id, name, segment, primary_iso, exposure_isos (CSV), hub, hq_state, size_mw, est_annual_mwh, tam_tier, lead_source, rep_id, stage, is_liquidity_partner, has_other_exchange_account, kyc_redlines, created_at, signed_at, kyc_approved_at, funded_at, funded_amount_usd, first_trade_at, first_qualifying_trade_at, active_since, latent_propensity | `latent_propensity` is **seed-only** ground truth. Features and services never read it; only tests do. `active_since` is the start of the *current* Active spell (null if not Active now). |
| `contacts` | 1,409 | id, account_id, name, title, persona, email, is_champion | 1–5 per account. More stakeholders and a champion when engagement quality is higher. |
| `activities` | 11,654 | id, account_id, rep_id, ts, kind, outcome, trigger_id, sequence | `sequence` ∈ {nurture, activation, kyc_chase, volatility, null}. `trigger_id` is set only on volatility sequences (`ERCOT-HB_HOUSTON-20260702` format). |
| `onboarding_events` | 2,644 | id, account_id, ts, step | Steps follow `definitions.ONBOARDING_STEPS`. `kyc_info_requested` repeats. `activated` is written on the day the account first meets the Active rule. |
| `trades` | 25,475 | id, account_id, ts, iso, hub, tenor, side, contracts, price, notional_usd, fee_usd, is_maker | Weekdays 13:00–22:00 UTC from 2026-01-05. notional = contracts × MWh/contract × price. fee = contracts × $0.25 taker or $0.10 maker. |
| `market_prices` | 45,864 | hub, ts, iso, lmp — PK (hub, ts) | Hourly for 7 hubs from 2026-01-05 00:00 to 2026-10-04 23:00 (6,552 h each). |
| `price_forecasts` | 35 | *id*, hub, iso, date, forecast_peak_lmp, forecast_avg_lmp, issued_at | 5 days from AS_OF, issued 2026-10-04 18:00. ERCOT peaks on 10-07: HB_HOUSTON $1,650 and HB_NORTH $1,320. |
| `spread_snapshots` | 3,822 | *id*, date, iso, hub, tenor, spread_usd_mwh, two_sided_uptime_pct, top_depth_contracts, active_accounts, lp_quote_share | Daily per hub × {HOURLY, DAILY_PEAK}. `active_accounts` counts accounts that are Active and traded that ISO in the trailing 30 days. |
| `marketing_spend` | 84 | id, month, channel, spend_usd, leads, campaign | 12 months (2025-10 → 2026-09) × 7 channels. |
| `volatility_events` | 29 | id, *trigger_id*, hub, iso, start_ts, end_ts, regime, peak_lmp, spike_hours, severity | Precomputed by `services.volatility.detect_historical_events`. For `negative_price`, `peak_lmp` is the most negative price and `spike_hours` counts negative hours. |
| `outreach_drafts` | 0 | id, account_id, rep_id, trigger_id, created_at, subject, body, engine, status, compliance_flags | Written at runtime by the Engineering services. |

### Stage rule (`definitions.classify_stage`, single source)

| Stage | Rule at AS_OF (trading days = distinct weekdays with a fill in `[AS_OF−30d, AS_OF)`) |
|---|---|
| TARGET / QUALIFIED | not signed (QUALIFIED = exposure confirmed and worked by a rep) |
| SIGNED | contract signed, KYC not approved |
| KYC_APPROVED | KYC approved, not funded |
| FUNDED | funded, **never traded** (the "funded-not-trading" stall, at any age) |
| FIRST_TRADE | traded, 1–3 trading days, never been Active |
| ACTIVE | **≥ 4 trading days** in the trailing 30 |
| EXPANDING | Active, current spell ≥ 60 d, and trailing-30 ADV ≥ 1.5× first-60-day ADV or a new ISO traded |
| AT_RISK | was Active before, 1–3 trading days now |
| DORMANT | has traded before, 0 trading days in the trailing 30 |

`stage ∈ {ACTIVE, EXPANDING} ⇔ trading_days_30 ≥ 4` is asserted in `tests/test_seed.py`.
Health (`features.account_health().state`) follows the D2 literal: *dormant* = funded ≥ 30 d
with 0 trading days. That includes funded accounts that never traded, which keep stage `FUNDED`.

Stage counts at AS_OF:

| Stage | Accounts |
|---|---:|
| TARGET | 155 |
| QUALIFIED | 113 |
| SIGNED | 94 |
| KYC_APPROVED | 40 |
| FUNDED | 55 |
| FIRST_TRADE | 12 |
| ACTIVE | 101 |
| EXPANDING | 10 |
| AT_RISK | 12 |
| DORMANT | 8 |

---

## 2. Generators (`ignition/seed.py`)

The seed is deterministic and fast. Global draws (prices, account attributes, signing) use
`default_rng(SEED)`. Every account then gets **independent streams**, keyed
`default_rng([seed, kind, account_id])`, for activities, onboarding, trading and touches.
Each AE sequencing decision is a separate per-(account, day) coin flip, and the daily
first-trade hazard uses a fixed per-account uniform stream. Re-tuning one subsystem, such as
trade sizes, therefore never reshuffles another, such as the trigger experiment.

| Generator | Model |
|---|---|
| **Prices** | `level × season × intraday shape × weekend × exp(AR(1) ISO shock + AR(1) daily weather + hub basis)`. Hubs share 85% of the ISO shock. ERCOT has an evening peak and summer scarcity (random 1-hour spikes of $1,000–2,600). PJM and MISO have winter dual peaks. CAISO follows a duck curve, with spring midday negatives (−$1 to −$25). Injected events: PJM/MISO cold snap (Jan 26–29); ERCOT winter event (Feb 16); CAISO deep-negative weekends (Apr 11–12, May 2–3); ERCOT scarcity on May 12, Jun 1, Jun 17, **Jul 2**, Jul 20, Aug 5, Aug 18, Sep 3 and Sep 17; PJM heat (Jun 24, Jul 21, Aug 12); MISO (Jul 15, Sep 9); CAISO heat (Aug 26, Sep 8). The **demo event** (§5) and mild CAISO negatives on Oct 3–4 complete the set. No other spikes occur in the final 10 days. |
| **Accounts** | 600 total: CI_LOAD 120, IPP 90, REP 72, UTILITY 72, STORAGE 60, DATACENTER 48, PROP 72, FUND 66. 12 are liquidity partners (10 PROP, 2 FUND). ISO mix is by segment: storage, REPs and data centres lean ERCOT; utilities lean PJM/MISO; IPPs lean CAISO/ERCOT. Size is lognormal by segment. Tier A is the top 20% of size within a segment. |
| **Latent propensity** | `z = segment + lead_source + rep_skill + 0.25·size_z + 0.75·u + 0.55·ε`, with `p = σ(z − 0.1)` and LPs +2.0. `u` is account quality. Proxies see only `u_obs = u + N(0, 0.8)`, so they are informative but noisy. |
| **Signing** | 332 accounts are drawn without replacement with weight `exp(1.1·z)`. LPs sign Nov–Dec 2025. Signing dates follow a ramping density from Nov 2025 to Oct 2026. `created_at` is signing minus Γ(2, 24 d). |
| **Onboarding** | contract → account → first login (lag ↑ when `u_obs` and `p` are low) → KYC submitted (+0.8 d per redline) → Poisson KYC info-request loops (UTILITY 1.5, CI_LOAD 1.3, others ≤ 0.6, scaled by 1.4−p; each loop logs RevOps chase touches) → KYC approved → bank linked → funded (DATACENTER Γ scale 8.5 vs 1.3) → API key (speculators 30–90%). Each step can **stall** (probability ↑ as p falls). 60% of stalls **revive** after Γ(2, 22 d). |
| **First trade** | Daily weekday hazard from funding (or launch): speculators 0.023·(p/.5); hedgers 0.0044·(p/.5)^1.3, × an unobserved lognormal factor (approvals, limits). A time trend `0.5 + 0.8·progress` makes cohorts improve. Inert accounts (30%·(1−p)^1.5) run at ×0.12. A hedger walkthrough multiplies the hazard by ×3.2. Events in the account's ISO add ×1.2. A **triggered sequence gives ×3.6 for 14 days and lifts inertia.** Rejections (FUND 45%, PROP 12%, others 8%) delay the fill. 30% of hedgers start with a 1–5 lot (non-qualifying) test fill. |
| **Trading** | Probability of trading on a weekday: speculators `0.40+0.55p+N(0,.14)`, hedgers `0.07+0.40p+N(0,.12)`, LPs 0.97. It ramps up over the first 30 days. Churn hazard is 0.0038·(1.3−p) per weekday. One-and-done accounts trade at 0.012. Daily size is `segment base × (1+Lomax(1.6)) × size^0.25`, with 40% of accounts growing 6–18%/month. Speculators trade ×1.6 more often and ×1.5 larger on event days. Tenors (by fills): hedgers 62/32/6% HOURLY/DAILY_PEAK/WEEKLY_PEAK, speculators 80/18/2%. DAILY_PEAK and WEEKLY_PEAK fills carry fewer contracts (×0.12 and ×0.03), since each contract is 16 or 80 MWh. LPs are 85% maker. |
| **Activities** | Pre-sign: emails, calls, meetings, demos, LinkedIn and webinars. Counts and reply or no-show rates depend on `u_obs`. Unqualified targets get marketing nurture. Post-sign: an 8-touch activation sequence (D0–D21, stops at first trade), periodic AE check-ins until Active, account-management touches once trading, QBRs for the top 20 by volume and walkthroughs. Volatility sequences: T0 triggered_email, +4 h LinkedIn, D1 call, D2 email, D3 call, D5 email, all carrying `trigger_id`, stopping on reply and limited to one per account per 14 days. **No sequences are logged for the 2026-10-02 event**: working it is today's job. |
| **Spreads** | `spread = (a_hub + b_hub/√(active+3)) × tenor_mult + AR(1) noise`, widened ×1.35 on event days. Uptime = `100 − c_hub/√(active+3)`. `lp_quote_share` falls as organic active accounts grow. |
| **Marketing** | Monthly spend and leads by channel. Conference spend is lumpy in Feb, Apr, Jun, Sep and Oct-25. CAC differences emerge from account `lead_source` × funnel outcome (§4). |
| **Contacts** | Personas weighted by side: speculators skew TRADER, hedgers RISK/CFO/OPS. Champion probability is 0.12 + 0.6·σ(u_obs). |

---

## 3. Causal structure the product can find

| Mechanism | How it is embedded | Where it shows (seed 42) |
|---|---|---|
| Latent propensity → funnel | `p` drives signing weight, stall probability, dwell, first-trade hazard and trading intensity | AUC(latent p → signed) > 0.7; AUC(latent p → ever Active \| signed) > 0.65 (tests) |
| Observable proxies | First-login lag, meetings, demo, reply rate, champion and stakeholders, other-exchange account, redlines, KYC loops and API key all depend on `u_obs` or `p` | Model coefficients, e.g. walkthrough (+), triggered_14d (+), other_exchange (+), days_in_step (−) |
| **Triggered outreach lifts activation** | Random 60% of eligible exposed accounts get a sequence; ×3.6 hazard for 14 days | Funded-not-trading cohort, first trade ≤ 14 d: **30.4% (n=171) vs 12.3% (n=114) → 2.48×** (`volatility.trigger_cohort_lift`) |
| Liquidity flywheel | spread = a + b/√active | corr(spread, active) from −0.71 to −0.80 on every hub × tenor; HB_NORTH −0.74 |
| KYC loops: #1 friction for UTILITY / CI_LOAD | Higher Poisson loop rate plus per-loop stall risk | Mean info requests per signed account: UTILITY 0.79, CI_LOAD 0.67 vs ≤ 0.42 elsewhere |
| DATACENTER bank_linked → funded slow | Γ scale 8.5 vs 1.3 | Median ≈ 11 d vs ≈ 2–3 d |
| Hedgers without walkthrough are slow to first order | ×3.2 hazard after walkthrough | Visible in funded → first_order dwell by walkthrough flag |
| FUND order rejections | 45% rejection rate on first order | FUND rejection rate ≈ 0.45 (max of all segments) |
| Channel quality | Lead-source effect in `z`; conference leads 1.5× larger | Partner Referrals CAC/funded ≈ $3.6k vs LinkedIn Paid ≈ $18.6k; conference-sourced Active accounts trade ≈ 2.8× the ADV of LinkedIn ones |

---

## 4. Calibration: synthetic "now" (AS_OF 2026-10-05) vs spec §C

| Metric (definition) | Target (§C calibration) | Actual (seed 42) |
|---|---|---|
| Signed, cumulative | ≈ 330 | **332** |
| Funded, cumulative | ≈ 205 | **198** |
| Active rate (Active ÷ funded ≥ 20 d) | ≈ 62% | **59.8%** (111 Active accounts) |
| ADV, 20 trading days (contracts/day, all incl. LP) | 14–17k, rising | **15,385** (prior 20 td: 14,842). Monthly: Jan 4.5k → Mar 7.7k → Jun 10.6k → Sep 14.9k |
| of which liquidity partners | separate line, large share | 7,884 (51%) |
| ADV notional, 20 td | (target $3M at 25k) | $2.34M (≈ $152/contract, same ratio as target) |
| Hedger share of Active accounts (incl. LPs in denominator) | ≈ 44% (< 50% target → B weight on) | **44.1%** (49.5% excluding LPs) |
| Top-5 share of ADV | ≈ 50% (> 45% ceiling) | **50.1%** |
| ERCOT North spread (HOURLY, last 5 days) | ≈ $0.9/MWh, tightening | **$0.91** (Q1 average $1.28). Uptime 92.5% (< 95% target) |
| 30-day cohort activation (first qualifying trade ≤ 30 d of funding; cohorts funded in the last 8 matured weeks) | ≈ 50%, trending up | **53.8%** (n=52). By funded quarter: Q1 19% (n=26) → Q2 33% (n=67) → Q3 54% (n=63) |
| Median days funded → first trade | (from ≈ 21 toward ≤ 10) | 28.9 (all-time, includes slow pre-launch cohorts) |
| Triggered vs untriggered 14-day activation | ≈ 2–2.5× | **2.48×** |
| ERCOT-exposed accounts at SIGNED / KYC_APPROVED / FUNDED (non-LP) | ≥ 14 incl. REP + Storage/Prop | **113** (REP 22, FUND 18, PROP 17, CI_LOAD 15, IPP 14, DATACENTER 10, STORAGE 9, UTILITY 8) |
| corr(spread, active_accounts) | < −0.6 | −0.71 to −0.80 (all hubs) |
| Seed runtime / DB size | < 20 s / < 60 MB | ≈ 6 s / ≈ 16 MB |

`tests/test_seed.py` asserts each of these within tolerance bands.

---

## 5. Volatility trigger (`services/volatility.py`)

The trigger evaluates each hub at the last hour before `as_of`:

1. **Spike hour**: `lmp > max(P99 of the 30 d preceding the 72 h window, ISO floor)`. Floors are ERCOT $1,000 and $250 elsewhere. `S` counts spike hours in `(T−72h, T]`. For CAISO, `N` counts negative hours.
2. **Volatility**: `RV72 = std(Δ asinh(lmp/10))` over 72 h. `vol_z = (RV72 − μ)/max(σ, 0.5μ)`, where μ and σ come from the trailing 30 d of RV72, lagged 72 h.
3. **Fire** when any of these hold:
   * `S ≥ 3`;
   * `vol_z ≥ 2.5` and the 72 h max is at least 0.5 × the floor;
   * the hub is in CAISO and `N ≥ 12`;
   * the forecast peak is at least the floor within 5 days (`forward_risk`).
4. **Regime**: `winter_peak` (spikes in Dec–Feb), `scarcity` (other spikes), `negative_price`, or `elevated_vol`.
5. **Severity**: `raw = 20·S + 15·clip(z,0,3) + 2·N + 10·log2(peak/floor)⁺ + 15·forward_risk`, then `severity = 100·(1−e^(−raw/100))`.

Triggers at AS_OF (seed 42):

| trigger_id | Regime | Severity | Spike/neg h | Peak | forward_risk |
|---|---|---:|---:|---:|---|
| ERCOT-HB_HOUSTON-20261002 | scarcity | 92.1 | 9 | $4,800 | yes ($1,650 on 10-07) |
| ERCOT-HB_NORTH-20261002 | scarcity | 88.7 | 7 | $3,500 | yes ($1,320) |
| CAISO-SP15-20261003 | negative_price | 51.8 | 14 neg | −$16.83 | no |

`detect_historical_events` runs the same rule at every hour, excluding vol-only firings, merges
runs separated by ≤ 24 h, and keys events with the same `trigger_id` the live detector emits.

**Exposure (D6).** `exposure_direction(segment, regime)` returns **hurt** for REP, CI_LOAD,
DATACENTER and UTILITY on spikes and for IPP on negatives. It returns **opportunity** for
STORAGE, PROP, FUND and IPP on spikes, for load segments and storage on negatives, and for LPs
always. `exposure_line(segment, hub, regime)` is a single plain-English sentence with no prices.
`exposure_score(segment, size_mw, severity)` = severity × segment sensitivity ×
(0.5 + 0.25·log10 MW), × 1.2 on the account's own hub.

---

## 6. Propensity model (`services/propensity.py`, spec D1)

* **Label**: the account first becomes Active (≥ 4 distinct trading days within 30) in `(t, t+60d]`.
* **Population per snapshot**: non-LP accounts signed before `t` and never Active before `t`.
* **Snapshots**: weekly from 2026-02-02. Train on `t ≤ AS_OF−120d` (06-07); test on `t ∈ (06-07, 08-06]`. Every test label is fully observed.
* **Features**: 46 in total (`features.FEATURES`).
  * Static, known at signing: segment and ISO one-hots, size, tier, lead-source groups, other-exchange flag, redlines, contacts.
  * Dynamic, `ts < t` only: onboarding progress, days in step, login lag, KYC loops, API key, ticket opened, rejection, days funded without trading, trading days in the last 30, touches over 14 and 30 days, meetings, demo, no-shows, smoothed reply rate, days since reply, walkthrough, triggered outreach in the last 14 days, webinar, and 30-day hub volatility.
* **Production model**: `StandardScaler + LogisticRegression(C=0.05)`, unweighted so probabilities stay calibrated. Metrics come from the train-only fit. The served model is then refit on train + test.
* **Challenger**: `HistGradientBoostingClassifier`.

| Metric (holdout) | Production LR | Challenger HGB |
|---|---:|---:|
| AUC | **0.836** | 0.816 |
| PR-AUC | 0.746 | 0.700 |
| Lift, top decile | **3.46×** | 3.24× |
| Brier | 0.131 | — |
| Base rate | 0.270 | — |
| train_n / test_n (account-snapshots) | 1,460 / 1,328 | — |

**Reasons.** Each reason is a contribution `coef_j × z_j` to the log-odds, and the top 3 are
shown by magnitude. The text comes from `content/reason_labels.json` (`high`/`low` relative to
the population mean) and always states a fact about the account. `direction` carries the
sign. Segment, ISO and lead one-hots the account does not have are never shown. Contributions
plus the intercept equal the logit (tested).

**Leakage controls.**

* `features_as_of` reads only static attributes and event rows with `ts < t`.
* Tests delete every row with `ts ≥ t` (three cut-offs) and confirm the features are identical.
* Tests also scramble `stage`, all `*_at` columns and `latent_propensity` and confirm the features are identical.

---

## 7. Repo / Frames API (`ignition/repo.py`, the only SQL touchpoint)

```python
from ignition import repo
frames = repo.load_all(session)            # cached per DB; Frames dataclass
frames.accounts, frames.trades, ...        # one DataFrame per table (columns = table columns)
repo.load_accounts(session)                # one loader per table: load_<table>(session)
repo.invalidate_cache("activities", "outreach_drafts")   # after writes; no args = everything
repo.frames_from_tables(seed.generate())   # Frames from in-memory tables (tests / notebooks)
```

Dtypes: DateTime and Date → `datetime64[us]`; nullable `rep_id` → `Int64`; booleans → `bool`.

---

## 8. Deviations from the spec / memos (deliberate)

1. **Severity uses a soft cap** (`100·(1−e^(−raw/100))`) instead of `min(100, …)`. Several hubs saturate during the demo event, and the soft cap keeps HB_HOUSTON ranked first. It also adds a peak-magnitude term and a forward-risk term (D6).
2. **vol_z** uses a floored baseline σ (`max(σ, 0.5μ)`) and adds at most 45 severity points. A vol-only trigger also requires a material price level (≥ ½ floor). Without these, a few CAISO negative hours in a calm month scored "50σ".
3. **DORMANT stage** applies only to accounts that have traded before. Funded accounts that never traded stay `FUNDED`, the funded-not-trading stall. The D2 literal ("funded ≥ 30 d, 0 trades") is exposed as `account_health().state == "dormant"`.
4. **Extra columns**: `volatility_events.trigger_id`, plus surrogate `id` PKs on `price_forecasts` and `spread_snapshots`.
5. **LR is unweighted** (CTO memo said `class_weight="balanced"`), with C=0.05, so `P` is calibrated for `P × E[ADV]`. The holdout window is calmer-trending than the live one, so expect mild under-prediction in the lowest bins (temporal drift: activation improves over 2026).
6. **Snapshots and windows**: the label horizon is 60 d (D1), so the time split is train ≤ AS_OF−120 d and test (AS_OF−120 d, AS_OF−60 d], not the 45 d memo split.
7. Calibration lands at **active rate 59.8%** (target ≈ 62%) and **cohort activation 53.8%** (target ≈ 50%). Both are inside test tolerances and tell the intended story.
