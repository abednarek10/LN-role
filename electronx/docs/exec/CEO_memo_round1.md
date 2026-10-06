# CEO Memo — Round 1: What Ignition Must Prove

**To:** CRO, CPO, CTO, Ignition build team · **From:** CEO · **Date:** 2026-10-06

The synthesis is right: conversion, not pipeline, is the constraint. These definitions and targets are fixed unless data says otherwise.

## 1. What I need to see every Monday (CEO Weekly)

Windows end Friday close. Volume **excludes self-matches**; **liquidity-partner volume is a separate line**.

| KPI | Definition |
|---|---|
| **ADV (contracts)** | Σ contracts traded over trailing 20 trading days ÷ 20. Shown vs. prior 20d and 5d ADV. |
| **ADV (notional $)** | Σ (contracts × MWh per contract × trade price) ÷ 20, same window. Split by ISO. |
| **Fee revenue** | Σ exchange fees, week and trailing 20d. |
| **Funded account velocity** | Net new funded accounts/week, 4-week moving average, plus median days signed→funded. |
| **Activation rate (cohort)** | % of accounts funded in week *W* whose first **qualifying trade** (≥ 10 contracts, no self-match) comes within 30 days of funding. Matured cohorts only, with *n*. |
| **Active rate** | Funded accounts with ≥ 3 trading days of activity in the trailing 20 ÷ funded accounts older than 20 days. The "vast majority" number. |
| **Days to first trade** | Median and P75, from funded to first qualifying trade, by segment. |
| **Account-type mix** | Active accounts and ADV share: hedgers / speculators / liquidity partners, and by segment. |
| **Concentration** | Top-5 accounts' share of ADV, and the HHI of ADV by account. |
| **Spread quality** | Time-weighted median top-of-book spread ($/MWh) for front daily and next-hour contracts at each ISO's main hub, measured 07:00–19:00 local. Plus **two-sided uptime**: % of those minutes with a two-sided quote ≥ 25 contracts deep. Organic vs. partner quotes split. |
| **Net ADV retention** | ADV this quarter from accounts active last quarter ÷ their ADV last quarter (institutional top-20). |
| **Stalled accounts** | Funded accounts more than 21 days past funding with no qualifying trade, ranked by expected ADV. |

## 2. 2026 targets (calibrate synthetic data and dashboards to these)

| Target (EOY 2026) | Number | Why |
|---|---|---|
| Signed accounts (cumulative) | **420** | ≈6/week from a 4-person team plus partners; credible for Series A. |
| Funded accounts | **260** | 62% signed→funded: real KYC friction, visible room to improve. |
| Active rate | **≥ 70%** (~180 active) | "Vast majority" as a number the board can hold us to. |
| 30-day cohort activation rate | **55% → 70%** (Q3 → Q4 cohorts) | Synthetic data must *show* Ignition moving the curve. |
| Median days funded→first trade | **≤ 10** (from ~21) | Hedgers act around events; slower means we missed the window. |
| ADV | **25,000 contracts / ~$3M notional** (20d) | Meaningful for a new short-dated venue; not incumbent-scale. |
| Hedger share of active accounts | **≥ 50%**; speculator ADV share **40–65%** | Hedgers bring interest, speculators bring depth; lose either and the flywheel stops. |
| Top-5 ADV concentration | **≤ 45%** | Above that, one departure is a board event. |
| ERCOT North spread / uptime | **≤ $0.75/MWh, ≥ 95%**. Other ISOs **≤ $1.50, ≥ 85%** | ERCOT is deepest; others still building. |
| Net ADV retention (institutional) | **≥ 120%** | Top-account expansion must outrun churn. |

## 3. Modules ranked by value

1. **Activation Queue (W2, with W4 scoring built in).** Every dormant funded account is sunk CAC one well-timed call can recover. W4 is its engine, not a separate module; the lift chart lives there.
2. **CEO Weekly (W1).** What the board consumes; it forces us to settle the definitions.
3. **Market Pulse (W3, with W10 copilot built in).** The differentiator: no CRM maps an ERCOT scarcity event to exposed accounts within hours. The copilot only matters inside this workflow.

**Defer: Marketing ROI (W8).** At ~260 funded accounts, channel attribution is noise in a nice chart; a "source → funded → active" column in Segments suffices until ~1,000. **Keep Team & Comp thin.**

## 4. The board narrative (three sentences, every week)

> *Liquidity:* "ADV is **X** (Δ vs. prior 20d), with spreads at **Y** and two-sided uptime **Z%**. The flywheel is [tightening / stalling], and here is why."
> *Balance:* "**N** of our **M** funded accounts are actively trading (**A%**). Hedgers are **H%** of active accounts and no single firm exceeds **C%** of volume, so growth is broad-based, not borrowed."
> *Action:* "This week's biggest lever is **[segment/ISO/stall step]**: **K** stalled accounts worth **~$E** expected ADV, and the team is working them through **[play]**."

## 5. Risks: how this product could mislead us

- **Vanity volume.** Self-matches or incentivized partner volume inflate ADV. Separate them, always.
- **Gamed activation.** An AE-pushed 1-lot is not activation; hence the qualifying threshold and 3-day rule. Comp pays on the same definitions.
- **Queue bias.** EV × ADV puts prop firms on top every time. Add a **mix-balancing weight** toward whichever side the market is short (usually hedgers).
- **Regulatory exposure.** "Prices spiked, trade now" aimed at smaller or non-institutional participants is a CFTC communications problem. Every draft passes a **compliance approval step**, makes no profit claims, and triggered outreach targets eligible commercial/institutional accounts only.
- **Small-n theater.** Cohorts of 15 swing 20 points weekly. Show *n*; grey out n < 20.
- **Synthetic data mistaken for real.** Watermark every screen and export; it must never look like leaked ElectronX numbers.

## 6. Where I disagree with the synthesis

1. **"Funded and actively trading" is necessary but not sufficient.** The headline needs *concentration and spread quality* too; 180 actives with one firm at 70% of ADV is fragile.
2. **Scoring horizon:** change P(first trade ≤ 45 days) to **≤ 30 days**: predict what we report.
3. **Revenue is missing.** Add fees, revenue per active account, and fee capture by segment.
4. **Liquidity partners are invisible.** Market-maker obligation compliance belongs in CEO Weekly; it is our cheapest spread lever.
5. **P5 ranks too low.** Weekly reporting is how the board judges whether this role works. Build it first, even though it ranks second on value.
