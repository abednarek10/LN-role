# CEO Review — Ignition v1

**Verdict:** Fine for **Monday's meeting**. **Not for the board** until the P0s ship. Two numbers would be challenged fast: the "231 ERCOT accounts" includes 99 from CAISO, PJM and MISO, and notional ADV's 140% jump came from one spike day ($29.0M on Oct 2 vs about $0.8M normally).

## Decisions

1. **Comp unit: $2,500.** OTE should pay at the 70% Active target, not at perfection. Derive it: `unit = $72k ÷ (funded quota × 1.20)`. After decision 2 the rule gives $1,250.
2. **Quota: raise it and rebalance the book.**
   - Quotas total 114 funded accounts, about half of the ~240 the plan implies. Set AE to 48/yr, Strategic to 36/yr plus an ADV quota.
   - In the seed data, Maya has 179 accounts and Tom 47, and Dana holds 61 of 66 funded PROP/FUND accounts plus 11 LPs. Move LPs to a house "Partnerships" owner and give each AE 2–4 PROP/FUND accounts.
3. **Report LP volume separately.** The band applies to organic (non-LP) ADV, where speculators are 81%.
   - 40–65% was my mistake for year one; hedgers trade sized to load. The 2026 band is **55–75%**, with 40–65% as the 2027 goal.
   - The real gap: hedgers are 45% of Active accounts but 9% of ADV. Target **hedger ADV ≥ 3,000/day** and **LP share ≤ 50%** of total ADV.
   - My notional target drops from $3M to **$1.5M**; $3M doesn't fit a 97%-hourly mix at ~$55/MWh.
4. **Yes, funded-not-trading only:** FUNDED with no qualifying trade after 7 days, FIRST_TRADE not yet Active, and AT_RISK, exposed to the top trigger's ISO, unsuppressed, deduplicated across hubs. That is about 29 accounts.

## Improvement requests

**P0-1 · Action line** (`/api/ceo/weekly`: `lever`, `headline[2]`, `decisions[0]`; `weekly.md`)
- Count as in decision 4. Replace "the team is working them" with drafted / sent / past-SLA counts from `outreach_drafts`.
- *Accept:* `lever.isos` has one key, and `lever.n` equals the distinct funded-not-trading accounts in that ISO's `/pulse/triggers/*/accounts`.

**P0-2 · Notional KPI** (`adv_notional_usd`)
- Median daily notional over 20 trading days, noting "incl. event days $X". `prior` = same metric a week earlier. Target $1.5M.
- *Accept:* moves less than 15% week over week on the seeded data.

**P0-3 · Plan pacing**
- Add `signed_cum` (420) and `funded_cum` (260) with pace-to-date and `required_per_week`, first in the KPI row.
- *Accept:* the page answers "will we hit 260?" on its own.

**P0-4 · Balance KPIs** (decision 3)
- Add `adv_organic`, `speculator_share_adv_organic`, `hedger_adv` and `lp_share_adv`, each with a target and status chip.
- *Accept:* the hedger share of ADV (9%) is judged against a target.

**P1-5 · Book and quota** (decision 2)
- Seed data, `reps.quota_funded_annual`, `comp_plans.json` (derived unit).
- *Accept:* every AE is at 70–130% attainment, at least one is below 100%, and no AE has more than 1.5× another's funded count.

**P1-6 · Queue uplift and capacity** (`/activation/queue`)
- Halve `k_stage` when P ≥ 0.95 with ≥2 trading days (Bufflehead ranks #3 at 99.95%).
- Raise B to 1.5 while hedger share is below 50% (11 of the top 15 are speculators).
- Add a "This week" view capped at 15 touches per AE.
- *Accept:* hedgers are at least 40% of the top 20.

**P1-7 · KPI hygiene**
- Median days funded→first trade: prior equals current (24.4), so it isn't recomputed.
- Fee revenue shows "On track" with no target. Add one or drop the status.
- "Prior" labels mix "prior 20 td" and "prior week". Pick one.

**P2-8 · Polish**
- Cohorts: drop pre-HISTORY_START (2025-12-22 shows 0%); 5 of 9 bars are greyed.
- Sidebar background stops at 900px on long pages.
- Caddo Bend's Account 360 shows P(Active) 99% beside 55% churn risk. Reconcile or explain.

## What's genuinely strong

- Three sentences plus three decisions is the board narrative I asked for.
- The balance donut shows hedgers at 45% of accounts but 9% of ADV, unspun.
- Definitions hold everywhere: LPs split out, small cohorts greyed, watermark on every surface, one Active definition.
- Market Pulse is the demo moment: spike, forward risk, hurt vs. opportunity, and a measured 2.5× lift from triggered outreach.
- The comp simulator runs on the same book; the model is credible (AUC 0.84, challenger, calibration table).
