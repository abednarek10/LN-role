/*
 * View 1 — CEO Weekly. "Are signatures becoming liquidity, and what do I decide?"
 * Consumes GET /api/ceo/weekly (+ /api/ceo/weekly.md for export).
 */
"use strict";

IG.views = IG.views || {};

IG.views.ceo = function renderCeo(main) {
  const { html, fmt } = IG;
  const meta = IG.state.meta || {};
  IG.setHTML(main, html`
    <div class="view-head">
      <div class="q">Are we converting signatures into active traders — and liquidity — fast enough to hit the 2026 plan?</div>
      <div class="actions">
        <span class="muted" id="ceo-week">Week ending ${fmt.date(meta.week_end, true)}</span>
        <button type="button" class="btn primary" id="ceo-export">${IG.icon("download")}Export memo (.md)</button>
      </div>
    </div>
    <div id="ceo-body"></div>`);

  IG.$("#ceo-export").addEventListener("click", (e) => {
    const we = (IG.state.ceo && IG.state.ceo.week_end) || meta.week_end || "";
    IG.download(`/ceo/weekly.md${IG.qs({ week_end: we })}`, `ignition-ceo-weekly-${we || "latest"}.md`, e.currentTarget);
  });

  const body = IG.$("#ceo-body");
  IG.setHTML(body, html`
    <div class="headline"><div class="card">${IG.skeleton("lines")}</div><div class="card">${IG.skeleton("lines")}</div></div>
    ${IG.skeleton("tiles")}
    <div class="grid g-12 mt"><div class="card span-8">${IG.skeleton()}</div><div class="card span-4">${IG.skeleton()}</div></div>`);

  IG.load(body, () => IG.api("/ceo/weekly"), (d) => drawCeo(body, d), null);
};

function drawCeo(body, d) {
  const { html, fmt } = IG;
  IG.state.ceo = d;
  if (d.week_end) IG.setHTML(IG.$("#ceo-week"), html`Week ending <b>${fmt.date(d.week_end, true)}</b>`);
  const tags = ["Liquidity", "Balance", "Action"];
  const headline = (d.headline || []).slice(0, 3);
  const decisions = (d.decisions || []).slice(0, 3);
  const series = d.weekly_series || [];

  // Is active_accounts a stock (end-of-week count) or a weekly flow? Decide by scale.
  const maxFlow = Math.max(1, ...series.map((w) => Math.max(w.signed || 0, w.funded || 0, w.first_trades || 0)));
  const maxActive = Math.max(0, ...series.map((w) => w.active_accounts || 0));
  const activeIsStock = maxActive > maxFlow * 3;

  IG.setHTML(body, html`
    <section class="headline" aria-label="Weekly narrative">
      <div class="card">
        <div class="eyebrow">This week in three sentences</div>
        ${headline.length
          ? html`<ol>${headline.map((h, i) => html`<li>${stripTag(h, tags[i])}</li>`)}</ol>`
          : IG.emptyState("No headline generated for this week.")}
      </div>
      <div class="card">
        <div class="eyebrow">Three decisions for Monday</div>
        ${decisions.length ? html`<ol class="decisions">${decisions.map((t) => html`<li>${t}</li>`)}</ol>` : IG.emptyState("No decisions proposed.")}
      </div>
    </section>

    <section aria-label="Key metrics" class="kpis" id="ceo-kpis">
      ${(d.kpis || []).length ? (d.kpis || []).map(kpiTile) : IG.emptyState("No KPIs returned.")}
    </section>

    <div class="grid g-12 mt">
      <section class="card span-8" aria-labelledby="ceo-hero-t">
        <div class="card-h"><div><h2 id="ceo-hero-t">Weekly conversion — signed → funded → first trade${activeIsStock ? "" : " → active"}</h2>
          <div class="sub">Accounts per week (bars, left axis) · ADV in contracts/day (line, right axis)</div></div></div>
        ${IG.legend([
          { label: "Signed", color: IG.css("--ord-1") },
          { label: "Funded", color: IG.css("--ord-2") },
          { label: "First trades", color: IG.css("--ord-3") },
          ...(activeIsStock ? [] : [{ label: "Newly active", color: IG.css("--ord-4") }]),
          { label: "ADV (20-td)", color: IG.css("--text"), kind: "line" },
        ])}
        <div class="chart-box tall">${series.length ? html`<canvas id="ceo-hero" role="img" aria-label="Weekly signed, funded and first-trade counts with ADV line"></canvas>` : IG.emptyState("No weekly history yet.")}</div>
      </section>
      <section class="card span-4" aria-labelledby="ceo-mix-t">
        <div class="card-h"><div><h2 id="ceo-mix-t">Market balance</h2><div class="sub">Hedgers bring open interest, speculators bring depth</div></div></div>
        <div id="ceo-mix"></div>
      </section>

      <section class="card span-6 wide-break" aria-labelledby="ceo-coh-t">
        <div class="card-h"><div><h2 id="ceo-coh-t" title="${IG.DEF.cohort}">30-day cohort activation</h2>
          <div class="sub">Share of each weekly funding cohort with a qualifying first trade within 30 days</div></div></div>
        <div id="ceo-cohorts"></div>
      </section>
      <section class="card span-6 flush wide-break" aria-labelledby="ceo-spr-t">
        <div class="card-h"><div><h2 id="ceo-spr-t" title="${IG.DEF.spread}">Spread quality</h2>
          <div class="sub">Top-of-book spread and two-sided uptime vs 2026 targets</div></div></div>
        <div class="table-wrap" id="ceo-spreads"></div>
      </section>

      <section class="card span-8 flush" aria-labelledby="ceo-stall-t">
        <div class="card-h"><div><h2 id="ceo-stall-t">Stalled funded accounts</h2>
          <div class="sub">Funded &gt;21 days with no qualifying trade, ranked by expected ADV — sunk CAC one good call can recover</div></div></div>
        <div class="table-wrap" id="ceo-stalled"></div>
      </section>
      <section class="card span-4" aria-labelledby="ceo-act-t">
        <div class="card-h"><div><h2 id="ceo-act-t">${activeIsStock ? "Active accounts & fee revenue" : "Fee revenue"}</h2>
          <div class="sub">${activeIsStock ? "End-of-week Active count (top) · weekly fees (bottom)" : "Exchange fees per week"}</div></div></div>
        ${activeIsStock ? html`<div class="chart-box xs"><canvas id="ceo-active" role="img" aria-label="Active accounts by week"></canvas></div>` : ""}
        <div class="chart-box xs"><canvas id="ceo-fees" role="img" aria-label="Fee revenue by week"></canvas></div>
      </section>
    </div>`);

  // sparklines
  IG.$$("#ceo-kpis canvas.spark").forEach((c, i) => {
    const k = (d.kpis || [])[i] || {};
    IG.spark(c, k.spark, { color: IG.css("--series"), target: IG.isNum(k.target) && k.spark && within(k.target, k.spark) ? k.target : undefined });
  });

  if (series.length) heroChart(series, activeIsStock);
  mixPanel(IG.$("#ceo-mix"), d.mix || {});
  cohortChart(IG.$("#ceo-cohorts"), d.activation_cohorts || []);
  spreadTable(IG.$("#ceo-spreads"), d.spreads || []);
  stalledTable(IG.$("#ceo-stalled"), d.stalled || []);
  smallSeries(series, activeIsStock);
}

/** Keep the target line on the sparkline only when it is on a comparable scale. */
function within(t, arr) {
  const v = arr.filter(IG.isNum);
  if (!v.length) return false;
  const lo = Math.min(...v), hi = Math.max(...v), span = Math.max(hi - lo, Math.abs(hi) * 0.05);
  return t >= lo - span * 1.5 && t <= hi + span * 1.5;
}

/** Bold the leading "Liquidity:" style tag if the backend included it. */
function stripTag(text, tag) {
  const m = String(text).match(/^\s*([A-Za-z ]{3,20}):\s*(.*)$/s);
  if (m) return IG.html`<b class="tag">${m[1]}:</b> ${m[2]}`;
  return IG.html`<b class="tag">${tag}:</b> ${text}`;
}

function kpiTile(k) {
  const { html, fmt } = IG;
  const lowerBetter = IG.lowerIsBetter(k.key, k.label);
  let deltaCls = "flat";
  if (IG.isNum(k.delta) && k.delta !== 0) deltaCls = (k.delta > 0) !== lowerBetter ? "good" : "bad";
  const arrow = IG.isNum(k.delta) ? (k.delta > 0 ? "▲" : k.delta < 0 ? "▼" : "■") : "";
  return html`<article class="kpi ${k.status || ""}" title="${IG.kpiDef(k.key, k.label)}">
    <div class="kpi-label">${k.label || fmt.humanize(k.key)} ${IG.statusPill(k.status)}</div>
    <div class="kpi-value">${IG.fmtUnit(k.value, k.unit)}</div>
    <div class="kpi-meta">
      ${IG.isNum(k.delta) ? html`<span class="delta ${deltaCls}">${arrow} ${IG.fmtDelta(k.delta, k.unit)}</span><span>vs prior</span>` : ""}
      ${IG.isNum(k.target) ? html`<span style="margin-left:auto">Target ${lowerBetter ? "≤" : "≥"} ${IG.fmtUnit(k.target, k.unit)}</span>` : ""}
    </div>
    <canvas class="spark" aria-hidden="true"></canvas>
  </article>`;
}

function heroChart(series, activeIsStock) {
  const t = IG.theme();
  const labels = series.map((w) => IG.fmt.date(w.week_end));
  const bar = (key, label, color) => ({
    type: "bar", label, data: series.map((w) => w[key] ?? null), backgroundColor: color,
    maxBarThickness: 9, categoryPercentage: 0.78, barPercentage: 0.92, yAxisID: "y", order: 2,
  });
  const datasets = [
    bar("signed", "Signed", t.ord[0]),
    bar("funded", "Funded", t.ord[1]),
    bar("first_trades", "First trades", t.ord[2]),
  ];
  if (!activeIsStock) datasets.push(bar("active_accounts", "Newly active", t.ord[3]));
  datasets.push({
    type: "line", label: "ADV (contracts/day)", data: series.map((w) => w.adv_contracts ?? null), borderColor: t.text,
    backgroundColor: t.text, yAxisID: "y2", order: 1, pointRadius: (c) => (c.dataIndex === series.length - 1 ? 4 : 0), pointBackgroundColor: t.text,
  });
  const advTarget = (IG.state.meta && IG.state.meta.targets && findNum(IG.state.meta.targets, /adv/i, 1000)) || null;
  IG.chart(IG.$("#ceo-hero"), {
    type: "bar",
    data: { labels, datasets },
    options: IG.baseOptions({
      scales: {
        x: IG.axis({ grid: false, maxTicks: 10 }),
        y: IG.axis({ beginAtZero: true, title: "accounts / week", maxTicks: 6 }),
        y2: IG.axis({ position: "right", grid: false, beginAtZero: true, title: "ADV (contracts/day)", fmt: (v) => IG.fmt.contracts(v, true), maxTicks: 6, suggestedMax: advTarget || undefined }),
      },
      plugins: {
        tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${c.dataset.yAxisID === "y2" ? IG.fmt.contracts(c.parsed.y) : IG.fmt.int(c.parsed.y)}` } },
        igBands: advTarget ? { hlines: [{ y: advTarget, axis: "y2", color: t.muted, label: `ADV target ${IG.fmt.contracts(advTarget, true)}` }] } : {},
      },
    }),
  });
}

/** Find a numeric target in meta.targets whose key matches. Tolerates nested objects. */
function findNum(obj, re, minVal = -Infinity, maxVal = Infinity) {
  for (const [k, v] of Object.entries(obj || {})) {
    if (re.test(k)) {
      if (IG.isNum(v) && v >= minVal && v <= maxVal) return v;
      if (v && typeof v === "object") {
        const inner = Object.values(v).find((x) => IG.isNum(x) && x >= minVal && x <= maxVal);
        if (inner != null) return inner;
      }
    }
  }
  return null;
}
IG.findTarget = findNum;

function mixPanel(el, mix) {
  const { html, fmt } = IG;
  const sides = ["hedger", "speculator", "liquidity_partner"];
  const acc = mix.by_side_accounts || {};
  const adv = mix.by_side_adv || {};
  const tot = (o) => sides.reduce((s, k) => s + (IG.isNum(o[k]) ? o[k] : 0), 0);
  const ta = tot(acc), tv = tot(adv);
  if (!ta && !tv) { IG.setHTML(el, IG.emptyState("No mix data.")); return; }
  const share = (o, total, k) => (total ? (o[k] || 0) / total : null);
  const hedgerTarget = findNum((IG.state.meta || {}).targets, /hedger/i, 0, 1) ?? 0.5;
  const top5Target = findNum((IG.state.meta || {}).targets, /top5|top_5|concentration/i, 0, 1) ?? 0.45;
  IG.setHTML(el, html`
    ${IG.legend(sides.map((s) => ({ label: IG.sideLabel(s), color: IG.sideColor(s) })))}
    <div class="two-up">
      <figure><div class="chart-box xs"><canvas id="mix-acc" role="img" aria-label="Active accounts by side"></canvas></div>
        <figcaption class="muted" style="text-align:center;font-size:11.5px">Active accounts</figcaption></figure>
      <figure><div class="chart-box xs"><canvas id="mix-adv" role="img" aria-label="ADV by side"></canvas></div>
        <figcaption class="muted" style="text-align:center;font-size:11.5px">ADV</figcaption></figure>
    </div>
    <table class="t" style="margin-top:8px">
      <thead><tr><th>Side</th><th class="num">Accounts</th><th class="num">ADV share</th></tr></thead>
      <tbody>${sides.map((s) => html`<tr><td>${IG.sideTag(s)}</td><td class="num">${fmt.pct(share(acc, ta, s))}</td><td class="num">${fmt.pct(share(adv, tv, s))}</td></tr>`)}</tbody>
    </table>
    <div class="stat-row" style="margin-top:10px">
      <span title="${IG.DEF.top5}">Top-5 ADV share <b>${fmt.pct(mix.top5_adv_share)}</b> ${IG.isNum(mix.top5_adv_share) ? IG.statusPill(mix.top5_adv_share <= top5Target ? "on_track" : "off_track") : ""}</span>
      <span title="${IG.DEF.hhi}">HHI <b>${IG.isNum(mix.hhi) ? mix.hhi.toFixed(3) : "—"}</b></span>
      <span>Hedger target ≥ <b>${fmt.pct(hedgerTarget, 0)}</b></span>
    </div>`);
  const donut = (id, o, total, centerLabel) => {
    const data = sides.map((s) => o[s] || 0);
    IG.chart(IG.$(id), {
      type: "doughnut",
      data: { labels: sides.map(IG.sideLabel), datasets: [{ data, backgroundColor: sides.map(IG.sideColor), hoverOffset: 3 }] },
      options: {
        cutout: "68%",
        plugins: {
          tooltip: { callbacks: { label: (c) => ` ${c.label}: ${fmt.pct(total ? c.parsed / total : 0)}` } },
          igCenter: { text: fmt.pct(share(o, total, "hedger"), 0), sub: "hedgers" },
        },
      },
      plugins: [centerText],
    });
  };
  donut("#mix-acc", acc, ta);
  donut("#mix-adv", adv, tv);
}

const centerText = {
  id: "igCenter",
  afterDraw(chart, _a, opts) {
    if (!opts || !opts.text) return;
    const { ctx, chartArea: a } = chart;
    const cx = (a.left + a.right) / 2, cy = (a.top + a.bottom) / 2;
    ctx.save();
    ctx.textAlign = "center";
    ctx.fillStyle = IG.css("--text");
    ctx.font = `650 17px ${IG.theme().font}`;
    ctx.fillText(opts.text, cx, cy + 3);
    ctx.fillStyle = IG.css("--muted");
    ctx.font = `500 10.5px ${IG.theme().font}`;
    ctx.fillText(opts.sub || "", cx, cy + 17);
    ctx.restore();
  },
};
IG.centerTextPlugin = centerText;

function cohortChart(el, cohorts) {
  const { html, fmt } = IG;
  if (!cohorts.length) { IG.setHTML(el, IG.emptyState("No matured cohorts yet.")); return; }
  const t = IG.theme();
  const target = findNum((IG.state.meta || {}).targets, /cohort/i, 0, 1) ?? 0.55;
  const small = cohorts.filter((c) => c.greyed).length;
  IG.setHTML(el, html`
    ${IG.legend([
      { label: "Matured cohort (n ≥ 20)", color: t.series },
      { label: "n < 20 — not decision-grade", color: t.greyed },
      { label: `Target ${fmt.pct(target, 0)}`, color: t.muted, kind: "dash" },
    ])}
    <div class="chart-box"><canvas id="ceo-coh" role="img" aria-label="30-day activation rate by funding cohort week"></canvas></div>
    <div class="footnote">${small} of ${cohorts.length} cohorts greyed for small n. Hover a bar for n.</div>`);
  IG.chart(IG.$("#ceo-coh"), {
    type: "bar",
    data: {
      labels: cohorts.map((c) => fmt.date(c.cohort_week)),
      datasets: [{
        label: "Activated ≤30d", data: cohorts.map((c) => c.activated_30d_rate),
        backgroundColor: cohorts.map((c) => (c.greyed ? t.greyed : t.series)), maxBarThickness: 22, categoryPercentage: 0.8,
      }],
    },
    options: IG.baseOptions({
      scales: { x: IG.axis({ grid: false, maxTicks: 8 }), y: IG.axis({ beginAtZero: true, suggestedMax: Math.max(0.8, target + 0.1), fmt: (v) => fmt.pct(v, 0), maxTicks: 5 }) },
      plugins: {
        tooltip: {
          callbacks: {
            title: (c) => `Cohort week of ${c[0].label}`,
            label: (c) => ` Activated ≤30d: ${fmt.pct(c.parsed.y)}`,
            afterLabel: (c) => { const co = cohorts[c.dataIndex]; return ` n = ${co.n}${co.greyed ? " (greyed: n < 20)" : ""}`; },
          },
        },
        igBands: { hlines: [{ y: target, color: t.muted, label: `target ${fmt.pct(target, 0)}` }] },
      },
    }),
  });
}

function spreadTable(el, spreads) {
  const { html, fmt } = IG;
  if (!spreads.length) { IG.setHTML(el, IG.emptyState("No spread snapshots.")); return; }
  IG.setHTML(el, html`<table class="t stackable">
    <thead><tr><th>Hub · tenor</th><th class="num">Spread $/MWh</th><th class="num">Two-sided uptime</th><th>Status</th></tr></thead>
    <tbody>${spreads.map((s) => {
      const badSpread = IG.isNum(s.target_spread) && s.spread_usd_mwh > s.target_spread;
      const badUp = IG.isNum(s.target_uptime) && pctVal(s.uptime_pct) < pctVal(s.target_uptime);
      return html`<tr>
        <td data-l="Hub" class="nowrap"><b>${s.hub}</b> <span class="stage">${String(s.tenor || "").replace(/_/g, " ")}</span><span class="tgt">${s.iso}</span></td>
        <td data-l="Spread" class="num nowrap"><span style="${badSpread ? "color:var(--crit-text);font-weight:600" : ""}">${fmt.spread(s.spread_usd_mwh)}</span><span class="tgt">target ≤ ${fmt.spread(s.target_spread)}</span></td>
        <td data-l="Uptime" class="num nowrap"><span style="${badUp ? "color:var(--crit-text);font-weight:600" : ""}">${fmt.pctAuto(s.uptime_pct)}</span><span class="tgt">target ≥ ${fmt.pctAuto(s.target_uptime, 0)}</span></td>
        <td data-l="Status">${IG.statusPill(s.status)}</td></tr>`;
    })}</tbody></table>`);
}
const pctVal = (v) => (IG.isNum(v) ? (v > 1.5 ? v / 100 : v) : null);

function stalledTable(el, rows) {
  const { html, fmt } = IG;
  if (!rows.length) { IG.setHTML(el, IG.emptyState("No stalled funded accounts.", "Every funded account older than 21 days has traded.")); return; }
  const maxAdv = Math.max(1, ...rows.map((r) => r.exp_adv || 0));
  IG.setHTML(el, html`<table class="t stackable">
    <thead><tr><th>Account</th><th>Segment</th><th>Stage</th><th class="num">Days stalled</th><th title="${IG.DEF.exp_adv}">E[ADV] contracts/day</th><th>Next action</th></tr></thead>
    <tbody>${rows.map((r) => html`<tr>
      <td data-l="Account">${IG.acct(r.account_id, r.name)}</td>
      <td data-l="Segment">${IG.segTag(r.segment, null, true)}</td>
      <td data-l="Stage">${IG.stagePill(r.stage)}</td>
      <td data-l="Days stalled" class="num"><b>${fmt.int(r.days_stalled)}</b></td>
      <td data-l="E[ADV]">${IG.bar((r.exp_adv || 0) / maxAdv, fmt.contracts(r.exp_adv))}</td>
      <td data-l="Next action" class="text-2">${typeof r.next_action === "object" && r.next_action ? r.next_action.action : r.next_action || "—"}</td>
    </tr>`)}</tbody></table>`);
}

function smallSeries(series, activeIsStock) {
  if (!series.length) return;
  const t = IG.theme();
  const labels = series.map((w) => IG.fmt.date(w.week_end));
  if (activeIsStock && IG.$("#ceo-active")) {
    IG.chart(IG.$("#ceo-active"), {
      type: "line",
      data: { labels, datasets: [{ label: "Active accounts", data: series.map((w) => w.active_accounts), borderColor: t.series, backgroundColor: IG.alpha(t.series, 0.1), fill: true, pointRadius: (c) => (c.dataIndex === series.length - 1 ? 4 : 0), pointBackgroundColor: t.series }] },
      options: IG.baseOptions({ scales: { x: IG.axis({ grid: false, maxTicks: 5 }), y: IG.axis({ maxTicks: 4 }) } }),
    });
  }
  IG.chart(IG.$("#ceo-fees"), {
    type: "bar",
    data: { labels, datasets: [{ label: "Fee revenue", data: series.map((w) => w.fee_revenue ?? null), backgroundColor: t.series, maxBarThickness: 10 }] },
    options: IG.baseOptions({
      scales: { x: IG.axis({ grid: false, maxTicks: 5 }), y: IG.axis({ beginAtZero: true, maxTicks: 4, fmt: (v) => IG.fmt.usd(v) }) },
      plugins: { tooltip: { callbacks: { label: (c) => ` Fees: ${IG.fmt.usdFull(c.parsed.y)}` } } },
    }),
  });
}
