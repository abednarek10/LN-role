/*
 * Account 360 drawer (GET /api/accounts/{id}) and the shared outreach Draft panel
 * (POST /api/outreach/draft → /api/outreach/{id}/approve → /api/outreach/{id}/queue).
 */
"use strict";

/* ====================================================================== Account 360 */
IG.openAccount = function openAccount(id) {
  const { html } = IG;
  IG.drawer.open(html`${IG.drawerHead("Account 360")}<div class="drawer-b">${IG.skeleton("lines")}${IG.skeleton()}${IG.skeleton("table")}</div>`, { label: "Account 360" });
  const d = IG.drawer.el();
  bindClose(d);
  IG.state.acctOpenId = id;
  const token = Symbol("acct");
  IG.state.acctToken = token;
  IG.api(`/accounts/${encodeURIComponent(id)}`)
    .then((data) => { if (IG.state.acctToken === token && IG.drawer.isOpen()) renderAccount(data); })
    .catch((e) => {
      if (IG.state.acctToken !== token) return;
      IG.setHTML(d, html`${IG.drawerHead("Account 360")}<div class="drawer-b">${IG.errorState(e)}</div>`);
      bindClose(d);
      const r = d.querySelector("[data-retry]");
      if (r) r.addEventListener("click", () => IG.openAccount(id));
    });
};

function bindClose(root) {
  IG.$$("[data-close]", root).forEach((b) => b.addEventListener("click", () => IG.drawer.close()));
}

function renderAccount(data) {
  const { html, fmt } = IG;
  const a = data.account || {};
  const h = data.health || {};
  const qbr = data.qbr || null;
  const na = data.next_action || null;
  const steps = (IG.state.meta && IG.state.meta.steps) || [];
  const done = new Map((data.onboarding || []).map((o) => [o.step, o.ts]));
  const timeline = (data.timeline || []).slice().sort((x, y) => String(y.ts).localeCompare(String(x.ts)));
  const iso = a.primary_iso || a.iso;
  const side = a.is_liquidity_partner ? "liquidity_partner" : IG.segInfo(a.segment).side;
  const repName = a.rep_name || a.rep || (a.rep_id != null ? IG.repName(a.rep_id) : "Unassigned");
  const util = qbr ? normalizeUtil(qbr.utilization_by_tenor) : [];
  const plays = (qbr && qbr.growth_plays) || [];
  const fundedDays = a.funded_at ? IG.daysSince(a.funded_at) : null;
  const d = IG.drawer.el();

  IG.setHTML(d, html`
    ${IG.drawerHead(a.name || "Account " + a.id, html`${IG.segTag(a.segment, side)} ${IG.stagePill(a.stage)} ${IG.healthPill(h.state, fundedDays)}
      <span class="muted">${iso || ""}${a.hub ? " · " + a.hub : ""} · ${repName}</span>
      ${a.is_liquidity_partner ? html`<span class="pill" title="Excluded from the AE queue; 25% kicker credit"><span class="dot" style="background:var(--lp)"></span>Liquidity partner</span>` : ""}`)}
    <div class="drawer-b">
      <section aria-label="Health">
        <div class="kv">
          <div title="${IG.DEF.active}">Trading days (30d)<b>${fmt.int(h.trading_days_30)} <span class="muted" style="font-size:11px;font-weight:500">/ 4 for Active</span></b></div>
          <div>ADV 30d<b>${fmt.contracts(h.adv_30d)}</b></div>
          <div>ADV prior 30d<b>${fmt.contracts(h.adv_prior_30d)}</b></div>
          ${IG.isNum(h.net_retention) ? html`<div>Net ADV retention<b>${fmt.pct(h.net_retention, 0)}</b></div>` : ""}
          ${IG.isNum(h.churn_risk) ? html`<div title="Risk of an already-trading account going quiet. Not defined before the first trade.">Churn risk<b style="${(h.churn_risk || 0) >= 0.5 ? "color:var(--crit-text)" : ""}">${fmt.prob(h.churn_risk)}</b></div>` : ""}
          ${IG.isNum(a.p_active) ? html`<div title="${IG.DEF.p_active}">P(active ≤60d)<b>${fmt.prob(a.p_active)}</b></div>` : ""}
          ${IG.isNum(a.funded_amount_usd) ? html`<div>Funded<b>${fmt.usd(a.funded_amount_usd)}</b></div>` : ""}
          ${IG.isNum(a.size_mw) ? html`<div>Size<b>${fmt.int(a.size_mw)} MW</b></div>` : ""}
        </div>
      </section>

      <section aria-labelledby="adv-h">
        <h3 class="section-t" id="adv-h">Daily volume (contracts)</h3>
        ${(data.adv_series || []).length ? html`<div class="chart-box short"><canvas id="acct-adv" role="img" aria-label="Daily contracts traded"></canvas></div>` : IG.emptyState("No trades yet.", "This account has not placed a qualifying trade.")}
      </section>

      ${na ? html`<section aria-labelledby="na-h">
        <h3 class="section-t" id="na-h">Next best action</h3>
        <div class="friction"><div class="ask"><b>${na.action || "—"}</b><div class="muted" style="margin-top:4px">${[na.owner, na.sla ? "SLA " + na.sla : null, na.rule_id ? "rule " + na.rule_id : null, na.sequence ? na.sequence + " sequence" : null].filter(Boolean).join(" · ")}</div></div></div>
      </section>` : ""}

      ${(data.reasons || []).length ? html`<section aria-labelledby="rs-h"><h3 class="section-t" id="rs-h">Why the model ranks it here</h3>${IG.reasonsList(data.reasons)}</section>` : ""}

      <section aria-labelledby="ob-h">
        <h3 class="section-t" id="ob-h">Onboarding journey</h3>
        <div class="steps">${(steps.length ? steps : [...done.keys()]).map((s) => html`<span class="${done.has(s) ? "done" : ""}" title="${done.has(s) ? fmt.date(done.get(s), true) : "not yet"}">${done.has(s) ? "✓ " : ""}${String(s).replace(/_/g, " ")}</span>`)}</div>
      </section>

      ${qbr ? html`      <section aria-labelledby="qbr-h" class="card" style="background:var(--surface-2)">
        <div class="card-h"><div><h3 id="qbr-h" style="font-size:13px">QBR — is this institution growing?</h3><div class="sub">Utilization by tenor, ISO footprint, growth plays</div></div></div>
        ${util.length ? html`<div style="display:grid;gap:4px;margin-bottom:10px">${util.map((u) => html`<div class="row" style="flex-wrap:nowrap"><span style="width:110px" class="text-2">${IG.tenorLabel(u.tenor)}</span>${IG.bar(u.share, fmt.pct(u.share, 0))}</div>`)}</div>` : ""}
        <div class="row" style="margin-bottom:8px"><span class="muted">ISOs traded</span>${(qbr.isos_traded || []).length ? (qbr.isos_traded || []).map((i) => html`<span class="stage">${i}</span>`) : html`<span class="muted">none yet</span>`}
          ${a.exposure_isos ? html`<span class="muted" style="margin-left:8px">Exposure</span>${String(a.exposure_isos).split(",").filter(Boolean).map((i) => html`<span class="stage">${i.trim()}</span>`)}` : ""}</div>
        ${plays.length ? html`<ol style="margin:0;padding-left:18px">${plays.map((p) => html`<li style="margin:3px 0">${typeof p === "string" ? p : html`<b>${p.title || p.play || p.name || ""}</b>${p.detail || p.description ? html` — <span class="text-2">${p.detail || p.description}</span>` : ""}`}</li>`)}</ol>` : html`<div class="muted">No growth plays yet.</div>`}
      </section>` : ""}

      <section aria-labelledby="tl-h">
        <h3 class="section-t" id="tl-h">Timeline</h3>
        ${timeline.length ? html`<ol class="timeline">${timeline.slice(0, 14).map((e) => html`<li class="${/onboard|step/.test(e.type) ? "ob" : /trigger|email|queue/.test(e.type) ? "touch" : ""}"><time>${fmt.dateTime(e.ts)} · ${String(e.type || "").replace(/_/g, " ")}</time>${e.label}</li>`)}</ol>` : IG.emptyState("No activity logged.")}
      </section>

      <section aria-labelledby="ct-h">
        <h3 class="section-t" id="ct-h">Contacts</h3>
        ${(data.contacts || []).length ? (data.contacts || []).map((c) => html`<div class="contact"><span class="avatar">${initials(c.name)}</span>
          <div><b>${c.name}</b>${c.is_champion ? html` <span class="pill good"><span class="dot"></span>Champion</span>` : ""}<div class="muted">${c.title || ""}${c.persona ? " · " + c.persona : ""}</div></div>
          ${c.email ? html`<span class="muted mono" style="margin-left:auto">${c.email}</span>` : ""}</div>`) : IG.emptyState("No contacts on file.")}
      </section>
    </div>
    <div class="drawer-f">
      <button type="button" class="btn primary" data-draft-kind="activation">${IG.icon("mail")}Draft activation outreach</button>
      ${qbr ? html`<button type="button" class="btn" data-draft-kind="qbr">Draft QBR note</button>` : ""}
      <span class="watermark" style="margin-left:auto">Synthetic data — illustrative</span>
    </div>`);
  bindClose(d);
  IG.$$("[data-draft-kind]", d).forEach((b) => b.addEventListener("click", () => {
    IG.openDraft({ account_id: a.id, name: a.name, segment: a.segment, kind: b.dataset.draftKind, back: () => IG.openAccount(a.id) });
  }));

  const series = data.adv_series || [];
  if (series.length && IG.$("#acct-adv")) {
    const t = IG.theme();
    IG.chart(IG.$("#acct-adv"), {
      type: "bar",
      data: { labels: series.map((p) => fmt.date(p.date)), datasets: [{ label: "Contracts", data: series.map((p) => p.contracts), backgroundColor: t.series, maxBarThickness: 8, categoryPercentage: 0.9, barPercentage: 0.9 }] },
      options: IG.baseOptions({
        scales: { x: IG.axis({ grid: false, maxTicks: 6 }), y: IG.axis({ beginAtZero: true, maxTicks: 4, fmt: (v) => fmt.contracts(v, true) }) },
        plugins: { tooltip: { callbacks: { label: (c) => ` ${fmt.contracts(c.parsed.y)} contracts` } } },
      }),
    }, "drawer");
  }
}

function initials(n) {
  return String(n || "?").split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();
}
function normalizeUtil(u) {
  if (!u) return [];
  if (Array.isArray(u)) return u.map((x) => ({ tenor: x.tenor || x.name, share: pick(x.share, x.utilization, x.pct, x.value) })).filter((x) => IG.isNum(x.share));
  const entries = Object.entries(u).filter(([, v]) => IG.isNum(v));
  const tot = entries.reduce((s, [, v]) => s + v, 0);
  return entries.map(([tenor, v]) => ({ tenor, share: tot > 1.01 ? v / tot : v }));
}
function pick(...v) { return v.find(IG.isNum); }

/** Reasons (+/− weights), shared by Queue rows and Account 360. */
IG.reasonsList = (reasons) => {
  const { html } = IG;
  const mx = Math.max(1e-9, ...reasons.map((r) => Math.abs(r.weight || 0)));
  return html`<div class="reasons">${reasons.map((r) => {
    const pos = r.direction === "+" || (r.direction == null && (r.weight || 0) >= 0);
    return html`<div class="reason"><span class="sign ${pos ? "pos" : "neg"}" aria-label="${pos ? "raises" : "lowers"} priority">${pos ? "+" : "−"}</span>
      <span>${r.label || r.feature}</span>
      <span class="w">${IG.isNum(r.weight) ? Math.abs(r.weight).toFixed(2) : ""}</span>
      <span class="wbar"><b class="${pos ? "pos" : "neg"}" style="width:${((Math.abs(r.weight || 0) / mx) * 100).toFixed(0)}%"></b></span></div>`;
  })}</div>`;
};

/* ====================================================================== Draft panel */
IG.openDraft = function openDraft(opts) {
  const { html } = IG;
  const { account_id, name, direction, trigger_id, kind = "activation", onQueued, back } = opts;
  IG.state.acctOpenId = null;
  const kindLabel = { volatility: "Volatility outreach", activation: "Activation outreach", qbr: "QBR note" }[kind] || "Outreach";
  const head = () => html`<div class="drawer-h">
      <div>
        ${back ? html`<button type="button" class="btn ghost sm" data-back style="margin:-4px 0 6px -8px">← Back to account</button>` : ""}
        <h2 id="drawer-title">${kindLabel}</h2>
        <div class="row" style="margin-top:6px">${IG.acct(account_id, name)} ${direction ? IG.dirPill(direction) : ""} ${trigger_id ? html`<span class="chip trigger">${IG.icon("bolt")}${trigger_id}</span>` : ""}</div>
      </div>
      <button type="button" class="icon-btn close" data-close aria-label="Close panel (Esc)">${IG.icon("x")}</button></div>`;
  IG.drawer.open(html`${head()}<div class="drawer-b">${flow("draft")}${IG.skeleton("lines")}<div class="skel" style="height:240px"></div></div>`, { narrow: true, label: kindLabel });
  const d = IG.drawer.el();
  const wire = () => {
    bindClose(d);
    const b = d.querySelector("[data-back]");
    if (b) b.addEventListener("click", back);
  };
  wire();

  // Capture the account's current queue rank so the Queue can show the re-rank after we log the touch.
  let prevRank = null;
  IG.api(`/activation/queue${IG.qs({ view: "all", limit: 200 })}`, { fresh: true })
    .then((q) => { const it = (q.items || []).find((x) => String(x.account_id) === String(account_id)); prevRank = it ? it.rank : null; })
    .catch(() => {});

  const body = { account_id, kind };
  if (trigger_id) body.trigger_id = trigger_id;
  const t0 = performance.now();
  IG.api("/outreach/draft", { method: "POST", body })
    .then((dr) => render(dr, Math.round(performance.now() - t0)))
    .catch((e) => {
      IG.setHTML(d, html`${head()}<div class="drawer-b">${IG.errorState(e)}</div>`);
      wire();
      const r = d.querySelector("[data-retry]");
      if (r) r.addEventListener("click", () => IG.openDraft(opts));
    });

  function flow(stage) {
    const order = ["draft", "review", "approved", "queued"];
    const labels = { draft: "Drafted", review: "Compliance check", approved: "Approved", queued: "Queued" };
    const idx = order.indexOf(stage);
    return html`<div class="steps-flow" aria-label="Workflow">${order.map((s, i) => html`${i ? html`<span class="sepr">→</span>` : ""}<span class="${i <= idx ? "on" : ""}">${i < idx || (i === idx && stage === "queued") ? "✓ " : ""}${labels[s]}</span>`)}</div>`;
  }

  function render(dr0, ms) {
    let dr = dr0;
    let status = dr.status || "pending_review";
    let editing = false;
    let rejecting = false;
    let errMsg = "";
    const cleared = new Set();
    let reviewer = "";
    try { reviewer = localStorage.getItem("ignition.reviewer") || ""; } catch (_) { /* storage blocked */ }
    const stageOf = (s) => (s === "queued" || s === "sent" ? "queued" : s === "approved" ? "approved" : "review");
    const normFlags = () => {
      const comp = dr.compliance || { passed: true, flags: [] };
      return (comp.flags || []).map((f, i) => {
        if (typeof f === "string") return { id: `f${i}`, level: comp.passed ? "caution" : "block", message: f };
        const level = f.level || (comp.passed ? "caution" : "block");
        return { id: f.id != null ? String(f.id) : `f${i}`, level, message: f.message || f.detail || f.phrase || f.rule || JSON.stringify(f), phrase: f.phrase, rule: f.rule };
      });
    };

    const draw = () => {
      const comp = dr.compliance || { passed: true, flags: [] };
      const flags = normFlags();
      const blocks = flags.filter((f) => f.level === "block");
      const cautions = flags.filter((f) => f.level !== "block");
      const engine = String(dr.engine || "template").toLowerCase();
      const facts = Object.entries(dr.facts || {}).filter(([, v]) => v != null && typeof v !== "object");
      const open = status === "pending_review" || status === "draft";
      const allCleared = cautions.every((f) => cleared.has(f.id));
      const canApprove = open && comp.passed !== false && !blocks.length && allCleared && reviewer.trim().length > 1 && !editing;
      const why = !open ? "" : blocks.length || comp.passed === false ? "Blocking flags — edit the draft or regenerate" : !allCleared ? "Clear each caution first" : reviewer.trim().length < 2 ? "Enter the reviewer’s name" : editing ? "Save or cancel the edit first" : "";
      IG.setHTML(d, html`${head()}
        <div class="drawer-b">
          ${flow(stageOf(status))}
          <div class="row">
            <span class="pill engine-${engine === "claude" ? "claude" : "template"}" title="${engine === "claude" ? "Written by Claude from computed facts only — any number not in the facts is blocked" : "Deterministic template (works offline, no API key)"}">${engine === "claude" ? "✦ Claude" : "Template engine"}</span>
            <span class="muted" style="font-size:11.5px">${ms != null ? `generated in ${ms} ms · ` : ""}status <b>${String(status).replace(/_/g, " ")}</b>${dr.reviewer ? ` · by ${dr.reviewer}` : ""}</span>
          </div>
          <div class="compliance ${blocks.length || comp.passed === false ? "fail block" : cautions.length ? "fail" : "pass"}" role="status">
            <b>${blocks.length || comp.passed === false ? "✕ Blocked by the compliance linter" : cautions.length ? `! ${cautions.length} caution${cautions.length > 1 ? "s" : ""} to clear before approval` : "✓ Compliance linter passed"}</b>
            ${!flags.length && comp.passed !== false ? html`<div class="muted" style="margin-top:3px">No promissory or advice language; required disclaimer footer present.</div>` : ""}
            ${blocks.length ? html`<ul>${blocks.map((f) => html`<li>${f.message}</li>`)}</ul><div class="muted" style="margin-top:4px">Edit the text and re-lint, or regenerate (falls back to the template).</div>` : ""}
            ${cautions.length && open ? html`<div class="cautions">${cautions.map((f) => html`<label class="caution"><input type="checkbox" data-clear="${f.id}" ${cleared.has(f.id) ? "checked" : ""} ${editing ? "disabled" : ""}/><span><b>Clear:</b> ${f.message}</span></label>`)}</div>` : ""}
            ${cautions.length && !open ? html`<ul>${cautions.map((f) => html`<li>${f.message} <span class="muted">(cleared)</span></li>`)}</ul>` : ""}
          </div>
          ${open ? html`<div class="field reviewer"><label for="rv-name">Reviewer (compliance sign-off)</label><input type="text" id="rv-name" value="${reviewer}" placeholder="Your name" autocomplete="name" /></div>` : ""}
          ${editing ? html`<div class="email-edit">
              <div class="field"><label for="ed-subj">Subject</label><input type="text" id="ed-subj" value="${dr.subject || ""}" /></div>
              <div class="field"><label for="ed-body">Body</label><textarea id="ed-body" rows="14">${dr.body || ""}</textarea></div>
              <div class="row"><button type="button" class="btn primary sm" data-save>Re-lint &amp; save</button><button type="button" class="btn ghost sm" data-cancel-edit>Cancel</button><span class="muted" style="font-size:11.5px">Saving re-runs the compliance linter.</span></div>
            </div>`
          : html`<div class="email-preview">
            <div class="subj"><span class="muted" style="font-weight:500">Subject: </span>${dr.subject || "(no subject)"}</div>
            <div class="body">${dr.body || ""}</div>
          </div>`}
          ${rejecting ? html`<div class="reject-box"><div class="field"><label for="rj-reason">Reason for rejection</label><input type="text" id="rj-reason" placeholder="e.g. tone too promotional for a co-op board" /></div>
            <div class="row"><button type="button" class="btn sm" data-confirm-reject>Reject draft</button><button type="button" class="btn ghost sm" data-cancel-reject>Cancel</button></div></div>` : ""}
          ${errMsg ? html`<div class="state error" role="alert" style="min-height:0;padding:10px"><code>${errMsg}</code></div>` : ""}
          ${facts.length ? html`<details><summary class="muted" style="cursor:pointer">Facts passed to the engine (${facts.length})</summary>
            <div class="kv" style="margin-top:8px">${facts.map(([k, v]) => html`<div>${IG.fmt.humanize(k)}<b style="font-size:12.5px">${typeof v === "number" ? (Math.abs(v) >= 100 ? IG.fmt.int(v) : v) : String(v)}</b></div>`)}</div></details>` : ""}
        </div>
        <div class="drawer-f">
          ${status === "queued" || status === "sent"
            ? html`<span class="pill good"><span class="dot"></span>Touch logged</span><a class="btn primary" href="#/queue" data-goqueue>Open Activation Queue →</a>`
            : status === "rejected"
              ? html`<span class="pill crit"><span class="dot"></span>Rejected</span><button type="button" class="btn" data-regen>Regenerate</button>`
              : html`
              <button type="button" class="btn ${status === "approved" ? "done" : "primary"}" data-approve ${!canApprove || status === "approved" ? "disabled" : ""} title="${why}">${status === "approved" ? "✓ Approved" : "Approve"}</button>
              <button type="button" class="btn ${status === "approved" ? "primary" : ""}" data-queue ${status !== "approved" ? "disabled" : ""} title="${status !== "approved" ? "Approve first (compliance review)" : "Queue for sending and log the touch"}">Queue</button>
              ${open && !editing ? html`<button type="button" class="btn ghost" data-edit>Edit</button><button type="button" class="btn ghost" data-reject>Reject</button>` : ""}
              ${blocks.length || comp.passed === false ? html`<button type="button" class="btn ghost" data-regen>Regenerate</button>` : ""}`}
          <button type="button" class="btn ghost" data-copy style="margin-left:auto">Copy</button>
        </div>`);
      wire();
      const on = (sel, fn) => { const el = d.querySelector(sel); if (el) el.addEventListener("click", fn); return el; };
      on("[data-approve]", approve);
      on("[data-queue]", queue);
      on("[data-regen]", () => IG.openDraft(opts));
      on("[data-goqueue]", () => IG.drawer.close());
      on("[data-edit]", () => { editing = true; rejecting = false; errMsg = ""; draw(); const b = d.querySelector("#ed-body"); if (b) b.focus(); });
      on("[data-cancel-edit]", () => { editing = false; draw(); });
      on("[data-save]", saveEdit);
      on("[data-reject]", () => { rejecting = true; editing = false; draw(); const r = d.querySelector("#rj-reason"); if (r) r.focus(); });
      on("[data-cancel-reject]", () => { rejecting = false; draw(); });
      on("[data-confirm-reject]", reject);
      // Update the Approve gate in place (no re-render, so focus and checkbox state are kept).
      const refreshGate = () => {
        const ap = d.querySelector("[data-approve]");
        if (!ap || status === "approved") return;
        const cl = cautions.every((f) => cleared.has(f.id));
        const ok = open && comp.passed !== false && !blocks.length && cl && reviewer.trim().length > 1 && !editing;
        ap.disabled = !ok;
        ap.title = ok ? "" : blocks.length || comp.passed === false ? "Blocking flags — edit the draft or regenerate" : !cl ? "Clear each caution first" : reviewer.trim().length < 2 ? "Enter the reviewer’s name" : "";
        const head = d.querySelector(".compliance > b");
        if (head && cautions.length && !blocks.length) head.textContent = cl ? "✓ All cautions cleared by reviewer" : `! ${cautions.filter((f) => !cleared.has(f.id)).length} caution(s) to clear before approval`;
      };
      IG.$$("[data-clear]", d).forEach((cb) => cb.addEventListener("change", () => { if (cb.checked) cleared.add(cb.dataset.clear); else cleared.delete(cb.dataset.clear); refreshGate(); }));
      const rv = d.querySelector("#rv-name");
      if (rv) rv.addEventListener("input", () => {
        reviewer = rv.value;
        try { localStorage.setItem("ignition.reviewer", reviewer); } catch (_) { /* storage blocked */ }
        refreshGate();
      });
      on("[data-copy]", async (e) => {
        const btn = e.currentTarget;
        try { await navigator.clipboard.writeText(`Subject: ${dr.subject}\n\n${dr.body}`); btn.textContent = "Copied ✓"; } catch (_) { IG.toast("Clipboard unavailable — select the text to copy.", { error: true }); }
      });
    };

    async function approve(e) {
      e.currentTarget.disabled = true;
      e.currentTarget.textContent = "Approving…";
      errMsg = "";
      try {
        const r = await IG.api(`/outreach/${encodeURIComponent(dr.draft_id)}/approve`, { method: "POST", body: { reviewer: reviewer.trim(), cleared_flag_ids: [...cleared] } });
        status = r.status || "approved";
        if (r.reviewer) dr.reviewer = r.reviewer;
      } catch (err) {
        errMsg = /409/.test(err.message) ? `Not approved: ${err.message.replace(/^.*?—\s*/, "")}` : `Approve failed: ${err.message}`;
      }
      draw();
    }
    async function queue(e) {
      e.currentTarget.disabled = true;
      e.currentTarget.textContent = "Queueing…";
      errMsg = "";
      try {
        const r = await IG.api(`/outreach/${encodeURIComponent(dr.draft_id)}/queue`, { method: "POST" });
        status = r.status || "queued";
        IG.state.queued.add(String(account_id));
        IG.state.lastQueued = { account_id, name, prevRank, trigger_id, at: Date.now() };
        draw();
        IG.toast(IG.html`Logged touch · Activation Queue re-ranked <a href="#/queue" data-toast-queue>View queue →</a>`, { timeout: 7000 });
        const tl = IG.$("[data-toast-queue]");
        if (tl) tl.addEventListener("click", () => IG.drawer.close());
        if (onQueued) onQueued(r);
      } catch (err) {
        errMsg = /409/.test(err.message) ? `Not queued: ${err.message.replace(/^.*?—\s*/, "")}` : `Queue failed: ${err.message}`;
        draw();
      }
    }
    async function saveEdit(e) {
      const subject = d.querySelector("#ed-subj").value;
      const body = d.querySelector("#ed-body").value;
      e.currentTarget.disabled = true;
      e.currentTarget.textContent = "Re-linting…";
      errMsg = "";
      try {
        const r = await IG.api(`/outreach/${encodeURIComponent(dr.draft_id)}/edit`, { method: "POST", body: { subject, body } });
        dr = { ...dr, ...r };
        status = r.status || "pending_review";
        cleared.clear();
        editing = false;
        IG.toast("Draft saved and re-linted");
      } catch (err) {
        dr = { ...dr, subject, body };
        errMsg = `Edit not saved: ${err.message}`;
      }
      draw();
    }
    async function reject(e) {
      const reason = (d.querySelector("#rj-reason").value || "").trim();
      if (!reason) { d.querySelector("#rj-reason").focus(); return; }
      e.currentTarget.disabled = true;
      errMsg = "";
      try {
        const r = await IG.api(`/outreach/${encodeURIComponent(dr.draft_id)}/reject`, { method: "POST", body: { reviewer: reviewer.trim() || "unknown", reason } });
        status = r.status || "rejected";
        rejecting = false;
      } catch (err) {
        errMsg = `Reject failed: ${err.message}`;
      }
      draw();
    }
    draw();
    const f0 = d.querySelector("#rv-name") && !reviewer ? d.querySelector("#rv-name") : d.querySelector("[data-approve]:not([disabled])");
    if (f0) f0.focus();
  }
};
