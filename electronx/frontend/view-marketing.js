/*
 * View 7 — Marketing ROI. "Which channel yields *active* accounts?"
 * Consumes: GET /api/marketing/roi?months=6.
 */
"use strict";

IG.views = IG.views || {};

IG.views.marketing = function renderMarketing(main) {
  const { html } = IG;
  IG.setHTML(main, html`
    <div class="view-head"><div class="q">Which marketing dollar produced an <em>active</em> account — not just a lead? Cost per Active is the number that matters; small-n channels are greyed.</div>
      <div class="actions"><span class="muted">Trailing 6 months</span></div></div>
    <div id="mk-body"></div>`);
  const body = IG.$("#mk-body");
  IG.load(body, () => IG.api(`/marketing/roi${IG.qs({ months: 6 })}`), (d) => drawMarketing(body, d), html`${IG.skeleton("tiles")}<div class="grid g-12 mt"><div class="card span-6">${IG.skeleton()}</div><div class="card span-6">${IG.skeleton()}</div></div>`);
};

function drawMarketing(body, d) {
  const { html, fmt } = IG;
  const ch = d.channels || [];
  const monthly = d.monthly || [];
  if (!ch.length) { IG.setHTML(body, html`<div class="card">${IG.emptyState("No channel data in this window.")}</div>`); return; }
  const sum = (k) => ch.reduce((s, c) => s + (IG.isNum(c[k]) ? c[k] : 0), 0);
  const spend = sum("spend"), active = sum("active"), funded = sum("funded"), adv = sum("adv");
  const big = ch.filter((c) => !c.n_small && IG.isNum(c.cac_active));
  const best = big.length ? big.reduce((a, b) => (b.cac_active < a.cac_active ? b : a)) : null;
  const worst = big.length ? big.reduce((a, b) => (b.cac_active > a.cac_active ? b : a)) : null;
  const metaCh = (IG.state.meta && IG.state.meta.channels) || [];
  const order = metaCh.length ? metaCh.concat(ch.map((c) => c.channel).filter((c) => !metaCh.includes(c))) : ch.map((c) => c.channel);
  const t = IG.theme();
  const colorOf = (name) => t.cat[Math.max(0, order.indexOf(name)) % 8];

  const sorted = ch.slice().sort((a, b) => (a.cac_active ?? Infinity) - (b.cac_active ?? Infinity));
  IG.setHTML(body, html`
    <div class="kpis">
      <article class="kpi compact"><div class="kpi-label">Spend</div><div class="kpi-value">${fmt.usd(spend)}</div><div class="kpi-meta">${ch.length} channels</div></article>
      <article class="kpi compact"><div class="kpi-label">Funded / Active</div><div class="kpi-value">${fmt.int(funded)} <small>/ ${fmt.int(active)}</small></div><div class="kpi-meta">${funded ? fmt.pct(active / funded, 0) + " of funded are Active" : ""}</div></article>
      <article class="kpi compact"><div class="kpi-label">Blended CAC per Active</div><div class="kpi-value">${active ? fmt.usd(spend / active) : "—"}</div><div class="kpi-meta">vs ${funded ? fmt.usd(spend / funded) : "—"} per funded</div></article>
      <article class="kpi compact on_track"><div class="kpi-label">Most efficient (n ≥ 5)</div><div class="kpi-value" style="font-size:16px;margin-top:8px">${best ? best.channel : "—"}</div><div class="kpi-meta">${best ? fmt.usd(best.cac_active) + " per Active" : ""}</div></article>
      <article class="kpi compact"><div class="kpi-label">ADV per $1k spend</div><div class="kpi-value">${spend ? fmt.num(adv / (spend / 1000), 1) : "—"}</div><div class="kpi-meta">contracts/day, blended</div></article>
    </div>
    <div class="grid g-12 mt">
      <section class="card span-6" aria-labelledby="mk-cac-t">
        <div class="card-h"><div><h2 id="mk-cac-t">Cost per Active account, by channel</h2><div class="sub">Lower is better · grey = fewer than 5 active accounts, not decision-grade</div></div></div>
        <div class="chart-box tall"><canvas id="mk-cac" role="img" aria-label="Customer acquisition cost per active account by channel"></canvas></div>
        ${best && worst && best !== worst ? html`<div class="footnote">Shifting $10k from ${worst.channel} to ${best.channel} buys ~${fmt.num(10000 / best.cac_active - 10000 / worst.cac_active, 1)} more Active accounts at current rates (illustrative, linear).</div>` : ""}
      </section>
      <section class="card span-6" aria-labelledby="mk-sp-t">
        <div class="card-h"><div><h2 id="mk-sp-t">Monthly spend by channel</h2><div class="sub">Stacked, USD</div></div></div>
        ${IG.legend(order.filter((c) => monthly.some((m) => m.channel === c)).map((c) => ({ label: c, color: colorOf(c) })))}
        <div class="chart-box">${monthly.length ? html`<canvas id="mk-spend" role="img" aria-label="Monthly marketing spend by channel"></canvas>` : IG.emptyState("No monthly spend.")}</div>
      </section>
      <section class="card span-12 flush" aria-labelledby="mk-t">
        <div class="card-h"><div><h2 id="mk-t">Channel funnel — lead to Active</h2><div class="sub">Sorted by cost per Active</div></div></div>
        <div class="table-wrap"><table class="t stackable">
          <thead><tr><th>Channel</th><th class="num">Spend</th><th class="num">Leads</th><th class="num">Signed</th><th class="num">Funded</th><th class="num">Active</th>
            <th class="num">CAC funded</th><th class="num">CAC active</th><th class="num">ADV</th><th class="num">ADV / $1k</th></tr></thead>
          <tbody>${sorted.map((c) => html`<tr class="${c.n_small ? "greyed" : ""}">
            <td data-l="Channel"><span class="side-tag"><i style="background:${c.n_small ? "var(--greyed)" : colorOf(c.channel)}"></i>${c.channel}</span>${c.n_small ? html` <span class="pill ghost" title="Fewer than 5 active accounts — treat as directional">small n</span>` : ""}</td>
            <td data-l="Spend" class="num">${fmt.usd(c.spend)}</td>
            <td data-l="Leads" class="num">${fmt.int(c.leads)}</td>
            <td data-l="Signed" class="num">${fmt.int(c.signed)}</td>
            <td data-l="Funded" class="num">${fmt.int(c.funded)}</td>
            <td data-l="Active" class="num"><b>${fmt.int(c.active)}</b></td>
            <td data-l="CAC funded" class="num">${fmt.usd(c.cac_funded)}</td>
            <td data-l="CAC active" class="num"><b>${fmt.usd(c.cac_active)}</b></td>
            <td data-l="ADV" class="num">${fmt.contracts(c.adv)}</td>
            <td data-l="ADV / $1k" class="num">${fmt.num(c.adv_per_1k_spend, 1)}</td></tr>`)}</tbody></table></div>
      </section>
    </div>`);

  const cacRows = sorted.filter((c) => IG.isNum(c.cac_active));
  IG.chart(IG.$("#mk-cac"), {
    type: "bar",
    data: { labels: cacRows.map((c) => c.channel), datasets: [{ label: "CAC per Active", data: cacRows.map((c) => c.cac_active), backgroundColor: cacRows.map((c) => (c.n_small ? t.greyed : t.series)), maxBarThickness: 22 }] },
    options: IG.baseOptions({
      indexAxis: "y",
      interaction: { mode: "nearest", axis: "y", intersect: false },
      scales: { x: IG.axis({ beginAtZero: true, fmt: (v) => fmt.usd(v), maxTicks: 6 }), y: IG.axis({ grid: false }) },
      plugins: { tooltip: { callbacks: { label: (c) => ` ${fmt.usdFull(c.parsed.x)} per Active`, afterLabel: (c) => { const r = cacRows[c.dataIndex]; return ` ${fmt.int(r.active)} active · ${fmt.usd(r.spend)} spend${r.n_small ? " · small n" : ""}`; } } } },
    }),
  });

  if (monthly.length) {
    const months = [...new Set(monthly.map((m) => m.month))].sort();
    const chans = order.filter((c) => monthly.some((m) => m.channel === c));
    IG.chart(IG.$("#mk-spend"), {
      type: "bar",
      data: {
        labels: months.map((m) => fmt.month(m)),
        datasets: chans.map((c) => ({
          label: c, stack: "s", backgroundColor: colorOf(c), maxBarThickness: 24, borderSkipped: false, borderRadius: 0, borderColor: t.surface, borderWidth: { top: 2 },
          data: months.map((m) => monthly.filter((x) => x.month === m && x.channel === c).reduce((s, x) => s + (x.spend || 0), 0)),
        })),
      },
      options: IG.baseOptions({
        scales: { x: IG.axis({ stacked: true, grid: false }), y: IG.axis({ stacked: true, beginAtZero: true, fmt: (v) => fmt.usd(v), maxTicks: 6 }) },
        plugins: { tooltip: { itemSort: (a, b) => b.datasetIndex - a.datasetIndex, callbacks: { label: (c) => ` ${c.dataset.label}: ${fmt.usd(c.parsed.y)}`, footer: (items) => `Total ${fmt.usd(items.reduce((s, i) => s + i.parsed.y, 0))}` } } },
      }),
    });
  }
}
