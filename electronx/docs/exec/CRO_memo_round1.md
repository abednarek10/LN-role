# CRO Memo — Round 1: Funnel, Activation Queue, Scoring, Comp, Sequencing

**From:** CRO · **To:** CEO, CPO, CTO · **Re:** Operating spec for Ignition (W2, W3, W4, W7)

Bottom line: we pay for and measure **Active** accounts and ADV, not signatures. Every rule below is a parameter the product exposes. The numbers are v1 defaults that we tune with data.

## 1. Funnel stages

| # | Stage | Entry criteria | Exit criteria | Stall flag |
|---|---|---|---|---|
| S0 | **Target** | In TAM, ICP segment, assets/load in ERCOT/PJM/CAISO/MISO | Discovery held; exposure confirmed | Top-quintile score untouched > 5 d |
| S1 | **Qualified** | Exposure + use case confirmed; risk/treasury owner identified; eligibility screened | Participant agreement executed | > 30 d |
| S2 | **Signed** | Agreement executed (enters activation system) | KYC/AML approved | Not submitted > 3 d; submitted but open > 5 d; total > 10 d |
| S3 | **KYC Approved** | Compliance approval | Collateral deposited ≥ minimum | > 5 d |
| S4 | **Funded** | Deposit cleared | First filled order | > 7 d (exec escalation at 21 d) |
| S5 | **First Trade** | ≥ 1 fill | Meets the Active definition | No 2nd trading day within 10 d |
| S6 | **Active** | **≥ 4 distinct trading days in trailing 30** (≈ weekly habit) | Expanding, or At-Risk | Trading days down ≥ 50% vs prior 30 d |
| S7 | **Expanding** | Active ≥ 60 d AND (trailing-30 ADV ≥ 1.5× first-60-day baseline OR added 2nd ISO/product) | Back to Active if the conditions lapse | Same as S6 |
| — | **At-Risk / Dormant** | At-Risk: 1–3 trading days in trailing 30. Dormant: funded, 0 trades in 30 d | Re-enters Active | — |

The time clock for each stage starts on entry. Every stall flag routes to a rule in §2.

## 2. Activation Queue

**Priority = P(active ≤ 60 d) × E[ADV] × k_stage × U**

- **P**: propensity from W4, calibrated.
- **E[ADV]** (contracts/day, segment prior, updated with sizing data from discovery): Prop 400 · Hedge Fund 150 · REP 100 · Storage 80 · IPP 60 · Utility 40 · Data Center 30 · C&I 20.
- **k_stage**: how much a touch helps at this stage, a proxy for uplift. Funded/no-trade 0.35 · KYC stall 0.25 · First-Trade 0.30 · Qualified 0.15 · Active 0.10.
- **U**: urgency multiplier, capped at 2.0. Base 1.0. ×1.5 for a volatility trigger in the account's ISO within 72 h when the segment is exposed. ×1.25 for a breached stall threshold. ×1.2 when a forecast peak is ≤ 5 d out.

**Next-best-action rulebook**

| # | IF | THEN | Owner | SLA |
|---|---|---|---|---|
| 1 | S0, inbound, score top decile, untouched | First call + tailored exposure brief | AE | 1 business day |
| 2 | S1 > 10 d with no agreement sent | Send agreement + 15-min onboarding preview | AE | 2 bd |
| 3 | S2, KYC not started > 3 d | Prefilled KYC packet + 20-min guided session | RevOps | 1 bd |
| 4 | S2, KYC submitted, stalled > 5 d | Chase the *named* missing doc. Escalate to Compliance at day 8 | RevOps | Same day |
| 5 | S3, unfunded > 5 d | Funding instructions + first-hedge sizing against their stated exposure | AE | 1 bd |
| 6 | S4, no trade > 7 d | Live trading walkthrough using the past 7 days of price action at their ISO hub, with a worked hedge | AE + Product Specialist | 2 bd |
| 7 | S4, no trade > 21 d | Exec call to diagnose the blocker (internal approvals, risk limits, tech) | Head of GTM | 3 bd |
| 8 | Prop/HF, funded, no API key > 5 d | API onboarding + sandbox certification | Solutions Eng | 2 bd |
| 9 | Any stage S1–S5 AND volatility trigger in their ISO AND exposed segment | Launch volatility sequence (§5) | AE | 4 h |
| 10 | S5, no 2nd trading day in 10 d | Post-trade debrief: P&L vs index exposure; propose a standing weekly hedge routine | AE | 2 bd |
| 11 | S6, trading days down ≥ 50% | Churn-risk check-in; log the reason code | AE | 3 bd |
| 12 | S6 ≥ 60 d, single ISO/product, multi-ISO assets | Expansion play: 2nd ISO or hourly products | AE | 5 bd |
| 13 | Top-20 account by ADV | QBR (Account 360) | Strategic Sales | Every 90 d |
| 14 | Dormant > 30 d | Win-back nurture tied to the next forecast event | Marketing | Weekly |

When an SLA is missed, the item turns red on the AE scorecard (§4).

## 3. Lead-scoring features (target: Active ≤ 60 d)

| Family | Feature | Sign |
|---|---|---|
| Firmographic | Segment = Prop / Storage / REP | + |
| | Assets/load in a live ISO; MW merchant or unhedged | + |
| | Existing futures account at another exchange (CME/ICE) | + |
| | Regulated utility / board-approval hedging policy | − (velocity) |
| Exposure | Trailing-30 d realized volatility at their hub/node | + |
| | Recent loss event (scarcity spike, basis blowout) | + |
| | Merchant share of output / index-priced share of load | + |
| Engagement | Inbound source or partner referral | + |
| | ≥ 2 stakeholders engaged, including risk/treasury | + |
| | Demo attended; champion seniority | + |
| | Days since last reply | − |
| Behavioral | Pre-funding logins; sandbox orders; contract-spec views | + |
| | Days signature → KYC submission | − |
| | Count of legal redlines | − |
| | Funding amount ÷ stated exposure | + |
| | API key created (Prop/HF) | + |

## 4. AE scorecard and comp

**Scorecard**

| Metric | Weight |
|---|---|
| Net-new funded accounts vs quota | 25% |
| Activation rate (funded → Active ≤ 60 d) | 25% |
| ADV from the book vs target | 20% |
| Median days from signature to first trade | 10% |
| Qualified pipeline created (3× coverage) | 10% |
| NBA SLA adherence | 10% |

**Comp simulator parameters.** OTE $250k, split 60/40 (base $150k, variable $100k). Quota: 24 funded accounts per year. Accelerator 1.5× above 100% of quota.

| | (a) Pay on signature | (b) Pay on funded | (c) Funded + activation + ADV |
|---|---|---|---|
| Per-account payout | $4,167 per signature | $4,167 per funded account | Unit $2,000 × M. M = 0.5 at funding, +1.0 at Active ≤ 60 d, +0.25 if Active ≤ 21 d |
| Volume | — | — | ADV kicker: **$50 per 1k contracts** traded by the account in its first 12 months. 1.5× above volume target. Capped at $10k per account |
| Clawback | None | 50% if no trade within 60 d | **100% of the funding payment if no trade within 60 d of funding** |
| Mix at plan | 100% signatures | 100% funding | ~72% accounts / ~28% volume |
| Behavior it rewards | Signing marginal accounts; activation dumped on RevOps | Funded-but-dormant accounts | Fast activation of high-ADV fits |

Recommendation: **(c)**. Liquidity-partner and market-maker accounts get 25% kicker credit, because fee programs already incentivize their volume. The simulator should report **variable cost per Active account** and **variable cost per 1k contracts** under each plan, using the same synthetic book.

## 5. Outreach sequencing

**Volatility-triggered.** Trigger: real-time hub price > 3σ of its 30-day mean, or a scarcity/emergency alert, or a forecast peak ≤ 72 h out. Five touches over five business days.

| Day | Channel | Touch |
|---|---|---|
| T0 (≤ 4 h) | Email | References the event, includes a chart of their hub and "what a daily peak contract would have done" |
| T0 + 4 h | LinkedIn | Short note from the AE |
| D1 | Phone | Call + voicemail |
| D2 | Email | Marketing's auto-generated event recap + forward look |
| D3 | Phone | Call |
| D5 | Email | Offer a 20-min walkthrough before the next forecast peak |

Rules: at most 1 triggered sequence per account per 14 days. Active accounts get a market note, not a sequence. The sequence stops on reply.

**Standard activation.** Stage-driven, 8 touches over 21 days.

| Day | Touch |
|---|---|
| D0 | Welcome + checklist (automated, email + in-app) |
| D1 | Call |
| D3 | Segment explainer video |
| D5 | Call |
| D7 | Invite to live walkthrough |
| D10 | Same-segment case study |
| D14 | Call + note from Head of GTM |
| D21 | Escalate per Rule 7 |

## 6. Disagreements with the synthesis

1. **Wrong model target.** W4 predicts P(first trade ≤ 45 d), but a single one-lot trade is easy to coax and worthless. The target should be **P(Active ≤ 60 d)**. Keep first trade as a secondary target.
2. **Rank on uplift, not propensity.** Accounts that will activate anyway don't need rep time. k_stage is the v1 proxy. Once touch logs exist, run holdout tests by stage.
3. **The funnel isn't linear.** Add At-Risk and Dormant states. Without them, "vast majority actively trading" can't be measured.
4. **Spike-chasing can backfire.** Pitching a hedge right after a spike reads as "insurance after the fire." Market Pulse must weight **forward** risk (weather/load forecasts) as much as realized spikes. Outreach on a regulated exchange also needs compliance-approved templates: no advice, no promissory language. That applies to the Claude output as well.
5. **Separate the liquidity motion.** Market makers and partners shouldn't sit in the AE queue at full credit.
6. **Fix the W10 metric.** "Rep hours saved" is weak. Measure **activations per rep-hour** instead.
7. **Sequence the build to the deadline.** We have about 12 weeks to end-2026. Ship W2, W3 and W7 first; W8 and W9 follow.
