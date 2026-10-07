/*
 * View 4 — Funnel & Journey. "Which onboarding step leaks, what does it cost, what should we build?"
 * Consumes: GET /api/funnel?segment=&iso=, GET /api/funnel/friction/{index}.md (export).
 */
"use strict";

IG.views = IG.views || {};
IG.state.funnel = IG.state.funnel || { segment: "", iso: "" };

IG.views.funnel = function renderFunnel(main) {
  const { html } = IG;
  const meta = IG.state.meta || {};
  const st = IG.state.funnel;
  IG.setHTML(main, html`
    <div class="view-head">
      <div class="q">Which onboarding step leaks, for whom, and what is it worth? Each friction flag becomes a priced roadmap ticket.</div>
    </div>
    <form class="filters" onsubmit="return false" aria-label="Funnel filters">
      <div class="field"><label for="fn-seg">Segment</label><select id="fn-seg"><option value="">All segments</option>${(meta.segments || []).map((s) => html`<option value="${s.code}" ${s.code === st.segment ? "selected" : ""}>${s.label}</option>`)}</select></div>
      <div class="field"><label for="fn-iso">ISO</label><select id="fn-iso"><option value="">All ISOs</option>${Object.keys(meta.isos || {}).map((i) => html`<option ${i === st.iso ? "selected" : ""}>${i}</option>`)}</select></div>
      <span class="muted" style="margin-left:auto;font-size:11.5px" title="${IG.DEF.active}">Funnel starts at contract signed · Active = ≥4 trading days in trailing 30</span>
    </form>
    <div id="fn-body"></div>`);
  IG.$("#fn-seg").addEventListener("change", (e) => { st.segment = e.target.value; load(); });
  IG.$("#fn-iso").addEventListener("change", (e) => { st.iso = e.target.value; load(); });

  // Friction export indexes refer to the unfiltered list served by /funnel/friction/{index}.md.
  const unfiltered = IG.api("/funnel").catch(() => null);
  function load() {
    const body = IG.$("#fn-body");
    IG.load(body, () => IG.api(`/funnel${IG.qs({ segment: st.segment, iso: st.iso })}`), async (d) => {
      const base = await unfiltered;
      drawFunnel(body, d, base);
    }, html`<div class="grid g-12"><div class="card span-8">${IG.skeleton("table")}</div><div class="card span-4">${IG.skeleton("lines")}</div></div>`);
  }
  load();
};

const STEP_LABEL = {};
IG.stepLabel = (k) => STEP_LABEL[k] || IG.fmt.humanize(String(k || "").replace(/_/g, " ")).replace(/\bKyc\b/g, "KYC");

function drawFunnel(body, d, base) {
  const { html, fmt } = IG;
  const steps = d.steps || [];
  steps.forEach((s) => { if (s.label) STEP_LABEL[s.step] = String(s.label).replace(/\s*\(.*\)\s*$/, "").replace(/^'|'$/g, ""); });
  const states = d.states || {};
  const friction = (d.friction || []).slice();
  const n0 = steps.length ? steps[0].n || 0 : 0;
  // worst two conversion steps get flagged visually
  const convs = steps.filter((s) => IG.isNum(s.conv_from_prev)).map((s) => s.conv_from_prev).sort((a, b) => a - b);
  const lowCut = convs.length > 2 ? convs[1] : -1;
  const stKeys = ["not_started", "ramping", "active", "at_risk", "dormant"].filter((k) => IG.isNum(states[k]));
  const stTot = stKeys.reduce((t, k) => t + (states[k] || 0), 0);
  const baseFr = (base && base.friction) || friction;
  const idxOf = (f) => {
    const i = baseFr.findIndex((b) => b.step === f.step && b.segment === f.segment && b.metric === f.metric);
    return i >= 0 ? i : null;
  };
  const sevRank = (s) => (IG.isNum(s) ? s : { critical: 4, high: 3, medium: 2, low: 1 }[String(s).toLowerCase()] || 0);
  friction.sort((a, b) => (b.adv_at_stake || 0) - (a.adv_at_stake || 0) || sevRank(b.severity) - sevRank(a.severity));

  IG.setHTML(body, html`
    <div class="grid g-12">
      <section class="card span-8" aria-labelledby="fn-t">
        <div class="card-h"><div><h2 id="fn-t">Onboarding funnel</h2><div class="sub">Accounts reaching each step · conversion from previous step · median and P75 days from previous step${steps.some((x) => IG.isNum(x.n_mature)) ? " · conversion on mature cohorts only" : ""}</div></div></div>
        ${steps.length ? html`<div class="funnel" role="table" aria-label="Funnel steps">
          <div class="f-row head" role="row"><span role="columnheader">Step</span><span role="columnheader">Accounts</span><span class="num" role="columnheader">Conv.</span><span class="num" role="columnheader">Median d</span><span class="num" role="columnheader">P75 d</span></div>
          ${steps.map((s) => {
            const low = IG.isNum(s.conv_from_prev) && s.conv_from_prev <= lowCut;
            const w = n0 ? (s.n || 0) / n0 : 0;
            return html`<div class="f-row" role="row">
              <span role="cell" title="${IG.isNum(s.n_mature) ? `${fmt.int(s.n_mature)} mature accounts behind this step’s conversion` : s.step}">${IG.stepLabel(s.step)}${IG.isNum(s.n_mature) ? html` <span class="muted" style="font-size:10.5px">n=${fmt.int(s.n_mature)}</span>` : ""}</span>
              <span role="cell" class="f-bar"><b style="width:${(w * 100).toFixed(1)}%"></b><span>${fmt.int(s.n)}</span></span>
              <span role="cell" class="num conv ${low ? "low" : ""}">${IG.isNum(s.conv_from_prev) ? fmt.pct(s.conv_from_prev) : "—"}${low ? " ▼" : ""}</span>
              <span role="cell" class="num">${fmt.days(s.median_days_from_prev)}</span>
              <span role="cell" class="num muted">${fmt.days(s.p75_days)}</span></div>`;
          })}</div>
          <div class="footnote">▼ marks the two leakiest steps.${steps.some((x) => IG.isNum(x.n_mature)) ? " Conversion uses mature cohorts (old enough to have completed the step: p75 dwell + 30 d, or signed ≥90 d ago), so recent signings don’t read as leaks; n = mature accounts." : ""} ${n0 ? `End-to-end signed → ${IG.stepLabel(steps[steps.length - 1].step)}: ${fmt.pct((steps[steps.length - 1].n || 0) / n0)}.` : ""}</div>`
          : IG.emptyState("No funnel data for this filter.")}
      </section>
      <section class="card span-4" aria-labelledby="fst-t">
        <div class="card-h"><div><h2 id="fst-t" title="${IG.DEF.active}">Funded account health</h2><div class="sub">Off-path states the linear funnel hides</div></div></div>
        <div class="states" style="grid-template-columns:repeat(${Math.min(stKeys.length || 3, 3)}, 1fr)">
          ${stKeys.map((k) => { const h = IG.healthInfo(k); return html`
            <div class="mini" title="${h.def}"><div class="l">${IG.healthPill(k)}</div>
            <div class="v" style="margin-top:6px">${fmt.int(states[k])}</div><div class="muted" style="font-size:11px">${stTot ? fmt.pct((states[k] || 0) / stTot, 0) + " of funded" : ""}</div></div>`; })}
        </div>
        ${stTot ? html`<div style="display:flex;height:10px;border-radius:3px;overflow:hidden;margin-top:12px;gap:2px" aria-hidden="true">
          ${stKeys.map((k) => html`<span style="flex:${states[k] || 0};background:${STATE_COLOR[k] || "var(--muted)"}"></span>`)}</div>` : ""}
        <p class="text-2" style="font-size:12.5px;margin:12px 0 0">${stTot ? `${fmt.pct((states.active || 0) / stTot, 0)} of funded accounts are Active — the board’s “vast majority actively trading” number. Target ≥70%.` : ""}</p>
      </section>

      <section class="card span-12" aria-labelledby="hm-t">
        <div class="card-h"><div><h2 id="hm-t">Step conversion by segment</h2><div class="sub">Conversion from the previous step. Red cells sit below the all-segment rate — the deeper the red, the bigger the leak. Hover for the gap and median days.</div></div>
          <div class="tools heat-scale"><span>at/above all</span><span class="ramp" style="background:linear-gradient(90deg, var(--surface-2), var(--hurt))"></span><span>−30 pp</span></div></div>
        <div class="table-wrap" id="fn-heat"></div>
      </section>

      <section class="span-12" aria-labelledby="fr-t">
        <div class="view-head" style="margin:4px 0 10px"><h2 id="fr-t" style="font-size:15px">Friction flags → roadmap asks</h2><span class="muted">ranked by ADV at stake</span></div>
        ${friction.length ? html`<div class="friction-grid">${friction.slice(0, 6).map((f) => frictionCard(f, idxOf(f)))}</div>
          ${friction.length > 6 ? html`<details class="more-kpis"><summary>Show ${friction.length - 6} more</summary><div class="friction-grid" style="margin-top:10px">${friction.slice(6).map((f) => frictionCard(f, idxOf(f)))}</div></details>` : ""}`
          : html`<div class="card">${IG.emptyState("No friction flags for this filter.", "Every step is within its benchmark.")}</div>`}
      </section>
    </div>`);

  drawHeat(IG.$("#fn-heat"), d.by_segment || [], steps);
  IG.$$("[data-ticket]", body).forEach((b) => b.addEventListener("click", (e) => {
    const i = b.dataset.ticket;
    IG.download(`/funnel/friction/${i}.md`, `ignition-roadmap-ticket-${Number(i) + 1}.md`, e.currentTarget);
  }));
}

const STATE_COLOR = { not_started: "var(--warn)", ramping: "var(--accent-line)", active: "var(--good)", at_risk: "var(--serious)", dormant: "var(--crit)" };

function fmtMetric(metric, v) {
  const m = String(metric || "").toLowerCase();
  if (!IG.isNum(v)) return "—";
  if (/day|dwell|time/.test(m)) return IG.fmt.days(v);
  if (/per_account|requests|count/.test(m)) return IG.fmt.num(v, 2);
  if (/rate|conv|pct|share|ratio/.test(m) || (v >= 0 && v <= 1 && !Number.isInteger(v))) return IG.fmt.pct(v, 0);
  return IG.fmt.num(v, 1);
}

function frictionCard(f, idx) {
  const { html, fmt } = IG;
  const sev = String(f.severity || "").toLowerCase();
  const cls = /crit|high/.test(sev) || (IG.isNum(f.severity) && f.severity >= 0.7) ? "crit" : /med/.test(sev) || (IG.isNum(f.severity) && f.severity >= 0.4) ? "warn" : "";
  const seg = IG.segInfo(f.segment);
  return html`<article class="card friction">
    <div class="f-top"><span class="pill ${cls}"><span class="dot"></span>${IG.isNum(f.severity) ? "Severity " + f.severity.toFixed(2) : fmt.humanize(f.severity || "flag")}</span>${IG.segTag(f.segment)}</div>
    <h3>${seg.label}: leak at ${f.from_step ? `${IG.stepLabel(f.from_step)} → ` : ""}${f.step_label || IG.stepLabel(f.step)}</h3>
    <div class="metric">
      <div><div class="muted" style="font-size:11px">${f.metric_label ? f.metric_label.charAt(0).toUpperCase() + f.metric_label.slice(1) : fmt.humanize(f.metric)}</div><div class="v" style="color:var(--crit-text)">${fmtMetric(f.metric, f.value)}</div></div>
      <div><div class="muted" style="font-size:11px">Benchmark</div><div class="v" style="font-size:16px;color:var(--text-2)">${fmtMetric(f.metric, f.benchmark)}</div></div>
    </div>
    <div class="stat-row"><span>Accounts affected <b>${fmt.int(f.accounts_affected)}</b></span><span title="${IG.DEF.adv_at_stake}">ADV at stake <b>~${fmt.contracts(f.adv_at_stake)}</b>/day</span></div>
    <div class="ask"><span class="muted" style="font-size:11px;display:block">Roadmap ask</span>${f.roadmap_ask || "—"}</div>
    <div class="foot">${idx != null ? html`<button type="button" class="btn sm" data-ticket="${idx}">${IG.icon("download")}Export ticket (.md)</button>` : html`<span class="muted">Export unavailable for this filter</span>`}</div>
  </article>`;
}

function drawHeat(el, bySeg, steps) {
  const { html, fmt } = IG;
  if (!bySeg.length) { IG.setHTML(el, IG.emptyState("No segment breakdown.")); return; }
  const stepKeys = (steps.length ? steps.map((s) => s.step) : (bySeg[0].steps || []).map((s) => s.step)).slice(1);
  const labelOf = (k) => IG.stepLabel(k);
  const overall = new Map(steps.map((s) => [s.step, s.conv_from_prev]));
  const hurt = IG.css("--hurt");
  // Diverging-from-benchmark: cells at/above the all-segment rate stay neutral; leaks shade toward red by gap size.
  IG.setHTML(el, html`<table class="heat">
    <thead><tr><th class="rowh">Segment</th>${stepKeys.map((k) => html`<th title="${k}">${labelOf(k).replace(/^(.{12}).+$/, "$1…")}</th>`)}</tr>
      <tr><th class="rowh muted" style="font-weight:500">All segments</th>${stepKeys.map((k) => html`<th class="muted" style="font-weight:500">${IG.isNum(overall.get(k)) ? fmt.pct(overall.get(k), 0) : "—"}</th>`)}</tr></thead>
    <tbody>${bySeg.map((r) => {
      const m = new Map((r.steps || []).map((s) => [s.step, s]));
      return html`<tr><th class="rowh" scope="row" style="text-align:left">${IG.segTag(r.segment)}</th>${stepKeys.map((k) => {
        const c = m.get(k);
        if (!c || !IG.isNum(c.conv_from_prev)) return html`<td class="na">—</td>`;
        const v = c.conv_from_prev;
        const base = overall.get(k);
        const gap = IG.isNum(base) ? base - v : 0; // positive = leak
        const a = gap > 0.03 ? Math.min(0.85, 0.15 + (gap / 0.3) * 0.7) : 0;
        const style = a ? `background:${IG.alpha(hurt, a.toFixed(3))};${a > 0.5 ? "color:#fff;" : ""}` : "background:var(--surface-2);color:var(--text-2)";
        return html`<td style="${style}" title="${IG.segLabel(r.segment)} · ${labelOf(k)}: ${fmt.pct(v)} conversion${IG.isNum(base) ? ` (${fmt.pp(v - base)} vs all)` : ""} · median ${fmt.days(c.median_days)}">${fmt.pct(v, 0)}</td>`;
      })}</tr>`;
    })}</tbody></table>`);
}
