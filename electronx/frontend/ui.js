/*
 * Ignition — core UI helpers (no framework, no build).
 *   IG.api         fetch wrapper (GET cache, readable errors)
 *   IG.html / raw  escaped template literals
 *   IG.fmt         number / money / date formatting
 *   IG.load        skeleton -> data -> render | error state, per slot
 *   IG.drawer      accessible right-hand drawer (Esc closes, focus trap)
 *   IG.toast       transient status message
 * All views are plain functions that write into #main.
 */
"use strict";

const IG = (window.IG = window.IG || {});
IG.state = {
  meta: null,
  routeToken: 0,
  charts: [],
  pulse: { iso: null, hub: null, trigger: null },
  queue: { filters: {}, expanded: new Set() },
  lastQueued: null,
  queued: new Set(),
};

/* ------------------------------------------------------------ DOM + templating */
IG.$ = (sel, root = document) => root.querySelector(sel);
IG.$$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

class Raw {
  constructor(s) { this.s = s; }
  toString() { return this.s; }
}
IG.raw = (s) => new Raw(String(s ?? ""));
const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
IG.esc = (s) => String(s).replace(/[&<>"']/g, (c) => ESC[c]);
function renderVal(v) {
  if (v == null || v === false) return "";
  if (v instanceof Raw) return v.s;
  if (Array.isArray(v)) return v.map(renderVal).join("");
  return IG.esc(String(v));
}
/** Tagged template: interpolations are escaped unless wrapped in IG.raw / nested IG.html. */
IG.html = (strings, ...vals) => {
  let out = "";
  strings.forEach((s, i) => {
    out += s;
    if (i < vals.length) out += renderVal(vals[i]);
  });
  return new Raw(out);
};
IG.setHTML = (el, h) => { el.innerHTML = String(h); return el; };
IG.icon = (id, cls = "") => IG.raw(`<svg class="${cls}" aria-hidden="true"><use href="#i-${id}"/></svg>`);

/* ------------------------------------------------------------ API */
const GET_CACHE = new Map();
const CACHE_MS = 60_000;
IG.api = async function api(path, opts = {}) {
  const method = (opts.method || "GET").toUpperCase();
  const key = path;
  if (method === "GET" && !opts.fresh) {
    const hit = GET_CACHE.get(key);
    if (hit && Date.now() - hit.t < CACHE_MS) return hit.p;
  }
  const p = (async () => {
    const init = { method, headers: { Accept: "application/json" } };
    if (opts.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body);
    }
    let res;
    try {
      res = await fetch("/api" + path, init);
    } catch (e) {
      throw new Error(`Network error calling /api${path} — is the Ignition API running? (${e.message})`);
    }
    const text = await res.text();
    if (!res.ok) {
      let msg = text;
      try {
        const j = JSON.parse(text);
        msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
      } catch (_) { /* not JSON */ }
      throw new Error(`${res.status} ${res.statusText || ""} · /api${path}${msg ? " — " + String(msg).slice(0, 300) : ""}`.replace(/\s+·/, " ·"));
    }
    try {
      return text ? JSON.parse(text) : {};
    } catch (e) {
      throw new Error(`Malformed JSON from /api${path}`);
    }
  })();
  if (method === "GET") {
    GET_CACHE.set(key, { t: Date.now(), p });
    p.catch(() => GET_CACHE.delete(key));
  } else {
    GET_CACHE.clear(); // any write may change rankings / touches
  }
  return p;
};
IG.clearCache = () => GET_CACHE.clear();
IG.qs = (obj) => {
  const p = Object.entries(obj || {}).filter(([, v]) => v !== "" && v != null);
  return p.length ? "?" + p.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&") : "";
};

/** Download a server-rendered text file (memo / ticket) with a friendly filename. */
IG.download = async function download(path, filename, btn) {
  const label = btn ? btn.innerHTML : null;
  if (btn) { btn.disabled = true; btn.textContent = "Preparing…"; }
  try {
    const res = await fetch("/api" + path);
    if (!res.ok) throw new Error(`${res.status} · /api${path}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(new Blob([blob], { type: "text/markdown" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    IG.toast(IG.html`Downloaded <b>${filename}</b>`);
  } catch (e) {
    IG.toast(IG.html`Export failed: ${e.message}`, { error: true });
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = label; }
  }
};

/* ------------------------------------------------------------ formatting */
const isNum = (v) => typeof v === "number" && Number.isFinite(v);
IG.isNum = isNum;
const nf0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DASH = "—";

/** Parse naive timestamps / dates as local wall-clock (the API is naive UTC; we never shift it). */
IG.parseTs = (s) => {
  if (s == null) return null;
  if (s instanceof Date) return s;
  if (typeof s === "number") return new Date(s);
  const str = String(s);
  const d = /^\d{4}-\d{2}-\d{2}$/.test(str) ? new Date(str + "T00:00:00") : new Date(str.replace(/Z$/, ""));
  return isNaN(d) ? null : d;
};

IG.fmt = {
  /** $ with k / M suffix. */
  usd(v, { digits } = {}) {
    if (!isNum(v)) return DASH;
    const a = Math.abs(v), s = v < 0 ? "-" : "";
    if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(digits ?? 2)}B`;
    if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(digits ?? 2)}M`;
    if (a >= 1e4) return `${s}$${(a / 1e3).toFixed(digits ?? 0)}k`;
    if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(digits ?? 1)}k`;
    return `${s}$${nf0.format(a)}`;
  },
  usdFull: (v) => (isNum(v) ? (v < 0 ? "-$" : "$") + nf0.format(Math.abs(v)) : DASH),
  /** $/MWh price: whole dollars when large, cents when small. */
  price(v) {
    if (!isNum(v)) return DASH;
    const a = Math.abs(v), s = v < 0 ? "-" : "";
    return `${s}$${a >= 100 ? nf0.format(a) : nf2.format(a)}`;
  },
  spread: (v) => (isNum(v) ? `$${nf2.format(v)}` : DASH),
  int: (v) => (isNum(v) ? nf0.format(v) : DASH),
  num: (v, d = 1) => (isNum(v) ? new Intl.NumberFormat("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }).format(v) : DASH),
  /** Contracts with thousands separators; compact=true -> 15.8k. */
  contracts(v, compact = false) {
    if (!isNum(v)) return DASH;
    if (compact && Math.abs(v) >= 10_000) return nf1.format(v / 1000) + "k";
    return nf0.format(v);
  },
  /** Rate (0–1 per the API contract) -> "62.1%". Ratios above 1 (attainment 1.17) -> "117%". */
  pct(v, d = 1) {
    if (!isNum(v)) return DASH;
    return `${(v * 100).toFixed(d)}%`;
  },
  /** Probabilities are displayed capped: never "100%" for a model output (X11). */
  prob(v) {
    if (!isNum(v)) return DASH;
    if (v > 0.95) return ">95%";
    if (v < 0.01) return "<1%";
    return `${Math.round(v * 100)}%`;
  },
  /** For fields literally named *_pct, which may arrive as 0–1 or 0–100. */
  pctAuto(v, d = 1) {
    if (!isNum(v)) return DASH;
    return `${(Math.abs(v) > 1.5 ? v : v * 100).toFixed(d)}%`;
  },
  /** Signed percentage-point delta for rates. */
  pp(v, d = 1) {
    if (!isNum(v)) return DASH;
    const p = Math.abs(v) > 1.5 ? v : v * 100;
    return `${p > 0 ? "+" : ""}${p.toFixed(d)} pp`;
  },
  mult: (v, d = 1) => (isNum(v) ? `${v.toFixed(d)}×` : DASH),
  days: (v) => (isNum(v) ? `${v >= 10 || Number.isInteger(v) ? nf0.format(v) : nf1.format(v)} d` : DASH),
  relDays(n) {
    if (n == null || !isNum(n)) return "never";
    if (n <= 0) return "today";
    if (n === 1) return "1 day ago";
    if (n < 60) return `${Math.round(n)} days ago`;
    return `${Math.round(n / 30)} mo ago`;
  },
  date(s, withYear = false) {
    const d = IG.parseTs(s);
    if (!d) return DASH;
    return `${MONTHS[d.getMonth()]} ${d.getDate()}${withYear ? ", " + d.getFullYear() : ""}`;
  },
  dateTime(s) {
    const d = IG.parseTs(s);
    if (!d) return DASH;
    return `${MONTHS[d.getMonth()]} ${d.getDate()}, ${String(d.getHours()).padStart(2, "0")}:00`;
  },
  month(s) {
    const d = IG.parseTs(s);
    return d ? `${MONTHS[d.getMonth()]} ’${String(d.getFullYear()).slice(2)}` : DASH;
  },
  humanize: (s) => String(s ?? "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()).replace(/\bAdv\b/g, "ADV").replace(/\bLp\b/g, "LP").replace(/\bSla\b/g, "SLA").replace(/\bKyc\b/g, "KYC").replace(/\bApi\b/g, "API").replace(/\bIso\b/g, "ISO"),
};

/** Format a KPI value by its declared unit (spec: unit is free text — tolerate variants). */
IG.fmtUnit = (v, unit) => {
  const u = String(unit || "").toLowerCase();
  if (!isNum(v)) return DASH;
  if (/usd_?mwh|\$\/mwh|per_mwh/.test(u)) return IG.fmt.spread(v);
  if (/usd|\$|dollar|revenue/.test(u)) return IG.fmt.usd(v);
  if (/pct|percent|%/.test(u)) return IG.fmt.pctAuto(v);
  if (/rate|share|ratio/.test(u)) return IG.fmt.pct(v);
  if (/day/.test(u)) return IG.fmt.days(v);
  if (/^x$|multiple|lift/.test(u)) return IG.fmt.mult(v);
  if (/contract/.test(u)) return IG.fmt.contracts(v, true);
  if (Number.isInteger(v)) return IG.fmt.int(v);
  return IG.fmt.num(v, Math.abs(v) < 10 ? 2 : 0);
};
IG.fmtDelta = (v, unit) => {
  const u = String(unit || "").toLowerCase();
  if (!isNum(v)) return "";
  if (/pct|percent|rate|share|ratio|%/.test(u)) return IG.fmt.pp(v);
  const s = v > 0 ? "+" : v < 0 ? "-" : "±";
  return s + IG.fmtUnit(Math.abs(v), unit).replace(/^-/, "");
};
/** Metrics where a lower number is the good direction. */
IG.lowerIsBetter = (key, label = "") => /spread|days|top5|top_5|concentration|hhi|cac|churn|breach|stall|dormant|at_risk|brier/i.test(String(key) + " " + label);

/* ------------------------------------------------------------ meta lookups */
const SIDE_LABEL = { hedger: "Hedger", speculator: "Speculator", liquidity_partner: "Liquidity partner" };
IG.sideLabel = (s) => SIDE_LABEL[s] || IG.fmt.humanize(s || "—");
IG.segInfo = (code) => {
  const segs = (IG.state.meta && IG.state.meta.segments) || [];
  return segs.find((s) => s.code === code) || { code, label: IG.fmt.humanize(code || "—"), side: null };
};
IG.segLabel = (code) => IG.segInfo(code).label;
IG.repName = (id) => {
  const r = ((IG.state.meta && IG.state.meta.reps) || []).find((x) => String(x.id) === String(id));
  return r ? r.name : id == null ? "Unassigned" : `Rep ${id}`;
};
const REGIME = { scarcity: "Scarcity", negative_price: "Negative price", winter_peak: "Winter peak", elevated_vol: "Elevated vol" };
IG.regimeLabel = (r) => REGIME[r] || IG.fmt.humanize(r);
const STATUS = { on_track: "On track", watch: "Watch", off_track: "Off track", info: "Info" };

/* ------------------------------------------------------------ small components */
IG.sideTag = (side, text) => IG.html`<span class="side-tag"><i class="${side || ""}"></i>${text ?? IG.sideLabel(side)}</span>`;
const SHORT_SEG = { IPP: "IPP", STORAGE: "Storage", REP: "Retail (REP)", CI_LOAD: "C&I load", UTILITY: "Utility / co-op", DATACENTER: "Data center", PROP: "Prop trading", FUND: "Hedge fund" };
IG.segShort = (code) => SHORT_SEG[code] || IG.segLabel(code);
IG.segTag = (code, side, short = false) => {
  const info = IG.segInfo(code);
  const s = side || info.side;
  return IG.html`<span class="side-tag" title="${info.label} · ${IG.sideLabel(s)}"><i class="${s || ""}"></i>${short ? IG.segShort(code) : info.label}</span>`;
};
IG.stagePill = (stage) => IG.html`<span class="stage">${String(stage || "—").replace(/_/g, " ")}</span>`;
IG.statusPill = (status) => {
  const icon = status === "on_track" ? "✓" : status === "off_track" ? "!" : status === "watch" ? "~" : "";
  return status
    ? IG.html`<span class="pill ${status}" title="Status: ${STATUS[status] || status}"><span class="dot"></span>${STATUS[status] || IG.fmt.humanize(status)}<span class="sr-only"> ${icon}</span></span>`
    : "";
};
IG.dirPill = (dir) =>
  dir === "opportunity"
    ? IG.html`<span class="pill opp" title="Long the spike: the event is an opportunity"><span class="arrow">▲</span>Opportunity</span>`
    : IG.html`<span class="pill hurt" title="Short the spike: the event hurts this account"><span class="arrow">▼</span>Hurt</span>`;
/* Health-state vocabulary (spec X2) — one function used everywhere. */
const HEALTH = {
  pre_funding: { cls: "ghost", label: "Pre-funding", def: "Signed or in KYC; not yet funded." },
  not_started: { cls: "warn", label: "No trades yet", def: "Funded, never traded." },
  ramping: { cls: "ramp", label: "Ramping", def: "First trade ≤14 days ago and ≥2 trading days in the last 30." },
  active: { cls: "good", label: "Active", def: "≥4 distinct trading days in the trailing 30." },
  expanding: { cls: "good", label: "Expanding", def: "Active and growing ADV or footprint." },
  at_risk: { cls: "serious", label: "At risk", def: "1–3 trading days in the trailing 30." },
  dormant: { cls: "crit", label: "Dormant", def: "Previously traded; 0 trades in the trailing 30." },
};
IG.healthInfo = (state) => HEALTH[String(state || "").toLowerCase()] || { cls: "", label: IG.fmt.humanize(state || "unknown"), def: "" };
/** fundedDays: optional, renders "No trades yet · funded N d". */
IG.healthPill = (state, fundedDays) => {
  if (!state) return "";
  const h = IG.healthInfo(state);
  const label = state === "not_started" && IG.isNum(fundedDays) ? `${h.label} · funded ${Math.round(fundedDays)} d` : h.label;
  return IG.html`<span class="pill ${h.cls}" title="${h.def}"><span class="dot"></span>${label}</span>`;
};
IG.daysSince = (ts) => {
  const d = IG.parseTs(ts);
  const asof = IG.parseTs((IG.state.meta && IG.state.meta.as_of) || null) || new Date();
  return d ? (asof - d) / 864e5 : null;
};
IG.acct = (id, name) => (id == null ? IG.html`<span>${name}</span>` : IG.html`<button type="button" class="acct" data-acct="${id}" title="Open Account 360">${name || "Account " + id}</button>`);
IG.bar = (frac, label, cls = "") => {
  const w = Math.max(0, Math.min(1, isNum(frac) ? frac : 0)) * 100;
  return IG.html`<div class="bar-cell"><div class="bar-track"><div class="bar-fill ${cls}" style="width:${w.toFixed(1)}%"></div></div><span class="v">${label}</span></div>`;
};
IG.legend = (items) =>
  IG.html`<div class="legend">${items.map((it) => IG.html`<span><i class="${it.kind || ""}" style="${it.kind === "dash" ? `color:${it.color}` : `background:${it.color}`}"></i>${it.label}</span>`)}</div>`;

/* ------------------------------------------------------------ states */
IG.skeleton = (kind = "chart") => {
  if (kind === "tiles") return IG.html`<div class="kpis">${Array.from({ length: 5 }, () => IG.raw('<div class="skel skel-tile"></div>'))}</div>`;
  if (kind === "table") return IG.html`<div>${Array.from({ length: 7 }, (_, i) => IG.raw(`<div class="skel skel-line" style="width:${96 - (i % 3) * 9}%"></div>`))}</div>`;
  if (kind === "lines") return IG.html`<div>${Array.from({ length: 3 }, (_, i) => IG.raw(`<div class="skel skel-line" style="width:${92 - i * 14}%"></div>`))}</div>`;
  return IG.raw('<div class="skel skel-chart"></div>');
};
IG.emptyState = (msg, sub = "") =>
  IG.html`<div class="state"><div class="ico">${IG.icon("inbox")}</div><div>${msg}</div>${sub ? IG.html`<div class="muted">${sub}</div>` : ""}</div>`;
IG.errorState = (err) =>
  IG.html`<div class="state error" role="alert"><div class="ico">${IG.icon("alert")}</div><div><b>Couldn’t load this panel.</b></div><code>${err && err.message ? err.message : String(err)}</code><button type="button" class="btn sm" data-retry>Retry</button></div>`;

/**
 * Load data into a slot: skeleton first, then render(data) or an error state with Retry.
 * Ignores results that land after the user navigated away (route token).
 */
IG.load = async function load(el, fetcher, render, skeletonKind = "chart") {
  if (!el) return;
  const token = IG.state.routeToken;
  if (skeletonKind !== null) IG.setHTML(el, typeof skeletonKind === "string" ? IG.skeleton(skeletonKind) : skeletonKind);
  try {
    const data = await fetcher();
    if (token !== IG.state.routeToken || !el.isConnected) return;
    await render(data, el);
  } catch (e) {
    if (token !== IG.state.routeToken || !el.isConnected) return;
    console.warn("[Ignition]", e);
    IG.setHTML(el, IG.errorState(e));
    const b = el.querySelector("[data-retry]");
    if (b) b.addEventListener("click", () => IG.load(el, fetcher, render, skeletonKind));
  }
};

/* ------------------------------------------------------------ toast */
IG.toast = (content, { error = false, timeout = 5200 } = {}) => {
  const host = IG.$("#toasts");
  const t = document.createElement("div");
  t.className = "toast" + (error ? " err" : "");
  IG.setHTML(t, IG.html`<span class="ok" aria-hidden="true">${error ? "!" : "✓"}</span><span>${content}</span>`);
  host.appendChild(t);
  setTimeout(() => t.remove(), timeout);
  return t;
};

/* ------------------------------------------------------------ drawer */
IG.drawer = (() => {
  let lastFocus = null;
  let onClose = null;
  const el = () => IG.$("#drawer");
  const scrim = () => IG.$("#scrim");
  function open(content, { narrow = false, label = "Details", onClose: oc = null } = {}) {
    const d = el();
    if (!d.classList.contains("open")) lastFocus = document.activeElement;
    onClose = oc;
    d.classList.toggle("narrow", narrow);
    IG.setHTML(d, content);
    d.setAttribute("aria-hidden", "false");
    d.setAttribute("aria-label", label);
    d.classList.add("open");
    const s = scrim();
    s.hidden = false;
    requestAnimationFrame(() => s.classList.add("open"));
    const f = d.querySelector("[data-autofocus]") || d.querySelector(".close") || d;
    setTimeout(() => f.focus(), 30);
    return d;
  }
  function close() {
    const d = el();
    if (!d.classList.contains("open")) return;
    d.classList.remove("open");
    d.setAttribute("aria-hidden", "true");
    const s = scrim();
    s.classList.remove("open");
    setTimeout(() => { s.hidden = true; }, 200);
    IG.destroyCharts("drawer");
    if (onClose) { const f = onClose; onClose = null; f(); }
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  const isOpen = () => el().classList.contains("open");
  return { open, close, isOpen, el };
})();
/** Standard drawer header markup. */
IG.drawerHead = (title, sub = "") =>
  IG.html`<div class="drawer-h"><div><h2 id="drawer-title">${title}</h2>${sub ? IG.html`<div class="row" style="margin-top:6px">${sub}</div>` : ""}</div>
  <button type="button" class="icon-btn close" data-close aria-label="Close panel (Esc)">${IG.icon("x")}</button></div>`;

/* ------------------------------------------------------------ metric definitions (tooltips) */
IG.DEF = {
  adv: "ADV = Σ contracts over the trailing 20 trading days ÷ 20. Excludes self-matches; liquidity-partner volume reported separately.",
  active: "Active = ≥4 distinct trading days in the trailing 30 calendar days. At-Risk = 1–3. Dormant = funded ≥30 d, 0 trades in 30 d.",
  active_rate: "Active accounts ÷ funded accounts older than 20 days.",
  cohort: "Share of accounts funded in the cohort week whose first qualifying trade (≥10 contracts, no self-match) came within 30 days. Cohorts with n < 20 are greyed.",
  priority: "Priority = P(Active ≤60d) × E[ADV] × k_stage × urgency U (cap 2.0) × balance weight B (hedgers ×1.15 while hedger share of Active < 50%).",
  p_active: "Calibrated probability the account becomes Active within 60 days of the scoring snapshot. Displayed capped at >95%.",
  touch_value: "Expected value of a touch now: P(Active) × E[ADV] × exposure, ranked within the event.",
  exp_adv: "Expected ADV (contracts/day) if the account activates — segment prior updated with sizing data.",
  adv_at_stake: "ADV at stake = Σ P(Active) × E[ADV] across the accounts in scope, in contracts/day.",
  spread: "Time-weighted median top-of-book spread ($/MWh), 07:00–19:00 local; uptime = share of minutes with a two-sided quote ≥25 contracts deep.",
  top5: "Top-5 accounts’ share of ADV. Target ≤45%.",
  hhi: "Herfindahl–Hirschman index of ADV by account (0–1).",
  vol_z: "Volatility z-score: how many standard deviations the recent price move sits above the 30-day norm.",
  lift: "Activation within 14 days for accounts that received triggered outreach vs comparable untriggered accounts.",
};
IG.kpiDef = (key = "", label = "") => {
  const k = (key + " " + label).toLowerCase();
  if (/cohort/.test(k)) return IG.DEF.cohort;
  if (/active_rate|active rate/.test(k)) return IG.DEF.active_rate;
  if (/spread/.test(k)) return IG.DEF.spread;
  if (/top5|top-5|top_5/.test(k)) return IG.DEF.top5;
  if (/hhi/.test(k)) return IG.DEF.hhi;
  if (/adv/.test(k)) return IG.DEF.adv;
  if (/hedger/.test(k)) return "Hedger accounts as a share of Active accounts. Target ≥50%. " + IG.DEF.active;
  if (/fee/.test(k)) return "Σ exchange fees, trailing 20 trading days.";
  if (/days/.test(k)) return "Median days from funding to first qualifying trade (≥10 contracts).";
  if (/funded/.test(k)) return "Accounts that have deposited collateral (cumulative).";
  return label;
};
