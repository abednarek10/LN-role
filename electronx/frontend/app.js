/*
 * Ignition — app shell: hash router, nav, theme, account search, keyboard.
 * Routes: #/ceo #/pulse #/queue(/model) #/funnel #/team #/segments #/marketing
 * Account 360 opens as a drawer from any [data-acct] element.
 */
"use strict";

const ROUTES = [
  { id: "ceo", label: "CEO Weekly", icon: "ceo", title: "CEO Weekly", crumb: "Are signatures becoming liquidity?" },
  { id: "pulse", label: "Market Pulse", icon: "pulse", title: "Market Pulse", crumb: "Where is power hurting — and who’s exposed?" },
  { id: "queue", label: "Activation Queue", icon: "queue", title: "Activation Queue", crumb: "Who do I touch next, with what?" },
  { id: "funnel", label: "Funnel & Journey", icon: "funnel", title: "Funnel & Journey", crumb: "Which step leaks, and what does it cost?" },
  { id: "team", label: "Team & Comp", icon: "team", title: "Team & Comp", crumb: "Does comp pay for volume or signatures?" },
  { id: "segments", label: "Segments", icon: "segments", title: "Segments", crumb: "Where is the unworked value?" },
  { id: "marketing", label: "Marketing ROI", icon: "roi", title: "Marketing ROI", crumb: "Which channel yields active accounts?" },
];

function buildNav() {
  const { html } = IG;
  IG.setHTML(IG.$("#nav"), html`${ROUTES.map((r, i) => html`<li><a class="nav-link" href="#/${r.id}" data-route="${r.id}" title="${r.label} (${i + 1})">
    <svg class="nav-ico" aria-hidden="true"><use href="#i-${r.icon}"/></svg><span class="nav-label">${r.label}</span><span class="nav-num" aria-hidden="true">${i + 1}</span></a></li>`)}`);
}

function parseHash() {
  const h = (location.hash || "").replace(/^#\/?/, "");
  const [id, sub] = h.split("/");
  const r = ROUTES.find((x) => x.id === id);
  return { route: r || ROUTES[0], sub: sub || null, valid: !!r };
}

function navigate() {
  const { route, sub, valid } = parseHash();
  if (!valid) { history.replaceState(null, "", "#/" + route.id); }
  IG.state.routeToken++;
  IG.destroyCharts();
  if (IG.drawer.isOpen()) IG.drawer.close();
  IG.$$(".nav-link").forEach((a) => (a.dataset.route === route.id ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  IG.$("#view-title").textContent = route.title;
  IG.$("#view-crumb").textContent = route.crumb;
  document.title = `${route.title} · Ignition`;
  const main = IG.$("#main");
  const render = IG.views[route.id];
  try {
    render(main, sub);
  } catch (e) {
    console.error(e);
    IG.setHTML(main, IG.errorState(e));
  }
  main.scrollTop = 0;
  window.scrollTo(0, 0);
}

/* ---------------------------------------------------------------- theme */
function currentTheme() { return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark"; }
function setTheme(t, rerender = true) {
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem("ignition.theme", t); } catch (_) { /* storage blocked */ }
  const btn = IG.$("#theme-toggle");
  IG.setHTML(btn, IG.html`<svg aria-hidden="true"><use href="#i-${t === "dark" ? "sun" : "moon"}"/></svg>`);
  btn.setAttribute("aria-label", `Switch to ${t === "dark" ? "light" : "dark"} theme`);
  IG.applyChartDefaults();
  if (rerender) {
    // Charts read tokens at render time: re-render the view (GETs are cached) and the open drawer.
    const reopen = IG.drawer.isOpen() ? IG.state.acctOpenId : null;
    navigate();
    if (reopen != null) IG.openAccount(reopen);
  }
}

/* ---------------------------------------------------------------- account search */
function wireSearch() {
  const input = IG.$("#acct-search");
  const box = IG.$("#acct-results");
  let t = null;
  let seq = 0;
  const close = () => { box.hidden = true; input.setAttribute("aria-expanded", "false"); };
  input.addEventListener("input", () => {
    clearTimeout(t);
    const q = input.value.trim();
    if (q.length < 2) { close(); return; }
    t = setTimeout(async () => {
      const my = ++seq;
      try {
        const d = await IG.api(`/accounts${IG.qs({ q, limit: 8 })}`);
        if (my !== seq) return;
        const items = d.items || [];
        IG.setHTML(box, items.length
          ? IG.html`${items.map((a) => IG.html`<button type="button" data-acct="${a.id}"><b>${a.name}</b><span class="muted" style="margin-left:auto;font-size:11.5px">${IG.segLabel(a.segment)} · ${a.iso || ""} · ${String(a.stage || "").replace(/_/g, " ")}</span></button>`)}`
          : IG.html`<div class="muted" style="padding:8px">No accounts match “${q}”.</div>`);
      } catch (e) {
        IG.setHTML(box, IG.html`<div class="muted" style="padding:8px">Search unavailable: ${e.message}</div>`);
      }
      box.hidden = false;
      input.setAttribute("aria-expanded", "true");
    }, 180);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { const f = box.querySelector("button"); if (f) { e.preventDefault(); f.focus(); } }
    if (e.key === "Escape") { close(); input.blur(); }
  });
  box.addEventListener("keydown", (e) => {
    const btns = IG.$$("button", box);
    const i = btns.indexOf(document.activeElement);
    if (e.key === "ArrowDown" && i < btns.length - 1) { e.preventDefault(); btns[i + 1].focus(); }
    if (e.key === "ArrowUp") { e.preventDefault(); (i > 0 ? btns[i - 1] : input).focus(); }
    if (e.key === "Escape") { close(); input.focus(); }
  });
  document.addEventListener("click", (e) => { if (!e.target.closest(".search")) close(); });
  box.addEventListener("click", (e) => { if (e.target.closest("[data-acct]")) { close(); input.value = ""; } });
}

/* ---------------------------------------------------------------- keyboard */
function wireKeys() {
  document.addEventListener("keydown", (e) => {
    const d = IG.drawer.el();
    if (e.key === "Escape" && IG.drawer.isOpen()) { e.preventDefault(); IG.drawer.close(); return; }
    if (e.key === "Tab" && IG.drawer.isOpen()) {
      // focus trap inside the drawer
      const f = IG.$$('a[href], button:not([disabled]), input, select, textarea, summary, [tabindex]:not([tabindex="-1"])', d).filter((x) => x.offsetParent !== null);
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      return;
    }
    const tag = (e.target.tagName || "").toLowerCase();
    if (["input", "select", "textarea"].includes(tag) || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "/") { e.preventDefault(); IG.$("#acct-search").focus(); return; }
    const n = parseInt(e.key, 10);
    if (n >= 1 && n <= ROUTES.length && !IG.drawer.isOpen()) location.hash = "#/" + ROUTES[n - 1].id;
  });
  // Roving arrows within the nav list
  IG.$("#nav").addEventListener("keydown", (e) => {
    if (!["ArrowDown", "ArrowUp"].includes(e.key)) return;
    const links = IG.$$(".nav-link");
    const i = links.indexOf(document.activeElement);
    if (i < 0) return;
    e.preventDefault();
    links[(i + (e.key === "ArrowDown" ? 1 : links.length - 1)) % links.length].focus();
  });
}

/* ---------------------------------------------------------------- boot */
async function boot() {
  buildNav();
  setTheme(currentTheme(), false);
  wireSearch();
  wireKeys();
  IG.$("#theme-toggle").addEventListener("click", () => setTheme(currentTheme() === "dark" ? "light" : "dark"));
  IG.$("#scrim").addEventListener("click", () => IG.drawer.close());
  document.addEventListener("click", (e) => {
    const a = e.target.closest("[data-acct]");
    if (a) { e.preventDefault(); IG.openAccount(a.dataset.acct); }
  });
  window.addEventListener("hashchange", navigate);

  try {
    IG.state.meta = await IG.api("/meta");
    const m = IG.state.meta;
    IG.setHTML(IG.$("#asof"), IG.html`As of <b>${IG.fmt.date(m.as_of, true)}</b>${m.week_end ? IG.html` <span class="muted">· week ending ${IG.fmt.date(m.week_end)}</span>` : ""}`);
  } catch (e) {
    console.warn("[Ignition] /api/meta failed", e);
    IG.state.meta = { segments: [], isos: { ERCOT: [], PJM: [], CAISO: [], MISO: [] }, stages: [], steps: [], channels: [], reps: [], targets: {} };
    IG.setHTML(IG.$("#asof"), IG.html`<span class="pill crit" title="${e.message}"><span class="dot"></span>API offline</span>`);
    IG.toast(IG.html`Couldn’t reach the Ignition API: ${e.message}`, { error: true, timeout: 9000 });
  }
  if (!location.hash) history.replaceState(null, "", "#/ceo");
  navigate();
}

document.addEventListener("DOMContentLoaded", boot);
