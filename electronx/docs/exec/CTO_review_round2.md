# CTO Review — Round 2: Ignition v1

**Verdict: conditional pass.** 180 tests pass and every endpoint answers in under 300 ms (slowest 248 ms). Two compliance bugs block the demo; fix the P0s, then ship. Every bug below was reproduced on an isolated DB with a fake Claude client.

## Confirmed bugs

**B1. Invented facts in Claude drafts can be approved.** `services/outreach.py:298-300`, `compliance.py:76-82`, `outreach.py:355`.
- *Failure:* a fake Claude body with "$9,999/MWh for 14 hours … your desk lost 40%" came back `engine=claude, passed=true`. R04 flagged only `$9,999`, as a caution; "14 hours" and "40%" passed. Approve returned 200 with the caution open, despite R03.
- *Fix:* extend R04 to every numeral (prices, hours, %, MW/MWh, dates). Fall back to the template on any R04 hit in a Claude draft. Return 409 on approve until each caution is cleared.

**B2. The 14-day triggered-outreach limit (R14) can be bypassed.** `outreach.py:366-378`; the limit is checked only at draft creation (`:313-316`).
- *Failure:* two volatility drafts for account 337, created before either was queued, both approved and both queued, producing two `triggered_email` rows the same day.
- *Fix:* re-check the limit in `queue()` and `approve()`, in the same transaction as the activity insert.

**B3. TARGET accounts get the trigger boost they can't use.** `services/activation.py:243-248`.
- *Failure:* 102 of 155 TARGET accounts get ×1.5 trigger urgency. R07, NBA rule R09 and Pulse's `TRIGGER_STAGES` all exclude TARGET.
- *Fix:* apply the factor only when `stage ∈ TRIGGER_STAGES`.

**B4. Model metrics are optimistic.** `services/propensity.py:39-40, 134-135`.
- *Failure:* the train cutoff is 7 days before the test window but labels look 60 days ahead, so training labels overlap the test period. 124 of 194 test accounts also appear in training. Reported AUC is 0.836; with a 60-day purge it is 0.774, and account-disjoint 0.765. A five-feature funnel-flag baseline scores 0.780.
- *Fix:* purge a gap of at least the label horizon, report account-disjoint metrics, and show the baseline.

**B5. Funnel counts in-flight accounts as drop-offs.** `services/funnel.py:57-79, 148-157`.
- *Failure:* signed→funded is 40% for August signers and 17% for September only because they are recent. Restricting to accounts signed ≥90 days ago changes 7 of 16 friction cards.
- *Fix:* use matured-cohort denominators or a survival estimate. Show n.

**B6. Co-op copy can never be approved.** `compliance_rules.json` `notes` vs `outreach.py:355`.
- *Failure:* "not-for-profit" matches the banned word "profit" (block). The rules file says a reviewer clears it, but blocks have no override, so approve always returns 409.
- *Fix:* add an exceptions list.

**Doc nit:** `COMP_PLAN.md` §3 says "remaining 21 accounts"; it should be 20. The simulator reproduces AE A's payouts to the cent ($137,500 / $89,583 / $79,690).

## Improvement requests

| # | Pri | Request | Acceptance check |
|---|---|---|---|
| 1 | **P0** | Fix B1 | A fake-client draft with invented $, hours and % gives `engine=template`. Approve with an uncleared caution returns 409. |
| 2 | **P0** | Fix B2 | Two parallel drafts: one queues, one gets 409, and one `triggered_email` row is written. |
| 3 | P1 | Honest model card (B4) | `/scoring/model` shows purged and account-disjoint AUC plus the baseline. A test asserts no train label window overlaps the test window. |
| 4 | P1 | Fix B3 and B5 | No TARGET row has a `trigger_id`. Friction cards stay within ±1 when restricted to mature cohorts. |
| 5 | P1 | Review workflow (R13/R17) | Approve requires a reviewer and per-flag clearance; add reject and edit + re-lint endpoints (none exist today); B6 fixed. |
| 6 | P1 | Runability | `electronx/README.md` and `requirements.txt` (`anthropic` listed as optional). A fresh clone reaches a warm `/api/health`; document the ~15 s boot from an empty DB. |
| 7 | P2 | Regression tests | COMP_PLAN AE A/B worked example; Claude `max_tokens` truncation; after a queue write, `/activation/queue` and `/pulse/.../accounts` reflect the touch. |
| 8 | P2 | Hardening | Size-limit the memo cache (LRU); today it is keyed by free-text `q` with no limit. Restrict CORS to same-origin (write endpoints have no auth). Document that the in-process cache needs a single worker. |

## What's strong

- **Clean layering:** pure services; `repo.py` is the only SQL, ORM `select()` only, so no injection surface. Typed path params return 404/422.
- **Claude integration meets the brief:**
  - `claude-opus-5-5` with `betas=["server-side-fallback-2026-07-01"]` and `fallbacks="default"`.
  - Refusals and typed errors fall back to the template; the key is never logged; both engines share the linter.
- **Leakage-safe features:** only events before the snapshot (`ts < t`), proven by a deletion test.
- **Cache invalidation works:** after a queue write, the queue and Pulse payloads rebuild.
- **No XSS found:** `IG.html` escapes every interpolation, attributes included.
- **One source of definitions:** CEO KPI math matches the memo (D2 reconciles Active); comp code matches `comp_plans.json`.
