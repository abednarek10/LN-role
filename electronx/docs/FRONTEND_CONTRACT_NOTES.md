# Frontend ↔ API contract notes (resolved by orchestrator)

Addendum to `02_PRODUCT_SPEC.md` §E, written after the Design agent built the
frontend against the spec. Engineering must honor these.

1. **Units.** Fields ending `_pct` (e.g. `uptime_pct`, `target_uptime`) are **0–100**. Every other rate/share/probability is **0–1**.
2. **"ADV at stake"** (`adv_at_stake` on triggers, queue summary, friction cards) is **contracts per day**, same unit as `exp_adv`.
3. **`weekly_series.active_accounts`** is the end-of-week count of Active accounts (level, not flow).
4. **Friction export index** `/api/funnel/friction/{index}.md` is **0-based into the unfiltered** `/api/funnel` friction list.
5. **KPI `unit`** vocabulary: `contracts`, `usd`, `usd_mwh`, `rate`, `share`, `pct`, `days`, `accounts`, `ratio`.
6. **`severity`**: number 0–100 on triggers (CTO §5 formula); string `low|medium|high|critical` on friction cards.
7. **Compliance `flags`**: list of `{rule, phrase, level[block|caution], message}`.
8. **`next_action`** is always an object `{rule_id, action, owner, sla, sequence}` (incl. inside `stalled`).
9. **Comp plans** identified by `plan_id`, display name `name`. `POST /api/team/comp-sim` body: `{plan_id, params}` where `params` mirrors plan keys and may be partial: `per_account_unit`, `multipliers.{signed,funded,active_60d,active_21d_bonus}`, `adv_kicker_per_1k`, `adv_kicker_cap`, `adv_kicker_accel`, `accelerator`, `clawback_pct` (0–1), `clawback_days`, `lp_kicker_credit` (0–1). Merge params over the stored plan.
10. **Approve** only allowed when `compliance.passed`; API returns 409 otherwise. **Queue** only after approve (409 otherwise).
11. Timestamps naive UTC ISO strings (`YYYY-MM-DDTHH:MM:SS`).
12. `qbr.utilization_by_tenor` is an object `{HOURLY: share, DAILY_PEAK: share, WEEKLY_PEAK: share}`; `growth_plays` list of strings.
13. `account` object in `/api/accounts/{id}` includes: `id, name, segment, segment_label, side, primary_iso, hub, exposure_isos (list), stage, rep_id, rep_name, is_liquidity_partner, funded_amount_usd, size_mw, p_active, signed_at, funded_at, first_trade_at`.
14. Comp `activation_adv` plan: the JSON's `per_account_unit` $2,000 stays the default; the CEO's call on $2,500 is a simulator parameter, not a code change.
