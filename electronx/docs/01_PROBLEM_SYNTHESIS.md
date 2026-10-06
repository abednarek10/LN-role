# ElectronX — Problem Synthesis & Workstreams

> Input: ElectronX *Head of GTM & Revenue* job description (Oct 2026).
> Output: the problems the role exists to solve, ranked, and the workstreams
> that turn each one into something we can operate and measure.

## 1. What the business is really asking for

ElectronX runs a CFTC-regulated, **direct-access** exchange for short-dated
electricity price contracts. It is live in **ERCOT, PJM, CAISO and MISO**, has
volume and liquidity partners, and a pipeline of engaged leads. The constraint
is no longer *product* or *pipeline* — it is **conversion and velocity**:

```
Target lead ─▶ Qualified ─▶ Signed ─▶ Onboarded (KYC) ─▶ Funded ─▶ First trade ─▶ Active trader ─▶ Growing ADV
                                          ▲ "once signed by any seller, the account enters YOUR activation system"
```

For an exchange, a signed account that never trades is worth roughly
nothing, and a funded account that trades once and goes dormant does nothing
for liquidity. **Liquidity is the product.** Every additional active
participant tightens spreads, which makes the venue more attractive to the next
participant (a two-sided network effect). So the headline metric is not
"accounts signed" but **funded accounts that are actively trading, and the ADV
they contribute**.

## 2. Problem statements (ranked by value at stake)

| # | Problem | Why it hurts | Evidence in JD |
|---|---|---|---|
| P1 | **Activation gap** — signed / funded accounts stall before their first trade | Revenue = f(ADV); dormant accounts are pure CAC with no return | "turn that pipeline into funded, actively trading accounts", "vast majority actively trading by end of 2026" |
| P2 | **No prioritization signal** — a small team of 4 cannot work every lead equally | Rep time is the scarcest input; it's spent on accounts that won't trade | "predictive account prioritization", "scoring frameworks", "segment and prioritize the full addressable market" |
| P3 | **Outreach isn't timed to the market** — power price volatility *is* the buying trigger, but nothing links an ERCOT scarcity event to the accounts exposed to it | The best moment to pitch a hedge is when the pain is visible; that window is hours to days | "volatile short-term price exposure", "outreach sequencing", "AI tooling … outreach personalization" |
| P4 | **Blind spots in the customer journey** — no instrumented first-login → first-trade funnel | You can't fix the step you can't see; product and GTM argue from anecdotes | "Instrument the customer journey from first login to first trade; bring market intelligence into roadmap decisions" |
| P5 | **Market-health reporting is manual** — CEO needs weekly funded velocity, mix, activation by segment, spread quality | Slow, inconsistent reporting → slow decisions | "Report weekly pipeline and market health metrics to the CEO" |
| P6 | **Incentives aren't tied to the right outcome** — paying on signatures produces signatures, not volume | Misaligned comp quietly kills activation | "incentive structures … tied to platform volume growth and net-new funded account acquisition", "quantitative, individual scorecards" |
| P7 | **Marketing spend has no line to funded accounts** | Can't reallocate budget to what works | "a clear line from every investment to funded account growth" |
| P8 | **Institutional accounts need structured growth reviews** | Top accounts drive most ADV; churn there is catastrophic | "quarterly institutional account reviews … you own platform utilization and growth metrics" |

## 3. The product: **Ignition** — ElectronX's Activation & Revenue OS

One system that takes every account from signature to steady trading, and that
reports on it. Design principle: *treat sales as an engineering problem* —
inputs, conversion rates, feedback loops, iteration.

### Workstreams → modules

| Workstream | Problem(s) | Module in Ignition | Primary user | North-star metric it moves |
|---|---|---|---|---|
| W1 Market Health Command Center | P5 | **CEO Weekly** dashboard + auto-written weekly memo (export to Markdown) | CEO, Head of GTM | Report time from hours → 0 |
| W2 Activation Engine | P1, P2 | **Activation Queue** — every account ranked by *expected value of a touch* (P(activate) × expected ADV × urgency) with a *next-best action* and stall diagnosis | AEs, RevOps | Funded→first-trade rate, days-to-first-trade |
| W3 Volatility-Triggered Outreach | P3 | **Market Pulse** — ISO/hub price monitor that detects spike / volatility regimes and maps them to exposed accounts, then drafts outreach that references the live event | AEs, Marketing | Reply/meeting rate, activation rate on triggered vs. untriggered cohorts |
| W4 Predictive Scoring | P2 | Explainable propensity model (P(first trade ≤ 45 days)) with per-account reasons; backtested lift chart | RevOps, Head of GTM | Lift @ top decile |
| W5 Journey Instrumentation | P4 | **Funnel & Journey** — step conversion and median time per onboarding step, by segment, with auto-flagged friction points and roadmap asks | Head of Product, Head of GTM | Time-to-first-trade |
| W6 Segmentation & TAM | P2 | **Segments** — addressable market by segment × ISO, penetration, activation, ADV per account → coverage plan | Head of GTM, Strategic Sales | Coverage of top-value segments |
| W7 Team Scorecards & Comp | P6 | **Team & Comp** — individual AE scorecards; comp-plan simulator showing payout under alternative plan designs and what behavior each one rewards | Head of GTM, CEO/board | % of variable comp tied to activation & ADV |
| W8 Marketing ROI | P7 | **Marketing ROI** — channel → lead → funded → active, CAC per funded and per *active* account, ADV per $ | Marketing Manager | Cost per active account |
| W9 Institutional Account Review | P8 | **Account 360 / QBR** — ADV trend, product utilization, health & churn risk, growth plays | Strategic Sales, Head of GTM | Net ADV retention |
| W10 AI copilot | P1, P3 | Outreach drafting: deterministic template engine always on; Claude API (`claude-opus-5-5`) when `ANTHROPIC_API_KEY` is set | AEs | Rep hours saved / touch |

### Account segments (ICP hypotheses)

| Segment | Why they trade short-dated power | Typical first product |
|---|---|---|
| Independent Power Producer (renewables) | Shape / basis risk on merchant wind & solar output | Daily/hourly hub contracts at their ISO |
| Battery Storage Operator | Monetize / hedge intraday spreads | Hourly contracts around peak |
| Retail Electric Provider | Load-following risk in heat waves | Daily peak contracts |
| C&I / Large Load (incl. data centers) | Budget certainty on unhedged index exposure | Daily/weekly hedges |
| Utility / Co-op / Muni | Supplemental hedging, regulatory prudence | Daily |
| Proprietary Trading Firm | Alpha on short-dated volatility; liquidity provision | Everything; API-first |
| Hedge Fund / Asset Manager | Macro / weather views, diversification | Daily/weekly |
| Data Center Developer | New, massive, price-sensitive load | Daily/weekly hedges |

Natural hedgers (IPPs, storage, REPs, large loads) bring *two-sided interest*;
speculators (prop, funds) bring *liquidity*. Healthy market = both, so Ignition
reports the **account-type mix** explicitly.

## 4. Assumptions & honesty notes

* All data in the product is **synthetic**, generated deterministically
  (seeded) and calibrated to look like the real thing (ERCOT summer scarcity
  spikes, CAISO duck curve, PJM/MISO winter peaks). No ElectronX internal data
  was used. Swapping in real CRM, exchange and ISO feeds is an adapter, not a
  rewrite.
* Contract specifications are described generically ("short-dated hourly and
  daily electricity price contracts at major ISO hubs"); we do not claim
  specifics of ElectronX's rulebook.
* Built as a reviewable portfolio product: FastAPI + SQLite + zero-build
  vanilla JS, runs in ~30 seconds from clone.
