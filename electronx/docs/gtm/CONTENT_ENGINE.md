# Content Engine: Marketing Plan with a Line to Funded, Active Accounts

**Owner:** Head of GTM & Revenue (Marketing Manager mandate: content, social,
events, brand, customer education) · **Status:** v1, Oct 2026 · **Horizon:** Q4 2026
plus the first week of 2027.
**Companion docs:** `POSITIONING.md` (what we say), `ignition/content/*.json` (the
machine-readable versions), `SALES_PLAYBOOK.md` (Sales-owned sequences).

> All numbers in Ignition are synthetic and illustrative. This plan describes the
> method and the targets; actual budgets and results replace them once real data
> is connected.

---

## 0. The rule: every dollar has to reach an active account

The unit we buy is an **active account**: ≥4 distinct trading days in the trailing
30 (spec D2). Leads, MQLs, impressions and signatures are intermediate counts, and
none of them is a goal.

```
spend (marketing_spend.campaign) → lead (accounts.lead_source = channel)
  → signed → funded → first qualifying trade → ACTIVE → ADV → fee revenue
                    ▲                        ▲
     education & Market Pulse touches (activities: webinar, walkthrough, triggered_email)
```

- **Primary KPI for every channel:** cost per active account (CPAA) = channel spend ÷ active accounts sourced by that channel, on cohorts at least 60 days past funding (the Active label needs the window to close).
- **Secondary:** ADV per $1k spend, with liquidity-partner ADV on its own line.
- **Mix guardrail:** hedger share of marketing-sourced active accounts ≥50%. This mirrors the CEO target and the queue's B weight, and it applies because hedgers are the scarce side of the book.
- **What we never optimize:** cost per lead. Cheap LinkedIn leads that never fund are the classic way a marketing budget looks productive and isn't.

## 1. Channel strategy

Channel names match spec §B and `segment_messaging.json → channels`.

| Channel | Role in funnel | Primary KPI | Leading indicator (read weekly) | Segments it serves best | Q4 budget share (plan) |
|---|---|---|---|---|---|
| **Webinars & Education** | Mid/bottom funnel: SIGNED→FUNDED→FIRST_TRADE. Teaches the product on the attendee's own hub | CPAA (influenced, reported separately) + funded→first-trade days vs. matched non-attendees | In-ICP attendees from accounts in SIGNED–FIRST_TRADE | All hedgers; Utility & C&I (KYC clinic) | 20% |
| **Content & SEO** | Always-on top of funnel and credibility. Market Pulse recaps, the event library, explainers | CPAA (first-touch) | Recap→meeting within 14 days; organic sessions on hub/event pages | REP, IPP, Storage, Fund | 15% |
| **Industry Conferences** | Top of funnel for hedgers + partner discovery; speaking slots built on event teardowns | CPAA within 120 days (sourced + meeting-influenced) | Meetings booked with in-ICP accounts per show | REP, Utility, IPP, Storage, Data Center | 25% |
| **LinkedIn Paid** | ABM amplification to named personas in TAM accounts; retargets funded-not-trading contacts with education | CPAA | Cost per in-ICP webinar attendee | Data Center, C&I, Utility | 10% |
| **Partner Referrals** | High-intent sourcing via energy consultants, retail energy brokers, ISO-market advisors, ETRM vendors | CPAA incl. referral fees | Referred accounts reaching KYC_APPROVED in ≤14 days | REP, C&I, Utility, Data Center | 10% |
| **Outbound Prospecting** | AE-led sourcing into top-scored TAM accounts, plus volatility-triggered sequences | CPAA (fully loaded rep time); triggered vs. holdout 14-day activation | Reply/meeting rate on triggered touches | All; exposed accounts after each event | 15% (SDR tooling, data, enrichment) |
| **Liquidity Partner Intros** | Supply side: market makers and prop firms via existing LPs | Spread tightening & two-sided uptime per added active LP (CPAA reported separately) | LP-introduced firms through API certification | Prop, Fund | 5% |

**Reallocation rule (quarterly, not monthly).** A channel's budget only moves on
evidence. The channel needs **≥20 funded accounts** in the trailing two quarters
(spec `SMALL_COHORT_N`), and the CPAA gap to the median channel has to hold at the
lower bound of an 80% interval on activation rate. Move at most 20% of total budget
per quarter. Below n=20, a channel is *on watch*, not cut. The exception is a
conference that produces zero funded accounts in two consecutive cycles: it is cut.

**Why this mix for Q4.** We are at ≈62% active vs. a ≥70% target, and hedgers are
≈44% of active vs. ≥50%. The binding constraint is **activation of hedgers already
signed**, not new logos. Education and Market Pulse content therefore get more
weight than a pure sourcing plan would give them, and conferences are chosen for
hedger density.

## 2. Customer education program ("ElectronX Power Desk")

Education is our highest-leverage activation tool. A hedger who has watched their
own hub's last week settle against a daily-peak contract is far more likely to
place a first order than one who has read a product sheet. Each module maps to a
funnel stage and to a friction flag in Funnel & Journey.

| # | Module | Audience (segments · personas) | Format | Funnel stage it moves | Success metric |
|---|---|---|---|---|---|
| E1 | **Short-dated power hedging 101**: hub vs. node, on-peak definitions, hourly/daily/weekly tenors, settlement against real-time, sizing arithmetic, basis risk | All hedgers · risk, CFO | 30-min live + recording + 1-page explainer | QUALIFIED → SIGNED; FUNDED → FIRST_TRADE | Attendee funded→first-trade days vs. matched non-attendees |
| E2 | **Reading ERCOT scarcity pricing**: energy-only design, reserve scarcity adders, offer cap, real-time vs. day-ahead, 4CP (and why energy contracts don't hedge it) | REP, Storage, IPP, Data Center, Prop · traders, risk | 30-min live, refreshed after each major ERCOT event | Exposed accounts after a trigger | Recap→meeting conversion; triggered activation |
| E3 | **Duck curve & negative prices for solar IPPs**: CAISO midday trough, curtailment, evening ramp, shape vs. basis | IPP, Storage · asset optimization | Live + SP15/NP15 data walkthrough | FUNDED → FIRST_TRADE (IPP) | IPP first-trade rate within 30 days |
| E4 | **Data center load & PJM capacity**: energy vs. capacity vs. transmission, what record capacity prices mean, what short-dated energy contracts do and don't cover, phasing hedges with a load ramp | Data Center, C&I, Utility · energy & finance leads | Live + exposure worksheet | QUALIFIED → FUNDED (DC funding lag is a known friction) | Bank_linked→funded days for DC attendees |
| E5 | **Winter peaks in PJM & MISO**: dual morning/evening peaks, gas-electric coupling, cold-snap history | Utility, C&I, REP, Fund | Live in November, before the season | Pre-season pipeline | Meetings booked before Dec 15 |
| E6 | **Writing a hedging policy that includes short-dated contracts**: policy language, limits, controls, board reporting | Utility, Co-op/Muni, C&I · CFO, board risk chair | Workshop + editable policy-template appendix (reviewed by Legal) | SIGNED (approval stalls) | Utility days in SIGNED/KYC |
| E7 | **Onboarding clinic: completing KYC in one pass**: what documents are typically requested, who on your side owns each | Utility, C&I (the #1 drop-off is `kyc_info_requested` loops) | 20-min guided session (RevOps) | SIGNED → KYC_APPROVED | KYC info-request rate and loop count for attendees |
| E8 | **First-trade lab**: the last seven days of your own hub, a worked position in the sandbox, the order ticket | Any FUNDED account (CRO Rule 6) | 30-min 1:1 or small group | FUNDED → FIRST_TRADE | 14-day first-trade rate after lab |
| E9 | **API & sandbox onboarding** + **Margin, limits & a first-order dry run** | Prop, Fund (`order_rejected` is common for funds) | Solutions-engineer session + docs | FUNDED → FIRST_TRADE | Days funded→API key; rejection rate on first orders |
| E10 | **Valuing the intraday spread**: storage revenue stack and hourly contracts | Storage, Prop | Live + replay dataset | QUALIFIED → FIRST_TRADE | Storage activation rate |

**Program rules:** every session runs on real hub price history (synthetic in
the demo), states what the product doesn't cover, never recommends a trade, and
carries the footer. Recordings are cut into 2–3 minute clips that become the
*segment explainer video* touch (D3 of the standard activation sequence) and the
D10 case-study slot.

## 3. Market Pulse: the always-on content loop

Every detected volatility event becomes content within 24 hours, and that content
feeds triggered outreach and social. The loop is weighted **forward**. A recap is
only half of it; the other half is the *Forward Look* published before a
forecast peak, which keeps us from selling insurance after the fire.

```
Ignition detects trigger (S≥3 spike hours, vol z≥2.5, or CAISO negatives N≥12; or forecast peak ≤72h)
 │
 ├─ T+1h   Marketing desk: verify facts in Ignition (hub, peak, hours, regime); check ISO grid status
 │         (active emergency with firm load shed → pause all commercial touches; recap only after recovery)
 ├─ T+4h   AEs: triggered emails from approved templates (outreach_templates.json), via compliance linter
 │         → pending_review → approved → queued.    [Sales-owned sequence, T0]
 ├─ T+24h  EVENT RECAP NOTE published (≤1 page):
 │           1. What happened: hub, hours, peak, regime, drivers (load, outages, wind/solar, reserves)
 │           2. What it revealed: exposure by side (hurt / opportunity), shape vs. monthly average
 │           3. Forward look: labeled 5-day model forecast for the hub
 │           4. Learn more: link to the matching education module (E2/E3/E4/E5)
 │           5. Footer
 │         → web (event library page per hub, SEO), PDF, LinkedIn post + chart, "market note" email to
 │           ACTIVE accounts (who get a note, not a sequence), D2 recap touch in the volatility sequence
 ├─ Weekly  "Pulse Weekly": events, spreads, the week ahead's forecast peaks, one education link
 ├─ Pre-peak FORWARD LOOK when a forecast peak is ≤5 days out: what the forecast shows, which exposures
 │           it touches, an invitation to a walkthrough before (not after) the hours in question
 ├─ Monthly Event Teardown webinar (the month's biggest event, hour by hour)
 └─ Quarterly Seasonal Outlook + event library refresh → feeds dormant win-back (CRO Rule 14)
```

**Loop KPIs:** recap time-to-publish (p90 ≤24h); share of triggers with a recap
(target 100% of severity ≥60); recap→meeting within 14 days; **triggered vs.
holdout 14-day activation** (the number that justifies the whole loop);
unsubscribe and complaint rate as a guardrail (≤0.3% per send). The synthetic
history shows triggered ≈41% vs. untriggered ≈16% (CPO §4; spec §D seeds a ≈2–2.5× gap). That gap is
built into the seed, so the demo proves the *measurement*, not the effect.

**Recap compliance:** recaps are educational market commentary. They go through
the same linter and a named reviewer, use only Ignition-computed facts, label
forecasts as model output, and never say what anyone should trade.

## 4. Social

| Surface | Purpose | Cadence | Content mix |
|---|---|---|---|
| LinkedIn: company page | Credibility with risk managers; distribution for recaps and webinars | 3 posts/week + every recap | 70% market education (charts, recaps) · 20% product how-to · 10% company/people |
| LinkedIn: Head of GTM + AEs | Desk-to-desk voice; the T0+4h LinkedIn touch in the volatility sequence | 1–2/week each | Personal take on the week's hub, always factual |
| X (ERCOT/real-time community) | Reach traders and analysts who watch real-time prices live | Event-driven | Chart + facts within hours; link to recap |

Rules: a chart, a hub and a time on every market post; no celebrating spikes; no
price predictions; no "DM us to trade". Pause promotional posting during grid
emergencies.

## 5. Events plan

| Tier | What | Examples (candidates, dates to be verified) | Goal | KPI |
|---|---|---|---|---|
| **Own events** | *Power Desk Breakfast*: 15–25 risk managers, one event teardown, no pitch | Houston (REPs, Storage), Austin (ERCOT IPPs), New York (Funds), Chicago (Prop, MISO utilities), Northern Virginia (Data centers, PJM) | Hedger activation and expansion | Funded and active accounts among attendee firms within 120 days |
| **Tier 1: speak + exhibit** | Conferences where hedger risk owners gather | Texas power-market conferences (e.g., GCPA); public-power and co-op annual meetings (APPA, NRECA; Q1 2027) | Pipeline + credibility | Meetings booked with in-ICP accounts; CPAA within 120 days |
| **Tier 2: attend + host a dinner** | Trading-industry and data-center events | FIA Expo (Chicago, Nov) for prop, funds and LPs; data-center energy summits | LP and speculator sourcing; DC education | Meetings; API certifications |
| **Virtual** | Monthly Event Teardown + education series (§2) | n/a | Activation | See §2 |

**Every event has a pre-booked meeting list** drawn from the Activation Queue
(top-scored accounts in the region), a post-event sequence, and a campaign tag in
`marketing_spend.campaign` so its cohort is traceable in Marketing ROI.

## 6. 90-day content calendar (Oct 12, 2026 – Jan 8, 2027)

Recaps are event-driven and slot in whenever Ignition fires. The calendar below
is the planned spine.

| Week of | Seasonal hook | Education (live) | Content & Market Pulse | Social / Paid | Events | Funnel focus |
|---|---|---|---|---|---|---|
| Oct 12 | Oct 2 ERCOT Houston scarcity event; fall maintenance season | E2 Reading ERCOT scarcity pricing | Event teardown: HB_HOUSTON/HB_NORTH, Oct 2 (long-form) | LinkedIn chart series on the event; ABM to Houston REPs | Power Desk Breakfast: Houston | ERCOT REPs & Storage, FUNDED→FIRST_TRADE |
| Oct 19 | CAISO fall negatives | E3 Duck curve & negative prices | Explainer: shape vs. basis for solar | Paid: IPP asset managers in CAISO | n/a | IPP first trade |
| Oct 26 | Q4 onboarding push | E7 KYC clinic (×2 sessions) | Guide: "Onboarding in one pass" checklist | Retarget SIGNED contacts (Utility, C&I) | Tier 1 Texas conference (verify) | SIGNED→KYC_APPROVED |
| Nov 2 | Winter readiness | E5 Winter peaks in PJM & MISO | Seasonal Outlook: Winter 2026–27 (forward-weighted) | Paid: utility & C&I risk owners in PJM/MISO | n/a | Pre-season pipeline |
| Nov 9 | Data center load growth | E4 Data center load & PJM capacity | Explainer: energy vs. capacity vs. transmission | ABM: data-center energy leads (NoVA, Ohio, Texas) | Power Desk Breakfast: Northern Virginia | DC bank_linked→funded |
| Nov 16 | Trading-industry season | E9 API & sandbox; margin & limits | API quick-start + event library for backtesting | X/LinkedIn for quant audience | FIA Expo, Chicago (Tier 2, verify) + Chicago breakfast | Prop/Fund API→first trade |
| Nov 23 | Short week (US Thanksgiving) | n/a (recordings only) | Pulse Weekly; clip library from E1–E5 | Organic only | n/a | Nurture |
| Nov 30 | Winter reliability assessments published (verify timing) | E1 Hedging 101 (winter edition) | Forward Look ahead of first cold-snap forecast | Paid: REPs in PJM/MISO | Power Desk Breakfast: New York (Funds) | Funds FUNDED→FIRST_TRADE |
| Dec 7 | Year-end budgets; 2027 hedge programs | E6 Writing a hedging policy | Policy template appendix (Legal-reviewed) | ABM: CFOs at utilities, co-ops, C&I | n/a | Utility SIGNED stalls |
| Dec 14 | Early-winter peaks | Monthly Event Teardown | Recap(s) of any PJM/MISO winter event | Event-driven | n/a | Exposed accounts, winter_peak triggers |
| Dec 21 | Holiday low-liquidity window | n/a | Year in short-dated power: 2026 event library review | Organic only | n/a | Dormant win-back list build |
| Dec 28 | Holiday | n/a | Pulse Weekly (light) | Organic only | n/a | n/a |
| Jan 4 | New-year hedging programs; deep-winter risk | E8 First-trade labs (cohort sessions) | Q1 Seasonal Outlook; ERCOT winter primer | Paid: restart at Q4 winners only (CPAA evidence) | Plan Q1: APPA/NRECA, Texas Q1 conferences | All FUNDED-not-trading → FIRST_TRADE |

## 7. Attribution model

| Model | What it credits | Where it lives | Use it for | Weakness |
|---|---|---|---|---|
| **First-touch (sourced)** | 100% to `accounts.lead_source` | **What Ignition's Marketing ROI reports today**: spend, leads, signed, funded, active, `cac_funded`, `cac_active`, ADV per $1k, `n_small` | Budget allocation between sourcing channels | Ignores education and Pulse, which work after sourcing |
| **Multi-touch (position-based, v2)** | 30% first touch · 30% the touch before signature · 30% the touch before the first qualifying trade · 10% spread across the rest | Needs every touch in `activities` tagged with channel and campaign | Understanding the *activation* contribution of education, Pulse and events | Weights are a convention, not a measurement; noisy at our n |
| **Incremental (holdout)** | Only the lift over a randomized control | Triggered cohort vs. a rotating 15% holdout of eligible exposed accounts per event (no account held out twice in a row) | The only causal claim we make: "triggered outreach lifts 14-day activation by X" | Needs many events to narrow the interval |

**What Ignition reports, and how to read it.** Ignition reports **first-touch cost
per active account by channel** as the headline and shows **influence**
(education attendance, triggered touches) as a separate activation-lift panel.
The two are never summed, because summing double-counts. Liquidity Partner
Intros ADV is shown on its own line so LP volume never flatters blended ROI.

**Honest caveats:**

1. **Small n.** With ≈205 funded accounts across 7 channels, a quarter's cohort per channel is often under 20. Ignition greys these out (`n_small`), and we treat them as watch items, not results. This is also why the CEO deferred Marketing ROI until volume is meaningful; until then it is a directional tool for killing obvious losers.
2. **Lag.** Active is measured over a 60-day window, so a channel's Q4 spend can't be judged before Q1. Read leading indicators weekly and CPAA quarterly.
3. **Selection bias.** Partner referrals and conference meetings look efficient partly because those firms were already ready to trade. First-touch can't separate the channel's effect from the account's readiness. Only holdouts can.
4. **Rep confounding.** Strategic accounts go to the strongest seller, so channel results partly measure rep assignment. Compare within segment and rep where n allows.
5. **Synthetic data.** The demo's channel CACs and the triggered-outreach lift are built into the generator. Ignition shows that the measurement works, not that ElectronX's channels perform this way.

## 8. Marketing scorecard (reported monthly, in the CEO Weekly appendix)

| Metric | Definition | Target (Q4 2026) |
|---|---|---|
| Cost per active account (blended, sourced) | Spend ÷ sourced active accounts, cohorts ≥60 d past funding | Set from the Q3 baseline; −15% QoQ |
| Marketing-sourced active accounts | Active accounts with a marketing `lead_source` | +25 in Q4 (illustrative) |
| Hedger share of marketing-sourced actives | Hedger actives ÷ all marketing-sourced actives | ≥50% |
| Education-influenced activation | Funded→first-trade days, attendees vs. matched non-attendees | ≥30% faster |
| Recap SLA | Recaps published ≤24h after trigger (p90) | 100% of severity ≥60 |
| Triggered lift | Triggered vs. holdout 14-day activation | Interval excludes 1.0× by year-end |
| Compliance | Drafts blocked at review ÷ drafts submitted; complaints | Blocked rate trending down; zero complaints |
