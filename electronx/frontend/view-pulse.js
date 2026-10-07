/*
 * View 2 — Market Pulse (the wow moment). "Where is power hurting now, and who's exposed?"
 * Consumes: GET /api/pulse/hubs?iso=&hours=168, /api/pulse/triggers,
 *           /api/pulse/triggers/{id}/accounts, /api/pulse/history,
 *           POST /api/outreach/draft → /approve → /queue (via IG.openDraft in account.js).
 */
"use strict";

IG.views = IG.views || {};

IG.views.pulse = function renderPulse(main) {
  const { html } = IG;
  const meta = IG.state.meta || {};
  const isos = Object.keys(meta.isos || { ERCOT: [], PJM: [], CAISO: [], MISO: [] });
  const ps = IG.state.pulse;
  if (!ps.iso || !isos.includes(ps.iso)) ps.iso = isos.includes("ERCOT") ? "ERCOT" : isos[0];

  IG.setHTML(main, html`
    <div class="view-head">
      <div class="q">Where is power hurting right now — and which of our not-yet-trading accounts are exposed to it?</div>
      <div class="actions">
        <div class="seg-ctl" role="tablist" aria-label="ISO">
          ${isos.map((iso) => html`<button type="button" role="tab" data-iso="${iso}" aria-selected="${iso === ps.iso}">${iso}</button>`)}
        </div>
        <button type="button" class="btn" id="pulse-replay" title="Replay the last 7 days hour by hour">${IG.icon("play")}Replay event</button>
      </div>
    </div>
    <div class="grid g-12">
      <section class="card span-8" aria-labelledby="hub-t">
        <div class="card-h">
          <div><h2 id="hub-t"><span id="hub-iso">${ps.iso}</span> hub prices — last 7 days</h2>
          <div class="sub">Real-time LMP, $/MWh · spike hours shaded · 5-day forecast daily peak dashed</div></div>
          <div class="tools" id="hub-chips"></div>
        </div>
        <div id="hub-legend"></div>
        <div class="replay-bar" id="replay-bar" hidden><span id="replay-read">Replaying…</span><div class="replay-progress"><b id="replay-prog"></b></div></div>
        <div class="chart-box tall" id="hub-chart-box">${IG.skeleton()}</div>
        <div class="stat-row" id="hub-stats" style="margin-top:10px"></div>
      </section>
      <section class="card span-4" aria-labelledby="trig-t">
        <div class="card-h"><div><h2 id="trig-t">Volatility triggers</h2><div class="sub">Realized spikes and forward risk · click to see who’s exposed</div></div></div>
        <div class="trigger-list" id="trig-list"></div>
      </section>
      <section class="span-12" id="exposure" aria-live="polite"></section>
      <section class="card span-12" aria-labelledby="hist-t">
        <div class="card-h"><div><h2 id="hist-t" title="${IG.DEF.lift}">Does triggered outreach work? Past events</h2>
          <div class="sub">14-day activation for accounts touched within 72h of an event vs comparable untouched accounts</div></div></div>
        <div id="pulse-hist"></div>
      </section>
    </div>`);

  IG.$$("[data-iso]", main).forEach((b) =>
    b.addEventListener("click", () => {
      if (ps.iso === b.dataset.iso) return;
      ps.iso = b.dataset.iso;
      ps.hub = null;
      IG.$$("[data-iso]", main).forEach((x) => x.setAttribute("aria-selected", String(x === b)));
      IG.$("#hub-iso").textContent = ps.iso;
      loadHubs();
      drawTriggerList();
    })
  );
  IG.$("#pulse-replay").addEventListener("click", () => replay());

  let triggers = [];
  let hubsData = null;
  let chart = null;
  let full = null; // {sel:[{x,y}], others:[...], fc:[...]} for replay
  let replaying = false;

  /* ---------------- hubs + chart */
  function loadHubs() {
    const box = IG.$("#hub-chart-box");
    IG.load(box, () => IG.api(`/pulse/hubs${IG.qs({ iso: ps.iso, hours: 168 })}`), (d) => {
      hubsData = d;
      const hubs = d.hubs || [];
      if (!hubs.length) { IG.setHTML(box, IG.emptyState(`No hub prices for ${ps.iso}.`)); IG.setHTML(IG.$("#hub-chips"), ""); IG.setHTML(IG.$("#hub-stats"), ""); return; }
      if (!ps.hub || !hubs.some((h) => h.hub === ps.hub)) {
        // default to the hub with the most severe trigger, else the most volatile
        const trig = triggers.filter((t) => t.iso === ps.iso).sort((a, b) => sevNum(b) - sevNum(a))[0];
        ps.hub = trig && hubs.some((h) => h.hub === trig.hub) ? trig.hub : hubs.slice().sort((a, b) => ((b.stats || {}).vol_z || 0) - ((a.stats || {}).vol_z || 0))[0].hub;
      }
      drawHubChips(hubs);
      drawChart();
    });
  }

  function drawHubChips(hubs) {
    IG.setHTML(IG.$("#hub-chips"), html`<div class="seg-ctl" role="group" aria-label="Hub">${hubs.map((h) => html`<button type="button" data-hub="${h.hub}" aria-pressed="${h.hub === ps.hub}">${h.hub}</button>`)}</div>`);
    IG.$$("[data-hub]").forEach((b) => b.addEventListener("click", () => {
      ps.hub = b.dataset.hub;
      IG.$$("[data-hub]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      drawChart();
    }));
  }

  function spikeThreshold(stats) {
    if (IG.isNum(stats.p99_30d) && stats.p99_30d > 0) return stats.p99_30d;
    if (IG.isNum(stats.avg_30d)) return Math.max(150, stats.avg_30d * 4);
    return 300;
  }

  function drawChart() {
    if (!hubsData) return;
    const box = IG.$("#hub-chart-box");
    IG.destroyCharts("pulse");
    chart = null;
    const hubs = hubsData.hubs || [];
    const sel = hubs.find((h) => h.hub === ps.hub) || hubs[0];
    const t = IG.theme();
    const toPts = (s) => (s || []).map((p) => ({ x: +IG.parseTs(p.ts), y: p.lmp })).filter((p) => IG.isNum(p.x) && IG.isNum(p.y));
    const selPts = toPts(sel.series);
    const others = hubs.filter((h) => h !== sel).map((h) => ({ hub: h.hub, pts: toPts(h.series) }));
    if (!selPts.length) { IG.setHTML(box, IG.emptyState(`No price series for ${sel.hub}.`)); return; }
    const last = selPts[selPts.length - 1];
    const fc = (sel.forecast || []).map((f) => {
      const d = IG.parseTs(f.date);
      if (d) d.setHours(17); // plot the daily peak at the typical on-peak hour (HE17)
      return { x: d ? +d : null, y: f.forecast_peak_lmp, avg: f.forecast_avg_lmp };
    }).filter((p) => IG.isNum(p.x) && IG.isNum(p.y) && p.x > last.x);
    const fcPts = fc.length ? [{ x: last.x, y: last.y }, ...fc] : [];
    full = { sel: selPts, others: others.map((o) => o.pts), fc: fcPts };

    const stats = sel.stats || {};
    const thr = spikeThreshold(stats);
    const bands = [];
    const runs = (pred, color) => {
      let start = null;
      selPts.forEach((p, i) => {
        if (pred(p.y) && start == null) start = p.x;
        const endRun = start != null && (!pred(p.y) || i === selPts.length - 1);
        if (endRun) {
          const endX = pred(p.y) ? p.x + 3600e3 : p.x;
          bands.push({ x0: start - 1800e3, x1: endX - 1800e3, color });
          start = null;
        }
      });
    };
    runs((y) => y >= thr, IG.alpha(t.hurt, 0.18));
    runs((y) => y < 0, IG.alpha(t.opp, 0.16));
    const lines = [{ x: last.x + 1800e3, color: t.muted, label: "As of " + IG.fmt.date(IG.state.meta && IG.state.meta.as_of ? IG.state.meta.as_of : new Date(last.x)) }];
    const trig = ps.trigger && ps.trigger.hub === sel.hub ? ps.trigger : null;
    if (trig && trig.peak_ts) lines.push({ x: +IG.parseTs(trig.peak_ts), color: t.hurt, label: `Peak ${IG.fmt.price(trig.peak_lmp)}`, dash: [2, 2] });

    const hasNeg = selPts.some((p) => p.y < 0);
    IG.setHTML(IG.$("#hub-legend"), IG.legend([
      { label: sel.hub, color: t.accent, kind: "line" },
      ...(others.length ? [{ label: "Other hubs in ISO", color: t.muted, kind: "line" }] : []),
      { label: `Spike hour (≥ ${IG.fmt.price(thr)}, p99 of 30d)`, color: t.hurt, kind: "band" },
      ...(hasNeg ? [{ label: "Negative price", color: t.opp, kind: "band" }] : []),
      ...(fcPts.length ? [{ label: "Forecast daily peak", color: t.accent, kind: "dash" }] : []),
    ]));

    IG.setHTML(box, html`<canvas id="hub-chart" role="img" aria-label="Hourly real-time price for ${sel.hub} over the last 7 days with forecast"></canvas>`);
    const allY = selPts.map((p) => p.y).concat(fcPts.map((p) => p.y), ...others.map((o) => o.pts.map((p) => p.y)));
    const yMax = Math.max(...allY), yMin = Math.min(0, ...allY);
    const xMin = selPts[0].x, xMax = fcPts.length ? fcPts[fcPts.length - 1].x + 6 * 3600e3 : last.x;
    chart = IG.chart(IG.$("#hub-chart"), {
      type: "line",
      data: {
        datasets: [
          { label: sel.hub, data: selPts, borderColor: t.accent, backgroundColor: t.accent, borderWidth: 2, tension: 0.15, order: 1, pointHoverBackgroundColor: t.accent },
          ...others.map((o) => ({ label: o.hub, data: o.pts, borderColor: IG.alpha(t.muted, 0.55), backgroundColor: t.muted, borderWidth: 1.25, tension: 0.15, order: 3 })),
          ...(fcPts.length ? [{ label: "Forecast peak", data: fcPts, borderColor: t.accent, backgroundColor: t.surface, borderDash: [6, 5], borderWidth: 2, tension: 0, pointRadius: (c) => (c.dataIndex === 0 ? 0 : 4), pointBorderColor: t.accent, pointBorderWidth: 2, order: 2 }] : []),
        ],
      },
      options: IG.baseOptions({
        parsing: false,
        normalized: true,
        interaction: { mode: "nearest", axis: "x", intersect: false },
        scales: {
          x: { ...IG.axis({ type: "linear", min: xMin, max: xMax, grid: false, fmt: (v) => IG.tickDay(v) }), afterBuildTicks: IG.noonTicks },
          y: IG.axis({ min: yMin < 0 ? Math.floor(yMin / 50) * 50 : 0, suggestedMax: yMax * 1.05, fmt: (v) => IG.fmt.price(v), maxTicks: 6, title: "$/MWh" }),
        },
        plugins: {
          igBands: { bands, lines },
          tooltip: {
            filter: (c) => c.datasetIndex === 0 || c.dataset.label === "Forecast peak" ? !(c.dataset.label === "Forecast peak" && c.dataIndex === 0) : true,
            callbacks: {
              title: (items) => (items.length ? (items[0].dataset.label === "Forecast peak" ? `Forecast · ${IG.fmt.date(new Date(items[0].parsed.x))}` : IG.fmt.dateTime(new Date(items[0].parsed.x))) : ""),
              label: (c) => ` ${c.dataset.label}: ${IG.fmt.price(c.parsed.y)}/MWh`,
              afterLabel: (c) => (c.dataset.label === "Forecast peak" && c.raw && IG.isNum(c.raw.avg) ? ` Forecast avg: ${IG.fmt.price(c.raw.avg)}/MWh` : c.datasetIndex === 0 && c.parsed.y >= thr ? " ▲ spike hour" : ""),
            },
          },
        },
      }),
    }, "pulse");

    IG.setHTML(IG.$("#hub-stats"), html`
      <span>Last <b>${IG.fmt.price(stats.last)}</b></span>
      <span>30d avg <b>${IG.fmt.price(stats.avg_30d)}</b></span>
      <span>30d p99 <b>${IG.fmt.price(stats.p99_30d)}</b></span>
      <span>72h max <b>${IG.fmt.price(stats.max_72h)}</b></span>
      <span>72h min <b>${IG.fmt.price(stats.min_72h)}</b></span>
      <span>Spike hours (72h) <b>${IG.fmt.int(stats.spike_hours_72h)}</b></span>
      <span title="${IG.DEF.vol_z}">Vol z <b>${IG.isNum(stats.vol_z) ? stats.vol_z.toFixed(1) + "σ" : "—"}</b></span>
      ${fc.length ? html`<span>Next forecast peak <b>${IG.fmt.price(Math.max(...fc.map((f) => f.y)))}</b> <span class="muted">(${IG.fmt.date(new Date(fc.reduce((a, b) => (b.y > a.y ? b : a)).x))})</span></span>` : ""}`);
  }

  /* ---------------- replay: progressive reveal of the 168h series up to the spike */
  function replay() {
    if (!chart || !full || replaying) return;
    replaying = true;
    const btn = IG.$("#pulse-replay");
    btn.disabled = true;
    const bar = IG.$("#replay-bar");
    bar.hidden = false;
    const ds = chart.data.datasets;
    const n = full.sel.length;
    const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dur = reduce ? 1 : 4800;
    const t0 = performance.now();
    const fcIdx = ds.findIndex((d) => d.label === "Forecast peak");
    if (fcIdx >= 0) ds[fcIdx].data = [];
    // Reveal shading and markers only once the replay cursor reaches them.
    const bandOpts = chart.options.plugins.igBands || {};
    const allBands = bandOpts.bands || [], allLines = bandOpts.lines || [];
    const step = (now) => {
      if (!chart || !chart.canvas || !chart.canvas.isConnected) { replaying = false; return; }
      const f = Math.min(1, (now - t0) / dur);
      const eased = f < 0.5 ? 2 * f * f : 1 - Math.pow(-2 * f + 2, 2) / 2;
      const k = Math.max(1, Math.round(eased * n));
      ds[0].data = full.sel.slice(0, k);
      full.others.forEach((o, i) => { if (ds[1 + i]) ds[1 + i].data = o.filter((p) => p.x <= full.sel[k - 1].x); });
      const cx = full.sel[k - 1].x;
      bandOpts.bands = allBands.filter((b) => b.x0 <= cx).map((b) => ({ ...b, x1: Math.min(b.x1, cx + 1800e3) }));
      bandOpts.lines = allLines.filter((l) => l.x <= cx);
      chart.update("none");
      const cur = full.sel[k - 1];
      IG.setHTML(IG.$("#replay-read"), html`Replaying <b>${IG.fmt.dateTime(new Date(cur.x))}</b> · ${ps.hub} <b>${IG.fmt.price(cur.y)}/MWh</b>`);
      IG.$("#replay-prog").style.width = (f * 100).toFixed(1) + "%";
      if (f < 1) requestAnimationFrame(step);
      else {
        bandOpts.bands = allBands;
        bandOpts.lines = allLines;
        if (fcIdx >= 0) ds[fcIdx].data = full.fc;
        chart.update();
        replaying = false;
        btn.disabled = false;
        setTimeout(() => { bar.hidden = true; }, 1200);
        // Land the punchline: open the trigger for this hub if one exists.
        const tr = triggers.filter((x) => x.hub === ps.hub).sort((a, b) => sevNum(b) - sevNum(a))[0] || triggers.filter((x) => x.iso === ps.iso).sort((a, b) => sevNum(b) - sevNum(a))[0];
        if (tr && (!ps.trigger || ps.trigger.trigger_id !== tr.trigger_id)) selectTrigger(tr);
      }
    };
    requestAnimationFrame(step);
  }

  /* ---------------- triggers (grouped by event_id, X6; intensity = peak ÷ p99, X8) */
  let events = []; // optional /api/pulse/events — single source for event numbers
  const eventOf = (t) => t.event_id || `${t.iso}-${String(t.start_ts || t.peak_ts || "").slice(0, 10).replace(/-/g, "")}`;
  const intensity = (t) => (IG.isNum(t.peak_ratio) ? t.peak_ratio : sevNum(t) / 100);
  function drawTriggerList() {
    const el = IG.$("#trig-list");
    if (!triggers.length) {
      IG.setHTML(el, IG.emptyState("No volatility triggers in the last 72 hours.", "Forward-risk triggers appear here when a forecast peak is ≤5 days out."));
      IG.setHTML(IG.$("#exposure"), "");
      return;
    }
    const groups = new Map();
    triggers.forEach((t) => { const k = eventOf(t); if (!groups.has(k)) groups.set(k, []); groups.get(k).push(t); });
    const ordered = [...groups.entries()].map(([k, ts]) => [k, ts.slice().sort((a, b) => intensity(b) - intensity(a))])
      .sort((a, b) => (a[1][0].iso === ps.iso ? 0 : 1) - (b[1][0].iso === ps.iso ? 0 : 1) || intensity(b[1][0]) - intensity(a[1][0]));
    IG.setHTML(el, html`${ordered.map(([k, ts]) => {
      const ev = events.find((e) => e.event_id === k);
      const day = IG.fmt.date(ts[0].start_ts || ts[0].peak_ts);
      return html`<div class="event-group">
        <div class="event-h"><b>${ts[0].iso}</b> · ${day} event${ts.length > 1 ? html` <span class="muted">· ${ts.length} hubs</span>` : ""}
          ${ev ? html`<span class="muted ev-tot">${IG.fmt.int(ev.exposed)} exposed · ${IG.fmt.int(ev.funded_not_trading)} funded-not-trading</span>` : ""}</div>
        ${ts.map((t) => triggerCard(t))}</div>`;
    })}`);
    IG.$$("[data-trigger]", el).forEach((b) => b.addEventListener("click", () => {
      const tr = triggers.find((x) => x.trigger_id === b.dataset.trigger);
      if (!tr) return;
      if (tr.iso !== ps.iso) {
        ps.iso = tr.iso;
        IG.$$("[data-iso]").forEach((x) => x.setAttribute("aria-selected", String(x.dataset.iso === ps.iso)));
        IG.$("#hub-iso").textContent = ps.iso;
        ps.hub = tr.hub;
        loadHubs();
      } else if (ps.hub !== tr.hub && hubsData && (hubsData.hubs || []).some((h) => h.hub === tr.hub)) {
        ps.hub = tr.hub;
        drawHubChips(hubsData.hubs);
      }
      selectTrigger(tr);
    }));
  }

  function triggerCard(t) {
    const sel = ps.trigger && ps.trigger.trigger_id === t.trigger_id;
    const lvl = sevLevel(t.severity);
    const neg = t.regime === "negative_price";
    const ratio = IG.isNum(t.peak_ratio) ? t.peak_ratio : null;
    const hours = neg && IG.isNum(t.neg_hours) ? t.neg_hours : t.spike_hours;
    return html`<button type="button" class="trig-card" data-trigger="${t.trigger_id}" aria-pressed="${!!sel}">
      <div>
        <div class="t-title"><span class="sev l${lvl}" title="Severity ${IG.isNum(t.severity) ? Math.round(t.severity) : t.severity} / 100"><i></i><i></i><i></i><i></i></span>${t.hub}</div>
        <div class="row" style="margin-top:4px;gap:6px">
          <span class="pill ${neg ? "opp" : "hurt"}">${IG.regimeLabel(t.regime)}</span>
          ${t.forward_risk ? html`<span class="pill warn" title="A forecast peak ≤5 days out adds forward risk"><span class="dot"></span>Forward risk</span>` : ""}
        </div>
      </div>
      <div class="t-lead">
        <div class="t-peak">${IG.fmt.price(t.peak_lmp)}</div>
        ${ratio != null ? html`<div class="t-ratio" title="${neg ? "Depth vs the 30-day low tail" : "Peak price ÷ the hub’s 30-day p99 — how far outside normal this was"}">${neg ? "" : "×"}${ratio >= 10 ? Math.round(ratio) : ratio.toFixed(1)}${neg ? "× p1" : " p99"}</div>` : html`<div class="muted" style="font-size:11px;text-align:right">${IG.fmt.dateTime(t.peak_ts || t.start_ts)}</div>`}
      </div>
      <div class="t-meta">
        <span>${neg ? "Neg. hours" : "Spike hrs"} <b>${IG.fmt.int(hours)}</b></span>
        <span>Exposed <b>${IG.fmt.int(t.exposed_count)}</b></span>
        <span>Funded-not-trading <b>${IG.fmt.int(t.funded_not_trading)}</b></span>
        ${IG.isNum(t.actionable_count) ? html`<span>Act now <b>${IG.fmt.int(t.actionable_count)}</b></span>` : ""}
        <span title="${IG.DEF.adv_at_stake}">ADV at stake <b>~${IG.fmt.contracts(t.adv_at_stake)}</b>/day</span>
        <span class="muted" title="${IG.DEF.vol_z}">${IG.isNum(t.vol_z) ? t.vol_z.toFixed(1) + "σ" : ""}</span>
      </div>
    </button>`;
  }

  /* ---------------- exposure: banner + "Act now" list (X7) */
  let dirFilter = "all";
  if (!ps.view) ps.view = "actionable";
  function selectTrigger(tr) {
    ps.trigger = tr;
    IG.$$("[data-trigger]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.trigger === tr.trigger_id)));
    if (hubsData && (hubsData.hubs || []).some((h) => h.hub === tr.hub)) drawChart();
    loadExposure(tr);
  }
  function loadExposure(tr) {
    const host = IG.$("#exposure");
    const view = ps.view;
    IG.load(host, () => IG.api(`/pulse/triggers/${encodeURIComponent(tr.trigger_id)}/accounts${IG.qs({ view })}`), (d) => {
      const merged = { ...tr, ...(d.trigger || {}) };
      let rows = d.accounts || [];
      let counts = d.counts || null;
      if (!d.view) {
        // Older API without server-side views: derive the Act-now list client-side with the same rule.
        const all = rows.slice().sort((a, b) => tv(b) - tv(a));
        const act = actionableOf(all);
        counts = counts || { exposed: merged.exposed_count ?? all.length, funded_not_trading: merged.funded_not_trading ?? all.filter(isFNT).length, actionable: act.length };
        rows = view === "actionable" ? act : all;
      }
      rows.forEach((r, i) => { if (!IG.isNum(r.rank)) r.rank = i + 1; });
      drawExposure(host, merged, rows, counts || {});
    }, html`<div class="card">${IG.skeleton("table")}</div>`);
  }

  function drawExposure(host, tr, accounts, counts) {
    const hub = hubsData && (hubsData.hubs || []).find((h) => h.hub === tr.hub);
    const fc = hub && (hub.forecast || []).length ? (hub.forecast || []).reduce((a, b) => ((b.forecast_peak_lmp || 0) > (a.forecast_peak_lmp || 0) ? b : a)) : null;
    const ev = events.find((e) => e.event_id === eventOf(tr));
    // Banner numbers: the event (single source shared with CEO Weekly) when available, else this trigger.
    const exposed = ev ? ev.exposed : counts.exposed ?? tr.exposed_count;
    const fnt = ev ? ev.funded_not_trading : counts.funded_not_trading ?? tr.funded_not_trading;
    const actN = ev && IG.isNum(ev.actionable) ? ev.actionable : counts.actionable ?? tr.actionable_count;
    const atStake = ev && IG.isNum(ev.adv_at_stake) ? ev.adv_at_stake : tr.adv_at_stake;
    const nHurt = accounts.filter((a) => a.direction !== "opportunity").length;
    const nOpp = accounts.length - nHurt;
    const maxTv = Math.max(1e-9, ...accounts.map(tv));
    const rows = accounts.filter((a) => dirFilter === "all" || (dirFilter === "opportunity") === (a.direction === "opportunity"));
    const neg = tr.regime === "negative_price";
    const hrs = neg && IG.isNum(tr.neg_hours) ? `${IG.fmt.int(tr.neg_hours)} negative-price hours` : `${IG.fmt.int(tr.spike_hours)} spike hours`;
    const hubExposed = counts.exposed ?? tr.exposed_count;

    IG.setHTML(host, html`
      <div class="banner" role="status">
        <div class="big"><b>${IG.fmt.int(exposed)}</b> exposed<span class="sep">·</span><b>${IG.fmt.int(fnt)}</b> funded-not-trading<span class="sep">·</span><b>${IG.fmt.int(actN)}</b> to act on now${IG.isNum(atStake) ? html`<span class="sep">·</span>~<b>${IG.fmt.contracts(atStake)}</b> contracts/day ADV at stake` : ""}</div>
        <div class="ctx"><span class="chip trigger">${IG.icon("bolt")}${ev ? ev.event_id : tr.trigger_id}</span> ${ev ? `${ev.iso} event, ${(ev.hubs || []).length || 1} hub${(ev.hubs || []).length > 1 ? "s" : ""} (accounts counted once) · ` : ""}${tr.hub} ${IG.regimeLabel(tr.regime).toLowerCase()} on ${IG.fmt.date(tr.peak_ts || tr.start_ts)} · peak ${IG.fmt.price(tr.peak_lmp)}/MWh at ${IG.fmt.dateTime(tr.peak_ts).split(", ")[1] || ""}${IG.isNum(tr.peak_ratio) && !neg ? ` (×${tr.peak_ratio.toFixed(1)} the 30-day p99)` : ""} · ${hrs}${fc ? ` · next forecast peak ${IG.fmt.price(fc.forecast_peak_lmp)} on ${IG.fmt.date(fc.date)}` : ""}</div>
      </div>
      <div class="card flush">
        <div class="card-h">
          <div><h2>${ps.view === "actionable" ? "Act now" : "All exposed accounts"} — ${tr.hub}</h2>
            <div class="sub">${ps.view === "actionable"
              ? `Top funded-not-trading accounts plus the best signed / KYC-approved ones, ranked by touch value. Prospects (QUALIFIED/TARGET) excluded.`
              : `Every eligible account exposed to ${tr.iso}, own-hub matches first. Same spike, two directions: pain for hedgers short the peak, opportunity for those long it.`}</div></div>
          <div class="tools">
            <div class="seg-ctl" role="group" aria-label="List scope">
              <button type="button" data-view="actionable" aria-pressed="${ps.view === "actionable"}">Act now${IG.isNum(counts.actionable) ? " " + counts.actionable : ""}</button>
              <button type="button" data-view="all" aria-pressed="${ps.view === "all"}">Show all${IG.isNum(hubExposed) ? " " + IG.fmt.int(hubExposed) : ""}</button>
            </div>
            <div class="seg-ctl" role="group" aria-label="Direction filter">
              <button type="button" data-dir="all" aria-pressed="${dirFilter === "all"}">Both</button>
              <button type="button" data-dir="hurt" aria-pressed="${dirFilter === "hurt"}">▼ Hurt ${nHurt}</button>
              <button type="button" data-dir="opportunity" aria-pressed="${dirFilter === "opportunity"}">▲ Opp. ${nOpp}</button>
            </div>
          </div>
        </div>
        <div class="table-wrap">${rows.length ? html`<table class="t stackable" id="exp-table">
          <thead><tr><th class="num">#</th><th>Account</th><th>Segment · stage</th><th>Direction</th><th>Why exposed</th><th class="num" title="${IG.DEF.p_active}">P(active)</th><th class="num col-opt" title="${IG.DEF.exp_adv}">E[ADV]</th><th title="${IG.DEF.touch_value}">Touch value</th><th class="col-opt">Last touch</th><th><span class="sr-only">Action</span></th></tr></thead>
          <tbody>${rows.map((a) => expRow(a, tr, maxTv))}</tbody></table>` : IG.emptyState("No accounts in this view.", ps.view === "actionable" ? "Try “Show all”." : "")}</div>
      </div>`);
    IG.$$("[data-dir]", host).forEach((b) => b.addEventListener("click", () => { dirFilter = b.dataset.dir; drawExposure(host, tr, accounts, counts); }));
    IG.$$("[data-view]", host).forEach((b) => b.addEventListener("click", () => { if (ps.view !== b.dataset.view) { ps.view = b.dataset.view; loadExposure(tr); } }));
    IG.$$("[data-draft]", host).forEach((b) => b.addEventListener("click", () => {
      const a = accounts.find((x) => String(x.account_id) === b.dataset.draft);
      IG.openDraft({
        account_id: a.account_id, name: a.name, segment: a.segment, direction: a.direction, trigger_id: tr.trigger_id, kind: "volatility",
        onQueued: () => {
          a.last_touch_days = 0;
          IG.state.queued.add(String(a.account_id));
          if (host.isConnected) drawExposure(host, tr, accounts, counts);
        },
      });
    }));
  }

  function expRow(a, tr, maxTv) {
    const queued = IG.state.queued.has(String(a.account_id));
    const ownHub = a.hub || null;
    const isoLevel = a.hub_match === false;
    return html`<tr>
      <td data-l="#" class="num"><b>${a.rank ?? ""}</b></td>
      <td data-l="Account" style="min-width:180px;max-width:260px">${IG.acct(a.account_id, a.name)}
        ${a.account_fact ? html`<div class="muted clamp1" style="font-size:11px;margin-top:2px" title="Internal fact — not customer-facing">${a.account_fact}</div>` : ""}
        ${ownHub ? html`<div style="margin-top:3px"><span class="stage" title="${isoLevel ? `Settles at ${ownHub}; exposed via ${tr.iso} footprint (score × 0.6)` : `Settles at the trigger hub`}">${ownHub}</span>${isoLevel ? html` <span class="muted" style="font-size:10.5px">ISO-level</span>` : ""}</div>` : ""}</td>
      <td data-l="Segment">${IG.segTag(a.segment, null, true)}<div style="margin-top:3px" class="row">${IG.stagePill(a.stage)}${a.health_state ? IG.healthPill(a.health_state) : ""}</div></td>
      <td data-l="Direction">${IG.dirPill(a.direction)}</td>
      <td data-l="Why" style="min-width:200px;max-width:320px"><div class="clamp2" title="${a.exposure_line || ""}">${a.exposure_line || "—"}</div></td>
      <td data-l="P(active)" class="num">${IG.fmt.prob(a.p_active)}</td>
      <td data-l="E[ADV]" class="num col-opt">${IG.fmt.contracts(a.exp_adv)}</td>
      <td data-l="Touch value" title="Exposure ${IG.isNum(a.exposure_score) ? a.exposure_score.toFixed(0) : "—"}">${IG.bar(tv(a) / maxTv, IG.fmt.num(tv(a), 0), a.direction === "opportunity" ? "opp" : "hurt")}</td>
      <td data-l="Last touch" class="nowrap col-opt ${a.last_touch_days === 0 ? "" : "muted"}">${a.last_touch_days === 0 ? html`<span class="pill good"><span class="dot"></span>today</span>` : IG.fmt.relDays(a.last_touch_days)}</td>
      <td data-l="Action" class="nowrap">${a.suppressed
        ? html`<span class="pill ghost" title="${a.suppressed_reason || "Suppressed"}">Suppressed</span>`
        : queued
          ? html`<span class="pill good"><span class="dot"></span>Queued</span>`
          : html`<button type="button" class="btn sm" data-draft="${a.account_id}">${IG.icon("mail")}Draft</button>`}</td>
    </tr>`;
  }

  /* ---------------- history / lift */
  const evRow = (e) => html`<li>
          <span class="pill ${e.regime === "negative_price" ? "opp" : "hurt"}">${IG.regimeLabel(e.regime)}</span>
          <b>${e.hub}</b><span class="muted">${IG.fmt.date(e.start_ts, true)}</span><span class="mono muted" style="font-size:11px">${e.trigger_id}</span>
          <span><b>${IG.fmt.price(e.peak_lmp)}</b>/MWh</span></li>`;
  function drawHistory(el, d) {
    const lift = d.lift || {};
    const tr = lift.triggered || {}, un = lift.untriggered || {};
    const ev = (d.events || []).slice().sort((a, b) => String(b.start_ts).localeCompare(String(a.start_ts)));
    const mx = Math.max(0.01, tr.activated_14d_rate || 0, un.activated_14d_rate || 0);
    const lx = IG.isNum(lift.lift_x) ? lift.lift_x : tr.activated_14d_rate && un.activated_14d_rate ? tr.activated_14d_rate / un.activated_14d_rate : null;
    IG.setHTML(el, html`<div class="grid g-12">
      <div class="span-5">
        <div class="row" style="align-items:baseline;gap:10px;margin-bottom:10px"><span class="lift-x">${IG.fmt.mult(lx)}</span><span class="text-2">14-day first-trade lift from triggered outreach</span></div>
        <div class="lift">
          <span>Triggered</span>${IG.bar((tr.activated_14d_rate || 0) / mx, "", "accent")}<span class="num"><b>${IG.fmt.pct(tr.activated_14d_rate, 0)}</b> <span class="muted">n=${IG.fmt.int(tr.n)}</span></span>
          <span>Untriggered</span>${IG.bar((un.activated_14d_rate || 0) / mx, "", "grey")}<span class="num"><b>${IG.fmt.pct(un.activated_14d_rate, 0)}</b> <span class="muted">n=${IG.fmt.int(un.n)}</span></span>
        </div>
        <div class="footnote">Converted = first qualifying trade within 14 days of the event, among funded-not-trading accounts exposed to the event’s ISO. Not the same as Active (≥4 trading days in 30). Synthetic cohort — illustrative.</div>
      </div>
      <div class="span-7">
        ${ev.length ? html`<ul class="event-list">${ev.slice(0, 8).map(evRow)}</ul>
          ${ev.length > 8 ? html`<details class="more-kpis"><summary>Show ${ev.length - 8} older events</summary><ul class="event-list">${ev.slice(8).map(evRow)}</ul></details>` : ""}` : IG.emptyState("No past events recorded.")}
      </div></div>`);
  }

  // kick off: triggers and hubs share one cached request; hubs pick their default hub from triggers
  const trigP = IG.api("/pulse/triggers").then((d) => { triggers = d.triggers || []; }).catch(() => {});
  // /pulse/events exists only on APIs that also tag triggers with event_id; don't probe older ones (avoids a 404).
  const evP = trigP.then(() => (triggers.some((t) => t.event_id) ? IG.api("/pulse/events") : []))
    .then((d) => { events = Array.isArray(d) ? d : (d && d.events) || []; }).catch(() => { events = []; });
  IG.load(IG.$("#trig-list"), () => IG.api("/pulse/triggers"), async (d) => {
    triggers = d.triggers || [];
    await evP;
    drawTriggerList();
    if (ps.trigger) {
      const again = triggers.find((x) => x.trigger_id === ps.trigger.trigger_id);
      if (again) selectTrigger(again);
    }
  }, "table");
  trigP.finally(loadHubs);
  if (!ps.trigger) IG.setHTML(IG.$("#exposure"), html`<div class="card hint-card"><div class="state" style="min-height:0;padding:18px">${IG.icon("play", "hint-ico")}<div><b>Press Replay</b> to watch the week unfold, or pick a trigger to see who is exposed.</div></div></div>`);
  IG.load(IG.$("#pulse-hist"), () => IG.api("/pulse/history"), (d) => drawHistory(IG.$("#pulse-hist"), d), "lines");
};

function sevNum(t) {
  const s = t.severity;
  if (IG.isNum(s)) return s;
  return { low: 1, medium: 2, moderate: 2, high: 3, severe: 4, critical: 4, extreme: 4 }[String(s).toLowerCase()] || 0;
}
function sevLevel(s) {
  if (IG.isNum(s)) {
    if (s > 10) return Math.max(1, Math.min(4, Math.ceil(s / 25))); // 0–100 (contract notes §6)
    if (s <= 1) return Math.max(1, Math.ceil(s * 4));
    if (s <= 4) return Math.max(1, Math.round(s));
    if (s <= 5) return Math.max(1, Math.ceil(s * 0.8));
    if (s <= 10) return Math.max(1, Math.ceil(s / 2.5));
    return 4;
  }
  return { low: 1, medium: 2, moderate: 2, high: 3, severe: 4, critical: 4, extreme: 4 }[String(s).toLowerCase()] || 2;
}

/** Touch value (X7); falls back to exposure × P × E[ADV] on older APIs. */
function tv(a) {
  if (IG.isNum(a.touch_value)) return a.touch_value;
  return (a.p_active || 0) * (a.exp_adv || 0) * ((a.exposure_score || 50) / 100);
}
const FNT_STAGES = new Set(["FUNDED", "FIRST_TRADE", "AT_RISK"]);
function isFNT(a) {
  return FNT_STAGES.has(a.stage) || ["not_started", "ramping", "at_risk"].includes(a.health_state) && a.stage === "FUNDED";
}
/** X7 rule: top 15 funded-not-trading + top 5 SIGNED/KYC_APPROVED by touch value; QUALIFIED/TARGET excluded. */
function actionableOf(sorted) {
  const fnt = sorted.filter(isFNT).slice(0, 15);
  const pre = sorted.filter((a) => a.stage === "SIGNED" || a.stage === "KYC_APPROVED").slice(0, 5);
  return fnt.concat(pre).sort((a, b) => tv(b) - tv(a));
}
