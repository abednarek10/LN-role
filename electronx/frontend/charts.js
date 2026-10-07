/*
 * Ignition — chart conventions on top of vendored Chart.js 4.4.4.
 * Colors are read from CSS tokens at render time, so a theme switch simply
 * re-renders the view. Conventions (see docs/DESIGN.md):
 *   - market side colors are fixed: hedger / speculator / liquidity partner
 *   - forecasts & targets are dashed; observed data is solid
 *   - one hue per magnitude (violet), ordinal violet ramp for funnel stages
 *   - 2px lines, ≤24px bars with 4px rounded data-ends, hairline solid grid
 */
"use strict";

IG.css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
IG.alpha = (color, a) => {
  const c = color.trim();
  if (c.startsWith("#")) {
    let h = c.slice(1);
    if (h.length === 3) h = h.split("").map((x) => x + x).join("");
    const n = parseInt(h, 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  }
  const m = c.match(/rgba?\(([^)]+)\)/);
  if (m) { const p = m[1].split(",").map((s) => s.trim()); return `rgba(${p[0]}, ${p[1]}, ${p[2]}, ${a})`; }
  return c;
};

IG.theme = () => {
  const v = (n) => IG.css(n);
  return {
    text: v("--text"), text2: v("--text-2"), muted: v("--muted"), grid: v("--grid"), axis: v("--axis"),
    surface: v("--surface"), accent: v("--accent-line"), series: v("--series"), greyed: v("--greyed"),
    hedger: v("--hedger"), speculator: v("--speculator"), lp: v("--lp"), hurt: v("--hurt"), opp: v("--opp"),
    good: v("--good"), warn: v("--warn"), crit: v("--crit"),
    ord: [v("--ord-1"), v("--ord-2"), v("--ord-3"), v("--ord-4")],
    cat: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => v(`--cat-${i}`)),
    font: v("--font") || "system-ui, sans-serif",
  };
};
IG.sideColor = (side) => {
  const t = IG.theme();
  return side === "hedger" ? t.hedger : side === "speculator" ? t.speculator : side === "liquidity_partner" ? t.lp : t.muted;
};

/* ------------------------------------------------------------ registry */
IG.chart = (canvas, config, scope = "view") => {
  if (!window.Chart || !canvas) return null;
  const c = new Chart(canvas, config);
  c.$igScope = scope;
  IG.state.charts.push(c);
  return c;
};
IG.destroyCharts = (scope = null) => {
  IG.state.charts = IG.state.charts.filter((c) => {
    if (scope && c.$igScope !== scope) return true;
    try { c.destroy(); } catch (_) { /* already gone */ }
    return false;
  });
};

/* ------------------------------------------------------------ defaults */
IG.applyChartDefaults = () => {
  if (!window.Chart) return;
  const t = IG.theme();
  const d = Chart.defaults;
  d.color = t.text2;
  d.borderColor = t.grid;
  d.font.family = t.font;
  d.font.size = 11;
  d.animation.duration = 350;
  d.maintainAspectRatio = false;
  d.responsive = true;
  d.plugins.legend.display = false; // we render HTML legends (accessible, consistent)
  const tt = d.plugins.tooltip;
  tt.backgroundColor = IG.css("--surface-3");
  tt.borderColor = IG.css("--border-strong");
  tt.borderWidth = 1;
  tt.titleColor = t.text;
  tt.bodyColor = t.text2;
  tt.footerColor = t.muted;
  tt.padding = 10;
  tt.cornerRadius = 8;
  tt.boxPadding = 4;
  tt.usePointStyle = true;
  tt.titleFont = { weight: "600", size: 12 };
  tt.bodyFont = { size: 12 };
  d.elements.line.borderWidth = 2;
  d.elements.line.tension = 0.25;
  d.elements.line.borderCapStyle = "round";
  d.elements.line.borderJoinStyle = "round";
  d.elements.point.radius = 0;
  d.elements.point.hoverRadius = 5;
  d.elements.point.hoverBorderWidth = 2;
  d.elements.point.borderColor = t.surface;
  d.elements.bar.borderRadius = 4;
  d.elements.bar.borderSkipped = "start";
  d.elements.arc.borderColor = t.surface;
  d.elements.arc.borderWidth = 2;
};

/** Axis builder: hairline solid grid, muted ticks, optional formatter. */
IG.axis = (opts = {}) => {
  const t = IG.theme();
  const a = {
    grid: { color: t.grid, drawTicks: false, display: opts.grid !== false },
    border: { display: opts.border ?? false, color: t.axis },
    ticks: { color: t.muted, padding: 6, maxRotation: 0, autoSkipPadding: 14, font: { size: 11 } },
    title: opts.title ? { display: true, text: opts.title, color: t.muted, font: { size: 11 } } : undefined,
  };
  if (opts.fmt) a.ticks.callback = function (v) { return opts.fmt(v); };
  ["min", "max", "suggestedMin", "suggestedMax", "beginAtZero", "type", "position", "stacked", "offset", "reverse"].forEach((k) => {
    if (opts[k] !== undefined) a[k] = opts[k];
  });
  if (opts.maxTicks) a.ticks.maxTicksLimit = opts.maxTicks;
  if (opts.stepSize) a.ticks.stepSize = opts.stepSize;
  return a;
};
IG.baseOptions = (extra = {}) => ({
  interaction: { mode: "index", intersect: false },
  layout: { padding: { top: 6, right: 6 } },
  ...extra,
  plugins: { ...(extra.plugins || {}) },
});

/* ------------------------------------------------------------ plugin: bands + vertical markers */
const bandsPlugin = {
  id: "igBands",
  beforeDatasetsDraw(chart, _args, opts) {
    const { ctx, chartArea: a, scales } = chart;
    const x = scales.x;
    if (!x || !opts) return;
    ctx.save();
    (opts.bands || []).forEach((b) => {
      const x0 = Math.max(a.left, x.getPixelForValue(b.x0));
      const x1 = Math.min(a.right, x.getPixelForValue(b.x1));
      if (x1 <= a.left || x0 >= a.right || x1 <= x0) return;
      ctx.fillStyle = b.color;
      ctx.fillRect(x0, a.top, Math.max(1, x1 - x0), a.bottom - a.top);
    });
    ctx.restore();
  },
  afterDatasetsDraw(chart, _args, opts) {
    const { ctx, chartArea: a, scales } = chart;
    const x = scales.x;
    if (!x || !opts) return;
    ctx.save();
    (opts.lines || []).forEach((l) => {
      const px = x.getPixelForValue(l.x);
      if (px < a.left || px > a.right) return;
      ctx.strokeStyle = l.color;
      ctx.lineWidth = 1;
      ctx.setLineDash(l.dash || [3, 3]);
      ctx.beginPath();
      ctx.moveTo(px, a.top);
      ctx.lineTo(px, a.bottom);
      ctx.stroke();
      if (l.label) {
        ctx.setLineDash([]);
        ctx.font = `600 11px ${IG.theme().font}`;
        const w = ctx.measureText(l.label).width + 10;
        const right = px + w + 4 > a.right;
        const lx = right ? px - w - 4 : px + 4;
        ctx.fillStyle = IG.css("--surface-3");
        ctx.strokeStyle = IG.css("--border-strong");
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(lx, a.top + 2, w, 18, 4); else ctx.rect(lx, a.top + 2, w, 18);
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = IG.css("--text");
        ctx.fillText(l.label, lx + 5, a.top + 15);
      }
    });
    (opts.hlines || []).forEach((l) => {
      const y = scales[l.axis || "y"];
      if (!y) return;
      const py = y.getPixelForValue(l.y);
      if (py < a.top || py > a.bottom) return;
      ctx.strokeStyle = l.color;
      ctx.lineWidth = 1.25;
      ctx.setLineDash(l.dash || [5, 4]);
      ctx.beginPath();
      ctx.moveTo(a.left, py);
      ctx.lineTo(a.right, py);
      ctx.stroke();
      if (l.label) {
        ctx.setLineDash([]);
        ctx.font = `600 10.5px ${IG.theme().font}`;
        ctx.fillStyle = IG.css("--text-2");
        const w = ctx.measureText(l.label).width;
        ctx.fillText(l.label, a.right - w - 4, py - 5);
      }
    });
    ctx.restore();
  },
};
document.addEventListener("DOMContentLoaded", () => {
  if (window.Chart) Chart.register(bandsPlugin);
});

/* ------------------------------------------------------------ sparkline (plain canvas; cheap for many tiles) */
IG.spark = (canvas, values, { color, target, emphasizeLast = true } = {}) => {
  if (!canvas) return;
  const vals = (values || []).filter(IG.isNum);
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || 160, h = canvas.clientHeight || 30;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);
  if (vals.length < 2) return;
  const all = IG.isNum(target) ? vals.concat([target]) : vals;
  let min = Math.min(...all), max = Math.max(...all);
  if (max === min) { max += 1; min -= 1; }
  const pad = 3;
  const X = (i) => pad + (i / (vals.length - 1)) * (w - pad * 2 - 4);
  const Y = (v) => h - pad - ((v - min) / (max - min)) * (h - pad * 2);
  const t = IG.theme();
  if (IG.isNum(target)) {
    ctx.strokeStyle = t.muted;
    ctx.setLineDash([3, 3]);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(pad, Y(target));
    ctx.lineTo(w - pad, Y(target));
    ctx.stroke();
    ctx.setLineDash([]);
  }
  const c = color || t.series;
  ctx.beginPath();
  vals.forEach((v, i) => (i ? ctx.lineTo(X(i), Y(v)) : ctx.moveTo(X(i), Y(v))));
  ctx.lineTo(X(vals.length - 1), h);
  ctx.lineTo(X(0), h);
  ctx.closePath();
  ctx.fillStyle = IG.alpha(c, 0.1);
  ctx.fill();
  ctx.beginPath();
  vals.forEach((v, i) => (i ? ctx.lineTo(X(i), Y(v)) : ctx.moveTo(X(i), Y(v))));
  ctx.strokeStyle = c;
  ctx.lineWidth = 1.6;
  ctx.lineJoin = "round";
  ctx.stroke();
  if (emphasizeLast) {
    const lx = X(vals.length - 1), ly = Y(vals[vals.length - 1]);
    ctx.beginPath();
    ctx.arc(lx, ly, 3.5, 0, Math.PI * 2);
    ctx.fillStyle = t.surface;
    ctx.fill();
    ctx.beginPath();
    ctx.arc(lx, ly, 2.5, 0, Math.PI * 2);
    ctx.fillStyle = c;
    ctx.fill();
  }
};

/** Shared tick formatters for linear time axes (ms epoch values). */
IG.tickDay = (v) => IG.fmt.date(new Date(v));
IG.tickDayHour = (v) => {
  const d = new Date(v);
  return d.getHours() === 0 ? IG.fmt.date(d) : `${String(d.getHours()).padStart(2, "0")}:00`;
};

/** Replace auto ticks on a linear ms axis with local midnights (one per day). */
IG.midnightTicks = (axis) => {
  const out = [];
  const d = new Date(axis.min);
  d.setHours(24, 0, 0, 0);
  for (; +d <= axis.max; d.setDate(d.getDate() + 1)) out.push({ value: +d });
  axis.ticks = out;
};

/** One tick per day at local noon, so a day's label sits over that day's hours (not at its midnight edge). */
IG.noonTicks = (axis) => {
  const out = [];
  const d = new Date(axis.min);
  d.setHours(12, 0, 0, 0);
  if (+d < axis.min) d.setDate(d.getDate() + 1);
  for (; +d <= axis.max; d.setDate(d.getDate() + 1)) out.push({ value: +d });
  axis.ticks = out;
};
