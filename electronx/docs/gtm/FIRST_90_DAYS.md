# First 90 Days as Head of GTM & Revenue

**Start:** Mon 2026-10-12 · **Day 30:** 11-10 · **Day 60:** 12-10 · **Day 90:** 2027-01-09. Day 80 falls on the end-2026 deadline.
**Starting point** (synthetic calibration as of 2026-10-05; illustrative):

| Metric | Now | EOY 2026 target | Gap |
|---|---|---|---|
| Signed (cumulative) | ≈330 | 420 | +90, about 7/week vs a ~6/week run-rate |
| Funded | ≈205 | 260 | +55, about 4.2/week |
| Active rate (funded >20 days) | ≈62% | ≥70% | +8 pts; ≈182 Active at 260 funded vs ≈127 today |
| 30-day cohort activation | ≈50% | 55% → 70% (Q4 cohorts) | +20 pts |
| Median days funded → first qualifying trade | ≈21 | ≤10 | −11 days |
| ADV (20-td, contracts) | 14–17k | 25k | +~9k |
| Hedger share of Active | ≈44% | ≥50% | +6 pts |
| Top-5 ADV share | ≈50% | ≤45% | −5 pts |
| ERCOT North spread | ≈$0.90/MWh | ≤$0.75, ≥95% uptime | tighten |

**Thesis.** The pipeline is enough. The gap sits between signature and habit. Most of the remaining 2026 upside comes from about 78 funded-but-not-Active accounts and about 125 signed-but-unfunded accounts, and from timing outreach to volatility. New logos matter less.

---

## Days 1–30: Instrument, triage, earn trust

| # | Action | Ignition module | Proof metric (by day 30) |
|---|---|---|---|
| 1 | Lock definitions with the CEO, CFO and Compliance: Active (≥4/30), qualifying trade (≥10 contracts, no self-match), Dormant, and a separate LP line | `definitions.py`; every view | Memo numbers equal dashboard numbers (test green); one definition in comp, memo and queue |
| 2 | Ship the Friday CEO memo from week 1, with three decisions every week | **CEO Weekly** + `/ceo/weekly.md` | 4/4 memos sent by Fri 17:00; each decision has a number and an owner |
| 3 | Triage the stalled funded book: every FUNDED account more than 21 days past funding gets an R07 exec call and a reason code | **Activation Queue** (R07, R06) | 100% of stalled accounts have a reason code; ≥25% of them have a qualifying trade by day 30 |
| 4 | Turn on volatility response with compliance-approved templates and the 07:30 Pulse triage | **Market Pulse** + copilot + compliance linter | Trigger → approved T0 email in ≤4h for ≥90% of triggers; 0 drafts sent without approval |
| 5 | KYC fast lane: prefilled packet and same-day chase on the named document | **Funnel & Journey** (friction flags), Queue R03/R04 | Median signed → KYC approved down from baseline by ≥3 days for that month's signings |
| 6 | Run 1:1s on scorecard baselines; publish NBA SLAs | **Team & Comp** scorecards | SLA adherence measured for every rep; baseline score captured |
| 7 | Listening tour: 15 customer calls across all 8 segments plus 3 LPs, each logged with a reason code | **Account 360** | Top-3 blockers by segment written into the playbook objections |

## Days 31–60: Run the engine, start the tests

| # | Action | Ignition module | Proof metric (by day 60) |
|---|---|---|---|
| 8 | Full NBA rulebook live (v1.1 precedence R16 → R07 → R04 → R09), with the Today view (caps 12/15/5, ≥50% hedger slots) and the Wednesday stand-up reviewing every red SLA | **Activation Queue** | SLA adherence ≥85% on Today items; hedgers ≥40% of the top 20; queue top decile shows ≥2× lift on holdout |
| 9 | Launch experiments E1, E2, E3, E5 and E6 (below) with pre-registered metrics | Market Pulse, Queue, Funnel & Journey | Assignment logged for 100% of eligible accounts; no contamination across arms |
| 10 | Rebalance coverage toward hedger segments below target. Strategic Sales takes the top-20 and runs QBRs | **Segments**, Account 360 (R13) | Hedger share of Active ≥47%; 20/20 top accounts have a QBR scheduled |
| 11 | Start the plan (c) shadow comp at v1.1 parameters (quota 48, unit $1,250, $25/1k kicker, accelerator gated at ≥50% book activation): reps paid max(current, c) | **Team & Comp** simulator | Variable cost per Active account and `pct_of_fee_revenue` reported weekly under all 3 plans; plan (c) ≤40% of book fees |
| 12 | Price the top 3 friction flags and take them to Product as roadmap asks | **Funnel & Journey** roadmap export | 3 tickets accepted with $ at stake; ≥1 shipped or scheduled |
| 13 | Scoring model review: calibration and reasons sanity check with RevOps | Queue › **Model** panel | AUC within 0.72–0.85, top-decile lift ≥2.0, calibration error <5 pts per bin |

## Days 61–90: Scale what worked, lock in 2027

| # | Action | Ignition module | Proof metric (by day 90) |
|---|---|---|---|
| 14 | Read out E1–E3 and E5–E6. Make winners default rules or sequences; retire losers | Queue rules (`nba_rules.json`), `sequences.json` | Q4 30-day cohort activation ≥65% (stretch 70%); median funded → first trade ≤12 days (stretch ≤10) |
| 15 | Re-estimate k_stage from holdouts; adjust queue priorities | Queue › Model | k_stage updated; activations per rep-hour up ≥20% vs days 1–30 |
| 16 | Comp decision for 2027: plan (c) with the derived unit ($72k ÷ (quota × 1.20)), presented with the simulator | **Team & Comp** | CEO/board approval; on-target payout within ±15% of OTE; every AE at 70–130% of start-date-prorated quota |
| 17 | Concentration and liquidity plan: LP quoting obligations by hub plus speculator adds outside the top-5 | **CEO Weekly** mix, liquidity view | Top-5 ADV share ≤47% and falling; ERCOT North spread ≤$0.80 |
| 18 | 2027 operating plan: capacity model (accounts per AE per stage), hiring asks, Marketing ROI reallocation, kept thin until n ≥ 1,000 | Segments, **Marketing ROI** | Plan ties each hire or dollar to funded and Active accounts and ADV |

**End-of-period scoreboard (day 90):** funded ≥260 · Active rate ≥70% · ADV ≥22k, run-rate to 25k in Q1 · hedger share ≥50% · net ADV retention (top-20) ≥110%, with ≥120% committed for Q1.

---

## Experiment backlog

**Conventions:** two-sided α = 0.05 and power 0.80 (z_α/2 + z_β ≈ 2.80). The MDE is absolute, in percentage points or days, computed from expected eligible volumes at the current run-rate (about 5 funded accounts/week, about 6–7 signings/week, about 40 eligible exposed accounts/month across ISOs). Our volumes are small, so several MDEs are large. Those tests are labeled **directional**: low-cost, low-risk changes ship if P(better) ≥ 80% under a Bayesian beta-binomial read with no harm signal. Randomization is at the account level and logged in `activities.sequence` or a test tag.

| ID | Experiment | Hypothesis | Primary metric | Design and n | MDE | Duration |
|---|---|---|---|---|---|---|
| **E1** | **Volatility-triggered vs standard sequence** | Exposed pre-Active accounts contacted within 4h of a trigger activate faster than accounts left on the standard activation cadence | Qualifying trade within 14 days of the trigger | 70/30 random holdout of R09-eligible accounts (v1.1 filter: severity ≥70, exposure ≥80, stage KYC_APPROVED–FIRST_TRADE) per ISO event; ≈84 / 36 | **24 pts** (baseline ≈16%; historical observational gap ≈25 pts) | 12 weeks |
| **E2** | **Walkthrough within 48h of funding** vs the D7 invite | A live hub-replay walkthrough before inertia sets in cuts time to first trade | Days funded → first qualifying trade (secondary: 30-day qualifying-trade rate) | Alternating assignment by funding date; ≈30 / 30 | **8.7 days** (sd ≈12); rate MDE 36 pts (directional) | 12 weeks |
| **E3** | **Prefilled KYC packet** vs the standard checklist | Pre-populating entity, LEI and authorized-trader fields removes the `kyc_info_requested` loop, the #1 drop-off for UTILITY and CI_LOAD | Median days signed → KYC approved (secondary: share with ≥1 info-request loop) | Alternating by signing week; ≈40 / 40 | **5.0 days** (sd ≈8); loop-rate MDE 30 pts | 12 weeks |
| **E4** | **Activation-weighted comp pilot** (plan c shadow) | Paying on Active plus ADV raises the book's 60-day activation rate without raising cost per Active account | Funded → Active ≤60d rate (secondary: variable cost per Active account, `pct_of_fee_revenue`) | All quota carriers on the shadow plan; pre/post with diff-in-diff vs a segment-mix-adjusted baseline; ≈205 pre / 60 post accounts | **20 pts** (directional; n = 5 reps cannot be randomized) | 1 quarter + 60-day maturation |
| **E5** | **Forward-risk vs realized-spike framing** in the T0 email | Leading with the next forecast peak reads as planning, not "insurance after the fire," and earns more replies | Reply or meeting booked within 5 business days | Message-level A/B within E1's treated arm; ≈60 / 60 | **20 pts** (baseline ≈20%) | 12 weeks |
| **E6** | **Uplift holdout by stage** (k_stage validation) | Touch uplift differs by stage. Funded/no-trade (k = 0.35) gains more than Active (0.10) | Stage exit within 14 days, treated vs holdout | 10% of queue items per stage held out for 14 days (excludes top-20, LPs, live triggers); ≈900 / 100 pooled | **13.5 pts** pooled; per-stage directional | 12 weeks |
| **E7** | **Debrief within 3 business days of first trade** vs the day-10 rule (R10) | An early debrief that agrees a weekly routine converts first-traders into habits | Days first trade → 2nd distinct trading day (secondary: Active ≤30d of first trade) | Alternating by first-trade date; ≈32 / 32 | **4.9 days** (sd ≈7); rate MDE 35 pts (directional) | 16 weeks |
| **E8** | **EV-of-touch ranking vs raw propensity** | Ranking on P × E[ADV] × k_stage × U × B produces more activations per rep-hour than ranking on P alone | Activations per rep-hour | Rep-week crossover: each AE alternates ranking weekly; 16 rep-weeks per arm | **35% relative** | 8 weeks |

**Stopping and ethics rules.**
- No holdout ever applies to an account with an open compliance issue, to a top-20 account, or to a liquidity partner.
- E1's holdout still gets the standard sequence. Nobody is left without a touch.
- Any experiment showing harm at P(worse) ≥ 90% at an interim read (weeks 4 and 8) stops.
- Results are published in the Friday memo with n. Cohorts with n < 20 are greyed out.
