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

/* Board tiles (X: exactly 6 flagged `board`); fallback order if the API predates the flag. */
const BOARD_KEYS = [["funded_cum", "funded_accounts"], ["active_rate"], ["adv_contracts"], ["cohort_activation", "cohort_activation_30d"], ["hedger_share_active"], ["ercot_spread", "ercot_north_spread"]];
function splitKpis(kpis) {
  const flagged = kpis.filter((k) => k.board === true);
  let board;
  if (flagged.length) board = flagged;
  else {
    board = [];
    BOARD_KEYS.forEach((alts) => { const k = kpis.find((x) => alts.includes(x.key)); if (k) board.push(k); });
    kpis.forEach((k) => { if (board.length < 6 && !board.includes(k) && !/stalled/.test(k.key)) board.push(k); });
  }
  return { board, more: kpis.filter((k) => !board.includes(k)) };
}

function drawCeo(body, d) {
  const { html, fmt } = IG;
  IG.state.ceo = d;
  if (d.week_end) IG.setHTML(IG.$("#ceo-week"), html`Week ending <b>${fmt.date(d.week_end, true)}</b>`);
  const tags = ["Liquidity", "Balance", "Action"];
  const headline = (d.headline || []).slice(0, 3);
  const decisions = (d.decisions || []).slice(0, 3);
  const series = d.weekly_series || [];
  const kpis = d.kpis || [];
  const { board, more } = splitKpis(kpis);

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

    <section aria-label="Board KPIs" class="kpis board" id="ceo-kpis">
      ${board.length ? board.map(kpiTile) : IG.emptyState("No KPIs returned.")}
    </section>
    ${more.length ? html`<details class="more-kpis" id="ceo-more"><summary>More KPIs <span class="muted">(${more.length})</span></summary>
      <div class="kpis" style="margin-top:10px">${more.map(kpiTile)}</div></details>` : ""}

    <div class="grid g-12 mt">
      <section class="card span-8" aria-labelledby="ceo-hero-t" id="ceo-hero-card">
        <div class="card-h"><div><h2 id="ceo-hero-t">Plan pacing — signed → funded → Active</h2>
          <div class="sub">Cumulative accounts by week. Dashed = the straight line still needed to reach each 2026 target by Dec 31.</div></div></div>
        <div id="ceo-hero-legend"></div>
        <div class="chart-box tall">${series.length ? html`<canvas id="ceo-hero" role="img" aria-label="Cumulative signed, funded and Active accounts against 2026 targets"></canvas>` : IG.emptyState("No weekly history yet.")}</div>
      </section>
      <div class="span-4 stack">
        <section class="card lever" aria-labelledby="ceo-lever-t" id="ceo-lever"></section>
        <section class="card" aria-labelledby="ceo-adv-t">
          <div class="card-h"><div><h2 id="ceo-adv-t" title="${IG.DEF.adv}">ADV, contracts/day</h2><div class="sub">20-trading-day average · liquidity-partner volume split out</div></div></div>
          <div id="ceo-adv-legend"></div>
          <div class="chart-box xs"><canvas id="ceo-adv" role="img" aria-label="ADV by week, total and liquidity-partner"></canvas></div>
        </section>
      </div>

      <section class="card span-4" aria-labelledby="ceo-mix-t">
        <div class="card-h"><div><h2 id="ceo-mix-t">Market balance</h2><div class="sub">Hedgers bring open interest, speculators bring depth</div></div></div>
        <div id="ceo-mix"></div>
      </section>
      <section class="card span-8" aria-labelledby="ceo-coh-t">
        <div class="card-h"><div><h2 id="ceo-coh-t" title="${IG.DEF.cohort}">30-day cohort activation</h2>
          <div class="sub">Share of each weekly funding cohort with a qualifying first trade within 30 days</div></div></div>
        <div id="ceo-cohorts"></div>
      </section>

      <section class="card span-6 flush" aria-labelledby="ceo-stall-t">
        <div class="card-h"><div><h2 id="ceo-stall-t">Stalled funded accounts</h2>
          <div class="sub">Funded &gt;21 days with no qualifying trade, ranked by expected ADV${IG.isNum(d.stalled_total) ? ` · top ${Math.min((d.stalled || []).length, d.stalled_total)} of ${d.stalled_total}` : ""}</div></div></div>
        <div class="table-wrap" id="ceo-stalled"></div>
      </section>
      <section class="card span-6 flush" aria-labelledby="ceo-spr-t">
        <div class="card-h"><div><h2 id="ceo-spr-t" title="${IG.DEF.spread}">Spread quality</h2>
          <div class="sub">Top-of-book spread and two-sided uptime vs 2026 targets</div></div></div>
        <div class="table-wrap" id="ceo-spreads"></div>
      </section>
    </div>`);

  const sparkAll = (root, list) => IG.$$("canvas.spark", root).forEach((c, i) => {
    const k = list[i] || {};
    IG.spark(c, k.spark, { color: IG.css("--series"), target: IG.isNum(k.target) && k.spark && within(k.target, k.spark) ? k.target : undefined });
  });
  sparkAll(IG.$("#ceo-kpis"), board);
  const moreEl = IG.$("#ceo-more");
  if (moreEl) moreEl.addEventListener("toggle", () => { if (moreEl.open) sparkAll(moreEl, more); });

  if (series.length) heroChart(series, kpis);
  leverCard(IG.$("#ceo-lever"), d.lever, d);
  advChart(series);
  mixPanel(IG.$("#ceo-mix"), d.mix || {});
  cohortChart(IG.$("#ceo-cohorts"), (d.activation_cohorts || []).filter((c) => (c.n || 0) > 0));
  spreadTable(IG.$("#ceo-spreads"), d.spreads || []);
  stalledTable(IG.$("#ceo-stalled"), d.stalled || []);
}

/** Lever card (§1 `lever`): the one event the team is working this week, with outreach progress. */
function leverCard(el, lv, d) {
  const { html, fmt } = IG;
  if (!lv) { IG.setHTML(el, html`<div class="eyebrow">This week’s lever</div>${IG.emptyState("No lever this week.")}`); return; }
  const evId = lv.event_id || null;
  const iso = lv.iso || (lv.isos ? Object.keys(lv.isos)[0] : "");
  const m = evId && String(evId).match(/(\d{4})(\d{2})(\d{2})$/);
  const day = m ? fmt.date(`${m[1]}-${m[2]}-${m[3]}`) : null;
  const fnt = IG.isNum(lv.funded_not_trading) ? lv.funded_not_trading : null;
  const adv = IG.isNum(lv.adv_at_stake) ? lv.adv_at_stake : lv.adv;
  const steps = [["drafted", "Drafted"], ["approved", "Approved"], ["queued", "Queued"]].filter(([k]) => IG.isNum(lv[k]));
  IG.setHTML(el, html`
    <div class="eyebrow" id="ceo-lever-t">This week’s lever</div>
    <div class="lever-title">${iso ? `${iso} ` : ""}${day ? `event on ${day}` : lv.action ? "volatility sequence" : "event"}</div>
    <div class="lever-big"><b>${fmt.int(fnt ?? lv.n)}</b> ${fnt != null ? "funded-not-trading accounts" : "exposed accounts"}</div>
    <div class="stat-row" style="margin-top:4px">
      ${fnt != null && IG.isNum(lv.n) ? html`<span><b>${fmt.int(lv.n)}</b> exposed</span>` : ""}
      ${IG.isNum(adv) ? html`<span title="${IG.DEF.adv_at_stake}">~<b>${fmt.contracts(adv)}</b> contracts/day at stake</span>` : ""}
    </div>
    ${steps.length ? html`<div class="lever-flow" aria-label="Outreach progress">
      ${steps.map(([k, l], i) => html`${i ? html`<span class="sepr">→</span>` : ""}<span><b>${fmt.int(lv[k])}</b> ${l.toLowerCase()}</span>`)}
      ${IG.isNum(lv.past_sla) ? html`<span class="pill ${lv.past_sla > 0 ? "crit" : "good"}" style="margin-left:auto"><span class="dot"></span>${fmt.int(lv.past_sla)} past SLA</span>` : ""}
    </div>` : ""}
    <a class="btn sm" href="#/pulse" style="margin-top:10px">Work it in Market Pulse →</a>`);
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
  const delta = IG.isNum(k.delta) ? k.delta : IG.isNum(k.value) && IG.isNum(k.prior) ? k.value - k.prior : null;
  if (!IG.isNum(k.delta) && IG.isNum(delta) && delta !== 0) deltaCls = (delta > 0) !== lowerBetter ? "good" : "bad";
  const arrow = IG.isNum(delta) ? (delta > 0 ? "▲" : delta < 0 ? "▼" : "■") : "";
  const pace = k.pace || null;
  return html`<article class="kpi ${k.status || ""}" title="${IG.kpiDef(k.key, k.label)}">
    <div class="kpi-label">${k.label || fmt.humanize(k.key)}</div>
    <div class="kpi-vrow"><div class="kpi-value">${IG.fmtUnit(k.value, k.unit)}${pace && IG.isNum(k.target) ? html`<small>/ ${IG.fmtUnit(k.target, k.unit)}</small>` : ""}</div>${IG.statusPill(k.status)}</div>
    ${pace ? html`<div class="kpi-meta pace">
        <span>Need <b>${fmt.num(pace.needed_weekly, 1)}</b>/wk</span><span>running <b class="${IG.isNum(pace.run_rate_4w) && IG.isNum(pace.needed_weekly) ? (pace.run_rate_4w >= pace.needed_weekly ? "delta good" : "delta bad") : ""}">${fmt.num(pace.run_rate_4w, 1)}</b>/wk</span>
        ${IG.isNum(pace.projected_eoy) ? html`<span style="margin-left:auto">EOY ≈ <b>${fmt.int(pace.projected_eoy)}</b></span>` : ""}</div>`
      : html`<div class="kpi-meta">
        ${IG.isNum(delta) ? html`<span class="delta ${deltaCls}">${arrow} ${IG.fmtDelta(delta, k.unit)}</span><span>vs ${k.prior_label || "prior"}</span>` : ""}
        ${IG.isNum(k.target) ? html`<span style="margin-left:auto">Target ${lowerBetter ? "≤" : "≥"} ${IG.fmtUnit(k.target, k.unit)}</span>` : ""}
      </div>`}
    ${k.note ? html`<div class="kpi-note" title="${k.note}">${k.note}</div>` : ""}
    <canvas class="spark" aria-hidden="true"></canvas>
  </article>`;
}

function cumSeries(series, key, flowKey, kpis, kpiKeys) {
  if (series.some((w) => IG.isNum(w[key]))) return series.map((w) => (IG.isNum(w[key]) ? w[key] : null));
  // Older API: running sum of weekly flow, anchored so the last point equals the cumulative KPI when known.
  let run = 0;
  const raw = series.map((w) => (run += w[flowKey] || 0));
  const k = kpis.find((x) => kpiKeys.includes(x.key));
  const off = k && IG.isNum(k.value) ? k.value - raw[raw.length - 1] : 0;
  return raw.map((v) => v + off);
}

function heroChart(series, kpis) {
  const t = IG.theme();
  const targets = (IG.state.meta && IG.state.meta.targets) || {};
  const xs = series.map((w) => +IG.parseTs(w.week_end));
  const last = xs[xs.length - 1];
  const yearEnd = +new Date(new Date(last).getFullYear(), 11, 31);
  const signed = cumSeries(series, "signed_cum", "signed", kpis, ["signed_cum"]);
  const funded = cumSeries(series, "funded_cum", "funded", kpis, ["funded_cum", "funded_accounts"]);
  const active = series.map((w) => (IG.isNum(w.active_accounts) ? w.active_accounts : null));
  const tSigned = findNum(targets, /^signed/i, 1) ?? 420;
  const tFunded = findNum(targets, /^funded/i, 1) ?? 260;
  const tActive = Math.round(tFunded * (findNum(targets, /^active_rate$/i, 0, 1) ?? 0.7));
  const lines = [
    { label: "Signed", data: signed, target: tSigned, color: t.ord[1] },
    { label: "Funded", data: funded, target: tFunded, color: t.ord[2] },
    { label: "Active", data: active, target: tActive, color: t.ord[3] },
  ];
  IG.setHTML(IG.$("#ceo-hero-legend"), IG.legend([
    ...lines.map((l) => ({ label: `${l.label} (target ${IG.fmt.int(l.target)})`, color: l.color, kind: "line" })),
    { label: "Pace needed to Dec 31", color: t.muted, kind: "dash" },
  ]));
  const datasets = [];
  lines.forEach((l) => {
    const pts = xs.map((x, i) => ({ x, y: l.data[i] })).filter((p) => IG.isNum(p.y));
    if (!pts.length) return;
    datasets.push({ label: l.label, data: pts, borderColor: l.color, backgroundColor: l.color, borderWidth: 2.5, tension: 0.2,
      pointRadius: (c) => (c.dataIndex === pts.length - 1 ? 4.5 : 0), pointBackgroundColor: l.color, pointBorderColor: t.surface, pointBorderWidth: 2 });
    const end = pts[pts.length - 1];
    datasets.push({ label: `${l.label} pace`, data: [end, { x: yearEnd, y: l.target }], borderColor: l.color, borderDash: [5, 5], borderWidth: 1.5,
      pointRadius: [0, 4], pointStyle: "rectRot", pointBackgroundColor: l.color, tension: 0, $pace: true, $from: end, $target: l.target, $name: l.label });
  });
  // Direct labels at the series ends: current value and the gap to target.
  const endLabels = {
    id: "igEndLabels",
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      ctx.save();
      ctx.font = `600 11px ${IG.theme().font}`;
      const minTarget = Math.min(...chart.data.datasets.filter((x) => x.$pace).map((x) => x.$target));
      chart.data.datasets.forEach((ds, i) => {
        if (!ds.$pace) return;
        const below = ds.$target === minTarget; // lowest line labels below its marker to avoid colliding with the one above
        const meta = chart.getDatasetMeta(i);
        const p0 = meta.data[0], p1 = meta.data[1];
        if (!p0 || !p1) return;
        ctx.fillStyle = IG.css("--text");
        ctx.textAlign = "right";
        ctx.fillText(`${IG.fmt.int(ds.$from.y)}`, p0.x - 7, below ? p0.y + 15 : p0.y - 7);
        ctx.fillStyle = IG.css("--text-2");
        ctx.textAlign = "right";
        ctx.fillText(`${ds.$name} ${IG.fmt.int(ds.$target)} · gap ${IG.fmt.int(Math.max(0, ds.$target - ds.$from.y))}`, p1.x - 8, below ? p1.y + 16 : p1.y - 8);
      });
      ctx.restore();
    },
  };
  const allY = datasets.flatMap((d) => d.data.map((p) => p.y));
  IG.chart(IG.$("#ceo-hero"), {
    type: "line",
    data: { datasets },
    options: IG.baseOptions({
      parsing: false,
      interaction: { mode: "nearest", axis: "x", intersect: false },
      layout: { padding: { top: 18, right: 8 } },
      scales: {
        x: IG.axis({ type: "linear", min: xs[0], max: yearEnd + 3 * 864e5, grid: false, fmt: (v) => IG.fmt.month(new Date(v)), maxTicks: 10 }),
        y: IG.axis({ beginAtZero: true, suggestedMax: Math.max(...allY) * 1.08, maxTicks: 6, title: "accounts (cumulative)" }),
      },
      plugins: {
        tooltip: {
          filter: (c) => !c.dataset.$pace,
          callbacks: { title: (c) => (c.length ? `Week ending ${IG.fmt.date(new Date(c[0].parsed.x), true)}` : ""), label: (c) => ` ${c.dataset.label}: ${IG.fmt.int(c.parsed.y)}` },
        },
        igBands: { lines: [{ x: last, color: IG.theme().muted, label: "Now" }] },
      },
    }),
    plugins: [endLabels],
  });
}

function advChart(series) {
  if (!series.length || !IG.$("#ceo-adv")) return;
  const t = IG.theme();
  const labels = series.map((w) => IG.fmt.date(w.week_end));
  const hasLp = series.some((w) => IG.isNum(w.adv_lp));
  const target = findNum((IG.state.meta || {}).targets, /^adv_contracts$|^adv/i, 1000);
  IG.setHTML(IG.$("#ceo-adv-legend"), IG.legend([
    { label: "Total", color: t.text, kind: "line" },
    ...(hasLp ? [{ label: "Liquidity partners", color: t.lp, kind: "line" }] : []),
    ...(target ? [{ label: `Target ${IG.fmt.contracts(target, true)}`, color: t.muted, kind: "dash" }] : []),
  ]));
  IG.chart(IG.$("#ceo-adv"), {
    type: "line",
    data: { labels, datasets: [
      { label: "Total ADV", data: series.map((w) => w.adv_contracts ?? null), borderColor: t.text, backgroundColor: t.text, pointRadius: (c) => (c.dataIndex === series.length - 1 ? 3.5 : 0) },
      ...(hasLp ? [{ label: "LP ADV", data: series.map((w) => w.adv_lp ?? null), borderColor: t.lp, backgroundColor: t.lp, borderWidth: 1.5 }] : []),
    ] },
    options: IG.baseOptions({
      scales: { x: IG.axis({ grid: false, maxTicks: 4 }), y: IG.axis({ beginAtZero: true, maxTicks: 4, suggestedMax: target || undefined, fmt: (v) => IG.fmt.contracts(v, true) }) },
      plugins: {
        tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${IG.fmt.contracts(c.parsed.y)}` } },
        igBands: target ? { hlines: [{ y: target, color: t.muted }] } : {},
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
        label: "First qualifying trade ≤30d", data: cohorts.map((c) => c.activated_30d_rate),
        backgroundColor: cohorts.map((c) => (c.greyed ? t.greyed : t.series)), maxBarThickness: 22, categoryPercentage: 0.8,
      }],
    },
    options: IG.baseOptions({
      scales: { x: IG.axis({ grid: false, maxTicks: 8 }), y: IG.axis({ beginAtZero: true, suggestedMax: Math.max(0.8, target + 0.1), fmt: (v) => fmt.pct(v, 0), maxTicks: 5 }) },
      plugins: {
        tooltip: {
          callbacks: {
            title: (c) => `Cohort week of ${c[0].label}`,
            label: (c) => ` First qualifying trade ≤30d: ${fmt.pct(c.parsed.y)}`,
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
        <td data-l="Hub" class="nowrap"><b>${s.hub}</b> <span class="stage tenor">${IG.tenorLabel(s.tenor)}</span><span class="tgt">${s.iso}</span></td>
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
    <thead><tr><th>Account</th><th>Segment · stage</th><th class="num" title="Days since funding without a qualifying trade">Days</th><th title="${IG.DEF.exp_adv}">E[ADV]/day</th><th>Next action</th></tr></thead>
    <tbody>${rows.map((r) => html`<tr>
      <td data-l="Account">${IG.acct(r.account_id, r.name)}</td>
      <td data-l="Segment">${IG.segTag(r.segment, null, true)}<div style="margin-top:3px">${IG.stagePill(r.stage)}</div></td>
      <td data-l="Days stalled" class="num"><b>${fmt.int(Math.round(r.days_stalled))}</b></td>
      <td data-l="E[ADV]">${IG.bar((r.exp_adv || 0) / maxAdv, fmt.contracts(r.exp_adv))}</td>
      <td data-l="Next action" class="text-2" style="min-width:130px"><div class="clamp2" title="${typeof r.next_action === "object" && r.next_action ? r.next_action.action : r.next_action || ""}">${typeof r.next_action === "object" && r.next_action ? r.next_action.action : r.next_action || "—"}</div></td>
    </tr>`)}</tbody></table>`);
}
