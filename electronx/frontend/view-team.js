/*
 * View 5 — Team & Comp. "Does comp pay for volume or for signatures?"
 * Consumes: GET /api/team/scorecards, GET /api/team/comp-plans, POST /api/team/comp-sim {plan_id, params}.
 */
"use strict";

IG.views = IG.views || {};
IG.state.comp = IG.state.comp || { plan_id: null, params: null };

IG.views.team = function renderTeam(main) {
  const { html } = IG;
  IG.setHTML(main, html`
    <div class="view-head"><div class="q">Are reps paid for signatures, or for accounts that become liquidity? Scorecard on the same Active definition the board sees, plus a plan simulator on the same book.</div></div>
    <section class="card flush" aria-labelledby="sc-t">
      <div class="card-h"><div><h2 id="sc-t">AE scorecard</h2><div class="sub">Composite = 25% funded vs quota · 25% activation · 20% book ADV · 10% speed · 10% pipeline · 10% SLA</div></div></div>
      <div class="table-wrap" id="sc-table"></div>
    </section>
    <section class="card mt" aria-labelledby="cs-t">
      <div class="card-h"><div><h2 id="cs-t">Comp plan simulator</h2><div class="sub">Same synthetic book, three plan designs — what each costs and what behavior it buys</div></div>
        <div class="tools" id="cs-plans"></div></div>
      <div id="cs-body"></div>
    </section>`);

  IG.load(IG.$("#sc-table"), () => IG.api("/team/scorecards"), (d) => drawScorecards(IG.$("#sc-table"), d.reps || []), "table");
  IG.load(IG.$("#cs-body"), () => IG.api("/team/comp-plans"), (d) => initSim(d.plans || []), html`<div class="grid g-12"><div class="span-4">${IG.skeleton("table")}</div><div class="span-8">${IG.skeleton()}</div></div>`);
};

function drawScorecards(el, reps) {
  const { html, fmt } = IG;
  if (!reps.length) { IG.setHTML(el, IG.emptyState("No reps with a book.")); return; }
  const rows = reps.slice().sort((a, b) => (b.score || 0) - (a.score || 0));
  const score100 = (s) => (IG.isNum(s) ? (s <= 1.5 ? s * 100 : s) : null);
  const attCls = (a) => (a >= 1 ? "good" : a >= 0.8 ? "warn" : "crit");
  const maxAdv = Math.max(1, ...rows.map((r) => r.book_adv || 0));
  IG.setHTML(el, html`<table class="t stackable">
    <thead><tr><th class="num">#</th><th>Rep</th><th>Funded YTD vs quota</th><th class="num" title="${IG.DEF.active}">Activation rate</th><th>Book ADV</th>
      <th class="num" title="Median days from signature to first qualifying trade">Days sign→trade</th><th class="num">Pipeline cov.</th><th class="num">SLA adherence</th><th>Composite score</th></tr></thead>
    <tbody>${rows.map((r, i) => {
      const att = IG.isNum(r.attainment) ? r.attainment : r.quota_ytd ? r.funded_ytd / r.quota_ytd : null;
      const s = score100(r.score);
      const comp = Object.entries(r.components || {}).map(([k, v]) => `${IG.fmt.humanize(k)}: ${IG.isNum(v) ? v.toFixed(1) : v}`).join(" · ");
      return html`<tr>
        <td data-l="#" class="num">${i + 1}</td>
        <td data-l="Rep"><b>${r.name}</b> <span class="stage">${r.role || ""}</span></td>
        <td data-l="Funded vs quota" style="min-width:160px">${IG.bar(Math.min(att || 0, 1.5) / 1.5, `${fmt.int(r.funded_ytd)}/${fmt.int(r.quota_ytd)} · ${fmt.pct(att, 0)}`, attCls(att || 0))}</td>
        <td data-l="Activation" class="num">${fmt.pct(r.activation_rate, 0)}</td>
        <td data-l="Book ADV" style="min-width:120px">${IG.bar((r.book_adv || 0) / maxAdv, fmt.contracts(r.book_adv))}</td>
        <td data-l="Days sign→trade" class="num ${(r.median_days_sign_to_trade || 0) > 30 ? "" : ""}">${fmt.days(r.median_days_sign_to_trade)}</td>
        <td data-l="Pipeline" class="num ${(r.pipeline_coverage || 0) < 3 ? "" : ""}">${fmt.mult(r.pipeline_coverage)}</td>
        <td data-l="SLA" class="num" style="${(r.sla_adherence || 1) < 0.85 ? "color:var(--crit-text)" : ""}">${fmt.pct(r.sla_adherence, 0)}</td>
        <td data-l="Score" style="min-width:120px" title="${comp}">${IG.bar((s || 0) / 100, s != null ? s.toFixed(0) : "—", "accent")}</td>
      </tr>`;
    })}</tbody></table>`);
}

/* ---------------------------------------------------------------- simulator */
const planId = (p) => p.plan_id ?? p.id ?? p.key ?? p.name;
const planName = (p) => p.name || p.label || IG.fmt.humanize(planId(p));
const PARAMS = [
  { key: "per_account_unit", label: "Per-account unit", unit: "$", step: 100 },
  { key: "multipliers.signed", label: "M at signature", unit: "×", step: 0.05 },
  { key: "multipliers.funded", label: "M at funding", unit: "×", step: 0.05 },
  { key: "multipliers.active_60d", label: "M at Active ≤60d", unit: "×", step: 0.05 },
  { key: "multipliers.active_21d_bonus", label: "Bonus if Active ≤21d", unit: "×", step: 0.05 },
  { key: "adv_kicker_per_1k", label: "ADV kicker / 1k contracts", unit: "$", step: 5 },
  { key: "adv_kicker_cap", label: "Kicker cap / account", unit: "$", step: 500 },
  { key: "adv_kicker_accel", label: "Kicker accel. >volume target", unit: "×", step: 0.1 },
  { key: "accelerator", label: "Accelerator >100%", unit: "×", step: 0.1 },
  { key: "clawback_pct", label: "Clawback", unit: "%", step: 5 },
  { key: "clawback_days", label: "Clawback window", unit: "days", step: 5 },
  { key: "lp_kicker_credit", label: "LP kicker credit", unit: "%", step: 5 },
];
const getP = (o, k) => k.split(".").reduce((x, p) => (x == null ? undefined : x[p]), o);
const setP = (o, k, v) => { const parts = k.split("."); let x = o; parts.slice(0, -1).forEach((p) => { x[p] = x[p] && typeof x[p] === "object" ? x[p] : {}; x = x[p]; }); x[parts[parts.length - 1]] = v; };

function initSim(plans) {
  const { html } = IG;
  const cs = IG.state.comp;
  const body = IG.$("#cs-body");
  if (!plans.length) { IG.setHTML(body, IG.emptyState("No comp plans configured.", "Sales owns ignition/content/comp_plans.json.")); return; }
  if (!cs.plan_id || !plans.some((p) => planId(p) === cs.plan_id)) {
    cs.plan_id = planId(plans.find((p) => /activation/.test(planId(p))) || plans[plans.length - 1]);
    cs.params = null;
  }
  const planFor = () => plans.find((p) => planId(p) === cs.plan_id);
  if (!cs.params) cs.params = JSON.parse(JSON.stringify(planFor()));

  IG.setHTML(IG.$("#cs-plans"), html`<div class="seg-ctl" role="radiogroup" aria-label="Comp plan">${plans.map((p) => html`<button type="button" role="radio" aria-checked="${planId(p) === cs.plan_id}" aria-pressed="${planId(p) === cs.plan_id}" data-plan="${planId(p)}">${planName(p)}</button>`)}</div>`);
  IG.$$("[data-plan]").forEach((b) => b.addEventListener("click", () => {
    cs.plan_id = b.dataset.plan;
    cs.params = JSON.parse(JSON.stringify(planFor()));
    IG.$$("[data-plan]").forEach((x) => { const on = x === b; x.setAttribute("aria-pressed", String(on)); x.setAttribute("aria-checked", String(on)); });
    drawForm();
    run();
  }));

  IG.setHTML(body, html`<div class="grid g-12">
    <div class="span-4"><div id="cs-form"></div></div>
    <div class="span-8"><div id="cs-out"></div></div>
  </div>
  <div class="mt" id="cs-compare"></div>`);

  function drawForm() {
    const p = cs.params;
    const shown = PARAMS.filter((d) => getP(p, d.key) !== undefined);
    IG.setHTML(IG.$("#cs-form"), html`
      <div class="plan-card" style="margin-bottom:10px">
        <div class="eyebrow">Behavior it rewards</div>
        <div style="font-weight:600;font-size:13.5px">${p.behavior || "—"}</div>
        <div class="muted" style="font-size:11.5px;margin-top:4px">OTE ${IG.fmt.usd(p.ote)} · base ${IG.fmt.usd(p.base)} · variable ${IG.fmt.usd(p.variable)} · quota ${IG.fmt.int(p.quota_funded_annual)} funded/yr</div>
        ${p.formula ? html`<details style="margin-top:6px"><summary class="muted" style="cursor:pointer;font-size:11.5px">How payout is computed</summary><p class="text-2" style="font-size:11.5px;margin:6px 0 0;line-height:1.5">${p.formula}</p></details>` : ""}
      </div>
      <form class="param-grid" id="cs-params" onsubmit="return false" aria-label="Plan parameters">
        ${shown.map((d) => {
          let v = getP(p, d.key);
          if (d.unit === "%") v = IG.isNum(v) ? +(v <= 1 ? v * 100 : v).toFixed(1) : v;
          return html`<div class="field"><label for="pp-${d.key}">${d.label} <span class="muted">(${d.unit})</span></label>
            <input type="number" id="pp-${d.key}" data-param="${d.key}" data-unit="${d.unit}" value="${v}" step="${d.step}" min="0" inputmode="decimal" /></div>`;
        })}
      </form>
      <div class="row mt"><button type="button" class="btn primary" id="cs-run">Run simulation</button><button type="button" class="btn ghost" id="cs-reset">Reset to plan</button></div>`);
    IG.$$("[data-param]").forEach((inp) => inp.addEventListener("input", () => {
      let v = parseFloat(inp.value);
      if (!Number.isFinite(v)) return;
      if (inp.dataset.unit === "%") v = v / 100;
      setP(cs.params, inp.dataset.param, v);
      clearTimeout(drawForm.t);
      drawForm.t = setTimeout(run, 450);
    }));
    IG.$("#cs-run").addEventListener("click", run);
    IG.$("#cs-reset").addEventListener("click", () => { cs.params = JSON.parse(JSON.stringify(planFor())); drawForm(); run(); });
  }

  function run() {
    const p = cs.params;
    const params = {};
    PARAMS.forEach((d) => { const v = getP(p, d.key); if (v !== undefined) setP(params, d.key, v); });
    const out = IG.$("#cs-out");
    IG.load(out, () => IG.api("/team/comp-sim", { method: "POST", body: { plan_id: cs.plan_id, params } }), (r) => drawSim(r, plans), "chart");
  }
  drawForm();
  run();
}

function drawSim(r, plans) {
  const { html, fmt } = IG;
  const out = IG.$("#cs-out");
  const reps = r.reps || [];
  const tot = r.totals || {};
  const keys = [];
  reps.forEach((rep) => Object.entries(rep.payout_breakdown || {}).forEach(([k, v]) => { if (IG.isNum(v) && !keys.includes(k)) keys.push(k); }));
  const t = IG.theme();
  const neg = (k) => /claw|penalt|deduct/i.test(k) || reps.every((rep) => ((rep.payout_breakdown || {})[k] || 0) <= 0);
  let pi = 0;
  const colors = keys.map((k) => (neg(k) ? t.crit : pi < 4 ? t.ord[pi++] : t.cat[(pi++ % 8)]));

  IG.setHTML(out, html`
    <div class="kpis" style="grid-template-columns:repeat(3,minmax(0,1fr))">
      <article class="kpi compact"><div class="kpi-label">Variable cost (team)</div><div class="kpi-value">${fmt.usd(tot.variable_cost)}</div><div class="kpi-meta">annualized, this book</div></article>
      <article class="kpi compact"><div class="kpi-label" title="${IG.DEF.active}">Cost per Active account</div><div class="kpi-value">${fmt.usd(tot.per_active_account)}</div><div class="kpi-meta">what we pay for liquidity</div></article>
      <article class="kpi compact"><div class="kpi-label">Cost per 1k contracts</div><div class="kpi-value">${fmt.usd(tot.per_1k_contracts)}</div><div class="kpi-meta">variable comp ÷ volume</div></article>
    </div>
    <div class="mt">
      <div class="eyebrow">Per-rep variable payout${r.plan && (r.plan.name || r.plan.plan_id) ? " — " + (r.plan.name || IG.fmt.humanize(r.plan.plan_id)) : ""}</div>
      ${keys.length ? IG.legend(keys.map((k, i) => ({ label: fmt.humanize(k), color: colors[i] }))) : ""}
      <div class="chart-box">${reps.length ? html`<canvas id="cs-chart" role="img" aria-label="Variable payout per rep by component"></canvas>` : IG.emptyState("No reps in simulation.")}</div>
    </div>`);

  if (reps.length) {
    const labels = reps.map((x) => x.name);
    const datasets = keys.length
      ? keys.map((k, i) => ({ label: fmt.humanize(k), data: reps.map((x) => (x.payout_breakdown || {})[k] ?? 0), backgroundColor: colors[i], maxBarThickness: 24, stack: "p", borderSkipped: false, borderRadius: 2 }))
      : [{ label: "Variable payout", data: reps.map((x) => x.payout_variable), backgroundColor: t.series, maxBarThickness: 24 }];
    IG.chart(IG.$("#cs-chart"), {
      type: "bar",
      data: { labels, datasets },
      options: IG.baseOptions({
        indexAxis: "y",
        interaction: { mode: "index", axis: "y", intersect: false },
        scales: { x: IG.axis({ stacked: true, fmt: (v) => fmt.usd(v), maxTicks: 6 }), y: IG.axis({ stacked: true, grid: false }) },
        plugins: { tooltip: { callbacks: {
          label: (c) => ` ${c.dataset.label}: ${fmt.usdFull(c.parsed.x)}`,
          footer: (items) => `Total variable: ${fmt.usdFull((reps[items[0].dataIndex] || {}).payout_variable)}`,
        } } },
      }),
    });
  }

  // plan comparison
  const cmp = r.comparison || [];
  const nameOf = (id) => { const p = plans.find((x) => planId(x) === id); return p ? planName(p) : IG.fmt.humanize(id); };
  const best = cmp.length ? cmp.reduce((a, b) => ((b.per_active_account ?? Infinity) < (a.per_active_account ?? Infinity) ? b : a)) : null;
  const cur = IG.state.comp.plan_id;
  IG.setHTML(IG.$("#cs-compare"), cmp.length ? html`<div class="eyebrow">Plan comparison on the same book</div>
    <div class="table-wrap"><table class="t stackable">
      <thead><tr><th>Plan</th><th class="num">Variable cost</th><th class="num">Per Active account</th><th class="num">Per 1k contracts</th><th>Behavior it rewards</th></tr></thead>
      <tbody>${cmp.map((c) => html`<tr class="${c.plan_id === cur ? "current-plan" : ""}">
        <td data-l="Plan"><b>${nameOf(c.plan_id)}</b> ${c.plan_id === cur ? html`<span class="pill ghost">simulating</span>` : ""} ${best && c.plan_id === best.plan_id ? html`<span class="pill good"><span class="dot"></span>Lowest cost per Active</span>` : ""}</td>
        <td data-l="Variable cost" class="num">${fmt.usd(c.variable_cost)}</td>
        <td data-l="Per Active" class="num"><b>${fmt.usd(c.per_active_account)}</b></td>
        <td data-l="Per 1k" class="num">${fmt.usd(c.per_1k_contracts)}</td>
        <td data-l="Behavior" class="text-2">${c.behavior || "—"}</td></tr>`)}</tbody></table></div>` : "");
}
