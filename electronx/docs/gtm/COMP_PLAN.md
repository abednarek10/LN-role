# AE Compensation Design: Paying for Liquidity, Not Signatures

**Source of truth:** `ignition/content/comp_plans.json`, which the Team & Comp simulator (`POST /api/team/comp-sim`) runs against the synthetic book. The parameters come from the CRO memo §4. The definitions come from `ignition/definitions.py`: Active means at least 4 distinct trading days in the trailing 30, and a qualifying trade is at least 10 contracts and not a self-match.

## 1. The design problem

An exchange earns fees on ADV, and ADV comes from accounts that trade habitually. A comp plan that pays at signature produces signatures. A plan that pays at funding produces funded accounts that sit dormant. With four AEs and 205 funded accounts, of which about 62% are Active against a 70% target, comp is the cheapest lever on activation. It is also the easiest to get wrong.

**Fixed for all plans:** OTE $250k, a 60/40 split (base $150k, variable $100k), a quota of 24 funded accounts per year, and a 1.5× accelerator above 100% of quota.

## 2. The three plans

| | (a) `pay_on_signature` | (b) `pay_on_funded` | (c) `activation_adv` (recommended) |
|---|---|---|---|
| Unit | $4,166.67 per signature ($100k/24) | $4,166.67 per funded account | $2,000 × M |
| Milestones M | signed = 1.0 | funded = 1.0 | funded 0.5 · Active ≤60d +1.0 · Active ≤21d +0.25 (max M = 1.75, so $3,500 per account) |
| Volume kicker | — | — | $50 per 1k contracts traded by the account in its first 12 months, capped at $10k per account. Book contracts above 560k/yr pay 1.5×. LP accounts get 25% credit |
| Accelerator | 1.5× above 24 signatures | 1.5× above 24 funded | 1.5× on milestones for funded accounts beyond the 24th |
| Clawback | None | 50% if no qualifying trade ≤60d of funding | 100% of the funding milestone ($1,000) if no qualifying trade ≤60d |
| Mix at plan | 100% accounts | 100% accounts | ~72% accounts / ~28% volume (24 × 1.5 × $2k = $72k; 560k × $50/1k = $28k) |
| Behavior it rewards | Signing marginal accounts; activation dumped on RevOps | Funded-but-dormant accounts; a one-lot trade avoids the clawback | Fast activation of high-ADV fits, plus continued trading |

Exact payout formulas, written so they can be implemented without interpretation, are in each plan's `formula` field. All of them use qualifying trades, and none of them count self-matches.

## 3. Worked example: one AE, one year, three plans

**AE A ("the activator").** Signs 30 agreements and funds 24 accounts, which is exactly quota, so no accelerator applies. Of the 24 funded:
- 6 reach Active within 21 days
- 10 reach Active between 22 and 60 days
- 3 trade but never become Active
- 5 have no qualifying trade within 60 days

The book is 2 PROP (one of them a liquidity partner), 2 FUND, 5 REP, 4 STORAGE, 4 IPP, 3 UTILITY, 2 DATACENTER and 2 CI_LOAD. These accounts trade **666,300 contracts** in their first 12 months:
- the LP prop account: 150k
- the non-LP prop account: 240k
- the funds: 60k and 30k
- the remaining 21 accounts: 186.3k

| Line | (a) Signature | (b) Funded | (c) Activation + ADV |
|---|---|---|---|
| Account payments | 24 × $4,167 + 6 × $4,167 × 1.5 = **$137,500** | 24 × $4,167 = **$100,000** | Funded 24 × $1,000 = $24,000; Active ≤60d 16 × $2,000 = $32,000; ≤21d bonus 6 × $500 = $3,000 → **$59,000** |
| Clawback | $0 | 5 × 50% × $4,167 = **−$10,417** | 5 × $1,000 = **−$5,000** |
| ADV kicker | — | — | Credited contracts: prop 240k is capped at 200k ($10k); LP 150k × 25% = 37.5k ($1,875); the other 276.3k pay $13,815. Total **$25,690** (513.8k credited < 560k target, so no 1.5× uplift) |
| **Variable payout** | **$137,500** | **$89,583** | **$79,690** |
| Variable cost per Active account (16) | $8,594 | $5,599 | **$4,981** |
| Variable cost per 1k contracts | $206 | $134 | **$120** |

**The same plans applied to AE B ("the signature chaser").** B signs 40 and funds 24. Of those, 7 become Active (none within 21 days), 11 never trade, and the book trades 122,000 contracts.

| | (a) | (b) | (c) |
|---|---|---|---|
| AE B variable payout | **$200,000** | $77,083 | **$33,100** |
| Ratio A ÷ B | 0.69× (pays the chaser more) | 1.16× (barely separates them) | **2.41×** |
| Cost per Active account for B | $28,571 | $11,012 | $4,729 |

**Reading the tables.**
- **Plan (a) pays the wrong rep more.** B produced 7 Active accounts and 122k contracts and earns $62.5k more than A, who produced 16 Active accounts and 666k contracts.
- **Plan (b) is flat.** The two reps differ by 5.5× in contracts traded, but their payouts differ by only 16%.
- **Plan (c) separates them 2.4×.** It also has the lowest variable cost per Active account and per 1k contracts for both reps. The money follows liquidity.

You can reproduce these numbers by running the formulas in `comp_plans.json` against the two books above.

## 4. Calibration finding (decision for the CEO)

Using the CRO's numbers exactly, plan (c) pays the $72k account component **only if 100% of funded accounts become Active within 60 days**. The company target is 70%. AE A is close to that target, with 67% Active, 25% fast activators and 21% no-trade, yet earns $79.7k of a $100k variable target. A rep who hits funded quota at the 70% target with 30% fast activation earns about **$57.6k** from milestones plus the kicker. Plans that make OTE look out of reach lose reps.

**Recommendation:** adopt (c) with **unit = $2,500**. That pays the $72k account component at 70% Active, 30% ≤21d and 15% no-trade, because 72,000 ÷ (24 × (0.5 + 0.70 + 0.075 − 0.075)) = $2,500. At $2,500, AE A earns about $93.2k and AE B about $39.9k. The 2.3× separation holds, and an on-target activator reaches OTE when volume is at target. The JSON keeps the CRO's $2,000 as the v1 default. The unit is a simulator parameter (`params.per_account_unit`), so the CEO can see both versions side by side.

## 5. Recommendation and guardrails

**Adopt plan (c).** Pilot it as a shadow plan for one quarter (Experiment E4 in `FIRST_90_DAYS.md`): reps are paid max(current plan, plan c) while we confirm the payout distribution. It becomes the 2027 plan if variable cost per Active account falls by at least 20% and no rep's on-target payout moves more than ±15%.

| Risk | Guardrail |
|---|---|
| Coaxed one-lot trades | Milestones require Active (≥4 days); the clawback uses qualifying trades (≥10 contracts, not self-matched) |
| Cherry-picking prop and fund accounts for ADV | Hedger B-weight in the queue; the kicker cap ($10k/account) limits whale dependence; hedger share of Active is reviewed monthly by rep |
| LP volume inflating payouts | 25% kicker credit; the LP flag is locked at QUALIFIED (CRM rule 7) |
| Wash or self-match volume | Excluded from contracts counted |
| Kicker lag (12-month tail) | Pay quarterly in arrears; milestones pay the month after they are reached |
| Territory and timing luck (volatility seasons) | Scorecard weights activation rate and SLA adherence, not just outcomes; quota is prorated for mid-year starts |

**The scorecard is not the comp plan.** Scorecard weights (`scorecard.json`) are funded vs quota 25%, activation rate 25%, book ADV 20%, median days sign→trade 10%, pipeline coverage 10% and SLA adherence 10%. They drive coaching and promotion, and they surface the leading indicators that plan (c) pays for with a lag.
