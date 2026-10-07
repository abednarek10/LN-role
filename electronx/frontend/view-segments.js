/*
 * View 6 — Segments. "Where is the unworked value?"
 * Consumes: GET /api/segments, GET /api/liquidity?iso=&tenor=.
 */
"use strict";

IG.views = IG.views || {};
IG.state.seg = IG.state.seg || { metric: "penetration", iso: "ERCOT", tenor: "", hub: "" };

IG.views.segments = function renderSegments(main) {
  const { html } = IG;
  const meta = IG.state.meta || {};
  const st = IG.state.seg;
  const isos = Object.keys(meta.isos || {});
  if (isos.length && !isos.includes(st.iso)) st.iso = isos[0];
  IG.setHTML(main, html`
    <div class="view-head"><div class="q">Where is the unworked value — which segment × ISO cells have TAM but no traders — and how does each new Active account tighten spreads?</div></div>
    <div class="grid g-12">
      <section class="card span-6" aria-labelledby="sh-t">
        <div class="card-h"><div><h2 id="sh-t">Segment × ISO</h2><div class="sub" id="sh-sub"></div></div>
          <div class="tools"><div class="seg-ctl" role="radiogroup" aria-label="Heatmap metric">
            ${[["penetration", "Penetration"], ["activation_rate", "Activation rate"], ["adv_per_active", "ADV / active"]].map(([k, l]) => html`<button type="button" role="radio" data-metric="${k}" aria-checked="${st.metric === k}" aria-pressed="${st.metric === k}">${l}</button>`)}
          </div></div></div>
        <div class="table-wrap" id="sh-heat"></div>
      </section>
      <section class="card span-6 flush" aria-labelledby="st-t">
        <div class="card-h"><div><h2 id="st-t">Segments</h2><div class="sub">TAM, traders, share of ADV and recommended coverage</div></div></div>
        <div class="table-wrap" id="sh-table"></div>
      </section>
      <section class="card span-12" aria-labelledby="lq-t">
        <div class="card-h"><div><h2 id="lq-t">Liquidity flywheel</h2><div class="sub">More active accounts → tighter spreads → easier to activate the next account. Spread ≈ a + b/√active.</div></div>
          <div class="tools">
            <div class="field"><label for="lq-iso" class="sr-only">ISO</label><select id="lq-iso">${isos.map((i) => html`<option ${i === st.iso ? "selected" : ""}>${i}</option>`)}</select></div>
            <div class="field"><label for="lq-tenor" class="sr-only">Tenor</label><select id="lq-tenor"><option value="">All tenors</option>${["HOURLY", "DAILY_PEAK"].map((t) => html`<option value="${t}" ${t === st.tenor ? "selected" : ""}>${IG.tenorLabel(t)}</option>`)}</select></div>
          </div></div>
        <div id="lq-body"></div>
      </section>
    </div>`);

  let segData = null;
  IG.load(IG.$("#sh-heat"), () => IG.api("/segments"), (d) => {
    segData = d;
    drawHeat();
    drawSegTable(d.segments || []);
  }, "table");
  IG.setHTML(IG.$("#sh-table"), IG.skeleton("table"));
  IG.api("/segments").catch((e) => { IG.setHTML(IG.$("#sh-table"), IG.errorState(e)); });

  IG.$$("[data-metric]", main).forEach((b) => b.addEventListener("click", () => {
    st.metric = b.dataset.metric;
    IG.$$("[data-metric]", main).forEach((x) => { const on = x === b; x.setAttribute("aria-pressed", String(on)); x.setAttribute("aria-checked", String(on)); });
    if (segData) drawHeat();
  }));

  function drawHeat() {
    const { fmt } = IG;
    const cells = segData.cells || [];
    const el = IG.$("#sh-heat");
    if (!cells.length) { IG.setHTML(el, IG.emptyState("No segment × ISO cells.")); return; }
    const segs = [...new Set(cells.map((c) => c.segment))];
    const cols = isos.length ? isos.filter((i) => cells.some((c) => c.iso === i)) : [...new Set(cells.map((c) => c.iso))];
    const key = st.metric;
    const vals = cells.map((c) => c[key]).filter(IG.isNum);
    const mx = Math.max(1e-9, ...vals);
    const isRate = key !== "adv_per_active";
    const show = (v) => (isRate ? fmt.pct(v, 0) : fmt.contracts(v));
    IG.setHTML(IG.$("#sh-sub"), {
      penetration: "Signed ÷ TAM accounts. Pale = untapped market.",
      activation_rate: "Active ÷ funded. Pale = we sign them but they don’t trade.",
      adv_per_active: "ADV per Active account (contracts/day). Dark = whales.",
    }[key]);
    const light = document.documentElement.dataset.theme === "light";
    IG.setHTML(el, IG.html`<table class="heat">
      <thead><tr><th class="rowh">Segment</th>${cols.map((c) => IG.html`<th>${c}</th>`)}<th class="muted">Row TAM</th></tr></thead>
      <tbody>${segs.map((s) => {
        const row = cells.filter((c) => c.segment === s);
        const tam = row.reduce((a, c) => a + (c.tam_accounts || 0), 0);
        return IG.html`<tr><th class="rowh" scope="row" style="text-align:left">${IG.segTag(s)}</th>${cols.map((iso) => {
          const c = row.find((x) => x.iso === iso);
          if (!c || !IG.isNum(c[key])) return IG.html`<td class="na" title="${c ? "No activity yet" : "Not in TAM"}">—</td>`;
          const f = isRate ? Math.min(1, c[key]) : c[key] / mx;
          const a = 0.06 + 0.94 * f;
          return IG.html`<td style="background:rgba(var(--series-rgb), ${a.toFixed(3)});color:${a > 0.55 ? (light ? "#fff" : "#0a0e14") : "var(--text)"}"
            title="${IG.segLabel(s)} · ${iso}\nTAM ${fmt.int(c.tam_accounts)} · signed ${fmt.int(c.signed)} · funded ${fmt.int(c.funded)} · active ${fmt.int(c.active)}\nPenetration ${fmt.pct(c.penetration, 0)} · activation ${fmt.pct(c.activation_rate, 0)} · ADV/active ${fmt.contracts(c.adv_per_active)} · ADV ${fmt.contracts(c.adv_total)}">${show(c[key])}</td>`;
        })}<td class="num muted" style="background:none">${fmt.int(tam)}</td></tr>`;
      })}</tbody></table>
      <div class="heat-scale" style="margin-top:8px"><span>low</span><span class="ramp"></span><span>high</span><span style="margin-left:auto">Hover a cell for TAM → signed → funded → active</span></div>`);
  }

  function drawSegTable(segs) {
    const { html, fmt } = IG;
    const el = IG.$("#sh-table");
    if (!segs.length) { IG.setHTML(el, IG.emptyState("No segments.")); return; }
    const rows = segs.slice().sort((a, b) => (b.adv_share || 0) - (a.adv_share || 0));
    const mx = Math.max(1e-9, ...rows.map((r) => r.adv_share || 0));
    IG.setHTML(el, html`<table class="t stackable">
      <thead><tr><th>Segment</th><th class="num">TAM</th><th class="num">Active</th><th>ADV share</th><th>Recommended coverage</th></tr></thead>
      <tbody>${rows.map((r) => html`<tr>
        <td data-l="Segment" class="nowrap" title="${r.label || IG.segLabel(r.segment)}">${IG.sideTag(r.side || IG.segInfo(r.segment).side, IG.segShort(r.segment))}</td>
        <td data-l="TAM" class="num">${fmt.int(r.tam)}</td>
        <td data-l="Active" class="num">${fmt.int(r.active)}</td>
        <td data-l="ADV share" style="min-width:96px">${IG.bar((r.adv_share || 0) / mx, fmt.pct(r.adv_share, 0))}</td>
        <td data-l="Coverage" class="text-2" style="font-size:12px;min-width:140px;white-space:normal">${r.recommended_coverage || "—"}</td></tr>`)}</tbody></table>`);
  }

  /* ---------------- liquidity */
  IG.$("#lq-iso").addEventListener("change", (e) => { st.iso = e.target.value; st.hub = ""; loadLiq(); });
  IG.$("#lq-tenor").addEventListener("change", (e) => { st.tenor = e.target.value; loadLiq(); });
  function loadLiq() {
    const el = IG.$("#lq-body");
    IG.load(el, () => IG.api(`/liquidity${IG.qs({ iso: st.iso, tenor: st.tenor })}`), (d) => drawLiq(el, d), "chart");
  }
  loadLiq();

  function drawLiq(el, d) {
    const { html, fmt } = IG;
    const series = (d.series || []).filter((p) => IG.isNum(p.spread_usd_mwh));
    const el2 = d.elasticity || {};
    if (!series.length) { IG.setHTML(el, IG.emptyState(`No spread history for ${st.iso}.`)); return; }
    const hubs = [...new Set(series.map((p) => p.hub))];
    if (!st.hub || !hubs.includes(st.hub)) st.hub = hubs.includes("HB_NORTH") ? "HB_NORTH" : hubs[0];
    const pts = series.filter((p) => p.hub === st.hub).sort((a, b) => String(a.date).localeCompare(String(b.date)));
    // Daily series may contain one row per tenor: average per date for the time series.
    const byDate = new Map();
    pts.forEach((p) => { const k = p.date; const o = byDate.get(k) || { n: 0, s: 0, u: 0, a: 0 }; o.n++; o.s += p.spread_usd_mwh; o.u += p.uptime_pct || 0; o.a += p.active_accounts || 0; byDate.set(k, o); });
    const ts = [...byDate.entries()].map(([date, o]) => ({ x: +IG.parseTs(date), spread: o.s / o.n, uptime: o.u / o.n, active: o.a / o.n }));
    const b = IG.isNum(el2.b) ? el2.b : null;
    const valid = pts.filter((p) => (p.active_accounts || 0) > 0);
    const a = b != null && valid.length ? valid.reduce((s, p) => s + (p.spread_usd_mwh - b / Math.sqrt(p.active_accounts)), 0) / valid.length : null;
    const xs = valid.map((p) => p.active_accounts);
    const curve = a != null && xs.length ? Array.from({ length: 40 }, (_, i) => { const x = Math.min(...xs) + (i / 39) * (Math.max(...xs) - Math.min(...xs)); return { x, y: a + b / Math.sqrt(Math.max(1, x)) }; }) : [];
    const tmap = ((IG.state.meta || {}).targets || {}).spread_usd_mwh;
    const target = tmap && typeof tmap === "object" && IG.isNum(tmap[st.iso]) ? tmap[st.iso] : IG.isNum(tmap) ? tmap : st.iso === "ERCOT" ? 0.75 : 1.5;
    const t = IG.theme();
    IG.setHTML(el, html`
      <div class="row" style="margin-bottom:8px">
        ${hubs.length > 1 ? html`<div class="seg-ctl" role="group" aria-label="Hub">${hubs.map((h) => html`<button type="button" data-lhub="${h}" aria-pressed="${h === st.hub}">${h}</button>`)}</div>` : html`<span class="stage">${st.hub}</span>`}
        <span class="stat-row" style="margin-left:auto">
          ${b != null ? html`<span>b = <b>${fmt.num(b, 2)}</b></span>` : ""}
          ${IG.isNum(el2.r2) ? html`<span>R² <b>${fmt.num(el2.r2, 2)}</b></span>` : ""}
          <span>Latest spread <b>${fmt.spread(ts[ts.length - 1].spread)}</b>/MWh</span>
          <span>Active accounts <b>${fmt.int(ts[ts.length - 1].active)}</b></span>
        </span>
      </div>
      ${el2.note ? html`<p class="text-2" style="margin:0 0 10px;font-size:12.5px"><span class="muted">${st.iso} fit${hubs.length > 1 ? " (all hubs)" : ""}:</span> ${el2.note}</p>` : ""}
      <div class="grid g-12">
        <div class="span-6"><div class="eyebrow">Spread vs active accounts</div>
          ${IG.legend([{ label: "Daily snapshot", color: t.series }, ...(curve.length ? [{ label: "Fit: a + b/√active", color: t.text2, kind: "dash" }] : [])])}
          <div class="chart-box"><canvas id="lq-scatter" role="img" aria-label="Spread versus active accounts"></canvas></div></div>
        <div class="span-6"><div class="eyebrow">Spread over time</div>
          ${IG.legend([{ label: "Spread $/MWh", color: t.series, kind: "line" }, { label: `Target ≤ ${fmt.spread(target)}`, color: t.muted, kind: "dash" }])}
          <div class="chart-box"><canvas id="lq-ts" role="img" aria-label="Spread over time"></canvas></div></div>
      </div>`);
    IG.$$("[data-lhub]", el).forEach((btn) => btn.addEventListener("click", () => { st.hub = btn.dataset.lhub; drawLiq(el, d); }));
    IG.destroyCharts("liq");
    IG.chart(IG.$("#lq-scatter"), {
      type: "scatter",
      data: { datasets: [
        { label: "Snapshot", data: valid.map((p) => ({ x: p.active_accounts, y: p.spread_usd_mwh, date: p.date })), backgroundColor: IG.alpha(t.series, 0.75), borderColor: t.surface, borderWidth: 1, pointRadius: 4, pointHoverRadius: 6 },
        ...(curve.length ? [{ type: "line", label: "Fit", data: curve, borderColor: t.text2, borderDash: [5, 4], borderWidth: 1.5, pointRadius: 0, tension: 0.3 }] : []),
      ] },
      options: IG.baseOptions({
        parsing: false,
        interaction: { mode: "nearest", intersect: true },
        scales: { x: IG.axis({ type: "linear", title: "Active accounts", maxTicks: 6 }), y: IG.axis({ fmt: (v) => "$" + v.toFixed(2), title: "$/MWh", maxTicks: 6 }) },
        plugins: { tooltip: { filter: (c) => c.datasetIndex === 0, callbacks: { title: (c) => fmt.date(c[0].raw.date, true), label: (c) => ` ${fmt.int(c.raw.x)} active → ${fmt.spread(c.raw.y)}/MWh` } } },
      }),
    }, "liq");
    IG.chart(IG.$("#lq-ts"), {
      type: "line",
      data: { datasets: [{ label: "Spread", data: ts.map((p) => ({ x: p.x, y: p.spread })), borderColor: t.series, backgroundColor: IG.alpha(t.series, 0.08), fill: true, pointRadius: 0 }] },
      options: IG.baseOptions({
        parsing: false,
        scales: { x: IG.axis({ type: "linear", grid: false, min: ts[0].x, max: ts[ts.length - 1].x, fmt: (v) => fmt.date(new Date(v)), maxTicks: 8 }), y: IG.axis({ fmt: (v) => "$" + v.toFixed(2), maxTicks: 6, suggestedMin: Math.min(target * 0.8, ...ts.map((p) => p.spread)) }) },
        plugins: {
          igBands: { hlines: [{ y: target, color: t.muted, label: `target ${fmt.spread(target)}` }] },
          tooltip: { callbacks: { title: (c) => fmt.date(new Date(c[0].parsed.x), true), label: (c) => ` Spread ${fmt.spread(c.parsed.y)}/MWh`, afterLabel: (c) => { const p = ts[c.dataIndex]; return p ? ` ${fmt.int(p.active)} active · uptime ${fmt.pctAuto(p.uptime, 0)}` : ""; } } },
        },
      }),
    }, "liq");
  }
};
