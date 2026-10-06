# Ignition v1 — Product Spec & Decision Record

**Status:** binding build contract for all agents (Data, Engineering, Design,
Sales, Marketing). Supersedes the synthesis where they conflict. Inputs:
`01_PROBLEM_SYNTHESIS.md`, `exec/CEO_memo_round1.md`, `exec/CRO_memo_round1.md`,
`exec/CPO_memo_round1.md`, `exec/CTO_memo_round1.md` — read the memo relevant to
your role in full; this file resolves their conflicts.

---

## A. Decision record (exec disagreements resolved)

| # | Question | Decision | Why |
|---|---|---|---|
| D1 | Model target: first trade ≤45d (synthesis) vs ≤30d (CEO) vs Active ≤60d (CRO, CPO) | **Primary label: becomes *Active* within 60 days of the scoring snapshot.** Secondary reported metric: *qualifying first trade* within 30 days of funding (CEO cohort activation). | Comp, queue and memo all pay on Active; a one-lot trade is cheap to coax. |
| D2 | Definition of Active (CEO ≥3 of 20 trading days; CRO ≥4 distinct days in trailing 30) | **Active = ≥4 distinct trading days in the trailing 30 calendar days.** At-Risk = 1–3. Dormant = funded, 0 trades in trailing 30 (after having been funded ≥30 d). One constant in `ignition/definitions.py`, used everywhere. | Single definition across views, memo and comp (CPO). |
| D3 | Qualifying trade | Fill of **≥10 contracts**, non-self-match. First trade below that does not start the activation clock for comp. | CEO anti-gaming. |
| D4 | Ranking | **Priority = P(Active≤60d) × E[ADV] × k_stage × U × B** (CRO formula) with **B** = market-balance weight: hedger accounts ×1.15 while hedger share of Active accounts < 50% target (CEO). U capped at 2.0. | Rank on expected value *of a touch*, not raw propensity. |
| D5 | Liquidity partners / market makers | `accounts.is_liquidity_partner` flag. **Excluded** from the AE Activation Queue; LP volume shown as a separate line everywhere (ADV, spreads, mix); 25% kicker credit in comp. | CEO + CRO. |
| D6 | Market Pulse direction | Each exposure is labeled **hurt** (hedger short the spike: REP, C&I, Data Center, Utility) or **opportunity** (Storage, Prop, Hedge Fund, IPP long the spike — IPP solar = evening-ramp/curtailment risk on CAISO negatives). Pulse weighs **forward risk** (synthetic 5-day peak forecast) alongside realized spikes. | CRO "insurance after the fire", CPO wow-moment. |
| D7 | Compliance | Every outreach draft passes a **compliance linter** (banned promissory/advice phrases, required disclaimer footer) and enters state `pending_review` → `approved` → `queued`. Claude only receives computed facts; it never invents prices. Volatility outreach targets eligible commercial/institutional accounts only. | CEO, CRO, CPO all flagged. |
| D8 | Views (10 modules → 7 tabs) | Tabs in nav/demo order: **CEO Weekly · Market Pulse · Activation Queue (+ Model panel) · Funnel & Journey · Team & Comp · Segments · Marketing ROI**. Account 360/QBR = drawer opened from any account name. AI copilot = capability inside Pulse/Queue/360. | CPO IA; CEO wanted Marketing ROI deferred — kept but thin. |
| D9 | Revenue | Fee revenue is a first-class KPI (CEO). | It's a Revenue OS. |
| D10 | Funnel start | Onboarding funnel starts at `contract_signed`. Off-path states At-Risk / Dormant tracked. | CPO + CRO. |
| D11 | Synthetic-data honesty | Every screen and export carries a "Synthetic data — illustrative" watermark. Model AUC target 0.72–0.85, not 0.99. Cohorts with n<20 greyed out. | CEO, CTO. |

---

## B. Canonical definitions (`ignition/definitions.py`)

```
AS_OF                 = 2026-10-05 (Monday 00:00, data runs through Sunday 10-04 23:00). Week_end default = 2026-10-02 (Friday close).
HISTORY_START         = 2026-01-05  (≈ 39 weeks of exchange history; prices hourly from 2026-01-05)
ACTIVE_MIN_DAYS       = 4      # distinct trading days in trailing 30 calendar days
AT_RISK_DAYS          = (1, 3)
QUALIFYING_CONTRACTS  = 10
ACTIVATION_WINDOW_D   = 60     # model label horizon
COHORT_FIRST_TRADE_D  = 30     # CEO cohort activation window
ADV_WINDOW_TD         = 20     # trailing trading days (weekdays) for ADV
SMALL_COHORT_N        = 20
SEGMENTS (code → label, side):
  IPP        Independent Power Producer      hedger
  STORAGE    Battery Storage Operator        hedger
  REP        Retail Electric Provider        hedger
  CI_LOAD    C&I / Large Load                hedger
  UTILITY    Utility / Co-op / Muni          hedger
  DATACENTER Data Center Developer           hedger
  PROP       Proprietary Trading Firm        speculator
  FUND       Hedge Fund / Asset Manager      speculator
  (plus is_liquidity_partner accounts — usually PROP — side = "liquidity_partner")
ISOS / HUBS:
  ERCOT: HB_NORTH, HB_HOUSTON, HB_WEST
  PJM:   PJM_WESTERN_HUB
  CAISO: SP15, NP15
  MISO:  MISO_INDIANA_HUB
CONTRACT TENORS (contract size): HOURLY (1 MWh), DAILY_PEAK (16 MWh = 1 MW × 16 on-peak hours), WEEKLY_PEAK (80 MWh)
FEE                    = $0.25 per contract (taker), $0.10 maker rebate-adjusted net ≈ use fee column directly
STAGES (CRO): TARGET, QUALIFIED, SIGNED, KYC_APPROVED, FUNDED, FIRST_TRADE, ACTIVE, EXPANDING, AT_RISK, DORMANT
ONBOARDING STEPS (ordered): contract_signed, platform_account_created, first_login, kyc_submitted,
  kyc_info_requested (repeatable), kyc_approved, bank_linked, funded, api_key_created (optional; PROP/FUND),
  order_ticket_opened, first_order, order_rejected (optional), first_trade, activated
MARKETING CHANNELS: Industry Conferences, Webinars & Education, Content & SEO, LinkedIn Paid,
  Partner Referrals, Outbound Prospecting, Liquidity Partner Intros
REPS: 4 AEs + 1 Strategic Sales lead + 2 RevOps Associates + 1 Marketing Manager (only AEs + Strategic carry book/quota)
```

## C. 2026 targets (CEO) — `ignition/definitions.py: TARGETS_2026`

Signed (cum.) 420 · Funded 260 · Active rate ≥70% of funded older than 20 days ·
30-day cohort activation 55%→70% · median days funded→first trade ≤10 ·
ADV (20-td) 25,000 contracts / ≈$3M notional · hedger share of Active ≥50% ·
speculator share of ADV 40–65% · top-5 share of ADV ≤45% · ERCOT North spread
≤$0.75/MWh & two-sided uptime ≥95% · other ISOs ≤$1.50/MWh & ≥85% ·
institutional net ADV retention ≥120%.

**Calibration of the synthetic "now" (as of 2026-10-05):** ≈330 signed, ≈205
funded, ≈62% active rate, ADV ≈14–17k contracts and rising, 30d cohort
activation ≈50% and trending up, hedger share of Active ≈44% (*below* target → B
weight on), top-5 ADV share ≈50% (slightly above target → a visible risk), ERCOT
North spread ≈$0.9/MWh tightening. i.e. **on a trajectory that needs the
activation engine to hit plan** — that's the story.

---

## D. Data model (`ignition/models.py`) — names are a contract

All datetimes naive UTC. Integer PKs. Index every FK.

```
reps(id, name, role[AE|STRATEGIC|REVOPS|MARKETING], region, quota_funded_annual:int, quota_adv:float, start_date:date)
accounts(id, name, segment, primary_iso, exposure_isos:str CSV, hub, hq_state, size_mw:float,
         est_annual_mwh:float, tam_tier[A|B|C], lead_source (=marketing channel), rep_id FK null,
         stage, is_liquidity_partner:bool, has_other_exchange_account:bool, kyc_redlines:int,
         created_at, signed_at null, kyc_approved_at null, funded_at null, funded_amount_usd null,
         first_trade_at null, first_qualifying_trade_at null, active_since null,
         latent_propensity:float  # SEED-ONLY; never read by features/services except tests
        )
contacts(id, account_id, name, title, persona[TRADER|RISK|CFO|OPS|EXEC], email, is_champion:bool)
activities(id, account_id, rep_id, ts, kind[email|call|meeting|demo|webinar|linkedin|triggered_email|walkthrough|qbr],
           outcome[none|reply|meeting_booked|no_show], trigger_id:str null, sequence:str null)
onboarding_events(id, account_id, ts, step)          # step ∈ ONBOARDING STEPS
trades(id, account_id, ts, iso, hub, tenor, side[BUY|SELL], contracts:int, price:float,
       notional_usd:float, fee_usd:float, is_maker:bool)
market_prices(hub, ts, iso, lmp:float)               # PK (hub, ts); hourly, HISTORY_START..AS_OF
price_forecasts(hub, iso, date, forecast_peak_lmp, forecast_avg_lmp, issued_at)   # next 5 days from AS_OF
spread_snapshots(date, iso, hub, tenor, spread_usd_mwh, two_sided_uptime_pct, top_depth_contracts,
                 active_accounts:int, lp_quote_share:float)   # daily, per hub × [HOURLY, DAILY_PEAK]
marketing_spend(id, month:date, channel, spend_usd, leads:int, campaign:str)
volatility_events(id, hub, iso, start_ts, end_ts, regime[scarcity|negative_price|winter_peak|elevated_vol],
                  peak_lmp, spike_hours, severity)   # historical detected events (precomputed in seed via services.volatility)
outreach_drafts(id, account_id, rep_id, trigger_id null, created_at, subject, body, engine[claude|template],
                status[pending_review|approved|queued|sent|rejected], compliance_flags:str JSON)
```

Synthetic data requirements (see CTO memo §3 for generators):
* 600 accounts; segment mix per CTO memo; ~12 liquidity partners.
* Must embed **causal structure the product can find**: latent propensity drives
  funnel speed & activation; observable proxies (meetings, champion, first-login
  lag, api key, redlines, kyc_info_requested loops, lead source) correlate with
  it; **triggered outreach causally lifts** activation (past triggered cohort
  ≈2–2.5× untriggered 14-day activation); spreads follow `a + b/sqrt(active)`;
  friction: `kyc_info_requested` loops are the #1 drop-off for UTILITY & CI_LOAD,
  `bank_linked→funded` slow for DATACENTER, `funded→first_order` slow for hedgers
  without a walkthrough, `order_rejected` (margin/limits) common for FUND.
* **Seeded demo event:** ERCOT HB_HOUSTON (strongest) + HB_NORTH, starting
  2026-10-02 15:00 UTC-naive, 6–9 consecutive hours $2,200–4,800, peak $4,800 at
  HB_HOUSTON. CAISO negatives in the last week too (mild). A forward forecast
  peak for ERCOT within 5 days.
* At least ~14 accounts exposed to ERCOT that are in FUNDED-not-trading or
  earlier stages, including REPs (hurt) and Storage/Prop (opportunity).

## E. API contract (prefix `/api`, JSON) — names are a contract

All list endpoints accept optional `segment`, `iso`, `rep_id` filters where
sensible. All responses include `"as_of": "2026-10-05"` at top level where an
object is returned. Money in USD floats, rates as 0–1 floats.

| Method/Path | Response (top-level keys) |
|---|---|
| GET /health | `{status}` |
| GET /meta | `{as_of, week_end, segments:[{code,label,side}], isos:{ISO:[hubs]}, stages, steps, channels, reps:[{id,name,role}], targets, synthetic:true}` |
| GET /ceo/weekly?week_end= | `{as_of, week_end, headline:[3 strings: liquidity, balance, action], kpis:[{key,label,value,unit,prior,delta,target,status[on_track|watch|off_track],spark:[..12 weekly values]}], weekly_series:[{week_end, signed, funded, first_trades, active_accounts, adv_contracts, fee_revenue}], mix:{by_side_accounts:{hedger,speculator,liquidity_partner}, by_side_adv:{...}, top5_adv_share, hhi}, spreads:[{iso,hub,tenor,spread_usd_mwh,uptime_pct,target_spread,target_uptime,status}], activation_cohorts:[{cohort_week, n, activated_30d_rate, greyed}], stalled:[{account_id,name,segment,stage,days_stalled,exp_adv,next_action}], decisions:[3 strings]}` |
| GET /ceo/weekly.md?week_end= | `text/markdown` memo (watermarked) |
| GET /pulse/hubs?iso=&hours=168 | `{as_of, hubs:[{hub, iso, series:[{ts,lmp}], stats:{last,avg_30d,p99_30d,max_72h,min_72h,spike_hours_72h,vol_z}, forecast:[{date,forecast_peak_lmp,forecast_avg_lmp}]}]}` |
| GET /pulse/triggers | `{as_of, triggers:[{trigger_id, hub, iso, regime, severity, spike_hours, vol_z, peak_lmp, peak_ts, start_ts, end_ts, forward_risk:bool, exposed_count, funded_not_trading, adv_at_stake}]}` |
| GET /pulse/triggers/{trigger_id}/accounts | `{trigger, accounts:[{account_id, name, segment, stage, direction[hurt|opportunity], exposure_line (plain-English why), exposure_score, p_active, exp_adv, last_touch_days, suppressed:bool, suppressed_reason}]}` |
| GET /pulse/history | `{events:[{trigger_id,hub,regime,peak_lmp,start_ts}], lift:{triggered:{n, activated_14d_rate}, untriggered:{n, activated_14d_rate}, lift_x}}` |
| GET /activation/queue?limit=50&segment=&iso=&rep_id=&stage= | `{as_of, summary:{accounts_in_queue, stalled, sla_breaches, adv_at_stake}, items:[{rank, account_id, name, segment, side, iso, stage, days_in_stage, stall:bool, p_active, exp_adv, k_stage, urgency, balance_weight, priority, trigger_id, next_action:{rule_id, action, owner, sla, sequence}, reasons:[{label, direction[+|-], weight}]}]}` |
| GET /scoring/model | `{target, train_n, test_n, auc, pr_auc, brier, base_rate, lift_top_decile, gain_curve:[{pct_accounts, pct_positives}], calibration:[{bin, predicted, observed, n}], coefficients:[{feature,label,coef}], challenger:{name, auc, lift_top_decile}}` |
| GET /funnel?segment=&iso= | `{steps:[{step, label, n, conv_from_prev, median_days_from_prev, p75_days}], states:{active, at_risk, dormant}, by_segment:[{segment, steps:[{step, conv_from_prev, median_days}]}], friction:[{step, segment, metric, value, benchmark, accounts_affected, adv_at_stake, roadmap_ask, severity}]}` |
| GET /funnel/friction/{index}.md | markdown roadmap ticket |
| GET /segments | `{cells:[{segment, iso, tam_accounts, signed, funded, active, penetration, activation_rate, adv_per_active, adv_total}], segments:[{segment,label,side, tam, active, adv, adv_share, recommended_coverage}]}` |
| GET /liquidity?iso=&tenor= | `{series:[{date, hub, spread_usd_mwh, uptime_pct, active_accounts, lp_quote_share}], elasticity:{b, r2, note}}` |
| GET /team/scorecards | `{reps:[{rep_id, name, role, funded_ytd, quota_ytd, attainment, activation_rate, book_adv, median_days_sign_to_trade, pipeline_coverage, sla_adherence, score, components:{...}}]}` |
| GET /team/comp-plans | `{plans:[...from content/comp_plans.json]}` |
| POST /team/comp-sim body `{plan_id? , params?}` | `{plan, reps:[{rep_id,name,payout_variable, payout_breakdown:{...}}], totals:{variable_cost, per_active_account, per_1k_contracts}, comparison:[{plan_id, variable_cost, per_active_account, per_1k_contracts, behavior}]}` |
| GET /marketing/roi?months=6 | `{channels:[{channel, spend, leads, signed, funded, active, cac_funded, cac_active, adv, adv_per_1k_spend, n_small:bool}], monthly:[{month, channel, spend, leads}]}` |
| GET /accounts?segment=&iso=&stage=&q=&limit=&offset= | `{total, items:[{id,name,segment,iso,stage,rep,p_active,adv_30d}]}` |
| GET /accounts/{id} | `{account:{...}, contacts:[...], timeline:[{ts,type,label}], onboarding:[{step,ts}], adv_series:[{date,contracts}], health:{state, trading_days_30, adv_30d, adv_prior_30d, net_retention, churn_risk}, reasons:[...], next_action:{...}, qbr:{utilization_by_tenor, isos_traded, growth_plays:[...]}}` |
| POST /outreach/draft body `{account_id, trigger_id?, kind[volatility|activation|qbr]}` | `{draft_id, subject, body, engine[claude|template], facts:{...}, compliance:{passed:bool, flags:[...]}, status}` |
| POST /outreach/{draft_id}/approve, /queue | `{draft_id, status}`; queue logs an `activities` row (kind `triggered_email`, trigger_id) and the Activation Queue reflects it (U for that account → touched, `last_touch_days`=0). |

## F. Content contracts (`ignition/content/*.json`) — owned by Sales & Marketing

* `nba_rules.json` (Sales): `[{rule_id, stage, condition_code, condition_text, action, owner, sla_hours, sequence}]`.
  `condition_code` ∈ a fixed vocabulary the engineering service implements:
  `TOP_DECILE_UNTOUCHED, QUALIFIED_NO_AGREEMENT_10D, KYC_NOT_STARTED_3D, KYC_STALLED_5D, KYC_APPROVED_UNFUNDED_5D,
   FUNDED_NO_TRADE_7D, FUNDED_NO_TRADE_21D, NO_API_KEY_5D, VOL_TRIGGER_EXPOSED, NO_SECOND_DAY_10D,
   ACTIVE_DECLINING, EXPANSION_READY, TOP20_QBR_DUE, DORMANT_30D, DEFAULT`.
* `sequences.json` (Sales): `{volatility:{touches:[{day, channel, purpose}] , rules:[...]}, activation:{...}, qbr:{...}}`.
* `comp_plans.json` (Sales): 3 plans `pay_on_signature`, `pay_on_funded`, `activation_adv` with numeric params per CRO memo §4 (`ote, base, variable, quota_funded_annual, per_account_unit, multipliers:{funded, active_60d, active_21d_bonus}, adv_kicker_per_1k, adv_kicker_cap, accelerator, clawback_pct, clawback_days, lp_kicker_credit, behavior`).
* `scorecard.json` (Sales): metric weights.
* `outreach_templates.json` (Marketing): `[{template_id, kind[volatility|activation|qbr], segment|*, direction[hurt|opportunity|*], regime|*, subject, body}]` using **only** these placeholders:
  `{first_name} {account_name} {rep_name} {hub} {iso} {event_peak_price} {event_hours} {event_date} {regime_label} {exposure_line} {contract_suggestion} {forecast_line} {walkthrough_cta} {disclaimer}`.
* `compliance_rules.json` (Marketing): `{banned_phrases:[...], required_footer, max_claims_rules:[...], notes}`.
* `segment_messaging.json` (Marketing): per segment `{pain, value_prop, proof_point, first_product, persona_titles}`.
* `reason_labels.json` (Data/Eng): feature → plain-English label for reasons.

## G. File ownership (avoid edit collisions)

| Owner | Files |
|---|---|
| Data agent | `ignition/{__init__,config,definitions,database,models,seed,repo}.py`, `ignition/services/{features,propensity,volatility}.py`, `ignition/content/reason_labels.json`, `docs/DATA_MODEL.md`, `tests/test_seed.py`, `tests/test_propensity.py`, `tests/test_volatility.py`, `pytest.ini`, `tests/conftest.py` |
| Engineering agent | `ignition/main.py`, `ignition/schemas.py`, `ignition/routers/*`, `ignition/services/*` except Data's three, `tests/test_api*.py`, `tests/test_services_*.py`, `docs/ARCHITECTURE.md`, `docs/API.md` |
| Design agent | `frontend/*` (except vendored chart.umd.js), `docs/DESIGN.md` |
| Sales agent | `ignition/content/{nba_rules,sequences,comp_plans,scorecard}.json`, `docs/gtm/SALES_PLAYBOOK.md`, `docs/gtm/COMP_PLAN.md`, `docs/gtm/FIRST_90_DAYS.md` |
| Marketing agent | `ignition/content/{outreach_templates,compliance_rules,segment_messaging}.json`, `docs/gtm/POSITIONING.md`, `docs/gtm/CONTENT_ENGINE.md` |
| Orchestrator | `README.md`, `docs/01_*`, `docs/02_*`, `requirements.txt`, final integration |

Run: `cd electronx && python -m ignition.seed --reset && uvicorn ignition.main:app --port 8100` · Tests: `cd electronx && python -m pytest -q`.
