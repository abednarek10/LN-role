# CTO Review — Round 2: Ignition v1

**Verdict: conditional pass.** The architecture, the cache and the test suite are sound: 180 tests pass, and every endpoint answers in under 300 ms (slowest 248 ms). Two compliance bugs in the outreach workflow block a public demo. Fix the two P0s, then ship.

How I verified: I seeded an isolated database, ran the API through the test client and on uvicorn port 8104 (since stopped), and used a fake Claude client. Every bug below was reproduced.

## Confirmed bugs

**B1. Invented facts in Claude drafts can be approved.**
- *Where:* `services/outreach.py:298-300`, `services/compliance.py:76-82`, `services/outreach.py:355`.
- *Failure:* I gave the fake client a body containing "$9,999/MWh for 14 hours … your desk lost 40% of margin".
  - The draft came back with `engine=claude` and `passed=true`.
  - R04 flagged only the dollar figure, and only as a caution. "14 hours" and "40%" got no flag.
  - The approve call returned 200 with the caution still open, although R03 says the reviewer must clear each caution flag first.
- *Fix:* Extend R04 to every numeral (prices, hours, %, MW/MWh, dates). If a Claude draft has any R04 hit, use the template instead. Make approve return 409 until every caution flag is explicitly cleared.

**B2. The 14-day limit on triggered outreach (R14) can be bypassed.**
- *Where:* `services/outreach.py:366-378`. The limit is checked once, when the draft is created (`:313-316`), and never again.
- *Failure:* For account 337, I created two volatility drafts before either was queued. Both approved and both queued, producing two `triggered_email` activities on the same day. A third draft was then blocked by R14.
- *Fix:* Re-check the 14-day limit inside `queue()` (and `approve()`) in the same transaction as the activity insert, and return 409.

**B3. Accounts that can't receive volatility outreach still get the trigger boost.**
- *Where:* `services/activation.py:243-248`.
- *Failure:* 102 of 155 TARGET accounts get the ×1.5 trigger urgency, e.g. #51 Nighthawk Proprietary Trading, whose next action is R99. But TARGET is excluded from triggered outreach by R07, by NBA rule R09 (S1–S5 only) and by Pulse's `TRIGGER_STAGES`, so the queue ranks them up for a touch compliance would block.
- *Fix:* Apply the trigger factor only when `stage ∈ TRIGGER_STAGES`.

**B4. Model metrics are optimistic.**
- *Where:* `services/propensity.py:39-40, 134-135`.
- *Failure:* The last training snapshot (06-01) is only 7 days before the first test snapshot, but the label window is 60 days, so training labels overlap the test period. Also, 124 of the 194 test accounts are in training.
  - The reported AUC is 0.836. With a 60-day purge it is 0.774, and on account-disjoint test rows 0.765.
  - A baseline using only five funnel flags scores 0.780.
- *Fix:* Purge the gap to at least the label horizon, report account-disjoint metrics, and show the baseline next to the model.

**B5. Funnel conversion counts in-flight accounts as drop-offs.**
- *Where:* `services/funnel.py:57-79, 148-157`.
- *Failure:* Signed→funded falls to 40% for August signers and 17% for September signers only because they haven't had time to fund yet. When I restrict the population to accounts signed at least 90 days ago, 7 of the 16 friction cards change (4 disappear, 3 appear), including both DATACENTER order-ticket cards.
- *Fix:* Measure conversion on matured cohorts (accounts that reached the previous step at least N days ago) or use a survival estimate, and show n.

**B6. Co-op copy can never be approved.**
- *Where:* `content/compliance_rules.json` (`notes`) vs `services/outreach.py:355`.
- *Failure:* "not-for-profit co-ops" matches "profit", a block-level flag. The rules file says the reviewer clears this false positive, but a blocked draft has no override, so approve always returns 409. This hits the Utility/Co-op segment directly.
- *Fix:* Add an exceptions list to the rules.

**Doc nit:** `COMP_PLAN.md` §3 says "remaining 21 accounts"; it should be 20. The simulator itself reproduces AE A's three payouts to the cent ($137,500 / $89,583 / $79,690).

## Improvement requests

| # | Pri | Request | Acceptance check |
|---|---|---|---|
| 1 | **P0** | Fix B1 | Fake-client test with an invented $, hours and % gives `engine=template`. Approving a draft with an uncleared caution returns 409. |
| 2 | **P0** | Fix B2 | Two parallel drafts produce one queued and one 409, and only one `triggered_email` row is written. |
| 3 | P1 | Honest model card (B4) | `/scoring/model` shows purged, account-disjoint AUC plus baseline AUC. A test asserts no training label window overlaps the test window. |
| 4 | P1 | Fix B3 and B5 | No TARGET row carries a `trigger_id`. Friction cards stay within ±1 when restricted to mature cohorts. |
| 5 | P1 | Review workflow, rules R13/R17 | Approve requires a reviewer name and per-flag clearance. Add reject and edit + re-lint endpoints (today's 409 message says "edit and re-lint", but no edit endpoint exists). Store reviewer and timestamp. Fix B6. |
| 6 | P1 | Runability | Add `electronx/README.md` and `requirements.txt` (the optional `anthropic` package listed as optional). A fresh clone with `pip install … && cd electronx && uvicorn ignition.main:app` reaches a warm `/api/health`. An empty database boots in about 15 s; document that. |
| 7 | P2 | Missing regression tests | Add the COMP_PLAN AE A/B worked example as a test. Add a Claude test for `max_tokens` truncation. Add a cache test asserting that after `queue`, `/activation/queue` and `/pulse/.../accounts` reflect the touch. |
| 8 | P2 | Hardening | Bound the memo cache (LRU); today it is keyed by free-text `q`, `limit` and `offset` with no size limit. Restrict CORS to same-origin; the write endpoints have no auth. Document that the in-process cache requires a single worker. |

## What's strong

- **Architecture as specified.** Services are pure functions. `repo.py` is the only place SQL runs, and it uses ORM `select()` only, so there is no SQL-injection surface. Search uses `regex=False`. Path params are typed: bad ids return 404 or 422, a negative friction index returns 404, and a traversal-style trigger id returns 404.
- **Claude integration meets the brief.**
  - Calls `claude-opus-5-5` with `betas=["server-side-fallback-2026-07-01"]` and `fallbacks="default"`.
  - Checks `stop_reason == "refusal"` and catches typed errors most-specific first, falling back to the template on each.
  - Never logs the key, and runs only when the key is set. The client can be swapped out in tests.
  - Claude drafts and template drafts go through the same linter.
- **Leakage-safe features.** Every feature uses only events before the snapshot (`ts < t`), and a test deletes later rows to prove it. The challenger is reported side by side, and per-account reasons are provided.
- **Selective cache invalidation works.** After a queue write, the queue and Pulse payloads rebuild, and the next draft correctly picks up R14.
- **Frontend escaping is consistent.** The `IG.html` tagged template escapes every interpolation, including attributes. I found no unescaped API data reaching `innerHTML`.
- **The definitions file is the single source.** The CEO KPI math matches the memo, and D2 reconciles the CEO's and CRO's definitions of Active. Comp formulas match `comp_plans.json` exactly.
