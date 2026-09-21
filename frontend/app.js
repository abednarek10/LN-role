/*
 * Ticketmaster Market & Pricing Strategy Workbench — SPA controller.
 *
 * Vanilla JS + Chart.js only, no build step. State is intentionally tiny:
 * we keep a copy of the latest overview response (for cross-view linking)
 * and the id of the event currently loaded in the Price & Demand view.
 */

const API_BASE = "/api";
const state = {
  overview: null,
  selectedEventId: null,
  charts: { elasticity: null, scenario: null },
};

// ---------- utilities ----------
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
const fmt = {
  usd: (v) =>
    "$" +
    (v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 }),
  usdCompact: (v) => {
    const n = v ?? 0;
    if (Math.abs(n) >= 1e6) return "$" + (n / 1e6).toFixed(2) + "M";
    if (Math.abs(n) >= 1e3) return "$" + (n / 1e3).toFixed(1) + "K";
    return "$" + n.toFixed(0);
  },
  pct: (v, digits = 1) => ((v ?? 0) * 100).toFixed(digits) + "%",
  date: (iso) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }),
  num: (v, digits = 2) => (v ?? 0).toLocaleString(undefined, { maximumFractionDigits: digits }),
};

function scoreClass(score) {
  if (score >= 65) return "hot";
  if (score >= 45) return "warm";
  return "cool";
}

async function api(path, opts = {}) {
  const res = await fetch(API_BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API ${path} failed: ${res.status} ${err}`);
  }
  return await res.json();
}

// ---------- navigation ----------
function switchView(target) {
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${target}`));
  $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === target));
  if (target === "okr") loadOkr();
  if (target === "scenario") populateScenarioEvents();
}

$$(".nav-btn").forEach((b) => b.addEventListener("click", () => switchView(b.dataset.view)));

// ---------- Overview ----------
async function loadOverview() {
  const q = new URLSearchParams();
  const city = $("#f-city").value.trim();
  const tour = $("#f-tour").value.trim();
  const category = $("#f-category").value;
  const dateFrom = $("#f-date-from").value;
  const dateTo = $("#f-date-to").value;
  if (city) q.set("city", city);
  if (tour) q.set("tour_name", tour);
  if (category) q.set("category", category);
  if (dateFrom) q.set("date_from", `${dateFrom}T00:00:00`);
  if (dateTo) q.set("date_to", `${dateTo}T23:59:59`);

  const data = await api(`/events/overview?${q.toString()}`);
  state.overview = data;
  renderOverview(data);
  populateEventSelectors(data.events);
}

function renderOverview(data) {
  const tbody = $("#events-table tbody");
  tbody.innerHTML = "";
  data.events.forEach((e) => {
    const tr = document.createElement("tr");
    tr.dataset.eventId = e.event_id;
    tr.innerHTML = `
      <td>${e.event_name}</td>
      <td>${e.city}</td>
      <td>${e.venue_name}</td>
      <td>${fmt.date(e.event_date)}</td>
      <td class="num">$${fmt.num(e.avg_ticket_price)}</td>
      <td class="num">${fmt.pct(e.sell_through)}</td>
      <td class="num">${fmt.usdCompact(e.gross_revenue)}</td>
      <td class="num">${fmt.usdCompact(e.contribution_margin)}</td>
      <td class="num"><span class="score-badge ${scoreClass(
        e.market_opportunity_score
      )}">${e.market_opportunity_score.toFixed(1)}</span></td>
    `;
    tr.addEventListener("click", () => {
      state.selectedEventId = e.event_id;
      switchView("elasticity");
      $("#event-selector").value = e.event_id;
      loadElasticity();
    });
    tbody.appendChild(tr);
  });

  $("#kpi-revenue").textContent = fmt.usdCompact(data.summary.total_revenue);
  $("#kpi-margin").textContent = fmt.pct(data.summary.avg_margin_pct);
  $("#kpi-sellthrough").textContent = fmt.pct(data.summary.avg_sell_through);
  $("#kpi-eventcount").textContent = data.summary.event_count;

  const ul = $("#top-cities");
  ul.innerHTML = "";
  data.summary.top_cities.forEach((c) => {
    const li = document.createElement("li");
    li.innerHTML = `<span>${c.city} <small style="color:var(--muted)">(${c.event_count} ev)</small></span><b>${c.avg_opportunity}</b>`;
    ul.appendChild(li);
  });
}

// Sortable columns
let sortState = { col: null, dir: 1 };
$$("#events-table th").forEach((th) => {
  th.addEventListener("click", () => {
    if (!state.overview) return;
    const col = th.dataset.sort;
    if (!col) return;
    sortState.dir = sortState.col === col ? -sortState.dir : 1;
    sortState.col = col;
    state.overview.events.sort((a, b) => {
      const av = a[col], bv = b[col];
      if (typeof av === "string") return sortState.dir * av.localeCompare(bv);
      return sortState.dir * (av - bv);
    });
    renderOverview(state.overview);
  });
});

$("#f-apply").addEventListener("click", loadOverview);
$("#f-clear").addEventListener("click", () => {
  ["f-city", "f-tour", "f-date-from", "f-date-to"].forEach((id) => ($("#" + id).value = ""));
  $("#f-category").value = "";
  loadOverview();
});

function populateEventSelectors(events) {
  const sel = $("#event-selector");
  sel.innerHTML = "";
  events.forEach((e) => {
    const opt = document.createElement("option");
    opt.value = e.event_id;
    opt.textContent = `${e.city} — ${fmt.date(e.event_date)}`;
    sel.appendChild(opt);
  });
  if (events.length && !state.selectedEventId) {
    state.selectedEventId = events[0].event_id;
    sel.value = events[0].event_id;
  }
}

// ---------- Elasticity ----------
async function loadElasticity() {
  const id = $("#event-selector").value || state.selectedEventId;
  if (!id) return;
  state.selectedEventId = id;
  const data = await api(`/events/${id}/elasticity`);
  renderElasticity(data);
}

function renderElasticity(data) {
  const overviewRow = (state.overview?.events || []).find((e) => e.event_id === data.event_id);
  const info = $("#event-info");
  info.innerHTML = "";
  const rows = overviewRow
    ? [
        ["Tour", overviewRow.tour_name],
        ["Artist", overviewRow.artist_name],
        ["City", `${overviewRow.city}, ${overviewRow.state}`],
        ["Venue", overviewRow.venue_name],
        ["Date", fmt.date(overviewRow.event_date)],
        ["Avg Price", "$" + fmt.num(overviewRow.avg_ticket_price)],
        ["Sell-through", fmt.pct(overviewRow.sell_through)],
        ["Revenue", fmt.usdCompact(overviewRow.gross_revenue)],
        ["Contribution", fmt.usdCompact(overviewRow.contribution_margin)],
      ]
    : [["Event", data.event_name]];
  rows.forEach(([k, v]) => {
    const dt = document.createElement("dt"); dt.textContent = k;
    const dd = document.createElement("dd"); dd.textContent = v;
    info.appendChild(dt); info.appendChild(dd);
  });

  $("#ins-elasticity").textContent =
    `${data.beta_1.toFixed(2)} (${data.elasticity_verdict})`;
  $("#ins-price-range").textContent =
    `$${data.recommended_price_low.toFixed(2)} – $${data.recommended_price_high.toFixed(2)}`;
  $("#ins-fit").textContent = `R² = ${data.r_squared.toFixed(2)} · n = ${data.sample_size}`;
  $("#ins-narrative").textContent = data.narrative;

  const scatter = data.data_points.map((p) => ({ x: p.avg_price, y: p.tickets_sold }));
  const fitCurve = data.price_grid_predictions.map((p) => ({
    x: p.price,
    y: p.predicted_tickets_sold,
  }));

  if (state.charts.elasticity) state.charts.elasticity.destroy();
  const ctx = document.getElementById("elasticity-chart").getContext("2d");
  state.charts.elasticity = new Chart(ctx, {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "Observed (price, tickets sold)",
          data: scatter,
          backgroundColor: "rgba(110, 168, 255, 0.7)",
          pointRadius: 3,
        },
        {
          label: "Fitted log-log curve",
          data: fitCurve,
          type: "line",
          borderColor: "rgba(63, 191, 173, 1)",
          backgroundColor: "rgba(63, 191, 173, 0.15)",
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.25,
        },
        {
          label: "Recommended price",
          data: [{ x: data.recommended_price, y: 0 }, { x: data.recommended_price, y: Math.max(...scatter.map((p) => p.y)) }],
          type: "line",
          borderColor: "rgba(242, 180, 83, 0.9)",
          borderDash: [4, 4],
          borderWidth: 2,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { title: { display: true, text: "Price ($)" }, ticks: { color: "#9aa5bd" } },
        y: { title: { display: true, text: "Tickets sold / day" }, ticks: { color: "#9aa5bd" } },
      },
      plugins: {
        legend: { position: "bottom", labels: { color: "#9aa5bd" } },
        tooltip: { callbacks: { label: (ctx) => `$${ctx.parsed.x.toFixed(2)} → ${ctx.parsed.y.toFixed(0)} tix` } },
      },
    },
  });
}

$("#load-elasticity").addEventListener("click", loadElasticity);
$("#event-selector").addEventListener("change", () => {
  state.selectedEventId = $("#event-selector").value;
});

$("#to-scenario-from-event").addEventListener("click", () => {
  switchView("scenario");
  const sel = $("#scenario-events");
  Array.from(sel.options).forEach((o) => (o.selected = o.value === state.selectedEventId));
});

// ---------- Scenario ----------
function populateScenarioEvents() {
  const events = state.overview?.events || [];
  const sel = $("#scenario-events");
  const prevSelected = new Set(Array.from(sel.selectedOptions).map((o) => o.value));
  sel.innerHTML = "";
  events.forEach((e) => {
    const opt = document.createElement("option");
    opt.value = e.event_id;
    opt.textContent = `${e.city} — ${fmt.date(e.event_date)}`;
    if (prevSelected.has(e.event_id) || e.event_id === state.selectedEventId) {
      opt.selected = true;
    }
    sel.appendChild(opt);
  });
}

async function runScenario() {
  const ids = Array.from($("#scenario-events").selectedOptions).map((o) => o.value);
  if (ids.length === 0) {
    alert("Select at least one event.");
    return;
  }
  const body = {
    event_ids: ids,
    price_adjustment_type: document.querySelector('input[name="adj-type"]:checked').value,
    price_adjustment_value: parseFloat($("#adj-value").value || "0"),
    add_extra_show: $("#extra-show").checked,
  };
  const data = await api("/scenario/simulate", {
    method: "POST",
    body: JSON.stringify(body),
  });
  renderScenario(data);
}

function deltaClass(v) { return v > 0 ? "delta-pos" : v < 0 ? "delta-neg" : ""; }

function renderScenario(data) {
  $("#sc-revenue").textContent =
    `${fmt.usdCompact(data.baseline_revenue)} → ${fmt.usdCompact(data.scenario_revenue)}`;
  $("#sc-margin").textContent =
    `${fmt.usdCompact(data.baseline_margin)} → ${fmt.usdCompact(data.scenario_margin)}`;

  const rD = $("#sc-revenue-delta");
  rD.className = "kpi-delta " + deltaClass(data.delta_revenue);
  rD.textContent = `${data.delta_revenue >= 0 ? "+" : ""}${fmt.usdCompact(data.delta_revenue)} (${fmt.pct(data.delta_revenue_pct)})`;

  const mD = $("#sc-margin-delta");
  mD.className = "kpi-delta " + deltaClass(data.delta_margin);
  mD.textContent = `${data.delta_margin >= 0 ? "+" : ""}${fmt.usdCompact(data.delta_margin)} (${fmt.pct(data.delta_margin_pct)})`;

  const bPct = Math.min(1, data.okr_progress_baseline) * 100;
  const sPct = Math.min(1, data.okr_progress_scenario) * 100;
  $("#sc-okr-baseline").style.width = bPct + "%";
  $("#sc-okr-scenario").style.width = sPct + "%";
  const oD = $("#sc-okr-delta");
  oD.className = "kpi-delta " + deltaClass(data.okr_progress_delta_pts);
  oD.textContent = `${fmt.pct(data.okr_progress_baseline, 2)} → ${fmt.pct(data.okr_progress_scenario, 2)} (${data.okr_progress_delta_pts >= 0 ? "+" : ""}${data.okr_progress_delta_pts.toFixed(2)} pts vs target)`;

  $("#sc-narrative").textContent = data.narrative;

  if (state.charts.scenario) state.charts.scenario.destroy();
  const ctx = document.getElementById("scenario-chart").getContext("2d");
  const labels = data.per_event.map((r) => `${r.city}${r.event_id.startsWith("extra-") ? " (+show)" : ""}`);
  state.charts.scenario = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Baseline",
          data: data.per_event.map((r) => r.baseline_revenue),
          backgroundColor: "rgba(110, 168, 255, 0.75)",
        },
        {
          label: "Scenario",
          data: data.per_event.map((r) => r.scenario_revenue),
          backgroundColor: "rgba(63, 191, 173, 0.85)",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { ticks: { color: "#9aa5bd" } },
        y: {
          ticks: { color: "#9aa5bd", callback: (v) => fmt.usdCompact(v) },
          title: { display: true, text: "Revenue" },
        },
      },
      plugins: { legend: { position: "bottom", labels: { color: "#9aa5bd" } } },
    },
  });
}

$("#run-scenario").addEventListener("click", runScenario);

// ---------- OKR ----------
async function loadOkr() {
  const data = await api("/okr/summary");
  const tbody = $("#okr-table tbody");
  tbody.innerHTML = "";
  data.segments.forEach((s) => {
    const tr = document.createElement("tr");
    if (s.segment === data.default_segment) tr.classList.add("selected");
    tr.innerHTML = `
      <td>${s.segment}</td>
      <td class="num">${fmt.usdCompact(s.annual_revenue_target)}</td>
      <td class="num">${fmt.usdCompact(s.actual_revenue_to_date)}</td>
      <td class="num">${fmt.pct(s.revenue_progress_pct)}</td>
      <td class="num">${fmt.usdCompact(s.annual_margin_target)}</td>
      <td class="num">${fmt.usdCompact(s.actual_margin_to_date)}</td>
      <td class="num">${fmt.pct(s.margin_progress_pct)}</td>
      <td class="num">${s.events_counted}</td>
    `;
    tbody.appendChild(tr);
  });
}

// ---------- boot ----------
loadOverview().catch((err) => {
  console.error(err);
  document.body.insertAdjacentHTML(
    "afterbegin",
    `<div style="background:#c0392b;color:#fff;padding:12px;text-align:center">
      Failed to load workbench data. Run <code>python -m backend.seed</code> and refresh.
     </div>`
  );
});
