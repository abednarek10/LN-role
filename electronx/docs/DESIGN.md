# Ignition — Design System & Frontend Notes

Ignition is ElectronX's Activation & Revenue OS. The frontend is a zero-build, vanilla-JS (ES2020) single-page app served by the API. It uses the vendored Chart.js 4.4.4 and loads nothing from a CDN.

| File | Role |
|---|---|
| `frontend/index.html` | Shell: side nav, top bar (as-of date, watermark, account search, theme toggle), drawer, toasts, SVG icon sprite |
| `frontend/styles.css` | All tokens and components (dark-first, `[data-theme="light"]` override) |
| `frontend/ui.js` | `IG` core: API client (GET cache, readable errors), escaped `html` templates, formatters, skeleton, empty and error states, drawer, toast, metric definitions |
| `frontend/charts.js` | Chart.js defaults read from CSS tokens, axis builder, band and marker plugin, sparkline, midnight ticks |
| `frontend/view-*.js` | One render function per tab |
| `frontend/account.js` | Account 360 drawer and the shared outreach **Draft panel** (draft → approve → queue) |
| `frontend/app.js` | Hash router, nav, theme persistence, search, keyboard shortcuts, boot |
| `frontend/favicon.svg` | Mark: a volt-lime price trace with a spike, on ink |

The backend serves `frontend/` at `/static` and `index.html` at `/`. Every call is a relative `/api/...` request.

---

## 1. Design principles

1. **Dense but calm.** This is a trading-ops cockpit: many numbers, one quiet frame. Surfaces sit one step apart, borders are hairlines, and the only loud colors are data and status.
2. **Every view answers one question.** The question sits under the title (top-bar crumb) and again at the head of the view. Each view has a hero chart, KPI tiles and a table, in that order.
3. **Decisions over dashboards.** CEO Weekly leads with three sentences and three decisions. Pulse ends in a queued touch. Funnel ends in an exported ticket. Team & Comp ends in a plan comparison.
4. **One definition, everywhere.** *Active* (≥4 trading days in trailing 30), *ADV* and *qualifying trade* come from a single tooltip dictionary (`IG.DEF`) and appear the same way in every view.
5. **Honest about data.** A "Synthetic data — illustrative" watermark is always visible, in both the top bar and the nav footer. Cohorts with n < 20 and channels with small n are greyed. Model AUC is framed against the credible 0.72–0.85 band.
6. **Never a blank screen.** Every panel loads independently: skeleton → data, or an inline error with the API message and a Retry button. Empty data gets a sentence that explains the emptiness.
7. **Color is never the only channel.** Status pills carry a dot and a label. Direction pills carry ▲/▼ and a word. Reasons carry +/−. Charts with two or more series always have an HTML legend.

---

## 2. Color tokens

All colors are CSS custom properties on `:root` (dark, the default) and are overridden under `:root[data-theme="light"]`. The theme is stored in `localStorage["ignition.theme"]`, and every storage call is wrapped in try/catch. With no stored value the app opens dark. Charts read tokens when they render, so a theme switch re-renders the view. GETs are cached for 60 s, so the re-render is instant.

### Surfaces and ink

| Token | Dark | Light | Use |
|---|---|---|---|
| `--bg` | `#0a0e14` | `#f2f4f7` | Page plane |
| `--surface` | `#121821` | `#ffffff` | Cards and chart surface |
| `--surface-2` | `#18202c` | `#f6f8fb` | Hover, inset blocks, neutral heat cells |
| `--surface-3` | `#1f2937` | `#edf1f6` | Tracks, stage chips, tooltip |
| `--border` / `--border-strong` | `#232d3c` / `#324055` | `#e1e6ee` / `#c9d2de` | Hairlines |
| `--text` / `--text-2` / `--muted` | `#e8edf4` / `#aeb8c7` / `#7f8a9b` | `#0f1724` / `#465264` / `#677386` | Primary, secondary and muted ink |
| `--grid` / `--axis` | `#1d2633` / `#324055` | `#edf0f4` / `#cbd3de` | Chart chrome (solid hairlines) |

### Brand accent ("volt")

| Token | Dark | Light | Use |
|---|---|---|---|
| `--accent` | `#c8f04a` | `#c8f04a` | Primary buttons (ink text), decisions numbering |
| `--accent-line` | `#c8f04a` | `#4d7c0f` | Focal price line, priority bars, focus ring, selected trigger |

The accent is UI emphasis plus *the one focal series* (the selected hub's price). It is never used as a categorical series color.

### Market side — fixed everywhere

Hedger, speculator and liquidity partner use the same color in every donut, tag, table dot and drawer header.

| Side | Dark | Light |
|---|---|---|
| Hedger | `--hedger #3987e5` | `#2a78d6` |
| Speculator | `--speculator #d95926` | `#eb6834` |
| Liquidity partner | `--lp #199e70` | `#1baf7a` |

These are slots 1–3 of the reference categorical palette, validated with the dataviz six-check validator against the actual surfaces (`#121821` dark, `#ffffff` light) under **all-pairs** (scatter-grade):

- Dark: all checks pass. The worst CVD ΔE is 9.4 and the worst normal-vision ΔE is 20.9.
- Light: all checks pass. Aqua sits at 2.8:1 contrast on white, so side identity always ships with a text label (the relief rule).

### Exposure polarity (Market Pulse)

| | Dark | Light | Encoding |
|---|---|---|---|
| **Hurt** (short the spike: REP, C&I, Data Center, Utility, IPP shape risk) | `--hurt #e66767` | `#d63a3a` | ▼ pill, red exposure bar, red spike-hour bands |
| **Opportunity** (long the spike: Storage, Prop, Fund) | `--opp #2bc4b0` | `#0f9488` | ▲ pill, teal exposure bar, teal negative-price bands |

### Magnitude and ordinal

- `--series` (violet `#9d93ee` dark, `#5446b8` light) is the single-series magnitude hue: cohort bars, fee bars, gain curve, ADV bars and scatter points. It is deliberately *not* blue, so it never reads as "hedger".
- The **ordinal funnel ramp** `--ord-1..4` is one hue (violet) with monotone lightness. It encodes signed → funded → first trade → active. In dark mode the steps run dim to bright (later stage = brighter). In light mode they run light to dark. Both pass the ordinal validator.
- `--greyed` (`#3a4352` / `#cdd3dc`) marks small-n cohorts and channels.

### Status (reserved; always dot + label)

`--good #0ca30c` · `--warn #fab219` · `--serious #ec835a` · `--crit #d03b3b`. On-track, watch and off-track appear as KPI left rules and pills. Text-safe variants are `--good-text` and `--crit-text`.

### Categorical (channels, misc.)

The reference 8-slot order (blue, orange, aqua, yellow, magenta, green, violet, red), stepped per theme. It is used only for marketing channels, which always have a legend. It passes the adjacent-pair validation in both modes.

---

## 3. Type scale

The system sans stack is `Inter, system-ui, -apple-system, Segoe UI, Roboto`. Monospace (`JetBrains Mono`, `SF Mono`, `ui-monospace`) is used only for IDs and the score formula. Tables and axes use `tabular-nums`. Big numbers keep proportional figures.

| Role | Size / weight |
|---|---|
| View title (top bar) | 17 / 600 |
| Card title | 14 / 600 |
| Body, table | 13 / 12.5 |
| Sub-caption, legend | 12 |
| Eyebrow (uppercase, +0.1em) | 10.5 / 650 |
| KPI value | 24 / 650 (22 compact) |
| Hero numerals (lift ×, trigger peak $) | 30 / 18, weight 700 |

---

## 4. Component inventory

| Component | Class / helper | Notes |
|---|---|---|
| App shell | `.app`, `.sidenav`, `.topbar`, `main.view` | Nav collapses to an icon rail ≤1100px and becomes a top scroller ≤720px |
| Watermark badge | `.watermark` | Top bar, nav footer and Account 360 footer |
| KPI tile | `.kpi.{on_track,watch,off_track}` | Label + status pill, value, delta (▲/▼ colored by *good* direction, not sign), target, 12-point sparkline with a dashed target line when it is on scale |
| Status pill | `IG.statusPill()` | Dot + "On track / Watch / Off track" |
| Direction pill | `IG.dirPill()` | ▼ Hurt / ▲ Opportunity |
| Side and segment tag | `IG.sideTag()`, `IG.segTag(code, side, short)` | Colored square + label; short labels in dense tables, full label in tooltip |
| Stage chip | `IG.stagePill()` | Uppercase mono-ish chip |
| Inline bar | `IG.bar(frac, label, cls)` | Priority, touch value (hurt/opp colored), attainment, ADV share |
| Health pill | `IG.healthPill(state, fundedDays)` | X2 vocabulary: Pre-funding (ghost) · No trades yet · funded N d (warn) · Ramping (volt) · Active / Expanding (good) · At risk (serious) · Dormant (crit) |
| Probability | `IG.fmt.prob(v)` | Model probabilities are capped for display: ">95%" (never "100%"), "<1%" |
| Board KPI tile | `.kpis.board` + `kpiTile()` | 6 board tiles (`board:true`), status pill beside the value, `prior_label`, optional `note`. Pacing tiles show "Need X/wk · running Y/wk · EOY ≈ Z". The rest sit behind a "More KPIs" disclosure |
| Lever card | `.lever` | This week's event: funded-not-trading count, exposed, ADV at stake, drafted → approved → queued, past-SLA pill, link to Pulse |
| Event group | `.event-group` | Pulse trigger cards grouped by `event_id`, with event totals in the header |
| Reasons list | `IG.reasonsList()` | +/− sign tile, label, |weight|, weight bar |
| Data table | `table.t` (`.stackable` stacks into cards ≤720px) | Sticky header, hover row, `.greyed`, `.flash` |
| Heatmap | `table.heat` | Funnel: diverging from the all-segment benchmark (neutral → red leak). Segments: sequential violet alpha. Ink flips on dark cells |
| Trigger card | `.trig-card` (button, `aria-pressed`) | Severity bars, regime pill, forward-risk pill, peak $, meta row |
| Event banner | `.banner` | "N accounts exposed · M funded-not-trading · ~X ADV at stake" |
| Drawer | `IG.drawer.open()` | Right side, focus-trapped, Esc and scrim close it, focus returns to the opener |
| Draft panel | `IG.openDraft()` | Workflow steps, engine badge (✦ Claude vs Template), compliance box (block = red; cautions = checkboxes the reviewer must clear), reviewer-name field (remembered locally), email preview, **Edit** (re-lints on save), **Reject** (with reason), Approve → Queue; 409s shown inline |
| Toast | `IG.toast()` | Bottom-left, with a link |
| Skeleton, empty and error states | `IG.skeleton()`, `IG.emptyState()`, `IG.errorState()` | Errors show the API message and a Retry button |
| Segmented control | `.seg-ctl` | ISO, hub, plan, metric and direction toggles |

---

## 5. Chart conventions

- **Marks:** lines are 2px with round joins. Bars are ≤24px thick, with 4px rounded data-ends and square bases. End markers are ≥8px with a surface ring. Area fills are a 10% wash.
- **Chrome:** hairline solid gridlines in `--grid`, no axis borders, muted 11px ticks, axis titles only where units are not obvious.
- **Observed vs projected:** observed data is solid. **Forecasts and targets are dashed** (the forecast daily peak, the ADV target, the cohort target, the spread target, and random or perfect-calibration references).
- **Event shading:** spike hours (≥ the hub's 30-day p99) are `--hurt` at 18% alpha. Negative-price hours are `--opp` at 16% alpha. The selected trigger's peak and the as-of boundary get labeled vertical markers.
- **Focal vs context:** on Pulse the selected hub is the accent line and other hubs in the ISO are muted 1.25px lines.
- **Legends:** HTML legends (not canvas) are used for every chart with two or more series. Chart titles name single series.
- **Tooltips:** index-mode crosshair on line and bar charts. Values are formatted with the same `IG.fmt` helpers as the tables.
- **No dual axes.** v1.1 removed the CEO bars-plus-ADV-line dual axis. The hero is now cumulative signed → funded → Active on one axis, and ADV is its own small chart (total vs liquidity partners, target dashed).
- **Pacing lines:** each cumulative series ends in a dashed line to its Dec 31 target (◆). The value and the remaining gap are labelled directly on the chart, so the gap reads without hovering.
- **Pulse time axis:** one tick per day at **local noon**, so a day's label sits over that day's hours. An Oct 2 15:00 spike reads as "Oct 2", not "Oct 3".
- **Market side colors never change**, including when filters change the series count.

### Formatting

| Kind | Rule | Example |
|---|---|---|
| Money | `$` with k/M/B | `$79k`, `$1.92M` |
| Price | whole dollars ≥$100, else cents | `$4,800`, `$41.20`, `-$30.00` |
| Spread | always cents | `$0.91` |
| Contracts | thousands separators; compact in tiles | `15,840` / `15.8k` |
| Rates | API sends 0–1 floats → 1 decimal | `62.1%` |
| Deltas of rates | percentage points | `+1.7 pp` |
| Days and relative | `17 d`, `today`, `9 days ago`, `never` | |
| Timestamps | API naive UTC rendered as is (no tz shift) | `Oct 2, 18:00` |

---

## 6. Accessibility

- Semantic landmarks: `nav`, `header`, `main`, sections with `aria-labelledby`, `role="dialog"` drawer.
- Skip link. Visible 2px focus ring (`--focus`) on every interactive element.
- Keyboard:
  - <kbd>1</kbd>–<kbd>7</kbd> switch tabs.
  - <kbd>↑</kbd>/<kbd>↓</kbd> move within the nav.
  - <kbd>/</kbd> focuses account search, and arrow keys move through the results.
  - <kbd>Esc</kbd> closes the drawer or search.
  - <kbd>Tab</kbd> is trapped inside an open drawer.
- Expandable queue rows use `aria-expanded` and `aria-controls`. Toggles use `aria-pressed`, `aria-selected` or `aria-checked`.
- Canvases carry `role="img"` and an `aria-label`. Every chart has a table or tile view of the same numbers nearby.
- `prefers-reduced-motion` disables shimmer and transitions, and Replay jumps to the end.
- Contrast: body ink and muted ink clear 4.5:1 on their surfaces in both themes. Light-mode aqua and the status warning colors always ship with labels.

---

## 7. v1.1 changes (exec review round 2)

- **Market Pulse:**
  - The list defaults to **Act now** (top 15 funded-not-trading plus top 5 signed or KYC-approved, by `touch_value`; prospects excluded). A "Show all N" toggle shows everything.
  - The banner reads "N exposed · M funded-not-trading · K to act on now", using event numbers from `/api/pulse/events` (the same source as CEO Weekly).
  - New columns: rank (#), the account's own hub (with "ISO-level" when `hub_match=false`), and an internal `account_fact` line. "Why exposed" is clamped to 2 lines.
  - Trigger cards lead with peak $ and **×p99** (`peak_ratio`); σ is secondary. Negative-price triggers show negative-price hours.
  - Past events show the 8 most recent; older ones sit behind a disclosure.
  - Page height after replay is about 2.5k px, against a 4k limit.
- **CEO Weekly:** 6 board tiles first, the rest under "More KPIs". The pacing hero and lever card replace the dual-axis bars, and the hero's top edge sits about 600–750px down at 1440×900. Pre-history (n=0) cohorts are dropped.
- **Activation Queue:** a **Today / All** toggle. Today is grouped by owner (with hedger share and past-SLA count per rep), and a backlog tile shows what is over the caps. Rows carry a health pill, and P is capped at ">95%".
- **Model:** an "Honest evaluation" block (60-day-gap AUC as the headline, unseen-account AUC, and the 5-flag baseline with the model's uplift).
- **Funnel:**
  - Human step labels, including "from → to" on friction cards.
  - `n_mature` shown per step with a footnote on mature cohorts.
  - At most 6 friction cards, with "Show more".
  - Health states use the X2 vocabulary when the API sends them.
- **Team & Comp:** a "Share of fee revenue" tile and comparison column, plus per-rep accelerator chips (book activation, accelerator on/off against the gate).
- **Account 360:** QBR is hidden (and the QBR draft button removed) when `qbr` is null. Churn risk and net retention are hidden when undefined (before the first trade).
- **Copy:** events read "on Oct 2". Tenors read "Daily peak", not `DAILY_PEAK`. The Pulse lift is "first-trade lift", not "activation". Small-n wording no longer quotes a threshold the rows contradict.
- **Polish:**
  - The nav column background now runs the full page height.
  - Segments uses `targets.spread_usd_mwh[ISO]` (ERCOT $0.75), defaults to HB_NORTH and labels the elasticity note as ISO-level.
  - The coverage column wraps.

Every v1.1 field is read defensively. If the API predates a field, the view falls back: client-side Act-now selection, running-sum cumulative lines, BOARD_KEYS tile order, and hidden blocks.

## 8. Demo click-path (5 minutes)

1. **CEO Weekly (0:45).** Read the three sentences, then the six board tiles: "Funded 205 / 260 — need 4.6/wk, running 3.9/wk". On the hero, the dashed pace lines show the gap to each 2026 target. The lever card shows this week's event, with N funded-not-trading accounts and drafted → queued progress. Close the beat with *Export memo (.md)*.
2. **Market Pulse (1:30), the wow.**
   1. ERCOT is preselected on HB_HOUSTON. Press **Replay event** and the week plays hour by hour until the $4,800 spike lands. The spike band and peak marker appear as it hits, and the HB_HOUSTON trigger opens automatically.
   2. The banner reads "N exposed · M funded-not-trading · K to act on now", the same numbers as the CEO lever. The HB_HOUSTON card leads with $4,800 at ×p99.
   3. The **Act now** list is about 20 rows ranked by touch value. Each row shows the account's own hub and one internal fact line. Toggle **▼ Hurt / ▲ Opp.**: the same spike is pain for REPs and C&I loads and opportunity for Storage and Prop.
   4. Click **Draft** on a funded REP. Point at the engine badge and the compliance box. Enter a reviewer name, tick any caution, then **Approve**. Mention that **Edit** re-lints and **Reject** records a reason.
   5. **Queue**. The toast reads "Logged touch · Activation Queue re-ranked".
   6. Scroll to *Past events*: triggered outreach shows 41% activation against 16% untriggered, a 2.6× lift.
3. **Activation Queue (1:00).** The green banner shows "*Account* moved #7 → #15". **Today** shows per-rep capped lists that are at least half hedgers, plus the backlog count. Expand a row to show the score formula and the +/− reasons. Open the **Model** tab: the Honest evaluation block (60-day-gap AUC, unseen-account AUC, baseline), the gain curve and calibration.
4. **Funnel & Journey (0:45).** The leakiest steps are marked ▼. The red cells in the segment heatmap are leaks against the all-segment rate. Show a friction card's ADV at stake and its roadmap ask, then **Export ticket (.md)**.
5. **Team & Comp (0:45).** The scorecard pays on Active. In the simulator, switch plans (a) → (c): the behavior text and per-rep payouts change, and the comparison table shows cost per Active account.
6. **Close (0:15).** Go back to CEO Weekly and export the memo.

Held for Q&A:
- **Segments:** the heatmap metric toggle, and the liquidity flywheel (spread vs active accounts with the a + b/√active fit).
- **Marketing ROI:** CAC per *Active* account, with small-n channels greyed.
- **Account 360:** click any account name.
