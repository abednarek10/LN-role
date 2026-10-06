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
| Inline bar | `IG.bar(frac, label, cls)` | Priority, exposure, attainment, ADV share |
| Reasons list | `IG.reasonsList()` | +/− sign tile, label, |weight|, weight bar |
| Data table | `table.t` (`.stackable` stacks into cards ≤720px) | Sticky header, hover row, `.greyed`, `.flash` |
| Heatmap | `table.heat` | Funnel: diverging from the all-segment benchmark (neutral → red leak). Segments: sequential violet alpha. Ink flips on dark cells |
| Trigger card | `.trig-card` (button, `aria-pressed`) | Severity bars, regime pill, forward-risk pill, peak $, meta row |
| Event banner | `.banner` | "N accounts exposed · M funded-not-trading · ~X ADV at stake" |
| Drawer | `IG.drawer.open()` | Right side, focus-trapped, Esc and scrim close it, focus returns to the opener |
| Draft panel | `IG.openDraft()` | Workflow steps, engine badge (✦ Claude vs Template), compliance box, email preview, facts, Approve → Queue |
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
- **Dual axis (one sanctioned exception):** the CEO hero chart puts weekly account bars (left) and the ADV line (right) on two axes, as the product brief requests. Both axes are titled, the ADV line is in primary ink (a different mark type and color from the bars), and the ADV target is drawn against its own axis. If `active_accounts` is a stock (end-of-week count, far larger than weekly flows), it moves to its own small chart instead of distorting the bar scale.
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

## 7. Demo click-path (5 minutes)

1. **CEO Weekly (0:45).** Read the three sentences, then point at the off-track tiles (Active rate, median days to first trade, top-5 share). The hero chart shows signed outrunning first trades. Grey cohorts show n < 20 handled honestly. Close the beat with *Export memo (.md)*.
2. **Market Pulse (1:30), the wow.**
   1. ERCOT is preselected on HB_HOUSTON. Press **Replay event** and the week plays hour by hour until the $4,800 spike lands. The spike band and peak marker appear as it hits, and the HB_HOUSTON trigger opens automatically.
   2. The banner reads "14 accounts exposed · 6 funded-not-trading · ~1,2xx contracts/day ADV at stake".
   3. Toggle **▼ Hurt / ▲ Opportunity**: the same spike is pain for REPs and C&I loads and opportunity for Storage and Prop.
   4. Click **Draft** on a funded REP. The panel shows the hub, price, timestamp and illustrative sizing. Point at the *Template engine* or *✦ Claude* badge and the green **Compliance linter passed** box.
   5. **Approve**, then **Queue**. The toast reads "Logged touch · Activation Queue re-ranked".
   6. Scroll to *Past events*: triggered outreach shows 41% activation against 16% untriggered, a 2.6× lift.
3. **Activation Queue (1:00).** The green banner shows "*Account* moved #7 → #15". Use *Jump to row*. Expand a row to show the score formula (P × E[ADV] × k × U × B) and the +/− reasons. Open the **Model** tab and show the gain curve, calibration, AUC 0.79 inside the honest band, and the champion vs challenger comparison.
4. **Funnel & Journey (0:45).** The leakiest steps are marked ▼. The red cells in the segment heatmap are leaks against the all-segment rate. Show a friction card's ADV at stake and its roadmap ask, then **Export ticket (.md)**.
5. **Team & Comp (0:45).** The scorecard pays on Active. In the simulator, switch plans (a) → (c): the behavior text and per-rep payouts change, and the comparison table shows cost per Active account.
6. **Close (0:15).** Go back to CEO Weekly and export the memo.

Held for Q&A:
- **Segments:** the heatmap metric toggle, and the liquidity flywheel (spread vs active accounts with the a + b/√active fit).
- **Marketing ROI:** CAC per *Active* account, with small-n channels greyed.
- **Account 360:** click any account name.
