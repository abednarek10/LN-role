/*
 * View 3 — Activation Queue (+ Model sub-panel). "Who do I touch next, with what?"
 * Consumes: GET /api/activation/queue?view=today|all&limit=&segment=&iso=&rep_id=&stage=, GET /api/scoring/model.
 */
"use strict";

IG.views = IG.views || {};

IG.views.queue = function renderQueue(main, sub) {
  const { html } = IG;
  const meta = IG.state.meta || {};
  const qs = IG.state.queue;
  const tab = sub === "model" ? "model" : "queue";
  const f = qs.filters;
  if (!qs.view) qs.view = "today";
  const reps = (meta.reps || []).filter((r) => !r.role || /AE|STRATEGIC/i.test(r.role));
  const stages = meta.stages || [];

  IG.setHTML(main, html`
    <div class="view-head">
      <div class="q">Who should each rep touch next, why now, and with what? Ranked by expected value of the touch — not raw propensity.</div>
      <div class="actions">
        <div class="seg-ctl" role="tablist" aria-label="Queue or model">
          <button type="button" role="tab" aria-selected="${tab === "queue"}" data-tab="queue">Ranked queue</button>
          <button type="button" role="tab" aria-selected="${tab === "model"}" data-tab="model">Model</button>
        </div>
      </div>
    </div>
    <div id="q-body"></div>`);
  IG.$$("[data-tab]", main).forEach((b) => b.addEventListener("click", () => { location.hash = b.dataset.tab === "model" ? "#/queue/model" : "#/queue"; }));

  const body = IG.$("#q-body");
  if (tab === "model") { renderModel(body); return; }

  IG.setHTML(body, html`
    <form class="filters" id="q-filters" aria-label="Queue filters" onsubmit="return false">
      ${sel("segment", "Segment", (meta.segments || []).map((s) => [s.code, s.label]), f.segment)}
      ${sel("iso", "ISO", Object.keys(meta.isos || {}).map((i) => [i, i]), f.iso)}
      ${sel("rep_id", "Rep", reps.map((r) => [r.id, r.name]), f.rep_id)}
      ${sel("stage", "Stage", stages.map((s) => [s, s.replace(/_/g, " ")]), f.stage)}
      <button type="button" class="btn ghost" id="q-reset">Reset</button>
      <span class="muted" style="margin-left:auto;font-size:11.5px" title="${IG.DEF.priority}">Priority = P(Active≤60d) × E[ADV] × k<sub>stage</sub> × U × B</span>
    </form>
    <div id="q-banner"></div>
    <div id="q-summary"></div>
    <section class="card flush mt" aria-labelledby="q-t">
      <div class="card-h"><div><h2 id="q-t">${qs.view === "today" ? "Today — per-rep lists" : "Full ranked queue"}</h2><div class="sub" id="q-sub">${qs.view === "today"
        ? "Capped per owner (AE/Strategic 12, RevOps 15, Head of GTM 5), at least half hedger slots while hedgers are below 50% of Active. SLA clocks run only on listed items."
        : "Every open account ranked by expected value of a touch. Liquidity partners excluded (separate motion)."}</div></div>
        <div class="tools"><div class="seg-ctl" role="radiogroup" aria-label="Queue view">
          <button type="button" role="radio" data-qview="today" aria-checked="${qs.view === "today"}" aria-pressed="${qs.view === "today"}">Today</button>
          <button type="button" role="radio" data-qview="all" aria-checked="${qs.view === "all"}" aria-pressed="${qs.view === "all"}">All</button>
        </div></div></div>
      <div class="table-wrap" id="q-table"></div>
    </section>`);

  function sel(name, label, opts, val) {
    return html`<div class="field"><label for="qf-${name}">${label}</label><select id="qf-${name}" name="${name}"><option value="">All</option>${opts.map(([v, l]) => html`<option value="${v}" ${String(v) === String(val ?? "") ? "selected" : ""}>${l}</option>`)}</select></div>`;
  }
  IG.$$("#q-filters select").forEach((s) => s.addEventListener("change", () => { f[s.name] = s.value; load(); }));
  IG.$("#q-reset").addEventListener("click", () => { qs.filters = {}; IG.views.queue(main, sub); });
  IG.$$("[data-qview]", body).forEach((b) => b.addEventListener("click", () => { if (qs.view !== b.dataset.qview) { qs.view = b.dataset.qview; IG.views.queue(main, sub); } }));

  function load() {
    const params = { view: qs.view, limit: qs.view === "today" ? 200 : 50, segment: f.segment, iso: f.iso, rep_id: f.rep_id, stage: f.stage };
    IG.load(IG.$("#q-table"), () => IG.api(`/activation/queue${IG.qs(params)}`), async (d) => {
      const s = d.summary || {};
      drawSummary(s, d.items || [], qs.view);
      drawTable(d.items || [], qs.view === "today" && (s.view === "today" || s.view == null));
      await drawRerank(d.items || [], params);
    }, "table");
  }
  load();
};

function drawSummary(s, items, view) {
  const { html, fmt } = IG;
  const tile = (label, value, sub, cls = "", title = "") => html`<article class="kpi compact ${cls}" title="${title}"><div class="kpi-label">${label}</div><div class="kpi-value">${value}</div><div class="kpi-meta">${sub}</div></article>`;
  const trig = items.filter((i) => i.trigger_id).length;
  const hedg = items.filter((i) => i.side === "hedger").length;
  IG.setHTML(IG.$("#q-summary"), html`<div class="kpis">
    ${tile(view === "today" ? "On today’s lists" : "Accounts in queue", fmt.int(s.accounts_in_queue ?? items.length), `${items.length ? fmt.pct(hedg / items.length, 0) : "—"} hedgers · ${fmt.int(trig)} with a live trigger`)}
    ${IG.isNum(s.backlog) ? tile("Backlog", fmt.int(s.backlog), view === "today" ? "ranked but over today’s caps" : "not on any list today", "", "Open accounts beyond today’s per-owner caps") : ""}
    ${tile("Stalled", fmt.int(s.stalled), "past their stage stall threshold", (s.stalled || 0) > 0 ? "watch" : "on_track")}
    ${tile("SLA breaches", fmt.int(s.sla_breaches), view === "today" ? "on listed items only" : "next-best actions past SLA", (s.sla_breaches || 0) > 0 ? "off_track" : "on_track")}
    ${tile("ADV at stake", "~" + fmt.contracts(s.adv_at_stake, true), "contracts/day · Σ P × E[ADV]", "", IG.DEF.adv_at_stake)}
  </div>`);
}

function ownerOf(it) {
  return { id: it.owner_rep_id ?? it.rep_id ?? null, name: it.owner_name || it.rep_name || (it.rep_id != null ? IG.repName(it.rep_id) : "Unassigned") };
}

function drawTable(items, grouped = false) {
  const { html, fmt } = IG;
  const el = IG.$("#q-table");
  if (!items.length) { IG.setHTML(el, IG.emptyState("No accounts match these filters.", "Try clearing a filter.")); return; }
  const mx = Math.max(1e-9, ...items.map((i) => i.priority || 0));
  const exp = IG.state.queue.expanded;
  const lq = IG.state.lastQueued;
  const groups = [];
  if (grouped) {
    const m = new Map();
    items.forEach((it) => { const o = ownerOf(it); const k = String(o.id ?? o.name); if (!m.has(k)) { m.set(k, { owner: o, items: [] }); groups.push(m.get(k)); } m.get(k).items.push(it); });
  } else groups.push({ owner: null, items });
  IG.setHTML(el, html`<table class="t stackable" id="q-tbl">
    <thead><tr>
      <th><span class="sr-only">Expand</span></th><th class="num">#</th><th>Account</th><th>Segment</th><th>Stage · days</th>
      <th class="num" title="${IG.DEF.p_active}">P(active)</th><th class="num" title="${IG.DEF.exp_adv}">E[ADV]</th><th class="num" title="Urgency multiplier U (cap 2.0)">U</th>
      <th title="${IG.DEF.priority}">Priority</th><th>Next best action</th>
    </tr></thead>
    ${groups.map((g) => html`<tbody>${g.owner ? html`<tr class="group-row"><th colspan="10" scope="rowgroup">
      <span class="avatar sm">${initials2(g.owner.name)}</span><b>${g.owner.name}</b>
      <span class="muted">${g.items.length} to touch · ${fmt.pct(g.items.filter((i) => i.side === "hedger").length / g.items.length, 0)} hedgers${g.items.some((i) => i.sla_breached || (i.next_action || {}).sla_breached) ? ` · ${g.items.filter((i) => i.sla_breached || (i.next_action || {}).sla_breached).length} past SLA` : ""}</span></th></tr>` : ""}
    ${g.items.map((it) => {
      const open = exp.has(String(it.account_id));
      const na = it.next_action || {};
      const isLq = lq && String(lq.account_id) === String(it.account_id);
      return html`<tr class="${isLq ? "flash sel" : ""}" data-row="${it.account_id}">
        <td data-l=""><button type="button" class="expand-btn" aria-expanded="${open}" aria-controls="q-d-${it.account_id}" data-expand="${it.account_id}" aria-label="Why ${it.name} is ranked here">${IG.icon("chev")}</button></td>
        <td data-l="Rank" class="num"><b>${it.rank}</b></td>
        <td data-l="Account" style="min-width:160px">${IG.acct(it.account_id, it.name)}
          <div class="row" style="gap:6px;font-size:11px;margin-top:2px"><span class="muted">${it.iso || ""}</span>${it.trigger_id ? html`<span class="chip trigger" title="Volatility trigger ${it.trigger_id}">${IG.icon("bolt")}trigger</span>` : ""}${isLq ? html`<span class="pill good"><span class="dot"></span>touched</span>` : ""}</div></td>
        <td data-l="Segment">${IG.segTag(it.segment, it.side, true)}</td>
        <td data-l="Stage" class="nowrap"><div class="row" style="gap:4px">${IG.stagePill(it.stage)}${it.health_state ? IG.healthPill(it.health_state) : it.ramping ? IG.healthPill("ramping") : ""}</div>
          <div style="font-size:11px;margin-top:2px">${it.stall ? html`<span style="color:var(--crit-text);font-weight:600" title="Past the stall threshold for this stage">● stalled · ${IG.isNum(it.days_in_stage) ? it.days_in_stage + "d" : ""}</span>` : html`<span class="muted">${IG.isNum(it.days_in_stage) ? it.days_in_stage + "d in stage" : ""}</span>`}</div></td>
        <td data-l="P(active)" class="num">${fmt.prob(it.p_active)}</td>
        <td data-l="E[ADV]" class="num">${fmt.contracts(it.exp_adv)}</td>
        <td data-l="Urgency" class="num ${(it.urgency || 1) > 1 ? "" : "muted"}">${fmt.mult(it.urgency, 2)}</td>
        <td data-l="Priority" style="min-width:130px">${IG.bar((it.priority || 0) / mx, fmt.num(it.priority, 1), "accent")}</td>
        <td data-l="Next action" class="na-cell"><div class="clamp2" title="${na.action || ""}">${na.action || "—"}</div>
          <div class="muted" style="font-size:11px">${[na.owner, na.sla ? "SLA " + (IG.isNum(na.sla) ? na.sla + "h" : na.sla) : null, na.sequence ? na.sequence + " seq." : null].filter(Boolean).join(" · ")}</div></td>
      </tr>
      <tr class="detail" id="q-d-${it.account_id}" ${open ? "" : "hidden"}><td colspan="10">
        <div class="row" style="margin-bottom:8px;font-size:12px"><span class="muted">Score:</span>
          <span class="mono">P ${it.p_active > 0.95 ? ">0.95" : fmt.num(it.p_active, 2)} × E[ADV] ${fmt.contracts(it.exp_adv)} × k ${fmt.num(it.k_stage, 2)} × U ${fmt.num(it.urgency, 2)} × B ${fmt.num(it.balance_weight, 2)} = <b>${fmt.num(it.priority, 1)}</b></span>
          ${(it.balance_weight || 1) > 1 ? html`<span class="pill" title="Hedger share of Active is below the 50% target, so hedgers get a ×1.15 market-balance weight"><span class="dot" style="background:var(--hedger)"></span>Balance weight on</span>` : ""}
          ${na.rule_id ? html`<span class="muted">rule ${na.rule_id}</span>` : ""}</div>
        ${(it.reasons || []).length ? IG.reasonsList(it.reasons.slice(0, 6)) : html`<span class="muted">No reasons returned.</span>`}
      </td></tr>`;
    })}</tbody>`)}</table>`);
  IG.$$("[data-expand]", el).forEach((b) => b.addEventListener("click", () => {
    const id = b.dataset.expand;
    const open = b.getAttribute("aria-expanded") !== "true";
    b.setAttribute("aria-expanded", String(open));
    IG.$(`#q-d-${CSS.escape(id)}`).hidden = !open;
    if (open) exp.add(id); else exp.delete(id);
  }));
}

/** After a touch is queued from Pulse, show where the account moved. */
async function drawRerank(items, params) {
  const { html } = IG;
  const lq = IG.state.lastQueued;
  const el = IG.$("#q-banner");
  if (!lq || !el) return;
  let it = items.find((x) => String(x.account_id) === String(lq.account_id));
  let rank = it ? it.rank : null;
  if (!it) {
    try {
      const all = await IG.api(`/activation/queue${IG.qs({ ...params, view: "all", limit: 200 })}`);
      it = (all.items || []).find((x) => String(x.account_id) === String(lq.account_id));
      rank = it ? it.rank : null;
    } catch (_) { /* best effort */ }
  }
  const moved = IG.isNum(lq.prevRank) && IG.isNum(rank) ? rank - lq.prevRank : null;
  IG.setHTML(el, html`<div class="banner" style="border-color:color-mix(in srgb, var(--good) 45%, var(--border));background:linear-gradient(90deg, color-mix(in srgb, var(--good) 12%, transparent), transparent 70%), var(--surface)">
    <span class="pill good"><span class="dot"></span>Touch logged</span>
    <div class="big">${IG.acct(lq.account_id, lq.name)} ${IG.isNum(lq.prevRank) ? html`moved <b>#${lq.prevRank}</b> → <b>${rank ? "#" + rank : "out of view"}</b>` : rank ? html`now ranks <b>#${rank}</b>` : html`left the ranked view`}</div>
    <div class="ctx">${moved != null ? (moved > 0 ? `Down ${moved} — urgency drops once a triggered touch is logged, freeing the rep for the next-best account.` : moved < 0 ? `Up ${-moved}.` : "Rank unchanged.") : "Urgency for this account now reflects the logged touch (last touch = today)."} ${lq.trigger_id ? `Tagged ${lq.trigger_id}.` : ""}</div>
    <div class="row"><button type="button" class="btn sm" id="q-jump" ${rank ? "" : "hidden"}>Jump to row</button><button type="button" class="btn ghost sm" id="q-dismiss">Dismiss</button></div>
  </div>`);
  IG.$("#q-dismiss").addEventListener("click", () => { IG.state.lastQueued = null; el.innerHTML = ""; });
  const jump = IG.$("#q-jump");
  if (jump) jump.addEventListener("click", () => {
    const row = IG.$(`[data-row="${CSS.escape(String(lq.account_id))}"]`);
    if (row) { row.scrollIntoView({ block: "center", behavior: "smooth" }); row.classList.remove("flash"); void row.offsetWidth; row.classList.add("flash"); }
  });
}

/* ====================================================================== Model panel */
function renderModel(body) {
  const { html } = IG;
  IG.setHTML(body, html`<div id="m-body"></div>`);
  IG.load(IG.$("#m-body"), () => IG.api("/scoring/model"), (m) => drawModel(IG.$("#m-body"), m), html`${IG.skeleton("tiles")}<div class="grid g-12 mt"><div class="card span-6">${IG.skeleton()}</div><div class="card span-6">${IG.skeleton()}</div></div>`);
}

function drawModel(el, m) {
  const { html, fmt } = IG;
  const ch = m.challenger || null;
  const coefs = (m.coefficients || []).slice().sort((a, b) => Math.abs(b.coef) - Math.abs(a.coef)).slice(0, 12);
  const cmax = Math.max(1e-9, ...coefs.map((c) => Math.abs(c.coef)));
  const mini = (l, v, t = "") => html`<div class="mini" title="${t}"><div class="l">${l}</div><div class="v">${v}</div></div>`;
  const hn = m.honest || null;
  const headAuc = hn && IG.isNum(hn.auc_gap) ? hn.auc_gap : m.auc;
  const aucOk = IG.isNum(headAuc) && headAuc >= 0.72 && headAuc <= 0.85;
  IG.setHTML(el, html`
    ${hn ? html`<section class="card honest" aria-labelledby="hon-t">
      <div class="card-h"><div><h2 id="hon-t">Honest evaluation</h2><div class="sub">${hn.note || `Test snapshot ≥${hn.gap_days ?? 60} days after the training snapshot, so no label window overlaps.`}</div></div></div>
      <div class="honest-grid">
        <div><div class="l">AUC, ${fmt.int(hn.gap_days ?? 60)}-day gap</div><div class="v">${fmt.num(hn.auc_gap ?? m.auc, 3)}</div><div class="muted">headline number</div></div>
        <div><div class="l">AUC, unseen accounts</div><div class="v">${fmt.num(hn.auc_unseen, 3)}</div><div class="muted">accounts never in training</div></div>
        <div><div class="l">Baseline: ${hn.baseline_name || "funnel heuristic"}</div><div class="v muted-v">${fmt.num(hn.baseline_auc, 3)}</div>
          <div class="muted">${IG.isNum(hn.baseline_auc) && IG.isNum(headAuc) ? `model adds +${(headAuc - hn.baseline_auc).toFixed(3)} AUC` : ""}</div></div>
      </div>
    </section>` : ""}
    <div class="model-tiles ${hn ? "mt" : ""}">
      ${mini("Target", html`<span style="font-size:13px">${fmt.humanize(m.target || "active_60d")}</span>`)}
      ${mini(hn ? "AUC (gap-adjusted)" : "AUC (holdout)", fmt.num(headAuc, 3), "Area under ROC on the test split. Credible band for synthetic data: 0.72–0.85.")}
      ${mini("Lift, top decile", fmt.mult(m.lift_top_decile), "Activation rate in the top-scored 10% ÷ base rate. Acceptance: ≥2×.")}
      ${mini("PR-AUC", fmt.num(m.pr_auc, 3))}
      ${mini("Brier score", fmt.num(m.brier, 3), "Mean squared error of the probabilities (lower is better).")}
      ${mini("Base rate", fmt.pct(m.base_rate))}
      ${mini("Train / test n", `${fmt.int(m.train_n)} / ${fmt.int(m.test_n)}`)}
    </div>
    <div class="row mt" style="font-size:12px">
      ${IG.statusPill(aucOk ? "on_track" : "watch")}<span class="text-2">${aucOk ? "AUC inside the honest 0.72–0.85 band — strong enough to rank, not suspiciously perfect." : "AUC outside the 0.72–0.85 band — check for leakage or under-fitting."}</span>
      ${IG.isNum(m.lift_top_decile) ? html`${IG.statusPill(m.lift_top_decile >= 2 ? "on_track" : "off_track")}<span class="text-2">Top-decile lift ${fmt.mult(m.lift_top_decile)} vs ≥2× acceptance.</span>` : ""}
    </div>
    <div class="grid g-12 mt">
      <section class="card span-6" aria-labelledby="gain-t">
        <div class="card-h"><div><h2 id="gain-t">Cumulative gain</h2><div class="sub">Share of eventual Actives captured by working the top X% of the queue</div></div></div>
        ${IG.legend([{ label: "Model", color: IG.css("--series"), kind: "line" }, { label: "Random", color: IG.css("--muted"), kind: "dash" }])}
        <div class="chart-box">${(m.gain_curve || []).length ? html`<canvas id="m-gain" role="img" aria-label="Cumulative gain curve"></canvas>` : IG.emptyState("No gain curve.")}</div>
      </section>
      <section class="card span-6" aria-labelledby="cal-t">
        <div class="card-h"><div><h2 id="cal-t">Calibration</h2><div class="sub">Predicted vs observed activation by score bin — points on the diagonal mean P is honest</div></div></div>
        ${IG.legend([{ label: "Observed (dot size = n)", color: IG.css("--series") }, { label: "Perfect calibration", color: IG.css("--muted"), kind: "dash" }])}
        <div class="chart-box">${(m.calibration || []).length ? html`<canvas id="m-cal" role="img" aria-label="Calibration plot"></canvas>` : IG.emptyState("No calibration bins.")}</div>
      </section>
      <section class="card span-7" aria-labelledby="coef-t">
        <div class="card-h"><div><h2 id="coef-t">Top coefficients</h2><div class="sub">Standardized logistic-regression weights · green raises P(active), red lowers it</div></div></div>
        ${coefs.length ? html`<div>${coefs.map((c) => html`<div class="coef"><span>${c.label || c.feature}</span>
          <span class="axis"><b class="${c.coef >= 0 ? "pos" : "neg"}" style="width:${((Math.abs(c.coef) / cmax) * 50).toFixed(1)}%"></b></span>
          <span class="num ${c.coef >= 0 ? "" : ""}">${c.coef >= 0 ? "+" : "−"}${Math.abs(c.coef).toFixed(2)}</span></div>`)}</div>` : IG.emptyState("No coefficients.")}
      </section>
      <section class="card span-5" aria-labelledby="ch-t">
        <div class="card-h"><div><h2 id="ch-t">Champion vs challenger</h2><div class="sub">We ship the interpretable model unless the challenger wins by a margin that matters</div></div></div>
        <table class="t">
          <thead><tr><th>Model</th><th class="num">AUC</th><th class="num">Top-decile lift</th></tr></thead>
          <tbody>
            <tr><td><b>Logistic regression</b> <span class="pill good"><span class="dot"></span>Champion</span></td><td class="num">${fmt.num(m.auc, 3)}</td><td class="num">${fmt.mult(m.lift_top_decile)}</td></tr>
            ${ch ? html`<tr><td>${ch.name || "Challenger"}</td><td class="num">${fmt.num(ch.auc, 3)}</td><td class="num">${fmt.mult(ch.lift_top_decile)}</td></tr>` : ""}
          </tbody>
        </table>
        ${ch && IG.isNum(ch.auc) && IG.isNum(m.auc) ? html`<p class="text-2" style="margin:10px 0 0;font-size:12.5px">${ch.auc - m.auc > 0.02
          ? `Challenger leads by ${(ch.auc - m.auc).toFixed(3)} AUC — worth a holdout test before switching.`
          : `Challenger is within ${Math.abs(ch.auc - m.auc).toFixed(3)} AUC — keep the explainable champion; reps trust reasons they can read.`}</p>` : ""}
      </section>
    </div>`);

  const t = IG.theme();
  const g = m.gain_curve || [];
  if (g.length && IG.$("#m-gain")) {
    const pts = g.map((p) => ({ x: p.pct_accounts, y: p.pct_positives }));
    if (pts[0].x !== 0) pts.unshift({ x: 0, y: 0 });
    IG.chart(IG.$("#m-gain"), {
      type: "line",
      data: { datasets: [
        { label: "Model", data: pts, borderColor: t.series, backgroundColor: IG.alpha(t.series, 0.1), fill: true, pointRadius: 3, pointBackgroundColor: t.series },
        { label: "Random", data: [{ x: 0, y: 0 }, { x: 1, y: 1 }], borderColor: t.muted, borderDash: [5, 4], borderWidth: 1.5, pointRadius: 0 },
      ] },
      options: IG.baseOptions({
        parsing: false,
        interaction: { mode: "nearest", intersect: false },
        scales: { x: IG.axis({ type: "linear", min: 0, max: 1, fmt: (v) => fmt.pct(v, 0), title: "% of accounts worked (by score)" }), y: IG.axis({ min: 0, max: 1, fmt: (v) => fmt.pct(v, 0), title: "% of Actives captured" }) },
        plugins: { tooltip: { callbacks: { title: (c) => `Top ${fmt.pct(c[0].parsed.x, 0)} of queue`, label: (c) => ` ${c.dataset.label}: ${fmt.pct(c.parsed.y, 0)} of Actives` } } },
      }),
    });
  }
  const cal = m.calibration || [];
  if (cal.length && IG.$("#m-cal")) {
    const maxN = Math.max(1, ...cal.map((c) => c.n || 0));
    IG.chart(IG.$("#m-cal"), {
      type: "scatter",
      data: { datasets: [
        { label: "Observed", data: cal.map((c) => ({ x: c.predicted, y: c.observed, n: c.n })), backgroundColor: t.series, borderColor: t.surface, borderWidth: 2, pointRadius: cal.map((c) => 4 + 5 * Math.sqrt((c.n || 0) / maxN)), pointHoverRadius: cal.map((c) => 6 + 5 * Math.sqrt((c.n || 0) / maxN)) },
        { type: "line", label: "Perfect", data: [{ x: 0, y: 0 }, { x: 1, y: 1 }], borderColor: t.muted, borderDash: [5, 4], borderWidth: 1.5, pointRadius: 0 },
      ] },
      options: IG.baseOptions({
        parsing: false,
        interaction: { mode: "nearest", intersect: true },
        scales: { x: IG.axis({ type: "linear", min: 0, max: 1, fmt: (v) => fmt.pct(v, 0), title: "Predicted P(active)" }), y: IG.axis({ min: 0, max: 1, fmt: (v) => fmt.pct(v, 0), title: "Observed rate" }) },
        plugins: { tooltip: { filter: (c) => c.datasetIndex === 0, callbacks: { label: (c) => ` predicted ${fmt.pct(c.raw.x, 0)} → observed ${fmt.pct(c.raw.y, 0)} (n=${c.raw.n ?? "?"})` } } },
      }),
    });
  }
}

function initials2(n) {
  return String(n || "?").split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();
}
