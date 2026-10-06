# CPO Memo — Round 1: Ignition Product Shape

**From:** CPO · **To:** CEO, CRO, CTO

## 1. Jobs-to-be-done

| Persona | Job | View |
|---|---|---|
| CEO | "In 60 seconds: are signatures becoming liquidity, and what do I decide?" | CEO Weekly |
| Head of GTM | "Aim four people at the accounts and moments that create ADV, and pay for it." | Queue, Team & Comp |
| AE | "Who do I call today, why now, and give me the draft." | Market Pulse, Queue |
| RevOps | "Trust the score, see why it fires, prove its lift." | Queue › Model |
| Marketing Mgr | "Which dollar produced an *active* account?" | Marketing ROI |
| Head of Product | "Which onboarding step leaks, what it costs, and what to build." | Funnel & Journey |

## 2. Information architecture (nav order = demo order)

There are seven tabs. **Account 360** is a drill-down from any account name, not a tab.

| # | View | Question | Hero | Key components | Primary action |
|---|---|---|---|---|---|
| 1 | **CEO Weekly** | Are we converting signatures to active traders fast enough? | Weekly funded / first-trade / active bars against a 2026 target | KPI tiles; hedger-vs-speculator mix; activation by segment; spread quality | Export memo (.md) |
| 2 | **Market Pulse** | Where is power hurting now, and who's exposed? | Hub price chart with regime bands, per ISO | Event banner; exposed accounts with "why"; draft panel; triggered-vs-untriggered cohorts | Draft and queue outreach |
| 3 | **Activation Queue** | Who do I touch next, with what? | Table ranked by EV of touch | Stall diagnosis; next-best action; top-3 reason drawer; Model sub-tab (lift, calibration) | Log touch |
| 4 | **Funnel & Journey** | Which step leaks, and what does it cost? | Step funnel: conversion % and median days | Segment/ISO filter; time-to-first-trade curves; friction flags; roadmap cards | Export roadmap ask |
| 5 | **Team & Comp** | Does comp pay for volume or signatures? | AE scorecard grid | Funded, activated, ADV per AE; plan simulator; payout delta; "behavior rewarded" | Compare plans |
| 6 | **Segments** | Where is the unworked value? | Segment × ISO heatmap | TAM; penetration; ADV/account; coverage gaps | Assign coverage |
| 7 | **Marketing ROI** | Which channel yields active accounts? | Cost per *active* account by channel | Channel funnel; CAC funded vs. active; ADV per $ | Shift budget |
| — | **Account 360 / QBR** | Is this institution growing? | ADV trend with utilization overlay | Health; churn signals; journey timeline; plays | Export QBR |

**Demo script (5 minutes):**
1. CEO Weekly shows the gap (0:45).
2. Market Pulse delivers the wow (1:30).
3. Activation Queue (1:00).
4. Funnel & Journey (0:45).
5. Team & Comp (0:45).
6. Close on the CEO memo (0:15).

Segments, Marketing ROI and Account 360 are held in reserve for Q&A.

## 3. Onboarding instrumentation

Every event carries `account_id, ts, segment, iso, channel, owner_ae`. Steps in order:

0. `contract_signed`: the sales→ops handoff, from the CRM
1. `account_created`
2. `first_login`
3. `kyc_submitted`
4. `kyc_info_requested` {reason}: a loop that can repeat
5. `kyc_approved`
6. `agreements_signed`
7. `bank_linked`
8. `funded` {amount}
9. `order_ticket_opened`: intent
10. `first_order_placed`
11. `order_rejected` {reason}
12. `first_trade`
13. **`activated`**: ≥4 trading days in a rolling 30
14. `dormant`

**Auto-flags.** Each one fires per segment × ISO:
- Step conversion ≥10 pts below baseline.
- Median dwell more than 2× baseline.
- KYC information-request rate above 25%.
- Funded with no order for 14+ days.
- Ticket opened but no order, or a rejection before the first trade.
- One trade, never activated.

**Flag → roadmap ask.** Each flag becomes a card with:
- **Problem:** for example, "Data centers wait 11 days at bank_linked."
- **Evidence:** n accounts, conversion, dwell.
- **ADV at stake:** stalled × P(activate) × expected ADV × fee.
- **Ask**
- **Success metric**

Cards are ranked by dollars at stake and export as Markdown tickets. Product gets a priced backlog instead of anecdotes.

## 4. The wow moment

1. On **Market Pulse › ERCOT**, press **Replay** on a seeded event: HB_HOUSTON real-time price at $4,800/MWh, 5.1σ, regime SCARCITY. Replay keeps the event deterministic.
2. The banner reads: "14 accounts exposed · 6 funded-not-trading · ~$X ADV at stake."
3. Rows state the exposure *direction*:
   - REP: "short Houston load, unhedged, funded 19 days, no trade"
   - Solar IPP: "evening-ramp shape risk"
   - Battery: "opportunity, spread at a 90-day high"
   - Prop firm: "liquidity-provision opportunity"
4. **Draft** on the REP produces an email with:
   - the hub, price and timestamp;
   - the matching daily-peak contract;
   - an *illustrative* sizing line ("10 MW would have offset ~$Y");
   - a compliance footer ("educational, not a recommendation").

   The template engine works offline. Claude is used when a key is set.
5. **Queue** logs the touch and tags the account `triggered:ERCOT-0817`, and the **Activation Queue re-ranks live**.
6. **Past events** show the triggered cohort at 41% activated in 14 days, against 16% untriggered.

**Why it works:** the operator sees a closed loop with measured lift, and the power-markets expert sees that the same spike is pain for hedgers and opportunity for liquidity providers.

## 5. Scope cuts

- No auth or RBAC. A persona switcher sets the landing tab.
- No live ISO feeds. Seeded replay runs behind an adapter interface.
- No email sending and no CRM write-back. Drafts are copied or sent with `mailto:`.
- No training UI. Logistic regression is fit at seed time.
- No websockets, multi-tenancy, order book or free-form comp-formula editor.

## 6. Acceptance criteria (v1)

- [ ] One command boots a clean clone in ≤30 s. The same seed yields identical API responses (hash test).
- [ ] Each view renders in under 1 s on seed data (~600 accounts, 4 ISOs × 2 hubs, 12 months hourly), with no console errors.
- [ ] All taxonomy events are seeded. The funnel shows conversion and median dwell per step, filterable by segment and ISO.
- [ ] At least 3 friction flags are generated, each with $ at stake and an exportable roadmap ask.
- [ ] Every queue row has an EV score, top-3 reasons and a next-best action. Holdout top-decile lift is ≥2×.
- [ ] The ERCOT replay surfaces ≥5 exposed accounts across ≥3 segments with differing directions.
- [ ] The draft generates in under 2 s with no API key and includes hub, price, timestamp, account, segment angle and the compliance footer.
- [ ] Queueing a draft changes that account's rank.
- [ ] Switching comp plans changes per-AE payout and the behavior text.
- [ ] Memo numbers equal dashboard numbers (test).
- [ ] Every metric has a tooltip definition, a "Synthetic data" badge appears on every view, and pytest is green.

## 7. Disagreements with the synthesis

1. **Ten modules won't fit five minutes.** Fold W4 into the Queue, treat W10 as a capability rather than a view, and make Account 360 a drill-down.
2. **Score target.** P(first trade ≤45d) rewards token trades. Model P(`activated` by day 60) instead; P6 warns about exactly this.
3. **Start the funnel at `contract_signed`.** The handoff into "YOUR system" leaks too.
4. **Define "active" once** and use that definition in every view, the memo and comp.
5. **W1's north star is vanity.** "Report time → 0" is a side effect. Lead the memo with *this week's three decisions*.
6. **Pulse must target liquidity providers, not just hedgers.** Otherwise spreads starve. Volatility outreach also needs a compliance review step.
