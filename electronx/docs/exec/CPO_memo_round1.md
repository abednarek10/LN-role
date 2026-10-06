# CPO Memo — Round 1: Ignition Product Shape

**From:** CPO · **To:** CEO, CRO, CTO · **Re:** IA, instrumentation, demo spine, v1 scope

## 1. Jobs-to-be-done

| Persona | Job | Primary view |
|---|---|---|
| CEO | "Tell me in 60 seconds if signatures are becoming liquidity, and what to do about it." | CEO Weekly |
| Head of GTM | "Point four people at the accounts and moments that produce ADV, and pay them for it." | Activation Queue, Team & Comp |
| AE | "Tell me who to call today, why now, and give me the first draft." | Market Pulse, Activation Queue |
| RevOps | "Trust the score, see why it fires, and prove its lift." | Activation Queue (Model tab) |
| Marketing Mgr | "Know which dollar produced an *active* account, not a lead." | Marketing ROI |
| Head of Product | "See which onboarding step leaks, how much ADV it costs, and what to build." | Funnel & Journey |

## 2. Information architecture (nav order = demo order)

Seven tabs plus one drill-down. **Account 360** opens from any account name; it is not a tab.

| # | View | Question it answers | Hero | Key components | Primary action |
|---|---|---|---|---|---|
| 1 | **CEO Weekly** | Are we turning signatures into active traders, fast enough? | Weekly stacked bars (funded / first-trade / active) against a 2026 target line | KPI tiles (active accounts, funded→active %, median days-to-first-trade, ADV); hedger-vs-speculator mix; activation by segment; spread quality | Export weekly memo (.md) |
| 2 | **Market Pulse** | Where is power hurting right now, and who is exposed? | Hub price chart with spike/regime bands, one tab per ISO | Event banner (σ, $/MWh, hub); exposed-accounts list with "why exposed"; draft panel; triggered-vs-untriggered cohort chart | Draft and queue outreach |
| 3 | **Activation Queue** | Which account do I touch next, and with what? | Table ranked by expected value of a touch | Stall diagnosis; next-best action; "why this score" drawer (top 3 drivers); Model sub-tab with lift chart and calibration | Log touch / draft |
| 4 | **Funnel & Journey** | Which step leaks, and what does it cost? | Step funnel showing conversion % and median days per step | Segment/ISO filter; cohort time-to-first-trade curve; friction flags; roadmap-ask cards | Export roadmap ask |
| 5 | **Team & Comp** | Does our comp pay for volume or for signatures? | AE scorecard grid | Per-AE funded, activated, ADV influenced; plan simulator (3 presets + weights); payout delta; "behavior rewarded" callout | Compare plans |
| 6 | **Segments** | Where is the unworked value? | Segment × ISO heatmap (penetration × ADV/account) | TAM counts; activation by cell; coverage gaps; owner assignment | Assign coverage |
| 7 | **Marketing ROI** | Which channel produces active accounts? | Channel bar: cost per *active* account | Channel funnel; CAC per funded vs. active; ADV per $; reallocation slider | Shift budget |
| — | **Account 360 / QBR** | Is this institution growing or slipping? | ADV trend with product-utilization overlay | Health score; churn signals; journey timeline; growth plays | Export QBR pack |

**5-minute script:** CEO Weekly (0:45, shows the gap) → Market Pulse (1:30, the wow) → Activation Queue (1:00) → Funnel & Journey (0:45) → Team & Comp (0:45) → back to the CEO memo (0:15). Tabs 6–7 and Account 360 stay in reserve for Q&A.

## 3. Onboarding instrumentation

Event taxonomy, in order. Every event carries `account_id, user_id, ts, segment, iso, channel, owner_ae, source`.

0. `contract_signed` (CRM). The sales→ops handoff leaks too, so the funnel starts here.
1. `account_created`
2. `first_login`
3. `kyc_submitted` {entity_type, doc_count}
4. `kyc_info_requested` {reason}. This is a loop event that can repeat.
5. `kyc_approved`
6. `agreements_signed` {agreement_set}
7. `bank_linked` {method}
8. `funded` {amount}
9. `order_ticket_opened`. This captures intent.
10. `first_order_placed` {contract, iso}
11. `order_rejected` {reason: margin, price_band, permissions}
12. `first_trade`
13. `activated` (≥4 distinct trading days in a rolling 30 days). **This is the true finish line.**
14. `dormant` (no trade in 30 days after activation)

**Auto-flag rules.** Each fires per segment × ISO.
- Step conversion is ≥10 pts below the all-account baseline.
- Median dwell time is more than 2× baseline, or the p75 is above the SLA (KYC 5 days, funding 7 days).
- The `kyc_info_requested` rate is above 25%.
- An account is **funded with no order for 14+ days**.
- `order_ticket_opened` with no order, or `order_rejected` before the first trade.
- An account makes one trade and never activates.

**Flag → roadmap ask.** Each flag becomes a card with five parts:
- **Problem:** for example, "Data-center accounts wait 11 days at bank_linked."
- **Evidence:** n accounts, conversion, dwell time.
- **ADV at stake:** stalled accounts × P(activate) × expected ADV × fee.
- **Hypothesis**
- **Ask** and **success metric**

Cards are ranked by dollars at stake and export as Markdown tickets. Product gets a priced backlog, not anecdotes.

## 4. The wow moment

1. Open **Market Pulse** on ERCOT. Press **Replay** on a seeded event (Aug, 17:40, HB_HOUSTON real-time price at $4,800/MWh, 5.1σ, regime = SCARCITY). Replay keeps the demo deterministic.
2. The banner reads "14 accounts exposed · 6 funded-not-trading · ~$X ADV at stake."
3. Each exposed row explains the exposure in plain words, with the direction of the pain:
   - REP: "short Houston load, unhedged index, funded 19 days, no trade"
   - Solar IPP: "evening-ramp shape risk"
   - Battery: "opportunity, spread at a 90-day high"
   - Prop firm: "liquidity-provision opportunity"
4. Click **Draft** on the REP. The email cites the hub, the price, the timestamp and the daily peak contract that maps to that exposure. It adds an *illustrative* sizing line ("a 10 MW daily peak position would have covered ~$Y of this interval"), a segment-specific call to action and a compliance footer ("educational, not a recommendation"). The template engine runs offline; Claude is used when an API key is set.
5. The AE edits the draft and clicks **Queue**. The touch is logged, the account is tagged `triggered:ERCOT-0817`, and the **Activation Queue re-ranks live** with an urgency multiplier.
6. Scroll to **past events**: triggered cohort 41% activated in 14 days vs. 16% untriggered. The feature is measured, not a gimmick.

The operator signal is the closed loop (event → exposure → action → measured lift). The power-markets signal is that exposure *direction* differs by segment, and that volatility is pain for hedgers but opportunity for liquidity providers.

## 5. Scope cuts (v1)

- No auth or RBAC. A persona switcher only changes the default landing tab.
- No live ISO feeds. Seeded replay sits behind an adapter interface.
- No email sending and no CRM write-back. Users copy the draft or use a `mailto:` link.
- No in-app model training UI. Logistic regression is fit at seed time; the coefficients are shown.
- No websockets, no multi-tenancy and no order book. Spread quality is a single metric.
- No free-form comp formula editor.

## 6. v1 acceptance criteria

- [ ] One command boots a clean clone in ≤30 s. The same seed yields byte-identical API responses (hash test).
- [ ] Every view renders in <1 s on seed data (~600 accounts; 4 ISOs × 2 hubs; 12 months of hourly prices). No console errors.
- [ ] Seed data contains every taxonomy event. Funnel shows conversion and median dwell for all steps, filterable by segment and ISO.
- [ ] Seed data yields ≥3 friction flags. Each flag has $ at stake and an exportable Markdown roadmap ask.
- [ ] Every queue row has an EV score, the top 3 reason codes and a next-best action. Holdout lift at the top decile is ≥2×.
- [ ] The ERCOT replay surfaces ≥5 exposed accounts across ≥3 segments with different exposure directions.
- [ ] The draft generates in <2 s without an API key. It contains the hub, price, timestamp, account name, segment angle and compliance footer.
- [ ] Queueing a draft logs the touch and changes that account's queue rank.
- [ ] Switching comp plans changes per-AE payout and the "behavior rewarded" text.
- [ ] Memo export numbers equal the dashboard numbers (test).
- [ ] Every metric has a tooltip definition. A "Synthetic data" badge is on every view. pytest is green.

## 7. Disagreements with the synthesis

1. **Ten modules is too many for five minutes.** Collapse them to 7 tabs. W4 Scoring lives inside the Queue, W10 Copilot is a capability rather than a view, and Account 360 is a drill-down.
2. **Score target.** P(first trade ≤45d) rewards token trades. Model P(`activated` by day 60) instead. The synthesis itself says one-and-done does nothing for liquidity, and P6 warns about this kind of misalignment.
3. **The funnel starts too late.** `contract_signed` → `account_created` is a handoff we own ("enters YOUR system"), so instrument it.
4. **Define "active" once** (≥4 trading days in 30) and use that definition in every view, the memo and comp. An undefined north star breeds argument.
5. **W1's north star is vanity.** "Report time → 0" is a side effect. Lead the memo with the *three decisions this week*, each tied to a flag or event.
6. **Pulse must cover liquidity providers as well as hedgers.** Otherwise we market only to natural hedgers and starve the spread. Volatility outreach also needs a compliance review step before anything is sent.
