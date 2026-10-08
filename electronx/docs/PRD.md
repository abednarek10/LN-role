# PRD — Ignition: ElectronX Activation & Revenue OS

**Status:** Draft v1.1 · **Owner:** Head of GTM & Revenue (candidate) · **Data:** synthetic, illustrative

## 1. Problem

ElectronX is live in ERCOT, PJM, CAISO and MISO and already has a pipeline. Signing accounts is no longer the bottleneck; **getting signed accounts funded and trading regularly** is. An exchange earns nothing from dormant accounts, and every active trader tightens spreads for the next one. Today the GTM team of 4 has:

- no way to rank which accounts to work, so rep time is spread evenly;
- no link between power-price events (e.g. an ERCOT scarcity spike), the best moment to talk hedging, and the accounts exposed to them;
- no instrumented view of where onboarding stalls (KYC, funding, first order);
- manual weekly reporting to the CEO;
- comp that pays on signatures, not on trading activity.

## 2. Goal and success metrics (EOY 2026)

| Metric | Today (synthetic) | Target |
|---|---|---|
| Funded accounts | ~198 | 260 |
| Funded accounts actively trading (≥4 trading days in last 30) | ~60% | ≥70% |
| 30-day first-trade activation per funding cohort | ~54% | 70% |
| Avg daily volume (contracts) | ~15.4k | 25k |
| Median days funded → first trade | ~25–29 | ≤10 |
| Hedger share of active accounts | ~44% | ≥50% |

## 3. Users

CEO (weekly market health), Head of GTM (pipeline, team, plan), Account Executives (who to call and what to say), RevOps (stalls, CRM hygiene), Marketing Manager (spend → funded accounts), Head of Product (onboarding friction).

## 4. Scope — v1 (built)

| Module | What it does |
|---|---|
| **CEO Weekly** | KPI tiles vs targets, 3-sentence board narrative + 3 decisions, account/volume mix (hedger / speculator / liquidity partner), spread quality, cohort activation, stalled accounts; export memo as Markdown. |
| **Market Pulse** | Detects price spikes / volatility per hub, lists exposed accounts (hurt vs. opportunity), drafts compliance-checked outreach referencing the event; approve → queue → logged touch. Shows measured lift of triggered outreach (~2.5×). |
| **Activation Queue** | Ranks accounts by expected value of a touch = P(active in 60d) × expected volume × stage factor × urgency × hedger-balance weight; next-best action from a 17-rule playbook; explainable "why". Model panel with honest accuracy. |
| **Funnel & Journey** | Onboarding step conversion and dwell time by segment; auto-flags friction and exports a priced roadmap ticket for Product. |
| **Team & Comp** | AE scorecards; comp simulator comparing pay-on-signature vs. pay-on-funded vs. pay-on-activation+volume, with cost per active account. |
| **Segments** | Segment × ISO penetration and volume; liquidity flywheel (spread vs. active accounts). |
| **Marketing ROI** | Spend → leads → funded → active by channel; cost per *active* account. |
| **Account 360** | Drawer per account: health, onboarding timeline, volume trend, reasons, next action, QBR prep. |

**Guardrails:** every outreach draft passes a compliance linter (banned/caution phrases, required disclaimer) and needs human approval; optional Claude drafting uses only computed facts and falls back to templates; 14-day contact limit per account; "Synthetic data" watermark everywhere.

## 5. v1.1 changes (from exec review) — in progress

Narrow the volatility rule to ~20–40 truly actionable accounts; add "order rejected" rule; down-rank accounts already ramping; "Today" queue with per-rep caps; one consistent event count across views; plan-pacing KPIs; honest model card (AUC ~0.78 vs. 0.77 baseline); comp v1.1 (quota 48, $1,250 unit, accelerator gated on ≥50% book activation); reviewer-gated outreach with reject/edit; fixes for 6 bugs found by CTO review.

## 6. Out of scope

Real CRM/exchange/ISO data feeds (adapter only), authentication/multi-user, sending email, mobile app, production deployment.

## 7. Tech

Python 3.13 · FastAPI · SQLite (Postgres via env var) · pandas/scikit-learn · vanilla JS + Chart.js (no build) · pytest. Runs locally in ~30s:
`cd electronx && pip install -r ../requirements.txt anthropic && python -m ignition.seed --reset && uvicorn ignition.main:app` → http://localhost:8000

## 8. Acceptance (v1.1 done when)

Full test suite green; every page loads with no console errors; Pulse flow works end-to-end (spike → exposed accounts → draft → approve → queue → re-rank); CEO and Pulse show identical event numbers; all endpoints < 300 ms.

## 9. Supporting docs

`docs/01_PROBLEM_SYNTHESIS.md`, `docs/02_PRODUCT_SPEC.md` (detailed contract), `docs/03_ROUND2_CHANGES.md`, `docs/exec/*` (CEO/CRO/CPO/CTO memos & reviews), `docs/gtm/*` (playbook, comp plan, 90-day plan, positioning, content engine).
