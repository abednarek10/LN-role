# CPO Review — Ignition v1 (running build)

**Method.** Isolated instance, fresh seed. 5-minute path in Playwright at 1440×900, dark and light. Forced errors. pytest: 180 passed.

## Verdict

**Demo-ready after two P0s.** The IA matches round 1. Both themes are clean, and error states are good.

The wow works mechanically, but it doesn't land yet:
- **192 exposed rows make Pulse 17,875 px tall.** "Who do I call" drowns.
- **CEO Weekly says "231 accounts" (memo: 229) where Pulse says 192**, and it calls an Oct 2 event "today". One mismatch costs the panel's trust.

## Acceptance criteria (round 1)

| # | Criterion | Result |
|---|---|---|
| 1 | Boot ≤30 s, deterministic | **Pass:** seed 5.6 s + boot 9 s |
| 2 | Views <1 s, no console errors | **Pass** |
| 3 | Taxonomy seeded; funnel filterable | **Pass** |
| 4 | ≥3 friction flags with $ and export | **Pass, noisy:** 16 cards, some n=0 |
| 5 | EV score, 3 reasons, NBA; lift ≥2× | **Pass:** 3.5×, AUC 0.836 |
| 6 | Replay → ≥5 exposed, ≥3 segments, both directions | **Letter yes, intent no:** 192 rows; both ERCOT hubs return identical lists |
| 7 | Offline draft <2 s with facts + footer | **Pass:** 132 ms. Dropping the sizing line is accepted as compliance-safer |
| 8 | Queueing changes rank | **Pass:** #16 → #28, with an explanation |
| 9 | Comp switch changes payout and behavior text | **Pass** |
| 10 | Numbers agree across views | **Fail:** 231/229 vs 192; Active 112 (CEO) vs 111 (Funnel) |
| 11 | Tooltips, watermark, pytest | **Pass** |

## Improvement requests

**P0-1 · Pulse exposed-list default** (`frontend/view-pulse.js`, pulse router)
- **Default "Act now" = 20 rows:**
  - the top 15 funded-not-trading accounts by `touch_value`;
  - plus the top 5 SIGNED/KYC_APPROVED accounts by `touch_value`.
- Sort by `touch_value` with a # column. Exclude QUALIFIED prospects.
- Add a "Show all 192" toggle. Clamp "Why exposed" to 2 lines.
- Banner: "192 exposed · 29 funded-not-trading · 20 to act on now".
- *Check:* page height after replay ≤4,000 px. The default shows ≥1 FUNDED REP (hurt) and ≥1 Storage or Prop row (opportunity).

**P0-2 · One event number everywhere** (CEO service, `weekly.md`, Pulse)
- CEO sentence 3, decision 1, the memo, the trigger card and the banner all quote the same `exposed_count`, `funded_not_trading` and `adv_at_stake`.
- Replace "today" with "on Oct 2".
- *Check:* an API test asserts these are equal.

**P1-3 · Hub-specific exposure** (pulse service)
- HB_HOUSTON and HB_NORTH return the same 192 accounts (some on PJM or MISO hubs), and rows name the trigger hub, not the account's.
- Score exposure per settlement hub, and add one account fact per line ("58 MW Houston load · funded 34 d · no trade").
- *Check:* the two ERCOT triggers return different sets.

**P1-4 · Severity framing** (trigger card, banner)
- The $4,800 headline event shows 2.4σ, which is below HB_NORTH (3.7σ) and the CAISO negatives (4.8σ).
- Lead with peak ÷ 30-day p99. Keep σ secondary.
- *Check:* HB_HOUSTON shows the highest intensity of the three.

**P1-5 · CEO hero above the fold** (`view-ceo.js`)
- 12 tiles push the hero to y≈1,050; its violet bars blur together.
- Keep 6 board tiles and put the rest behind "More KPIs".
- Make the hero cumulative signed → funded → Active lines.
- *Check:* the hero's top edge ≤900 px, and the gap is readable without hover.

**P1-6 · Friction-flag noise** (funnel service, `view-funnel.js`)
- Require ≥5 accounts affected. Merge cards with the same segment × step.
- Show the top 6 plus "Show more". Use human step labels.
- The seeded #1 leak (Utility/C&I KYC loops) ranks "Low"; re-check.
- *Check:* ≤6 cards, no n<5.

**P1-7 · Credible #1 account** (stage logic, `account.js`)
- Queue #1 Shinnery shows stage FUNDED next to a "Dormant" pill, and P(active) 96% after 0 trades in 30 days.
- Apply the D2 stage rule.
- Display probabilities as at most ">95%"; the queue shows "100%".
- Audit the +0.54 "Days funded without trading" coefficient. Hide QBR for non-traders.

**P2-8 · Copy pass**
- Enum leaks: "DAILY_PEAK", "'Activated (Active)'", `..` in tickets.
- Rewrite the robotic draft splice and garbled CEO decision 3.
- Pulse footnote calls a first trade "activated" (contradicts D2).

**P2-9 · Calibration**
- 383% quota attainment, and SLA breaches on 48% of the queue, look broken.
- *Check:* attainment 60–160%, breaches <20%.

**P2-10 · Small fixes**
- Segments: the coverage column is clipped.
- Segments: the flywheel copy says HB_NORTH while HB_HOUSTON is selected.
- Segments: the ERCOT spread target shows $1.50; the spec says $0.75.
- Marketing: the small-n legend ("<5") contradicts rows with 5 greyed.
- Pulse: with no triggers it says both "No triggers" and "Select a trigger".
- Footnote the price-driven ADV-notional jump.

## What's strong

- **The IA tells the story.**
- **Compliance as a feature:** linter → Approve → Queue.
- **Honest modelling:** champion vs. challenger, calibration, a credible AUC band.
- **Team & Comp:** cost per Active of $5.7k vs. $23k is board-grade.
- **The friction → priced ticket export.**
