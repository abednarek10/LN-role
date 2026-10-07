# ElectronX Positioning & Messaging House

**Owner:** Head of GTM & Revenue (Marketing mandate) · **Status:** v1, Oct 2026 ·
**Feeds:** `ignition/content/segment_messaging.json`, `outreach_templates.json`,
`compliance_rules.json`, the Market Pulse recap format and every deck, page and post.

> Scope note: contract specifications are described generically ("short-dated
> hourly, daily-peak and weekly-peak price contracts at major ISO hubs"). Nothing
> here states ElectronX rulebook terms (margin, limits, fees, hours). Any number in
> a customer-facing asset comes from an approved source or is labeled illustrative.

---

## 1. Category

**Direct-access, short-dated power price risk.**

We don't sell "electricity futures" in general; CME and ICE already list monthly
power. We sell access, on a CFTC-regulated exchange, to the **hours, days and
weeks** where power price risk actually sits, for the participants who carry it.

Positioning statement:

> For commercial and institutional participants with short-dated power price
> exposure in ERCOT, PJM, CAISO and MISO, **ElectronX** is the CFTC-regulated,
> direct-access exchange for hourly, daily-peak and weekly-peak price contracts
> at major hubs. Participants manage risk in the window where it happens, without a
> broker credit line or an FCM in between. Unlike monthly futures or bilateral OTC
> deals, the contract matches the shape of the exposure, the price is on screen,
> and every new participant tightens the market for the next one.

**Umbrella line:** *Your exposure is hourly. Manage it in the hours where it lives.*

Short form for social and headers: **Hedge the hour, not the month.** (Copy and
social only; outreach copy avoids imperatives that read as advice.)

## 2. Why now

| Driver | What changed | Who feels it |
|---|---|---|
| **Load growth** | Data centers, electrification and reshoring have put US load growth back after a flat decade. PJM capacity auctions have cleared at record levels, largely on load-growth forecasts, and large loads are energizing in phases into tight systems. | Data centers, C&I, utilities, REPs |
| **Renewables reshape the price curve** | Solar has created a duck curve in CAISO (and increasingly ERCOT): negative midday prices, curtailment, and steep evening ramps. Value now sits in specific hours, not monthly averages. | Solar/wind IPPs, storage, REPs |
| **Scarcity pricing** | ERCOT is an energy-only market. Scarcity adders take real-time prices toward the offer cap in a handful of hours. Uri (2021) and Elliott (2022) showed that winter peaks in ERCOT, PJM and MISO can be as severe as summer ones. | Every load-serving entity; storage and prop on the other side |
| **Storage at scale** | Grid batteries arbitrage the intraday spread. Their revenue depends on the very hours that hedgers fear, which makes them natural counterparties. | Storage, prop, funds |
| **Access** | Most participants with short-dated exposure have no ISDA, broker credit line or FCM relationship sized for it. Mid-size REPs, co-ops, new data-center developers and smaller IPPs are underserved by the status quo. | The long tail of hedgers |

**One-sentence why-now:** power price risk has become more hourly at the same time
as the number of firms carrying it has grown, and the instruments most of them
can reach are still monthly or bilateral.

## 3. Positioning vs. the status quo

| | **OTC bilateral via brokers** | **CME/ICE monthly futures via FCMs** | **Doing nothing (ride the index)** | **ElectronX** |
|---|---|---|---|---|
| Tenor that matches the risk | Any shape, but custom shapes are slow to quote | Liquidity sits mostly in monthly peak/off-peak; daily and balance-of-month listings are thinner | n/a | Hourly, daily-peak, weekly-peak |
| Access | ISDA/EEI master, credit lines, broker relationships; hard for new or mid-size entrants | Through a clearing member (FCM) relationship and its credit terms | None needed | Direct onboarding to the exchange (eligibility applies) |
| Price transparency | Quote-by-quote, opaque | Screen-based | Real-time LMP after the fact | Screen-based, on the short-dated contract itself |
| Counterparty / credit | Bilateral credit exposure | Cleared | n/a | Exchange-traded on a CFTC-regulated venue |
| Minimum practical size | Often block-sized (e.g., 25–50 MW) | Contract-size and FCM-minimum dependent | n/a | Small, standardized contract sizes (exact specs per the ElectronX rulebook, not restated here) |
| What's left unhedged | Whatever the broker couldn't fill | The shape inside the month | Everything | Basis to the node; capacity, transmission, demand charges (we say so) |

**How we talk about competitors:** we don't attack. Monthly futures and OTC remain
right for the base of a portfolio. ElectronX is the **short-dated layer on top**,
the part of the risk that monthly tools average away. The message is "and", not
"instead of". It's also more credible to a risk manager who already has CME and
broker relationships, and those firms carry a positive score in our model
(`has_other_exchange_account`).

**Against "doing nothing":** never shame. Frame each event as *what it revealed
about the exposure*, then pair it with the *forward forecast*. Each event becomes a
data point in the customer's own risk process.

## 4. Messaging house

```
                    ┌──────────────────────────────────────────────────────────┐
  ROOF              │  Your exposure is hourly. Manage it in the hours where it  │
                    │  lives.                                                    │
                    └──────────────────────────────────────────────────────────┘
  PILLARS   ┌──────────────────┬──────────────────┬──────────────────┬──────────────────┐
            │ 1. Fits the risk │ 2. Direct access │ 3. Regulated &   │ 4. Liquidity     │
            │ Hourly / daily / │ No broker line   │ transparent      │ compounds        │
            │ weekly at the    │ or FCM in the    │ CFTC-regulated   │ Same spike: pain │
            │ hub that prices  │ middle; API-     │ venue; on-screen │ for the short,   │
            │ your exposure    │ first for desks  │ prices; standard │ signal for the   │
            │                  │                  │ contracts        │ long. Each new   │
            │                  │                  │                  │ participant      │
            │                  │                  │                  │ tightens spreads │
            └──────────────────┴──────────────────┴──────────────────┴──────────────────┘
  FOUNDATION   Education first · facts from the market, never predictions · fair & balanced
```

**Proof under each pillar (to build; all illustrative until real data replaces synthetic):**

1. *Fits the risk*: event recaps showing the hour-by-hour exposure vs. a monthly average (REP on HB_HOUSTON; solar on SP15).
2. *Direct access*: median days from signature to first trade by segment (from Funnel & Journey) and the API quick-start (target: sandbox certification in under one day).
3. *Regulated & transparent*: settlement against published ISO real-time prices; a "how settlement works" one-pager approved by Legal.
4. *Liquidity compounds*: spread vs. active accounts chart (`a + b/√active`) from CEO Weekly, ERCOT North spread trend and two-sided uptime. The same fact is reported per event (hub spread and two-sided uptime *during* the event, via the `{market_quality_line}` outreach placeholder) and is the lead fact in prop and fund outreach: market quality, not a pitch.

## 5. Messaging by segment

Full fields live in `ignition/content/segment_messaging.json`. Headlines:

| Segment | Direction in Pulse | One line | First product |
|---|---|---|---|
| IPP | opportunity (shape risk) | "Your output and the price don't peak in the same hour. Manage the hours your profile misses." | Hourly |
| Storage | opportunity | "Your revenue lives in a few hours a year. Manage those hours, not the month." | Hourly |
| REP | hurt | "Fixed-price customers, index-priced supply: the risk shows up in the hottest and coldest hours. Hedge the day, sized to the forecast." | Daily peak |
| C&I / Large Load | hurt | "A few extreme hours explain most budget variance. A direct tool for the energy component, with no supply renegotiation." | Weekly peak |
| Utility / Co-op / Muni | hurt | "Supplemental short-dated hedging your risk committee can follow: standard contracts, ISO-price settlement, clear reporting." | Daily peak |
| Data Center | hurt | "Your load ramps in phases; your hedge program can too. Energy only, not capacity, and we'll say so." | Weekly peak |
| Prop | opportunity | "Short-dated US power, API-first, in four ISOs. Every event brings two-sided demand from hedgers." | Hourly |
| Fund | opportunity | "Express weather and load views in the hours that carry them, on a regulated venue, with limits set right before the first order." | Daily peak |

**The direction rule (D6):** the same spike is *hurt* for hedgers short the spike
(REP, C&I, Data Center, Utility) and *opportunity* for those long flexibility
(Storage, Prop, Fund, and IPPs long the spike, which still carry shape risk). We
never send "hurt" copy to an "opportunity" account or the reverse, and in customer
copy "opportunity" stays an internal label: the word itself is a caution phrase.

## 6. Brand voice

**Desk-to-desk.** We write like a good risk manager writing to another.

| Do | Don't |
|---|---|
| Lead with the number, hub and hour: "HB_HOUSTON, Oct 2, 7 hours above $2,200/MWh" | Adjectives where a number works ("massive", "insane", "historic") |
| Use market terms correctly: LMP, hub vs. node, on-peak, basis, ORDC, net load, 4CP | Explaining basics to a trader, or using jargon on a CFO |
| Say what the contract does **and** doesn't cover | Imply a hub contract hedges node basis, capacity or transmission |
| Forecasts are labeled model forecasts with a horizon | "Prices will…", "the next spike is coming" |
| Offer a walkthrough; the decision is theirs | Tell anyone what to buy, sell or size |
| Short: ≤150 words in outreach, one idea per paragraph | Exclamation marks, emojis, urgency ("act now") |
| Acknowledge uncertainty and small samples | Celebrate price spikes; in a grid emergency people lose power |
| "Illustrative" on every hypothetical | Unlabeled "would have saved $X" |

**Visual identity rules for content:** charts always show the hub, the time zone
convention and the data source; synthetic or illustrative data is watermarked;
spikes are shown in context (30-day distribution, not a cropped y-axis).

## 7. Compliance guardrails for marketing on a regulated exchange

Marketing for a CFTC-regulated venue follows the same discipline as a regulated
broker's communications. These are operating rules; the binding policy belongs to
Compliance.

1. **Fair and balanced.** Every benefit is stated next to its limits and the risk of loss. The required footer (`compliance_rules.json → required_footer`) goes on every outreach, recap and gated asset.
2. **No performance claims.** No profit, return or savings claims. Backward-looking "how a position would have settled" examples are allowed only when labeled illustrative, sized hypothetically and shown gross, and they always route to human review (R06).
3. **No advice.** We explain mechanics, settlement and sizing arithmetic. We never recommend a trade, size or timing (R08).
4. **Eligible participants only.** Triggered and paid outreach targets commercial and institutional accounts that have passed an eligibility screen. No consumer targeting, no lookalike audiences built from individuals (R07).
5. **No regulator endorsement.** "CFTC-regulated" is a fact. "CFTC-approved" or "CFTC-backed" is banned (R10).
6. **Substantiated superlatives.** "First US-regulated direct-access electricity derivatives exchange" and similar claims are used only in the Legal-approved form and context, never generated by AI drafting (R11).
7. **Facts in, facts out.** AI drafting receives computed facts and cannot introduce numbers. The linter flags any figure not present in the facts object (R04).
8. **Human approval.** `pending_review → approved → queued`. Nothing auto-sends (R13).
9. **Grid-emergency tone.** During an ISO emergency with firm load shed, commercial touches pause. Only a factual recap goes out, after normal operations resume (R14).
10. **Record everything.** Approved communications, their facts and the reviewer are retained per the exchange's recordkeeping policy (R17).

## 8. The three lines we lead with

1. **"Your exposure is hourly. Manage it in the hours where it lives."** (category + roof)
2. **"Same spike, two sides: pain for the short, signal for the long. A market needs both."** (liquidity flywheel; why we court storage and prop as hard as REPs)
3. **"What the last event revealed about your exposure, and what the next five days look like."** (Market Pulse framing; the opposite of selling insurance after the fire)
