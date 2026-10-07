# Ignition Sales Playbook: Running the Activation Engine

**Owner:** Head of GTM & Revenue · **Users:** 4 AEs, Strategic Sales lead, 2 RevOps associates, Marketing Manager, Solutions Eng, Compliance
**Machine-readable sources:** `ignition/content/nba_rules.json`, `sequences.json`, `comp_plans.json`, `scorecard.json`
**Definitions** follow `docs/02_PRODUCT_SPEC.md` §B and appear once in `ignition/definitions.py`:
**Active** means at least 4 distinct trading days in the trailing 30 calendar days. **At-Risk** means 1 to 3. **Dormant** means funded with 0 trades in the trailing 30. A **qualifying trade** is a fill of at least 10 contracts that is not a self-match.

> We measure and pay for Active accounts and ADV, not signatures. A signed account that never trades is CAC with no return. A funded account that trades once does nothing for spreads.

Product language in this playbook stays generic: *short-dated hourly and daily electricity price contracts at major ISO hubs*. The tenor codes `HOURLY`, `DAILY_PEAK` and `WEEKLY_PEAK` come from Ignition's illustrative data model and are not ElectronX rulebook specifications. Before quoting any contract term, margin method or fee to a customer, check the current rulebook and fee schedule.

---

## 1. ICP and segment plays

**Coverage logic.** Hedgers bring two-sided interest. Speculators bring depth. The queue's balance weight (B = ×1.5 on hedgers since v1.1, up from 1.15, which couldn't offset a 3–5× ADV prior) stays on while hedgers are below 50% of Active accounts; they are about 44% today. On top of that, the Today view reserves ≥50% of slots for hedgers (§3). The expected-ADV priors that drive queue priority are Prop 400, Fund 150, REP 100, Storage 80, IPP 60, Utility 40, Data Center 30 and C&I 20 contracts/day.

**Universal opening rule.** Lead with *their* exposure at *their* hub. Lead with forward risk (the next forecast peak) at least as much as the spike that just happened. Pitching a hedge only after a spike reads as "insurance after the fire."

### 1.1 Retail Electric Provider (REP), hedger, *hurt* by spikes
| | |
|---|---|
| **Trigger events** | ERCOT scarcity pricing, where ORDC adders push real-time prices toward the offer cap. Heat-wave load forecasts. Forecast peak ≤5 days out at HB_HOUSTON or HB_NORTH. PJM/MISO winter cold snaps. A competitor REP exiting the market. |
| **Who to call** | VP Wholesale Supply / Portfolio Management (economic buyer), Director of Risk (gatekeeper), Head Scheduler / Trader (daily user), CFO (collateral sign-off) |
| **Opening angle** | "Your fixed-price customers' load rises exactly when price spikes, so you are short the peak. Monthly blocks cover the volume. They don't cover a 6-hour scarcity afternoon." |
| **First product** | Daily peak contracts at their load-zone hub, sized to forecast peak load above their existing block hedges |
| **Objections** | *"We hedge with monthly blocks and bilateral swaps."* That covers the average. Short-dated daily contracts address the residual shape: the peak-day load that comes in above the block. Show last summer's peak days against their block. *"Our load zone isn't the hub."* Correct. Hub contracts leave zone-to-hub basis open. Show the historical hub-to-zone price correlation in the exposure brief and size for it. *"We already have an FCM."* Direct access removes the intermediary layer: they post collateral and trade on the venue themselves. Walk treasury through the collateral flow before it becomes a blocker. *"Liquidity is thin."* Show spread and two-sided uptime at their hub from Ignition's liquidity view, and start with a size the book can absorb. |

### 1.2 Independent Power Producer (IPP: merchant wind and solar), hedger, *hurt* (shape) or *opportunity*
| | |
|---|---|
| **Trigger events** | CAISO negative-price days and solar curtailment (duck-curve belly). Evening-ramp spikes. HB_WEST negative prices against North in ERCOT. A PPA expiring and turning output merchant. A new COD date. |
| **Who to call** | VP Commercial / Asset Optimization, Director of Energy Trading, Head of Risk, CFO (tax-equity and lender covenants) |
| **Opening angle** | "Solar sells most when midday prices are lowest and goes quiet into the evening ramp. That shape risk is yours on merchant MWh." |
| **First product** | Daily or hourly hub contracts that cover merchant output in the hours where shape exposure concentrates |
| **Objections** | *"Our risk is basis, not hub."* Hub contracts address the energy-price component. Node-to-hub basis is a separate instrument problem (FTRs/CRRs) and should be stated plainly. *"Lenders require long-dated hedges."* Short-dated contracts don't replace a long-dated hedge; they cover the merchant tail and day-ahead shape the long-dated hedge leaves open. *"Volume risk: we don't know tomorrow's output."* Size to P90 forecast output, not nameplate. |

### 1.3 Battery Storage Operator, hedger with an *opportunity* framing
| | |
|---|---|
| **Trigger events** | Intraday spread at a 90-day high. Ancillary-service price compression (revenue shifts back to energy arbitrage). Forecast evening peaks. New MW reaching COD. |
| **Who to call** | Head of Optimization / Trading, VP Commercial, Quant / Bidding lead, CFO |
| **Opening angle** | "Your revenue is the midday-to-evening spread. Short-dated contracts let you lock part of a wide spread when you see it, instead of waiting for real-time." |
| **First product** | Hourly contracts around the evening ramp and peak hours |
| **Objections** | *"We optimize in real time; hedging caps upside."* Hedge a slice of capacity, not all of it. The rest stays merchant. *"State-of-charge risk: if we're empty during the spike, a short hedge hurts."* Size against duration and availability, and cover only the hours the dispatch plan commits. *"We're API-driven."* Route to Solutions Eng for API onboarding on day 1 (R08 pattern). |

### 1.4 C&I / Large Load, hedger, *hurt*
| | |
|---|---|
| **Trigger events** | ERCOT 4CP season (June–September). Transmission charges are allocated on load during the four monthly coincident peaks, so loads curtail on predicted 4CP days, and those are often the highest-price afternoons. A budget-variance quarter. An index-priced retail contract renewal. |
| **Who to call** | Director of Energy Procurement, Treasurer / Assistant Treasurer, VP Operations (curtailment authority), CFO |
| **Opening angle** | "On 4CP days you either curtail and lose production, or run and buy at scarcity prices. A daily peak position puts a number on running." |
| **First product** | Daily or weekly peak contracts on the index-priced share of load |
| **Objections** | *"Our retail supplier handles hedging."* Ask what share of load is index-priced pass-through; that slice is the open exposure. *"Treasury won't open a new collateral account."* Size the collateral to the first hedge at the R05 step and give treasury a one-page funding flow. *"We need board approval."* Provide a neutral policy-addendum checklist (instrument, limits, authorized traders, reporting). Do not draft their policy for them. |

### 1.5 Utility / Co-op / Muni, hedger, slow velocity (−) but sticky
| | |
|---|---|
| **Trigger events** | A winter-peak event in PJM/MISO. A G&T contract renewal. A rate-case filing that questions fuel and purchased-power costs. A capacity auction clearing at record levels, which pushes attention to energy-cost risk. |
| **Who to call** | Director of Power Supply / Energy Risk, General Manager (co-op/muni), CFO, Risk Committee chair |
| **Opening angle** | "Capacity covers availability, not the energy price on the coldest morning. Short-dated contracts are a supplemental, auditable hedge for those hours." |
| **First product** | Daily peak contracts at their RTO hub (PJM_WESTERN_HUB, MISO_INDIANA_HUB) |
| **Objections** | *"Regulatory prudence: new venue risk."* It is a CFTC-regulated exchange with transparent prices and audit trails. Provide documentation for the commission file. *"Our hedge policy lists approved instruments."* Expect a 60–120 day policy cycle; keep the account in QUALIFIED with a dated board-meeting next step. *"KYC is heavy for public entities."* Use the prefilled KYC packet (R03). Utilities and C&I are the segments with the most `kyc_info_requested` loops. |

### 1.6 Data Center Developer, hedger, *hurt*, new and very large load
| | |
|---|---|
| **Trigger events** | Energization date set. Large-load interconnection or curtailment rule changes in ERCOT. A hub-settled virtual PPA signed (creates shape and basis exposure). A capex financing round. |
| **Who to call** | VP Energy / Power Strategy, Head of Energy Procurement, CFO / Treasurer, Site Ops lead |
| **Opening angle** | "A data center can't curtail on a 4CP or scarcity afternoon the way a plant can. And a VPPA settled at the hub leaves you long midday solar and short the evening." |
| **First product** | Daily or weekly peak contracts at the hub of the energized site |
| **Objections** | *"Load isn't online yet."* Start at energization minus 60 days, sized to the commissioning ramp. *"Bank-linking and funding take weeks."* This is a known friction point: `bank_linked → funded` is slowest for data centers. RevOps pre-clears treasury signatories at signature. *"We'll hedge with our retail provider."* Compare the cost structure of the provider's index-plus product with a self-managed peak hedge on the same day. Show the mechanics, not a savings claim. |

### 1.7 Proprietary Trading Firm, speculator, *opportunity*, API-first
| | |
|---|---|
| **Trigger events** | A volatility regime change (vol_z > 3). New hubs or tenors listed. Spread tightening at a hub. A new desk launch or power-trader hire. |
| **Who to call** | Head of Trading / Power PM, CTO / Head of Execution, COO (onboarding), Head of Risk |
| **Opening angle** | "Short-dated power volatility is concentrated in hours your current venues don't list. When hedgers show up for a spike, the other side needs a price." |
| **First product** | Hourly contracts via API, then daily peak across ISOs |
| **Objections** | *"Book's too thin to matter."* Show hedger growth in Active accounts and the spread trend. Discuss the liquidity-partner program if they will quote. *"Fees and rebates?"* Refer to the published fee schedule only. *"Integration cost."* Offer a sandbox certification within 48h (R08) with Solutions Eng. |

### 1.8 Hedge Fund / Asset Manager, speculator, *opportunity*
| | |
|---|---|
| **Trigger events** | Weather-driven regime change (heat dome, polar vortex forecasts). Capacity-auction headlines. A new commodities PM. Allocation reviews. |
| **Who to call** | Commodities / Energy PM, Head of Commodities, COO / Head of Ops (collateral, account structure), CRO / Risk |
| **Opening angle** | "Express a short-dated weather view directly in the power price at the hub, not through a gas or monthly proxy." |
| **First product** | Daily and weekly peak contracts |
| **Objections** | *"We only trade through our clearing broker / FCM."* Direct access is an operational change. Solutions Eng and RevOps walk ops through account structure and collateral movement. *"Orders got rejected."* Order rejections on margin or limits are common for funds. Review pre-trade limits before the first order. *"Position limits and reporting?"* Point to the rulebook. Do not interpret it for them. |

### 1.9 Liquidity partners and market makers (separate motion)
`accounts.is_liquidity_partner = true`. They are **excluded from the AE Activation Queue**, their volume is reported on a separate line everywhere, and they carry **25% credit on both milestones and kicker** in comp. Since v1.1 they sit with the house **Partnerships Desk** (role `PARTNERSHIPS`, no AE quota, excluded from scorecards and comp), which Strategic Sales supports. The volatility response for LPs is a quoting note about the event hub, not a sequence. Their KPIs are two-sided uptime and quote share at each hub (CEO target: ERCOT North ≤$0.75/MWh and ≥95% uptime; other ISOs ≤$1.50/MWh and ≥85%).

---

## 2. Stage-by-stage handoffs

| From → To | Trigger | Handoff packet (required CRM fields) | Receiver SLA | Acceptance check |
|---|---|---|---|---|
| Marketing → AE (TARGET) | Inbound or partner lead in ICP, or top-decile score | Segment, ISO/hub, est. MW, lead source, engagement history | First touch in 1 business day (R01) | AE confirms ICP fit, or returns the lead with a reason code |
| AE (TARGET → QUALIFIED) | Discovery held | Exposure (ISO, hub, MW, side: short peak / long output), use case, risk/treasury owner named, eligibility screen passed (commercial/institutional) | Agreement sent ≤10 days (R02) | Head of GTM spot-checks 5 per week at the Monday review |
| AE → RevOps (SIGNED) | Agreement executed (`contract_signed`) | Authorized traders, entity docs available, treasury contact, target first-trade date, expected first product | KYC packet sent in 1 business day (R03); chase stalls same day (R04) | RevOps rejects handoffs with missing fields within 4h |
| RevOps → Compliance | KYC open more than 8 days, or any AML flag | Named missing document, history of `kyc_info_requested` loops | Compliance decision or a clear ask in 2 business days | — |
| RevOps → AE (KYC_APPROVED) | Approval | Collateral minimum, funding instructions sent | Sizing call in 1 business day (R05) | — |
| AE + Solutions Eng (FUNDED) | Deposit cleared | Walkthrough booked, API key status (PROP/FUND) | Walkthrough by day 7 (R06); API certified by day 5 (R08); any rejected order fixed in 8h (R16) | First qualifying trade logged |
| AE → Head of GTM (FUNDED day 21) | No qualifying trade | Blocker hypothesis, reason code | Exec call in 3 business days (R07) | Reason code logged, unblock plan dated |
| AE (FIRST_TRADE → ACTIVE) | 4th distinct trading day | Standing routine agreed (e.g., Monday peak ladder) | Debrief by day 10 if no 2nd trading day (R10) | — |
| AE → Strategic Sales (ACTIVE, top-20 ADV) | Enters top-20 by 20-td ADV | Account 360 pack | QBR within 10 business days of due date (R13) | — |
| AE → Marketing (DORMANT) | 0 trades in trailing 30 days | Dormancy reason code | Win-back starts in 1 week (R14) | AE retakes ownership on any reply or trade |

---

## 3. Next-best-action rules

The engine evaluates rules in ascending `priority`. The first rule whose `condition_code` is true **and** whose `stages` include the account's stage wins. `DEFAULT` always matches. The SLA clock starts when the rule fires. A missed SLA turns the item red on the owner's scorecard (`sla_adherence`, 10% weight).

| Prio | Rule | Stage | Condition | Action | Owner | SLA | Sequence |
|---|---|---|---|---|---|---|---|
| 10 | R16 | FUNDED / FIRST_TRADE | `ORDER_REJECTED_7D` | Fix the reject: pull the reason (margin, risk limit, price band, size), resolve it with their risk/ops lead, re-place the order live | Solutions Eng | 8h | — |
| 20 | R07 | FUNDED | `FUNDED_NO_TRADE_21D` | Head of GTM call with risk/treasury owner: diagnose the blocker (hedge policy, risk limits, ops/API) and log a reason code | Head of GTM | 72h | — |
| 30 | R04 | SIGNED | `KYC_STALLED_5D` | Chase the named missing KYC doc with its owner; offer a 15-min call with their compliance lead; escalate to Compliance at day 8 | RevOps | 8h | — |
| 40 | R09 | QUALIFIED / KYC_APPROVED / FUNDED / FIRST_TRADE | `VOL_TRIGGER_EXPOSED` | Launch volatility sequence: T0 email with their hub chart + illustrative DAILY_PEAK replay of the event, compliance-approved before send | AE | 4h | volatility |
| 50 | R03 | SIGNED | `KYC_NOT_STARTED_3D` | Send prefilled KYC packet (entity docs, LEI, authorized traders, UBO) and book a 20-min guided KYC session | RevOps | 24h | — |
| 60 | R05 | KYC_APPROVED | `KYC_APPROVED_UNFUNDED_5D` | Send funding steps + first-hedge sizing: stated MW × 16 on-peak hours → DAILY_PEAK contract count and collateral needed | AE | 24h | — |
| 70 | R08 | FUNDED / FIRST_TRADE | `NO_API_KEY_5D` | API onboarding: issue keys, sandbox-certify order/cancel/replace flow, review pre-trade risk limits with their dev lead | Solutions Eng | 48h | — |
| 80 | R06 | FUNDED | `FUNDED_NO_TRADE_7D` | Live walkthrough: replay last 7 days at their ISO hub and size a DAILY_PEAK hedge against stated load or output; SE joins | AE | 48h | activation |
| 90 | R10 | FIRST_TRADE | `NO_SECOND_DAY_10D` | Post-trade debrief: fill vs realized hub index on their exposure; propose a standing weekly routine (e.g., Monday peak ladder) | AE | 48h | — |
| 100 | R11 | ACTIVE / EXPANDING / AT_RISK | `ACTIVE_DECLINING` | Churn-risk check-in: show trailing vs prior 30d activity and spreads at their hub; log reason code (limits, P&L, desk, liquidity) | AE | 72h | — |
| 110 | R15 | ACTIVE / EXPANDING / AT_RISK | `VOL_TRIGGER_EXPOSED` | Send compliance-approved market note: hub, peak $/MWh, spike hours, 5-day forward look; no sequence for Active accounts | AE | 24h | — |
| 120 | R13 | ACTIVE / EXPANDING / AT_RISK | `TOP20_QBR_DUE` | Schedule QBR from Account 360: ADV trend, tenor/ISO use, spread experience, 2 growth plays; Head of GTM joins for top-5 | Strategic Sales | 48h | qbr |
| 130 | R12 | ACTIVE | `EXPANSION_READY` | Expansion play: 2nd ISO where they hold assets/load, or HOURLY contracts for ramp/shape hours, sized from their exposure | AE | 120h | — |
| 140 | R02 | QUALIFIED | `QUALIFIED_NO_AGREEMENT_10D` | Send participant agreement + 15-min onboarding preview: KYC checklist, collateral flow, sample DAILY_PEAK ticket at their hub | AE | 48h | — |
| 150 | R01 | TARGET | `TOP_DECILE_UNTOUCHED` | First call + 1-page exposure brief: hub price/spike history, peak vs off-peak spread, which short-dated tenor maps to their risk | AE | 24h | — |
| 160 | R14 | DORMANT | `DORMANT_30D` | Win-back nurture: forward-risk note before the next forecast peak at their hub + walkthrough offer; AE calls on reply | Marketing | 168h | — (win_back cadence) |
| 999 | R99 | * | `DEFAULT` | Review in Account 360: confirm ISO, hub, MW and side of exposure; set a dated next step in CRM (no open task >5 business days) | AE | 120h | — |

**Why this order (v1.1, X5 precedence: R16 → R07 → R04 → R09 → rest).** A rejected order (R16) is a known, fixable blocker on an account that has already tried to trade, so it comes first, and a volatility email to that account would miss the point. A 21-day funded stall is sunk CAC that needs an exec diagnosis (R07), and a stalled KYC (R04) blocks everything downstream. Neither should be replaced by an event email. R09 comes next because volatility windows close in hours. For PROP and FUND, a missing API key (R08) is the real reason there's no trade, so it outranks the generic walkthrough (R06). R01 sits low because untouched targets don't decay as fast as stalled funded accounts. Rule IDs R01–R14 follow the CRO memo §2 numbering. R15 is the Active-account market note, R16 is order-rejected (v1.1) and R99 is the default. Priority is set separately from the ID. **SLA convention:** 1 business day = 24h, "same day" = 8h.

**R09 narrowing (v1.1, X5).** v1 fired R09 on every exposed account in S1–S5. That sent a volatility email to 198 stalled accounts that needed their stage fix instead. R09 now fires only when **all** of the following hold:
- trigger severity ≥ 70
- stage is KYC_APPROVED, FUNDED or FIRST_TRADE. QUALIFIED counts only if exposure_score ≥ 90. SIGNED stays on its KYC rule, and RevOps may use the event as the subject line of the KYC chase.
- exposure_score ≥ 80. An own-hub match scores in full; another hub in the same ISO scores ×0.6.
- no triggered sequence in the last 14 days, and no touch in the last 3 days
- p_active < 0.95. Accounts that will activate anyway don't need the touch.
- at most **one sequence per account per ISO event** (`event_id` = `{ISO}-{YYYYMMDD}`), even when HB_HOUSTON and HB_NORTH both trigger

Expected volume for the seeded ERCOT event is about 20–40 R09 matches, mostly hedgers. Exposed accounts that fail the filter still appear in Market Pulse under "Show all", and each gets its own stage rule in the queue.

**R16 `ORDER_REJECTED_7D` (new in v1.1).** It applies to FUNDED or FIRST_TRADE accounts with an `order_rejected` event in the last 7 days and no qualifying trade since. Owner: Solutions Eng (RevOps assists on collateral). SLA: 8h.
- **Play:** pull the reject reason (margin or collateral shortfall, pre-trade risk limit, price band, size), fix it with the customer's risk or ops lead, and stay on the line while they re-place the order.
- **Most common in FUND accounts.** A rejected first order is the clearest intent signal in the funnel. It is also the fastest to lose if nobody calls within the day.

### The Today view (v1.1): what each person works today

The Activation Queue defaults to **Today** (`/activation/queue?view=today`). **All** shows the full ranked backlog.

| Owner | Daily cap | Notes |
|---|---|---|
| AE | **12** items | Grouped per rep. AEs own most R09, R06, R05 and R10 items |
| Strategic Sales | **12** items | QBRs (R13) and top-20 churn checks (R11) |
| RevOps associate | **15** items | KYC rules (R03, R04) and activation-sequence admin |
| Head of GTM | **5** items | R07 exec diagnostics only |

- **Hedger slots:** while hedgers are below 50% of Active accounts, at least 50% of each owner's Today list is hedger accounts. Remaining slots fill by priority. This works alongside the queue balance weight B = ×1.5 on hedgers.
- **SLA clocks start only on items that make the Today list.** Breaches count only on listed items, and the backlog count (`summary.backlog`) is shown so nothing is hidden.
- **Down-ranks:**
  - *ramping* accounts: first trade ≤14 days ago and ≥2 trading days in 30. Priority ×0.3, because the habit is forming without us.
  - accounts that fall through to `DEFAULT`: priority ×0.25.
  - The volatility urgency boost applies only to stages eligible for R09.
- **Partnerships Desk:** liquidity partners sit with the house Partnerships Desk (role `PARTNERSHIPS`). They never appear on an AE's Today list.

---

## 4. Sequences

The full spec is in `sequences.json`. Every customer email in every sequence moves through `pending_review → approved → queued`.

**Volatility-triggered** (R09; anchor = trigger detected; 6 touches over 5 business days)

| Day | +h | Channel | Purpose | Owner |
|---|---|---|---|---|
| T0 | 0 (send ≤4h) | Email | Hub chart, peak $/MWh, spike hours, illustrative daily-peak replay | AE |
| T0 | +4 | LinkedIn | Short personal note | AE |
| D1 | 24 | Phone | Call + VM: how did the event hit the book? | AE |
| D2 | 48 | Email | Event recap + 5-day forward look | Marketing |
| D3 | 72 | Phone | Offer illustrative sizing for the next forecast peak | AE |
| D5 | 120 | Email | 20-min walkthrough before the next forecast peak | AE |

Rules: R09's v1.1 filter applies (§3). At most 1 sequence per account per 14 days, and one per ISO event. Active accounts get a note (R15). LPs get a quoting note. The sequence stops on reply. Eligible commercial/institutional accounts only.

**Standard activation** (anchor = `funded_at`; 8 touches over 21 days): D0 welcome + checklist (RevOps, automated) · D1 call · D3 segment video · D5 call · D7 walkthrough invite · D10 case study · D14 call + Head of GTM note · D21 R07 escalation. It pauses while a volatility sequence runs. It exits on the first qualifying trade.

**QBR** (R13): D0 RevOps builds the 360 pack · D1 invite + agenda · D7 Head of GTM prep · D10 meeting · D11 recap · D40 follow-up.

**Win-back** (R14): D0 "what changed" · D7 forward-risk note (if a peak is forecast ≤5 days out) · D14 AE LinkedIn · D21 AE call + reason code · D28 walkthrough offer · then a monthly digest. At most one touch per week.

---

## 5. Weekly operating cadence (all times US Central, ERCOT clock)

| When | Meeting | Inputs (Ignition) | Output | Owner |
|---|---|---|---|---|
| **Daily 07:30** (15 min) | Pulse triage | Market Pulse triggers + 5-day forecast | Drafts in the compliance queue by 10:00, so T0 lands ≤4h after the trigger. Compliance review SLA for volatility drafts: 2h | AE on rotation + Marketing |
| **Mon 09:00** (60 min) | Pipeline review | CEO Weekly KPIs, Activation Queue summary, Segments coverage, `pipeline_coverage` per rep | Commit for the week: funded and first-trade forecast per rep. Top-10 stalled accounts with named owners. 5 qualification spot-checks | Head of GTM |
| **Wed 09:00** (30 min) | Activation stand-up | Queue filtered to FUNDED / FIRST_TRADE / KYC stalls; SLA breaches; Funnel & Journey friction flags | Every red SLA has an owner and a date. Top friction flag routed to Product with $ at stake | RevOps lead |
| **Fri 14:00 → 17:00** | CEO memo | `/ceo/weekly.md` export (liquidity · balance · action), cohort activation (n ≥ 20 only) | Three decisions for the CEO, each with a number and an owner. Sent by 17:00 | Head of GTM |
| Monthly (first Tue) | Scorecard 1:1s | Team & Comp scorecards, comp simulator | Per-rep plan on the lowest component | Head of GTM |
| Quarterly | Model + rules review | Queue › Model (AUC, lift, calibration), holdout results by stage | Re-estimated k_stage, rule SLA changes, retired rules | RevOps + Head of GTM |

**Team productivity metric:** *activations per rep-hour* (Active accounts reached ÷ logged rep hours on pre-Active accounts), not "hours saved."

---

## 6. CRM hygiene rules (enforced in the Wednesday stand-up)

1. **Stage timestamps are system-written.** Stage changes come from events (`contract_signed`, `kyc_approved`, `funded`, `first_trade`, `activated`), never from hand edits. Manual overrides need a RevOps note.
2. **No stage skipping.** An account cannot reach QUALIFIED without the exposure fields: `primary_iso`, `hub`, `size_mw`, side (short peak / long output / speculative), and a named risk or treasury owner.
3. **Every touch is logged within 24h** as an `activities` row with `kind`, `outcome`, plus `trigger_id` and `sequence` where they apply. Untracked touches don't count toward SLA adherence.
4. **One dated next step per open account.** Nothing sits more than 5 business days without a task (R99).
5. **Reason codes are mandatory** on R07 (blocker), R11 (decline), R14 (dormancy) and every closed-lost. They come from a fixed picklist: hedge policy/approval, risk limits, collateral/treasury, tech/API, liquidity/spread, price/fees, people change, no exposure.
6. **Contacts:** at least 2 per account by SIGNED, including one RISK or CFO persona. One `is_champion`.
7. **The LP flag is set at QUALIFIED** by Strategic Sales, and the account moves to the Partnerships Desk. It cannot be changed later without Head of GTM approval, because it changes comp credit.
8. **Credit and ownership:** `rep_id` is locked at SIGNED for comp purposes. Reassignments are logged with an effective date.
9. **Duplicate and entity hygiene:** one account per legal entity that trades. Affiliates link to a parent for reporting.
10. **Do-not-contact and opt-outs** suppress all sequences immediately and are audited monthly.

---

## 7. How AI tooling is used every day

Ignition's copilot always runs on the deterministic template engine. Claude (`claude-opus-5-5`) is used when an API key is configured. **Claude receives only computed facts** (hub, peak price, timestamps, spike hours, forecast values, the account's stated exposure). It never generates or estimates prices.

| Use | When | Input facts | Output | Human step |
|---|---|---|---|---|
| **Research brief** | Before the R01 first call | Segment, ISO/hub, size MW, hub price stats (30d avg, p99, spike hours), recent trigger history | One-page exposure brief plus 5 discovery questions | AE edits; internal use only |
| **Volatility drafting** | Daily Pulse triage, R09 / R15 | Trigger facts, exposure line, direction (hurt/opportunity), forecast line | T0 email + LinkedIn note from approved templates | Compliance linter → `pending_review` → reviewer approves → `queued` |
| **Call prep** | Before D1/D3/D5 calls and R06 walkthroughs | Onboarding steps completed, days in stage, top-3 queue reasons, last touches | Call plan: likely blocker, 3 questions, the walkthrough replay window | AE |
| **QBR prep** | R13, QBR D0 | Account 360: ADV trend, tenor/ISO utilization, health, spread experience | Draft QBR deck outline and 2 growth plays | Strategic Sales + Head of GTM review |

**Guardrails (non-negotiable)**
- **Compliance linter on every customer-facing draft.** It checks banned promissory or advice phrases ("guarantee", "you should buy", "will save", "risk-free", and others) and requires the disclaimer footer, which says the content is educational and not a recommendation. Drafts that fail cannot be approved.
- **Human approval before anything is queued.** Nothing sends from `pending_review`. Approvals and rejections are logged with the reviewer and timestamp for recordkeeping.
- **Eligibility:** triggered outreach goes only to eligible commercial or institutional accounts.
- **Sizing is labeled illustrative**, is computed by the service rather than the model, and is tied to the customer's stated exposure. The copy never makes P&L, savings or performance claims.
- **No invented facts.** If a fact is missing, the template omits that line. The model is not allowed to fill the gap.
- **Fallback:** if the API errors, times out or has no key, the template engine produces the draft in under 2s.
- **Measurement:** triggered-vs-untriggered 14-day activation (Market Pulse history) and activations per rep-hour. The copilot is judged on outcomes, not on draft count.
