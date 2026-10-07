# CRO Review — Ignition v1 (Round 3, as of 2026-10-05)

**Verdict: good enough to demo, not yet ready for reps to work from.** The plumbing is right: the formula is visible, compliance gating works, and approving and queueing a draft feeds straight back into the queue and Pulse (checked: account 337 was suppressed and changed to R07). The *ranking* and *R09* send rep time to the wrong accounts. Fix the four P0s below before any AE uses this.

## What I found

- **Top 3 all PROP: not right.**
  - **#1 Shinnery (337):** ranking it top is defensible on EV, but the action is wrong. It had an **order rejected on Oct 1** (margin/limits). That's the blocker, and it's an ops fix, not a volatility email.
  - **#2 Onyx (367) and #3 Bufflehead (374):** both are already ramping, with 3 trading days in 10 and 3 in 4 respectively, and P(active) of 1.0. A touch adds nothing.
  - **The DEFAULT rule at #3 wastes the top slot.**
- **Hedger weight is cosmetic.** A balance weight of B = 1.15 can't offset a 3–5× ADV prior. Only 6 of the top 20 are hedgers, and hedger share of Active is 44% against a 50% target.
- **NBA:**
  - The conditions themselves evaluate correctly.
  - **Rule order is wrong.** R09 fires ahead of R04 and R07, so 198 stalled accounts, KYC stalls among them, get a volatility email instead of their stage fix.
  - Onyx and Bufflehead are labelled "at_risk" during their first trading week.
- **Comp sim** reproduces my parameters faithfully. Unit, multipliers, 100% clawback over 60 days, the $50/1k kicker with its $10k cap, and the 25% LP credit all check out. It does expose flaws in my round-1 design, though:
  - **Accelerator ignores activation.** It pays on funded count regardless of whether accounts activate, so Maya earns $148k (148% of variable) at **37% activation**.
  - **Quota is miscalibrated.** A quota of 24/yr can't reach the CEO's 260 funded across 5 carriers, which is why every rep shows 105–383% attainment.
  - **The kicker is too rich.** $50/1k is 20% of the $0.25 fee.
  - **Proration ignores rep start date.** Tom's quota is 18.2 in the sim against 14.3 on the scorecard.
  - **LPs earn full milestones.**
- **Emails:**
  - **REP "hurt" draft:** I'd send it as written.
  - **Activation draft:** send after one fix. It offers "30 minutes" but the CTA says "20-minute".
  - **Prop draft:** reads like prospecting copy, offering an API/sandbox intro to an account funded 31 days ago. It talks about what the venue needs rather than the desk.
  - **SP15 −$16.83 draft:** I would not send it. It isn't news to a desk, and "14 hours" contradicts Pulse's "spike hrs 0".

## Decisions

- **(a) Narrow R09: yes.** The rule should match only when all of these hold:
  - trigger severity ≥ 70
  - stage ∈ {KYC_APPROVED, FUNDED, FIRST_TRADE}, plus QUALIFIED only if exposure ≥ 90 (SIGNED keeps its KYC rule and uses the event as the subject line)
  - exposure_score ≥ 80
  - no triggered sequence in 14 days and no touch at all in 3 days
  - p_active < 0.95
  - one sequence per account per ISO event

  On today's data that is about 28 accounts for HB_HOUSTON, 26 of them hedgers. R04, R07 and new R16 outrank R09.
- **(b) Cap the queue per rep per day: yes.** The daily "Today" list holds:
  - 12 items per AE or Strategic seller
  - 15 per RevOps associate
  - 5 for the Head of GTM

  While hedger share is below target, at least 50% of each list goes to hedgers. The SLA clock starts only when an item is on the list. Everything else sits in a backlog.
- **(c) Pulse default:** an "Actionable" view, which applies the R09 eligibility filter and shows the top 25 by touch_value. The highest-severity trigger is auto-selected. "All 192" remains a toggle.
- **Comp:**
  - The accelerator applies to Active milestones only, and only when book activation is ≥ 50%.
  - AE quota rises to 48 funded/yr; per-account unit $1,250.
  - Kicker $25 per 1k contracts; volume target 1.12M.
  - LP accounts get 25% credit on milestones.

## Improvement requests

| # | Pri | Where | Change | Acceptance check |
|---|---|---|---|---|
| 1 | P0 | `services/activation.py` (`VOL_TRIGGER_EXPOSED`), `content/nba_rules.json` priorities | Apply decision (a); `account_trigger` matches own-hub exposure ≥ 80 | HB_HOUSTON R09 count is 20–40. Zero SIGNED accounts on R09. Zero R09 from SP15. Account 337 is not on R09 |
| 2 | P0 | `activation.py` + vocabulary + `nba_rules.json` | New `ORDER_REJECTED_7D` rule (R16): FUNDED/FIRST_TRADE with `order_rejected` in the last 7 days and no qualifying trade since. Action: fix limits/margin. Owner: Solutions Eng + RevOps. SLA 8h. Outranks R07 and R09 | Account 337 → R16 |
| 3 | P0 | `activation.py score_rows`, `definitions.py` | Priority × 0.3 when first trade was ≤ 14 days ago and trading_days_30 ≥ 2 ("Ramping" state, also in `/accounts/{id}` health). Priority × 0.25 for DEFAULT | 367 and 374 drop out of the top 10. No R99 in the top 25. Health shows `ramping`, not `at_risk` |
| 4 | P0 | `services/team.py` simulate | Accelerator applies only to activation and speed milestones, and only if book activation ≥ 50%. Q prorated from `max(period_start, rep.start_date)`. LP milestone credit = `lp_kicker_credit` | Maya's accelerator = 0. Tom's Q is 14.3. Dana's funded milestone reflects LP at 25% |
| 5 | P1 | `content/comp_plans.json`, comp-sim response + Team UI tile | Plan (c) defaults: quota 48, unit 1250, kicker 25, volume target 1,120,000. Add `totals.pct_of_fee_revenue` for all plans | Field present = variable_cost ÷ book fees YTD. The UI shows it for (a), (b) and (c) |
| 6 | P1 | `GET /activation/queue?view=today`, `view-queue.js` | Apply decision (b): per-owner caps, hedger slots, `summary.backlog`; SLA breaches counted only for items on the Today list. UI defaults to Today | No owner exceeds their cap. Each AE's list is ≥ 50% hedgers. The breach count is ≤ total cap |
| 7 | P1 | `services/pulse.py`, `view-pulse.js` | Merge HB_NORTH and HB_HOUSTON into one ERCOT event, with each account mapped to its own hub. Show an `actionable` count and make Actionable the default view. Auto-select the top trigger. Make the SP15 hours consistent between trigger and draft facts | ERCOT shows 1 event. The default list is ≤ 25 rows. The two views agree on spike hours |
| 8 | P1 | `content/outreach_templates.json`, `services/outreach.py` facts | Stage-aware volatility variant for FUNDED/KYC_APPROVED ("your account is funded…"). The prop/fund variant cites hub spread and two-sided uptime during the event from `spread_snapshots`. Fix the 30 vs 20 minute mismatch | The account 337 draft mentions funded status and the event spread. No draft contains conflicting durations |

## What's strong

- **The priority decomposition is shown in every row** (P, E[ADV], k, U, B). Reps can argue with it, and that builds trust.
- **The compliance path works:** draft → linter → approve → queue → suppression, with a disclaimer on every draft, and approval can't be skipped.
- **Account 360** gave me the real blocker (the order rejection) in seconds. The onboarding chips are excellent.
- **The comp simulator's side-by-side plan comparison** makes the case to the CEO for paying on activation.
- **Pulse:** the chart with the forecast overlay, hurt/opportunity labels, and the 2.5× lift panel are the demo moment.
- **Liquidity partners are excluded from the queue**, mobile layout holds, and the UI threw no console errors.
