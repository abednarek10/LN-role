# Ignition — Architecture

**Owner:** Engineering agent · **Status:** matches `ignition/main.py`, `ignition/routers/*`,
`ignition/services/*` · All data is **synthetic and illustrative**.

```
cd electronx
python -m ignition.seed --reset              # build data/ignition.db (~6 s)
uvicorn ignition.main:app --port 8100        # API + frontend at http://localhost:8100
python -m pytest -q                          # 180 tests (seed, model, triggers, services, API, perf)
```

---

## 1. Layers

```
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │ frontend/  (vanilla JS + vendored Chart.js, served at /static, index at /)   │
 │   7 hash-routed views · Account 360 drawer · outreach draft panel             │
 └───────────────────────────────┬──────────────────────────────────────────────┘
                                 │  JSON over /api  (contract: spec §E + FRONTEND_CONTRACT_NOTES)
 ┌───────────────────────────────▼──────────────────────────────────────────────┐
 │ ignition/main.py      FastAPI app · lifespan (create_all → seed_if_empty →    │
 │                       warm → precompute) · CORS · SafeJSONResponse · /static  │
 │ ignition/routers/*    thin HTTP layer: param validation (422), 404/409 mapping│
 │ ignition/schemas.py   Pydantic for small shapes (draft, status, comp-sim body)│
 └───────────────────────────────┬──────────────────────────────────────────────┘
                                 │  AppState (in-process)
 ┌───────────────────────────────▼──────────────────────────────────────────────┐
 │ services/cache.py     AppState: frames · model bundle · scores · triggers ·   │
 │                       health · account context table · memo (payload cache)   │
 │                                                                              │
 │ Engineering services (pure: DataFrames in → dicts out)                       │
 │   activation.py  queue formula + NBA rule engine (content/nba_rules.json)    │
 │   pulse.py       hubs, live triggers, exposed accounts, history/lift          │
 │   ceo.py/memo.py weekly KPIs, series, mix, spreads, cohorts, narrative, .md   │
 │   funnel.py      step math, states, friction cards, roadmap tickets (.md)    │
 │   segments.py · liquidity.py · marketing.py · team.py (scorecards, comp sim)  │
 │   accounts.py    list/search, Account 360 + QBR block                         │
 │   outreach.py    facts → template → (Claude) → lint → persist → approve/queue │
 │   compliance.py  linter (content/compliance_rules.json)                       │
 │   common.py      content loader, JSON-safe scalars, per-account context table │
 │                                                                              │
 │ Data services (Data agent): features.py · propensity.py · volatility.py      │
 └───────────────────────────────┬──────────────────────────────────────────────┘
                                 │  repo.load_all(session)  ← the only SQL touchpoint
 ┌───────────────────────────────▼──────────────────────────────────────────────┐
 │ ignition/repo.py · models.py · database.py   SQLAlchemy 2 (SQLite by default) │
 │ data/ignition.db   built by ignition/seed.py (seed 42, deterministic)         │
 └──────────────────────────────────────────────────────────────────────────────┘
   ignition/definitions.py  — single source for every definition, target, constant
   ignition/content/*.json  — business rules owned by Sales/Marketing (no code change to edit)
```

**Rule of the codebase:** services never import a `Session` except `outreach.py` (which persists
drafts and activities). Every number in every view comes from `definitions.py` + data, and every
business rule (NBA rules, sequences, comp plans, scorecard weights, templates, compliance phrases)
comes from `content/*.json`.

## 2. Request lifecycle

```
GET /api/activation/queue?segment=REP
  └─ routers/activation.py   validate segment/iso/stage (422 on unknown codes)
      └─ deps.state()         cache.get_state()  (warm AppState; lazily warms in tests)
          └─ activation.queue(state, …)
               └─ state.cached(("queue", 50, "REP", …))      ← memo hit: ~5 ms
                    miss → score_rows (all non-LP accounts, memoized once) → filter → rank → JSON
  └─ SafeJSONResponse        NaN/inf → null, numpy → Python (never a 500 on a stray NaN)
  └─ middleware              X-Response-Time-ms, X-Synthetic-Data headers
```

Writes follow the same path, then refresh state:

```
POST /api/outreach/{id}/queue
  └─ outreach.queue(session)  409 unless approved · INSERT activities (ts = AS_OF,
                              kind triggered_email|email, outcome none, sequence) · status = queued
  └─ cache.refresh(session, "activities", "outreach_drafts")
        repo.invalidate_cache(tables) → reload those tables only
        rebuild account context table (last_touch, cooldown …)
        drop memo entries whose MEMO_DEPENDS intersect the changed tables
  └─ next GET /api/activation/queue recomputes → urgency drops, last_touch_days = 0,
     R09 (VOL_TRIGGER_EXPOSED) suppressed for 14 days, Pulse row shows suppressed
```

## 3. Caching

| Layer | What | Lifetime | Invalidation |
|---|---|---|---|
| `repo._CACHE` | one DataFrame per table | process | `repo.invalidate_cache(*tables)` after writes |
| `AppState.bundle` | trained LR + challenger (≈2–3 s) | process | never (retrain on restart) |
| `AppState.scores` | `score_accounts` at AS_OF | process | not needed: features read `ts < AS_OF`, queued touches are stamped `AS_OF` |
| `AppState.triggers` / `health` / `accounts` | live triggers, D2 health, per-account context table | until a write | `cache.refresh` rebuilds when an input table changed |
| `AppState.memo` | response payloads keyed by `(endpoint, params…)` | until a write that touches their inputs | `MEMO_DEPENDS` map in `services/cache.py` |

Startup (`lifespan`) warms everything and precomputes the default payload of every view
(~6 s on a laptop, of which ~3 s is model training). Measured after warm-up with `TestClient`
(`tests/test_perf.py`, budget 300 ms): every GET is **< 30 ms**; the slowest is
`/api/liquidity?iso=ERCOT` (~30 ms, 1,638 daily rows). Uncached variants: another CEO week
≈ 45 ms (weekly snapshots are memoized individually), comp-sim with custom params ≈ 170 ms.
The frontend additionally caches GETs for 60 s and clears its cache on every POST.

## 4. Swapping SQLite → Postgres

1. `pip install psycopg[binary]` and set
   `IGNITION_DB_URL=postgresql+psycopg://user:pw@host:5432/ignition`. Nothing else changes:
   `config.py` reads the URL, `database.make_engine` only adds SQLite pragmas for SQLite.
2. Types are portable (integers, floats, strings, naive-UTC `DateTime`, `Date`, `Text` for JSON).
   `create_all` runs on boot; use Alembic for real migrations once the schema stabilizes.
3. `repo.py` is the only SQL touchpoint; for larger books replace the full-table loaders with
   windowed queries (e.g. trades in the last 400 days, prices in the last 60 days) — services
   only need those windows.
4. Multi-worker deployment: `AppState` is per process. Either run one worker per pod with a
   short TTL refresh, or move the memo to Redis keyed by `(table versions, endpoint, params)`;
   `MEMO_DEPENDS` already lists each payload's input tables.

## 5. Swapping synthetic → real feeds

| Synthetic table | Real source | Adapter |
|---|---|---|
| `accounts`, `contacts`, `activities`, `reps` | CRM (Salesforce/HubSpot): Account, Contact, Task/Event, User | nightly + webhook upsert; map Stage → `definitions.classify_stage` (stage is *derived*, never trusted from CRM) |
| `onboarding_events` | onboarding/KYC platform + exchange admin events | one row per step; `kyc_info_requested` repeatable |
| `trades` | exchange matching-engine fills (drop-copy) | filter self-matches before insert; `fee_usd` from clearing |
| `market_prices` | ISO real-time LMP APIs (ERCOT, PJM Data Miner, CAISO OASIS, MISO) | hourly hub LMP, hour-beginning naive UTC |
| `price_forecasts` | weather/load vendor or in-house forecast | 5-day daily peak/avg per hub |
| `spread_snapshots` | market-data service (top-of-book sampler) | daily per hub × tenor, 07:00–19:00 local |
| `marketing_spend` | ad platforms / finance | monthly per channel |
| `outreach_drafts` → send | sales-engagement tool (Outreach/Salesloft) | `queued` drafts become sequence steps; replies write back `activities.outcome` |

Because services consume only `Frames`, a real deployment replaces `seed.py` with ingestion jobs
and keeps every service, router and test fixture shape unchanged. `latent_propensity` is seed-only
and is never read by services.

## 6. Claude integration & guardrails (spec D7)

```
facts (computed: hub, ISO, $4,800 peak, 9 h, Oct 2 2026, regime, exposure fragment,
       contract suggestion, labelled 5-day forecast, CTA, required footer)
  → template (content/outreach_templates.json, most-specific match: segment > direction > regime > stage, '*' fallbacks)
  → if ANTHROPIC_API_KEY: client.beta.messages.create(model="claude-opus-5-5", max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"], fallbacks="default", output_config={"effort": "low"},
        system=<compliance-aware writer; facts only; ≤150 words; "Subject: …" format; exact footer>,
        messages=[{template, facts, banned_phrases}])
        timeout 20 s, max_retries 1
  → lint (same linter for template and Claude output)
  → persist outreach_drafts(status=pending_review, compliance_flags JSON)
  → approve (409 unless passed) → queue (409 unless approved) → activities row
```

* **Facts only.** Claude receives the computed facts and the rendered template; the system prompt
  forbids new numbers, advice and promissory language. The linter's R04 check flags any `$` figure
  not present in the facts.
* **Fallbacks.** No key → template (the API is never called). `stop_reason == "refusal"`,
  `APIConnectionError`, `RateLimitError`, `APIStatusError`, any other exception, or output not in
  `Subject: …\n\n<body>` form → template, with `facts.engine_note` explaining why. A Claude draft
  that the linter **blocks** is discarded for the template (`engine: "template"`, note names the phrase).
* **Linter** (`services/compliance.py`): case-insensitive, quote/whitespace-normalized,
  word-boundary matching on subject + body excluding the footer; banned → `block`, caution →
  `caution`; missing/altered footer → `block`; extra review flags for unverified $ figures, > 3 price
  figures and > 190 words. Volatility drafts also get `block` flags for unscreened TARGET accounts
  (R07) and for a second triggered sequence within 14 days (R14).
* **Human in the loop.** Nothing sends: drafts move `pending_review → approved → queued`; queueing
  logs the touch so the Activation Queue and Pulse suppression reflect it immediately.
* **Tests never call the API** (`tests/test_services_outreach.py` monkeypatches a fake client to
  verify the exact request parameters, parsing, and every fallback path).

## 7. Definitions that are implementation choices (documented, test-covered)

* **Queue population:** non-LP accounts in TARGET → FIRST_TRADE, AT_RISK, DORMANT (Active and
  Expanding accounts get NBA actions in Account 360, not activation ranking).
* **E[ADV]:** CRO segment prior × `clip((size/segment median)^0.25, 0.7, 1.5)`.
* **Urgency:** ×1.5 live realized trigger in an exposure ISO unless a triggered sequence was sent in
  the last 14 days; ×1.25 stall (CRO §1 thresholds); ×1.2 forecast peak ≤ 5 d unless touched in the
  last 5 days; cap 2.0. **B:** ×1.15 for hedgers while hedger share of Active < 50%.
* **SLA breach:** the matched rule's condition has held longer than `sla_hours` with no touch since.
* **Pulse exposed list:** stages QUALIFIED → FIRST_TRADE plus AT_RISK/DORMANT, exposure by ISO
  (`exposure_isos`), ordered by `touch_value = exposure_score/100 × P × E[ADV]`.
* **CEO cohorts:** 4-week funding cohorts (weekly cohorts here are n≈5 — all greyed); the KPI uses
  the last 8 matured weeks pooled. Spreads use weekday snapshots; the trend compares with the
  10 trading days ending 8 weeks earlier.
* **Comp:** plan period YTD 2026 with quota and volume target prorated; `adv_kicker_cap = 0`
  means uncapped (only reachable via simulator params).
* **Churn risk:** transparent heuristic (inactivity, ADV decline, recency), not a model.
