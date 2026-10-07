# CRO Review — Ignition v1 (as of 2026-10-05)

**Verdict: good enough to demo, not ready for reps.** The plumbing works, but ranking and R09 send rep time to the wrong accounts. Fix the P0s first.

## What I found

- **Top 3 all PROP: wrong.**
  - **#1 Shinnery (337):** wrong action. Its real blocker is an **order rejected Oct 1**.
  - **#2 Onyx, #3 Bufflehead:** already ramping at P(active) = 1.0, so a touch adds nothing. #3 also falls through to DEFAULT.
- **Hedger weight is cosmetic.** A weight of 1.15 can't offset a 3–5× ADV prior: the top 20 has 6 hedgers (hedger share 44% vs 50% target).
- **NBA:** conditions evaluate correctly, but R09 outranks R04 and R07, so 198 stalled accounts get a volatility email instead of their stage fix. Ramping accounts show as "at_risk".
- **Comp sim matches my parameters exactly**, which exposes flaws in my round-1 design:
  - The accelerator pays on funded count, so Maya gets $148k at **37% activation**.
  - Quota 24 is too low for the CEO's 260 funded (reps at 105–383%), and $50/1k is 20% of the fee.
  - Proration ignores rep start date (Tom 18.2 vs 14.3), and LPs earn full milestones.
- **Emails:** REP draft sendable; activation draft needs its "30 vs 20 minute" fix. The prop draft ignores that 337 is funded. Don't send the SP15 −$16.83 draft: not news, and "14 hours" contradicts Pulse's "spike hrs 0".

## Decisions

- **(a) Narrow R09: yes.** It fires only when every condition holds:
  - severity ≥ 70
  - stage KYC_APPROVED, FUNDED or FIRST_TRADE (QUALIFIED only if exposure ≥ 90; SIGNED keeps its KYC rule with the event as subject line)
  - exposure_score ≥ 80
  - no triggered sequence in 14 d and no touch in 3 d
  - p_active < 0.95
  - one sequence per ISO event

  ≈28 HB_HOUSTON accounts (26 hedgers). R04, R07, R16 outrank R09.
- **(b) Cap: yes.** "Today" list: 12 per AE/Strategic, 15 per RevOps, 5 for the Head of GTM; ≥ 50% hedger slots while below target. SLA clocks start only on listed items.
- **(c) Pulse default: "Actionable"** (R09 filter), top 25 by touch_value; "All 192" is a toggle.
- **Comp:**
  - The accelerator applies only to Active milestones, and only when book activation ≥ 50%.
  - Quota 48/yr, unit $1,250.
  - Kicker $25/1k, volume target 1.12M.
  - LPs get 25% milestone credit.

## Improvement requests

| # | Pri | Where | Change | Acceptance |
|---|---|---|---|---|
| 1 | P0 | `services/activation.py` (`VOL_TRIGGER_EXPOSED`), `content/nba_rules.json` | Apply decision (a); own-hub exposure ≥ 80 | HB_HOUSTON R09 count 20–40. No SIGNED or SP15 accounts on R09. 337 not on R09 |
| 2 | P0 | `activation.py` + vocabulary + `nba_rules.json` | New `ORDER_REJECTED_7D` rule (R16): FUNDED/FIRST_TRADE, rejection ≤ 7 d, no qualifying trade since. Fix limits/margin. Owner: Solutions Eng + RevOps. SLA 8h. Outranks R07 and R09 | 337 → R16 |
| 3 | P0 | `activation.py score_rows`, `definitions.py`, `/accounts/{id}` health | Priority ×0.3 when first trade ≤ 14 d ago and trading_days_30 ≥ 2 (new "ramping" state). DEFAULT ×0.25 | 367 and 374 out of the top 10. No R99 in the top 25. Health shows `ramping` |
| 4 | P0 | `services/team.py` simulate | Accelerator applies to activation and speed milestones only, gated at book activation ≥ 50%. Q prorated from rep start_date. LP milestone credit = `lp_kicker_credit` | Maya's accelerator = 0. Tom's Q = 14.3 |
| 5 | P1 | `content/comp_plans.json`, comp-sim response + UI | Plan (c): quota 48, unit 1250, kicker 25, volume target 1.12M. Add `totals.pct_of_fee_revenue` for every plan | Field = variable_cost ÷ book fees YTD, shown for (a), (b) and (c) |
| 6 | P1 | `GET /activation/queue?view=today`, `view-queue.js` | Apply decision (b): caps, hedger slots, `summary.backlog`. Count breaches only on listed items. UI defaults to Today | No owner over cap. Each AE list ≥ 50% hedgers |
| 7 | P1 | `services/pulse.py`, `view-pulse.js` | Merge HB_NORTH and HB_HOUSTON into one ERCOT event. Default to Actionable and auto-select the top trigger. Make spike hours consistent | ERCOT shows 1 event. Default ≤ 25 rows. Trigger and draft agree on SP15 hours |
| 8 | P1 | `content/outreach_templates.json`, `services/outreach.py` | Stage-aware variant for FUNDED/KYC_APPROVED. Prop/fund variant cites hub spread and uptime during the event (`spread_snapshots`). Fix the duration mismatch | The 337 draft mentions funded status and the event spread |

## What's strong

- The priority breakdown is shown in every row, so reps can see why an account ranks where it does.
- Compliance gating is intact: linter, approve → queue, suppression, disclaimers (337 suppressed and moved to R07).
- Account 360 surfaced 337's real blocker in seconds.
- The comp sim's side-by-side comparison makes the CEO case for paying on activation.
- Pulse's forecast overlay, hurt/opportunity labels and 2.5× lift panel are the demo moment.
- LPs are excluded, mobile layout holds, no console errors.
