# Ignition API

**Owner:** Engineering agent · Base URL `http://localhost:8100/api` · JSON unless noted ·
OpenAPI at `/docs`. All data is **synthetic and illustrative** (responses carry
`X-Synthetic-Data: illustrative`).

Conventions (spec §E + `FRONTEND_CONTRACT_NOTES.md`): `as_of` = `2026-10-05` on every object
response; timestamps are naive-UTC `YYYY-MM-DDTHH:MM:SS`; money is USD; rates/shares/probabilities
are 0–1 except fields ending `_pct` (0–100); "ADV at stake" and `exp_adv` are contracts/day;
`next_action` is always `{rule_id, action, owner, sla, sequence}` (+ `condition_code`,
`condition_text`, `sla_hours`, `sla_breached`). Unknown `segment` / `iso` / `stage` / `tenor`
codes return **422**; unknown ids return **404**; workflow violations return **409**.
Examples below are trimmed (`"… N more"` marks elided list items).

## Endpoints

| Method | Path | Params / body | Returns (top-level keys) | Errors |
|---|---|---|---|---|
| GET | `/health` | — | `status, as_of, db, warmed, version, claude_enabled` | — |
| GET | `/meta` | — | `as_of, week_end, segments[{code,label,side}], isos, stages, steps, step_labels, channels, reps[{id,name,role}], targets, definitions, synthetic` | — |
| GET | `/ceo/weekly` | `week_end` (snaps to Friday) | `as_of, week_end, headline[3], kpis[], weekly_series[], mix, spreads[], activation_cohorts[], stalled[], stalled_total, decisions[3], lever` | 422 bad/out-of-range week |
| GET | `/ceo/weekly.md` | `week_end` | `text/markdown` memo, watermarked | 422 |
| GET | `/pulse/hubs` | `iso`, `hours` (24–1440, default 168) | `as_of, hubs[{hub, iso, series[{ts,lmp}], stats, forecast[]}]` | 422 |
| GET | `/pulse/triggers` | — | `as_of, triggers[{trigger_id, hub, iso, regime, severity (0–100), spike_hours, vol_z, peak_lmp, peak_ts, start_ts, end_ts, forward_risk, exposed_count, funded_not_trading, adv_at_stake, …}]` | — |
| GET | `/pulse/triggers/{trigger_id}/accounts` | — | `as_of, trigger, accounts[{account_id, name, segment, stage, direction, exposure_line, exposure_score, p_active, exp_adv, last_touch_days, suppressed, suppressed_reason, touch_value}]` | 404 not a live trigger |
| GET | `/pulse/history` | — | `as_of, events[], lift{triggered, untriggered, lift_x}` | — |
| GET | `/activation/queue` | `limit` (1–1000, 50), `segment, iso, rep_id, stage` | `as_of, summary{accounts_in_queue, stalled, sla_breaches, adv_at_stake, …}, items[]` | 422 |
| GET | `/activation/rules` | — | `rules[]` (NBA rules in evaluation order) | — |
| GET | `/scoring/model` | — | `as_of, target, target_description, train_n, test_n, auc, pr_auc, brier, base_rate, lift_top_decile, gain_curve, calibration, coefficients, challenger` | — |
| GET | `/funnel` | `segment, iso` | `as_of, steps[], states{active, at_risk, dormant, funded_new}, by_segment[], friction[]` | 422 |
| GET | `/funnel/friction/{index}.md` | 0-based into the **unfiltered** friction list | `text/markdown` roadmap ticket | 404 |
| GET | `/segments` | — | `as_of, cells[], segments[], liquidity_partners` | — |
| GET | `/liquidity` | `iso, tenor` | `as_of, series[], elasticity{b, a, r2, n, note}` | 422 |
| GET | `/team/scorecards` | — | `as_of, reps[], weights, scoring` | — |
| GET | `/team/comp-plans` | — | `as_of, plans[]` (content/comp_plans.json + `name`) | — |
| POST | `/team/comp-sim` | `{plan_id?, params?}` — params partial, merged over the plan | `as_of, period, plan, reps[], totals, comparison[]` | 404 plan, 422 params |
| GET | `/marketing/roi` | `months` (1–12, 6) | `as_of, months, window, channels[], monthly[]` | 422 |
| GET | `/accounts` | `segment, iso, stage, rep_id, q, limit (≤600), offset` | `as_of, total, items[{id,name,segment,iso,hub,stage,rep,rep_id,is_liquidity_partner,p_active,adv_30d}]` | 422 |
| GET | `/accounts/{id}` | — | `as_of, account, contacts, timeline, onboarding, adv_series, health, reasons, next_action, queue, qbr` | 404 |
| POST | `/outreach/draft` | `{account_id, trigger_id?, kind: volatility\|activation\|qbr}` | `draft_id, account_id, kind, trigger_id, template_id, subject, body, engine, facts, compliance{passed, flags[]}, status` | 404 account/trigger, 422 kind |
| GET | `/outreach/{draft_id}` | — | stored draft + compliance | 404 |
| POST | `/outreach/{draft_id}/approve` | — | `{draft_id, status}` | 404, **409** unless `compliance.passed` / already queued |
| POST | `/outreach/{draft_id}/queue` | — | `{draft_id, status, activity_id, account_id, trigger_id, logged_at}`; inserts `activities` (ts = AS_OF, `triggered_email` if trigger else `email`) and refreshes the queue | 404, **409** unless approved |

Static: `/` serves `frontend/index.html`; `/static/*` serves the frontend.

## Examples

### GET /health

```json
{
 "status": "ok",
 "as_of": "2026-10-05",
 "db": "sqlite",
 "warmed": true,
 "version": 1,
 "claude_enabled": false
}
```

### GET /meta

```json
{
 "as_of": "2026-10-05",
 "week_end": "2026-10-02",
 "segments": [
  {
   "code": "IPP",
   "label": "Independent Power Producer",
   "side": "hedger"
  },
  {
   "code": "STORAGE",
   "label": "Battery Storage Operator",
   "side": "hedger"
  },
  "… 6 more"
 ],
 "isos": {
  "ERCOT": [
   "HB_NORTH",
   "HB_HOUSTON",
   "… 1 more"
  ],
  "PJM": [
   "PJM_WESTERN_HUB"
  ],
  "CAISO": [
   "SP15",
   "NP15"
  ],
  "MISO": [
   "MISO_INDIANA_HUB"
  ]
 },
 "stages": [
  "TARGET",
  "QUALIFIED",
  "… 8 more"
 ],
 "channels": [
  "Industry Conferences",
  "Webinars & Education",
  "… 5 more"
 ],
 "reps": [
  {
   "id": 1,
   "name": "Maya Castillo",
   "role": "AE",
   "region": "ERCOT"
  },
  {
   "id": 2,
   "name": "Ben Okafor",
   "role": "AE",
   "region": "PJM"
  },
  "… 6 more"
 ],
 "synthetic": true,
 "targets": {
  "signed_cum": 420,
  "funded_cum": 260,
  "active_rate": 0.7,
  "cohort_activation_30d_start": 0.55
 }
}
```

### GET /ceo/weekly

```json
{
 "as_of": "2026-10-05",
 "week_end": "2026-10-02",
 "headline": [
  "Liquidity: ADV is 15.4k contracts/day (+3.7% vs prior 20 td; liquidity partners 7,884), with ERCOT North sp…",
  "Balance: 112 of our 183 funded accounts older than 20 days are actively trading (61%). Hedgers are 45% of A…",
  "… 1 more"
 ],
 "kpis": [
  {
   "key": "adv_contracts",
   "label": "ADV (20-td, contracts)",
   "unit": "contracts",
   "value": 15384.95,
   "prior": 14841.5,
   "delta": 543.45,
   "prior_label": "prior 20 td",
   "target": 25000.0,
   "target_direction": "min",
   "status": "off_track",
   "spark": [
    11060.95,
    12170.35,
    "… 10 more"
   ],
   "detail": {
    "adv_5d": 16140.0,
    "adv_lp": 7884.4,
    "adv_organic": 7500.6,
    "lp_share": 0.5125
   }
  },
  {
   "key": "adv_notional_usd",
   "label": "ADV notional (20-td)",
   "unit": "usd",
   "value": 2339145.242,
   "prior": 972437.9865,
   "delta": 1366707.2555,
   "prior_label": "prior week",
   "target": 3000000.0,
   "target_direction": "min",
   "status": "off_track",
   "spark": [
    841684.1785,
    1033383.9235,
    "… 10 more"
   ],
   "detail": {
    "by_iso": {
     "CAISO": 218287.0,
     "ERCOT": 1745327.0,
     "MISO": 91234.0,
     "PJM": 284298.0
    }
   }
  },
  "… 10 more"
 ],
 "weekly_series": [
  {
   "week_end": "2026-01-09",
   "signed": 2,
   "funded": 1,
   "first_trades": 9,
   "active_accounts": 3,
   "adv_contracts": 604.2,
   "adv_lp": 604.2,
   "fee_revenue": 1685.5
  },
  {
   "week_end": "2026-01-16",
   "signed": 3,
   "funded": 3,
   "first_trades": 3,
   "active_accounts": 11,
   "adv_contracts": 1449.7,
   "adv_lp": 1449.7,
   "fee_revenue": 2443.2
  },
  "… 37 more"
 ],
 "mix": {
  "by_side_accounts": {
   "hedger": 51,
   "speculator": 50,
   "liquidity_partner": 12
  },
  "by_side_adv": {
   "hedger": 1448.5,
   "speculator": 6052.1,
   "liquidity_partner": 7884.4
  },
  "top5_adv_share": 0.5008,
  "hhi": 0.0808,
  "hedger_share_active": 0.4513,
  "speculator_share_adv_organic": 0.8069
 },
 "spreads": [
  {
   "iso": "ERCOT",
   "hub": "HB_NORTH",
   "tenor": "HOURLY",
   "spread_usd_mwh": 0.844,
   "uptime_pct": 93.22,
   "target_spread": 0.75,
   "target_uptime": 95.0,
   "lp_quote_share": 0.429,
   "spread_8w_ago": 0.943,
   "status": "watch"
  },
  {
   "iso": "ERCOT",
   "hub": "HB_NORTH",
   "tenor": "DAILY_PEAK",
   "spread_usd_mwh": 0.713,
   "uptime_pct": 90.75,
   "target_spread": 0.75,
   "target_uptime": 95.0,
   "lp_quote_share": 0.429,
   "spread_8w_ago": 0.801,
   "status": "watch"
  },
  "… 6 more"
 ],
 "activation_cohorts": [
  {
   "cohort_week": "2025-12-22",
   "weeks": 4,
   "n": 9,
   "activated_30d_rate": 0.0,
   "greyed": true
  },
  {
   "cohort_week": "2026-01-19",
   "weeks": 4,
   "n": 6,
   "activated_30d_rate": 0.6667,
   "greyed": true
  },
  "… 7 more"
 ],
 "stalled": [
  {
   "account_id": 337,
   "name": "Shinnery Trading",
   "segment": "PROP",
   "stage": "FUNDED",
   "iso": "ERCOT",
   "rep_name": "Dana Whitfield",
   "days_stalled": 29.4,
   "p_active": 0.9641,
   "exp_adv": 322.2,
   "expected_adv": 310.6,
   "next_action": {
    "rule_id": "R09",
    "action": "Launch volatility sequence: T0 email with their hub chart + illustrative DAILY_PEAK replay of the event, co…",
    "owner": "AE",
    "sla": "4h",
    "sla_hours": 4,
    "sequence": "volatility",
    "condition_code": "VOL_TRIGGER_EXPOSED",
    "condition_text": "Stage QUALIFIED–FIRST_TRADE, hedger or speculator segment exposed to a volatility trigger (realized >3σ, sc…",
    "sla_breached": true
   }
  },
  {
   "account_id": 178,
   "name": "Caddo Bend Energy Services",
   "segment": "REP",
   "stage": "FIRST_TRADE",
   "iso": "ERCOT",
   "rep_name": "Maya Castillo",
   "days_stalled": 38.4,
   "p_active": 0.9887,
   "exp_adv": 118.6,
   "expected_adv": 117.3,
   "next_action": {
    "rule_id": "R09",
    "action": "Launch volatility sequence: T0 email with their hub chart + illustrative DAILY_PEAK replay of the event, co…",
    "owner": "AE",
    "sla": "4h",
    "sla_hours": 4,
    "sequence": "volatility",
    "condition_code": "VOL_TRIGGER_EXPOSED",
    "condition_text": "Stage QUALIFIED–FIRST_TRADE, hedger or speculator segment exposed to a volatility trigger (realized >3σ, sc…",
    "sla_breached": true
   }
  },
  "… 8 more"
 ],
 "decisions": [
  "Approve and staff the compliance-approved volatility sequence (NBA R09, 4h SLA) for the 231 accounts in the…",
  "Concentration is 50% top-5 vs a 45% ceiling and hedgers are 45% of Active vs a 50% floor: keep the ×1.15 he…",
  "… 1 more"
 ]
}
```

### GET /pulse/hubs?iso=ERCOT

```json
{
 "as_of": "2026-10-05",
 "iso": "ERCOT",
 "hours": 168,
 "hubs": [
  {
   "hub": "HB_NORTH",
   "iso": "ERCOT",
   "series": [
    {
     "ts": "2026-09-28T00:00:00",
     "lmp": 38.72
    },
    {
     "ts": "2026-09-28T01:00:00",
     "lmp": 39.38
    },
    "… 166 more"
   ],
   "stats": {
    "last": 34.65,
    "avg_30d": 66.16,
    "p99_30d": 2024.0,
    "max_72h": 3500.0,
    "min_72h": 21.88,
    "spike_hours_72h": 7,
    "neg_hours_72h": 0,
    "vol_z": 3.66
   },
   "forecast": [
    {
     "date": "2026-10-05",
     "forecast_peak_lmp": 160.0,
     "forecast_avg_lmp": 44.8
    },
    {
     "date": "2026-10-06",
     "forecast_peak_lmp": 380.0,
     "forecast_avg_lmp": 95.66
    },
    "… 3 more"
   ]
  },
  {
   "hub": "HB_HOUSTON",
   "iso": "ERCOT",
   "series": [
    {
     "ts": "2026-09-28T00:00:00",
     "lmp": 36.73
    },
    {
     "ts": "2026-09-28T01:00:00",
     "lmp": 35.98
    },
    "… 166 more"
   ],
   "stats": {
    "last": 36.47,
    "avg_30d": 77.5,
    "p99_30d": 2362.0,
    "max_72h": 4800.0,
    "min_72h": 22.48,
    "spike_hours_72h": 9,
    "neg_hours_72h": 0,
    "vol_z": 2.38
   },
   "forecast": [
    {
     "date": "2026-10-05",
     "forecast_peak_lmp": 185.0,
     "forecast_avg_lmp": 51.8
    },
    {
     "date": "2026-10-06",
     "forecast_peak_lmp": 420.0,
     "forecast_avg_lmp": 117.6
    },
    "… 3 more"
   ]
  },
  "… 1 more"
 ]
}
```

### GET /pulse/triggers

```json
{
 "as_of": "2026-10-05",
 "triggers": [
  {
   "trigger_id": "ERCOT-HB_HOUSTON-20261002",
   "hub": "HB_HOUSTON",
   "iso": "ERCOT",
   "regime": "scarcity",
   "regime_label": "Scarcity pricing",
   "severity": 92.1,
   "spike_hours": 9,
   "neg_hours": 0,
   "vol_z": 2.38,
   "peak_lmp": 4800.0,
   "peak_ts": "2026-10-02T19:00:00",
   "start_ts": "2026-10-02T15:00:00",
   "end_ts": "2026-10-02T23:00:00",
   "forward_risk": true,
   "forecast_peak_lmp": 1650.0,
   "forecast_date": "2026-10-07",
   "exposed_count": 192,
   "funded_not_trading": 29,
   "adv_at_stake": 4074.4,
   "hurt": 97,
   "opportunity": 95,
   "suppressed": 4
  },
  {
   "trigger_id": "ERCOT-HB_NORTH-20261002",
   "hub": "HB_NORTH",
   "iso": "ERCOT",
   "regime": "scarcity",
   "regime_label": "Scarcity pricing",
   "severity": 88.7,
   "spike_hours": 7,
   "neg_hours": 0,
   "vol_z": 3.66,
   "peak_lmp": 3500.0,
   "peak_ts": "2026-10-02T18:00:00",
   "start_ts": "2026-10-02T15:00:00",
   "end_ts": "2026-10-02T21:00:00",
   "forward_risk": true,
   "forecast_peak_lmp": 1320.0,
   "forecast_date": "2026-10-07",
   "exposed_count": 192,
   "funded_not_trading": 29,
   "adv_at_stake": 4074.4,
   "hurt": 97,
   "opportunity": 95,
   "suppressed": 4
  },
  "… 1 more"
 ]
}
```

### GET /pulse/triggers/ERCOT-HB_HOUSTON-20261002/accounts

```json
{
 "as_of": "2026-10-05",
 "trigger": {
  "trigger_id": "ERCOT-HB_HOUSTON-20261002",
  "hub": "HB_HOUSTON",
  "iso": "ERCOT",
  "regime": "scarcity",
  "regime_label": "Scarcity pricing",
  "severity": 92.1,
  "spike_hours": 9,
  "neg_hours": 0,
  "vol_z": 2.38,
  "peak_lmp": 4800.0,
  "peak_ts": "2026-10-02T19:00:00",
  "start_ts": "2026-10-02T15:00:00",
  "end_ts": "2026-10-02T23:00:00",
  "forward_risk": true,
  "forecast_peak_lmp": 1650.0,
  "forecast_date": "2026-10-07",
  "exposed_count": 192,
  "funded_not_trading": 29,
  "adv_at_stake": 4074.4,
  "hurt": 97,
  "opportunity": 95,
  "suppressed": 4
 },
 "accounts": [
  {
   "account_id": 337,
   "name": "Shinnery Trading",
   "segment": "PROP",
   "side": "speculator",
   "stage": "FUNDED",
   "hub": "HB_HOUSTON",
   "iso": "ERCOT",
   "direction": "opportunity",
   "exposure_line": "Trades ERCOT volatility; scarcity pricing at HB_HOUSTON creates short-dated dislocations its desk can expre…",
   "exposure_score": 83.1,
   "p_active": 0.9641,
   "exp_adv": 322.2,
   "last_touch_days": 6,
   "touch_value": 258.14,
   "suppressed": false,
   "suppressed_reason": null
  },
  {
   "account_id": 329,
   "name": "Gypsum Hills Trading Group",
   "segment": "PROP",
   "side": "speculator",
   "stage": "DORMANT",
   "hub": "HB_HOUSTON",
   "iso": "ERCOT",
   "direction": "opportunity",
   "exposure_line": "Trades ERCOT volatility; scarcity pricing at HB_HOUSTON creates short-dated dislocations its desk can expre…",
   "exposure_score": 85.5,
   "p_active": 0.5769,
   "exp_adv": 342.3,
   "last_touch_days": 4,
   "touch_value": 168.84,
   "suppressed": false,
   "suppressed_reason": null
  },
  "… 190 more"
 ]
}
```

### GET /pulse/history

```json
{
 "as_of": "2026-10-05",
 "events": [
  {
   "trigger_id": "PJM-PJM_WESTERN_HUB-20260126",
   "hub": "PJM_WESTERN_HUB",
   "iso": "PJM",
   "regime": "winter_peak",
   "peak_lmp": 599.67,
   "spike_hours": 18,
   "severity": 98.5,
   "start_ts": "2026-01-26T12:00:00",
   "end_ts": "2026-01-29T00:00:00"
  },
  {
   "trigger_id": "MISO-MISO_INDIANA_HUB-20260127",
   "hub": "MISO_INDIANA_HUB",
   "iso": "MISO",
   "regime": "winter_peak",
   "peak_lmp": 847.09,
   "spike_hours": 18,
   "severity": 98.5,
   "start_ts": "2026-01-27T12:00:00",
   "end_ts": "2026-01-30T00:00:00"
  },
  "… 27 more"
 ],
 "lift": {
  "triggered": {
   "n": 171,
   "activated_14d_rate": 0.3041
  },
  "untriggered": {
   "n": 114,
   "activated_14d_rate": 0.1228
  },
  "lift_x": 2.48
 },
 "note": "Cohort: funded-not-trading accounts exposed to each past event; activated = first trade within 14 days."
}
```

### GET /activation/queue?limit=2

```json
{
 "as_of": "2026-10-05",
 "summary": {
  "accounts_in_queue": 489,
  "stalled": 309,
  "sla_breaches": 239,
  "adv_at_stake": 6997.9,
  "with_trigger": 349,
  "hedger_share_active": 0.4414,
  "balance_weight_on": true
 },
 "formula": "priority = p_active × exp_adv × k_stage × urgency × balance_weight",
 "items": [
  {
   "rank": 1,
   "account_id": 337,
   "name": "Shinnery Trading",
   "segment": "PROP",
   "side": "speculator",
   "iso": "ERCOT",
   "hub": "HB_HOUSTON",
   "stage": "FUNDED",
   "rep_id": 5,
   "rep_name": "Dana Whitfield",
   "days_in_stage": 31,
   "stall": true,
   "p_active": 0.9641,
   "exp_adv": 322.2,
   "k_stage": 0.35,
   "urgency": 2.0,
   "urgency_factors": [
    "trigger ×1.5",
    "stall ×1.25",
    "… 1 more"
   ],
   "balance_weight": 1.0,
   "priority": 217.44,
   "trigger_id": "ERCOT-HB_HOUSTON-20261002",
   "last_touch_days": 6,
   "next_action": {
    "rule_id": "R09",
    "action": "Launch volatility sequence: T0 email with their hub chart + illustrative DAILY_PEAK replay of the event, co…",
    "owner": "AE",
    "sla": "4h",
    "sla_hours": 4,
    "sequence": "volatility",
    "condition_code": "VOL_TRIGGER_EXPOSED",
    "condition_text": "Stage QUALIFIED–FIRST_TRADE, hedger or speculator segment exposed to a volatility trigger (realized >3σ, sc…",
    "sla_breached": true
   },
   "reasons": [
    {
     "feature": "order_rejected",
     "label": "Had an order rejected (margin/limits)",
     "direction": "+",
     "weight": 2.026
    },
    {
     "feature": "seg_PROP",
     "label": "Proprietary trading firm",
     "direction": "+",
     "weight": 1.277
    },
    "… 1 more"
   ]
  },
  {
   "rank": 2,
   "account_id": 367,
   "name": "Onyx Markets",
   "segment": "PROP",
   "side": "speculator",
   "iso": "CAISO",
   "hub": "NP15",
   "stage": "FIRST_TRADE",
   "rep_id": 5,
   "rep_name": "Dana Whitfield",
   "days_in_stage": 10,
   "stall": false,
   "p_active": 0.997,
   "exp_adv": 370.6,
   "k_stage": 0.3,
   "urgency": 1.5,
   "urgency_factors": [
    "trigger ×1.5"
   ],
   "balance_weight": 1.0,
   "priority": 166.27,
   "trigger_id": "CAISO-SP15-20261003",
   "last_touch_days": 12,
   "next_action": {
    "rule_id": "R09",
    "action": "Launch volatility sequence: T0 email with their hub chart + illustrative DAILY_PEAK replay of the event, co…",
    "owner": "AE",
    "sla": "4h",
    "sla_hours": 4,
    "sequence": "volatility",
    "condition_code": "VOL_TRIGGER_EXPOSED",
    "condition_text": "Stage QUALIFIED–FIRST_TRADE, hedger or speculator segment exposed to a volatility trigger (realized >3σ, sc…",
    "sla_breached": true
   },
   "reasons": [
    {
     "feature": "trading_days_30",
     "label": "Already trading on several days",
     "direction": "+",
     "weight": 3.607
    },
    {
     "feature": "traded",
     "label": "Has already traded",
     "direction": "+",
     "weight": 1.451
    },
    "… 1 more"
   ]
  }
 ]
}
```

### GET /scoring/model

```json
{
 "as_of": "2026-10-05",
 "target": "active_60d",
 "train_n": 1460,
 "test_n": 1328,
 "train_accounts": 151,
 "test_accounts": 194,
 "train_window": [
  "2026-02-02",
  "2026-06-01"
 ],
 "test_window": [
  "2026-06-08",
  "2026-08-03"
 ],
 "auc": 0.836,
 "pr_auc": 0.7455,
 "brier": 0.1307,
 "base_rate": 0.2696,
 "lift_top_decile": 3.458,
 "gain_curve": [
  {
   "pct_accounts": 0.1,
   "pct_positives": 0.3464
  },
  {
   "pct_accounts": 0.2,
   "pct_positives": 0.5503
  },
  "… 8 more"
 ],
 "calibration": [
  {
   "bin": "0.0-0.1",
   "predicted": 0.0333,
   "observed": 0.1041,
   "n": 740
  },
  {
   "bin": "0.1-0.2",
   "predicted": 0.15,
   "observed": 0.2529,
   "n": 174
  },
  "… 8 more"
 ],
 "coefficients": [
  {
   "feature": "days_in_step",
   "label": "Days in current step",
   "coef": -0.7591
  },
  {
   "feature": "trading_days_30",
   "label": "Trading days (30d)",
   "coef": 0.55
  },
  "… 44 more"
 ],
 "challenger": {
  "name": "HistGradientBoostingClassifier",
  "auc": 0.8159,
  "pr_auc": 0.6995,
  "lift_top_decile": 3.235
 },
 "target_description": "P(Active within 60 days of snapshot) — Active = ≥4 distinct trading days within 30 calendar days"
}
```

### GET /funnel

```json
{
 "as_of": "2026-10-05",
 "filters": {
  "segment": null,
  "iso": null
 },
 "population": 332,
 "steps": [
  {
   "step": "contract_signed",
   "label": "Contract signed",
   "n": 332,
   "conv_from_prev": null,
   "median_days_from_prev": null,
   "p75_days": null
  },
  {
   "step": "platform_account_created",
   "label": "Platform account created",
   "n": 332,
   "conv_from_prev": 1.0,
   "median_days_from_prev": 1.09,
   "p75_days": 1.95
  },
  "… 9 more"
 ],
 "states": {
  "active": 111,
  "at_risk": 24,
  "dormant": 47,
  "funded_new": 16
 },
 "by_segment": [
  {
   "segment": "IPP",
   "label": "Independent Power Producer",
   "n": 45,
   "steps": [
    {
     "step": "contract_signed",
     "n": 45,
     "conv_from_prev": null,
     "median_days": null
    },
    {
     "step": "platform_account_created",
     "n": 45,
     "conv_from_prev": 1.0,
     "median_days": 1.01
    },
    "… 9 more"
   ]
  },
  {
   "segment": "STORAGE",
   "label": "Battery Storage Operator",
   "n": 35,
   "steps": [
    {
     "step": "contract_signed",
     "n": 35,
     "conv_from_prev": null,
     "median_days": null
    },
    {
     "step": "platform_account_created",
     "n": 35,
     "conv_from_prev": 1.0,
     "median_days": 1.13
    },
    "… 9 more"
   ]
  },
  "… 6 more"
 ],
 "friction": [
  {
   "step": "activated",
   "from_step": "first_trade",
   "segment": "IPP",
   "metric": "conversion",
   "metric_label": "conversion from previous step",
   "value": 0.6875,
   "benchmark": 0.8811,
   "accounts_affected": 5,
   "adv_at_stake": 198.7,
   "roadmap_ask": "Independent Power Producer: 69% vs 88% for all segments at 'Activated (Active)'. Ask: Post-first-trade rout…",
   "severity": "high",
   "affected_account_ids": [
    424,
    87,
    "… 3 more"
   ]
  },
  {
   "step": "order_ticket_opened",
   "from_step": "funded",
   "segment": "IPP",
   "metric": "median_days",
   "metric_label": "median days from previous step",
   "value": 44.65,
   "benchmark": 24.92,
   "accounts_affected": 7,
   "adv_at_stake": 81.2,
   "roadmap_ask": "Independent Power Producer: median 44.6 d vs 24.9 d for all segments at 'Order ticket opened'. Ask: In-app …",
   "severity": "high",
   "affected_account_ids": [
    361,
    442,
    "… 5 more"
   ]
  },
  "… 14 more"
 ]
}
```

### GET /segments

```json
{
 "as_of": "2026-10-05",
 "cells": [
  {
   "segment": "IPP",
   "iso": "ERCOT",
   "tam_accounts": 31,
   "signed": 21,
   "funded": 8,
   "active": 4,
   "penetration": 0.6774,
   "activation_rate": 0.5,
   "adv_per_active": 6.9,
   "adv_total": 27.4
  },
  {
   "segment": "IPP",
   "iso": "PJM",
   "tam_accounts": 15,
   "signed": 5,
   "funded": 2,
   "active": 0,
   "penetration": 0.3333,
   "activation_rate": 0.0,
   "adv_per_active": null,
   "adv_total": 0.0
  },
  "… 30 more"
 ],
 "segments": [
  {
   "segment": "IPP",
   "label": "Independent Power Producer",
   "side": "hedger",
   "tam": 90,
   "signed": 45,
   "funded": 25,
   "active": 10,
   "penetration": 0.5,
   "activation_rate": 0.4,
   "adv": 103.5,
   "adv_share": 0.0138,
   "adv_per_active": 10.4,
   "recommended_coverage": "Activation focus: RevOps KYC chases + AE hub walkthroughs before new logos"
  },
  {
   "segment": "STORAGE",
   "label": "Battery Storage Operator",
   "side": "hedger",
   "tam": 60,
   "signed": 35,
   "funded": 29,
   "active": 11,
   "penetration": 0.5833,
   "activation_rate": 0.3793,
   "adv": 510.3,
   "adv_share": 0.068,
   "adv_per_active": 46.4,
   "recommended_coverage": "Activation focus: RevOps KYC chases + AE hub walkthroughs before new logos"
  },
  "… 6 more"
 ],
 "liquidity_partners": {
  "accounts": 12,
  "active": 12,
  "adv": 7884.4
 },
 "note": "Liquidity partners excluded from segment cells (separate motion); ADV = 20-td contracts/day."
}
```

### GET /liquidity?iso=ERCOT&tenor=HOURLY

```json
{
 "as_of": "2026-10-05",
 "iso": "ERCOT",
 "tenor": "HOURLY",
 "series": [
  {
   "date": "2026-01-05",
   "iso": "ERCOT",
   "hub": "HB_HOUSTON",
   "tenor": "HOURLY",
   "spread_usd_mwh": 2.56,
   "uptime_pct": 66.8,
   "active_accounts": 0,
   "lp_quote_share": 0.97,
   "top_depth_contracts": 5
  },
  {
   "date": "2026-01-06",
   "iso": "ERCOT",
   "hub": "HB_HOUSTON",
   "tenor": "HOURLY",
   "spread_usd_mwh": 2.609,
   "uptime_pct": 64.72,
   "active_accounts": 0,
   "lp_quote_share": 0.97,
   "top_depth_contracts": 5
  },
  "… 817 more"
 ],
 "elasticity": {
  "b": 2.3758,
  "a": {
   "HB_HOUSTON|HOURLY": 0.8208,
   "HB_NORTH|HOURLY": 0.5851,
   "HB_WEST|HOURLY": 0.9988
  },
  "r2": 0.8963,
  "n": 807,
  "note": "Spread ≈ a + 2.38/√active (R² 0.90, n=807). At 80 active accounts on HB_NORTH, each +10 Active accounts tig…"
 }
}
```

### GET /team/scorecards

```json
{
 "as_of": "2026-10-05",
 "scoring": "component = min(actual / target, 1.5) for direction 'higher'; min(target / actual, 1.5) for 'lower' (actual…",
 "weights": {
  "funded_vs_quota": 0.25,
  "activation_rate": 0.25,
  "book_adv_vs_target": 0.2,
  "median_days_sign_to_trade": 0.1,
  "pipeline_coverage": 0.1,
  "sla_adherence": 0.1
 },
 "reps": [
  {
   "rep_id": 5,
   "name": "Dana Whitfield",
   "role": "STRATEGIC",
   "region": "National",
   "funded_ytd": 52.25,
   "quota_ytd": 13.7,
   "attainment": 3.825,
   "activation_rate": 0.7708,
   "activation_n": 48,
   "book_adv": 5601.2,
   "quota_adv": 6000.0,
   "book_adv_vs_target": 0.9335,
   "median_days_sign_to_trade": 49.1,
   "pipeline_coverage": 8.34,
   "pipeline_accounts": 37,
   "sla_adherence": 0.5217,
   "sla_items": 46,
   "score": 109.6,
   "components": {
    "funded_vs_quota": 37.5,
    "activation_rate": 27.5,
    "book_adv_vs_target": 18.7,
    "median_days_sign_to_trade": 5.1,
    "pipeline_coverage": 15.0,
    "sla_adherence": 5.8
   },
   "component_ratios": {
    "funded_vs_quota": 1.5,
    "activation_rate": 1.101,
    "book_adv_vs_target": 0.934,
    "median_days_sign_to_trade": 0.51,
    "pipeline_coverage": 1.5,
    "sla_adherence": 0.58
   },
   "red_flags": []
  },
  {
   "rep_id": 1,
   "name": "Maya Castillo",
   "role": "AE",
   "region": "ERCOT",
   "funded_ytd": 69.0,
   "quota_ytd": 18.2,
   "attainment": 3.7884,
   "activation_rate": 0.3673,
   "activation_n": 49,
   "book_adv": 1572.1,
   "quota_adv": 2500.0,
   "book_adv_vs_target": 0.6288,
   "median_days_sign_to_trade": 79.7,
   "pipeline_coverage": 10.98,
   "pipeline_accounts": 65,
   "sla_adherence": 0.5556,
   "sla_items": 36,
   "score": 87.5,
   "components": {
    "funded_vs_quota": 37.5,
    "activation_rate": 13.1,
    "book_adv_vs_target": 12.6,
    "median_days_sign_to_trade": 3.1,
    "pipeline_coverage": 15.0,
    "sla_adherence": 6.2
   },
   "component_ratios": {
    "funded_vs_quota": 1.5,
    "activation_rate": 0.525,
    "book_adv_vs_target": 0.629,
    "median_days_sign_to_trade": 0.314,
    "pipeline_coverage": 1.5,
    "sla_adherence": 0.617
   },
   "red_flags": [
    "median_days_sign_to_trade"
   ]
  },
  "… 3 more"
 ]
}
```

### POST /team/comp-sim  `{"plan_id":"activation_adv","params":{"per_account_unit":2500}}`

```json
{
 "as_of": "2026-10-05",
 "period": "YTD 2026 (2026-01-01 – 2026-10-04)",
 "reps": [
  {
   "rep_id": 1,
   "name": "Maya Castillo",
   "role": "AE",
   "payout_variable": 183320.5,
   "payout_breakdown": {
    "funded": 86250.0,
    "activation": 60000.0,
    "speed_bonus": 6250.0,
    "accelerator": 59375.0,
    "adv_kicker": 4570.5,
    "clawback": -33125.0
   },
   "signed_ytd": 110,
   "funded_ytd": 69,
   "active_60d": 24,
   "quota_ytd": 18.21
  },
  {
   "rep_id": 2,
   "name": "Ben Okafor",
   "role": "AE",
   "payout_variable": 39880.45,
   "payout_breakdown": {
    "funded": 26250.0,
    "activation": 15000.0,
    "speed_bonus": 1875.0,
    "accelerator": 1875.0,
    "adv_kicker": 1130.45,
    "clawback": -6250.0
   },
   "signed_ytd": 49,
   "funded_ytd": 21,
   "active_60d": 6,
   "quota_ytd": 18.21
  },
  "… 3 more"
 ],
 "totals": {
  "variable_cost": 496012.25,
  "active_accounts": 71,
  "per_active_account": 6986.09,
  "contracts_ytd": 1944654.0,
  "per_1k_contracts": 255.06
 },
 "comparison": [
  {
   "plan_id": "pay_on_signature",
   "name": "(a) Pay on signature",
   "variable_cost": 1647775.28,
   "per_active_account": 23208.1,
   "per_1k_contracts": 847.34,
   "behavior": "Rewards signing as many agreements as possible, including marginal accounts that never fund or trade.",
   "simulated_params": false
  },
  {
   "plan_id": "pay_on_funded",
   "name": "(b) Pay on funded",
   "variable_cost": 811458.99,
   "per_active_account": 11429.0,
   "per_1k_contracts": 417.28,
   "behavior": "Rewards getting accounts through KYC and funded, with a light penalty when they never trade.",
   "simulated_params": false
  },
  "… 1 more"
 ],
 "plan": {
  "plan_id": "activation_adv",
  "name": "(c) Funded + activation + ADV (recommended)",
  "per_account_unit": 2500.0,
  "multipliers": {
   "signed": 0.0,
   "funded": 0.5,
   "active_60d": 1.0,
   "active_21d_bonus": 0.25
  }
 }
}
```

### GET /marketing/roi?months=6

```json
{
 "as_of": "2026-10-05",
 "months": 6,
 "window": {
  "from": "2026-04-01",
  "to": "2026-09-30"
 },
 "channels": [
  {
   "channel": "Industry Conferences",
   "spend": 276244.22,
   "leads": 143,
   "accounts": 55,
   "signed": 34,
   "funded": 21,
   "active": 7,
   "cac_funded": 13154.49,
   "cac_active": 39463.46,
   "adv": 1200.5,
   "adv_per_1k_spend": 4.346,
   "n_small": false
  },
  {
   "channel": "Webinars & Education",
   "spend": 70962.8,
   "leads": 168,
   "accounts": 46,
   "signed": 25,
   "funded": 13,
   "active": 5,
   "cac_funded": 5458.68,
   "cac_active": 14192.56,
   "adv": 305.3,
   "adv_per_1k_spend": 4.302,
   "n_small": true
  },
  "… 5 more"
 ],
 "monthly": [
  {
   "month": "2026-04-01",
   "channel": "Content & SEO",
   "spend": 13044.51,
   "leads": 33,
   "campaign": "Contract spec guides"
  },
  {
   "month": "2026-04-01",
   "channel": "Industry Conferences",
   "spend": 74807.19,
   "leads": 39,
   "campaign": "Grid Markets Week sponsorship"
  },
  "… 40 more"
 ],
 "note": "Attribution: lead_source of accounts created in the window; channels with < 20 funded accounts are small-n …"
}
```

### GET /accounts?q=storage&limit=2

```json
{
 "as_of": "2026-10-05",
 "total": 50,
 "limit": 2,
 "offset": 0,
 "items": [
  {
   "id": 27,
   "name": "Basswood Grid Storage",
   "segment": "STORAGE",
   "iso": "PJM",
   "hub": "PJM_WESTERN_HUB",
   "stage": "QUALIFIED",
   "rep": "Ben Okafor",
   "rep_id": 2,
   "is_liquidity_partner": false,
   "p_active": 0.0008,
   "adv_30d": 0.0
  },
  {
   "id": 124,
   "name": "Big Bend Energy Storage",
   "segment": "STORAGE",
   "iso": "CAISO",
   "hub": "NP15",
   "stage": "FUNDED",
   "rep": "Priya Raman",
   "rep_id": 3,
   "is_liquidity_partner": false,
   "p_active": 0.3901,
   "adv_30d": 0.0
  }
 ]
}
```

### GET /accounts/{id}

```json
{
 "as_of": "2026-10-05",
 "account": {
  "id": 320,
  "name": "Albatross Power Partners",
  "segment": "IPP",
  "segment_label": "Independent Power Producer",
  "side": "hedger",
  "primary_iso": "CAISO",
  "iso": "CAISO",
  "hub": "NP15",
  "exposure_isos": [
   "CAISO",
   "PJM"
  ],
  "hq_state": "CA",
  "stage": "ACTIVE",
  "rep_id": 3,
  "rep_name": "Priya Raman",
  "is_liquidity_partner": false,
  "has_other_exchange_account": false,
  "kyc_redlines": 0,
  "funded_amount_usd": 106000.0,
  "size_mw": 57.6,
  "est_annual_mwh": 159226.0,
  "tam_tier": "C",
  "lead_source": "Outbound Prospecting",
  "p_active": 0.9951,
  "exp_adv": 43.7,
  "days_in_stage": 20,
  "last_touch_days": 3,
  "created_at": "2026-07-27T14:07:00",
  "signed_at": "2026-08-13T18:45:00",
  "kyc_approved_at": "2026-08-31T21:36:00",
  "funded_at": "2026-09-02T16:55:00",
  "first_trade_at": "2026-09-07T16:44:00",
  "first_qualifying_trade_at": "2026-09-07T16:44:00",
  "active_since": "2026-09-15T00:00:00"
 },
 "contacts": [
  {
   "id": 751,
   "name": "Adrian Thornton",
   "title": "VP Finance",
   "persona": "CFO",
   "email": "a.thornton@albatrosspowerpartners.example",
   "is_champion": true
  },
  {
   "id": 752,
   "name": "Mei Mercer",
   "title": "President",
   "persona": "EXEC",
   "email": "m.mercer@albatrosspowerpartners.example",
   "is_champion": false
  },
  "… 3 more"
 ],
 "timeline": [
  {
   "ts": "2026-10-01T14:42:00",
   "type": "call",
   "label": "Call · Priya Raman"
  },
  {
   "ts": "2026-09-15T21:00:00",
   "type": "trade",
   "label": "Traded 1 contracts in 1 fills (PJM_WESTERN_HUB)"
  },
  "… 36 more"
 ],
 "onboarding": [
  {
   "step": "contract_signed",
   "label": "Contract signed",
   "ts": "2026-08-13T18:45:00"
  },
  {
   "step": "platform_account_created",
   "label": "Platform account created",
   "ts": "2026-08-14T16:59:00"
  },
  "… 10 more"
 ],
 "adv_series": [
  {
   "date": "2026-09-07",
   "contracts": 19
  },
  {
   "date": "2026-09-08",
   "contracts": 5
  },
  "… 18 more"
 ],
 "health": {
  "state": "active",
  "trading_days_30": 4,
  "adv_30d": 2.0,
  "adv_prior_30d": 0.0,
  "net_retention": null,
  "churn_risk": 0.529,
  "last_trade_ts": "2026-09-15T14:11:00",
  "first_active_at": "2026-09-15T14:11:00"
 },
 "reasons": [
  {
   "feature": "trading_days_30",
   "label": "Already trading on several days",
   "direction": "+",
   "weight": 4.85
  },
  {
   "feature": "traded",
   "label": "Has already traded",
   "direction": "+",
   "weight": 1.451
  },
  "… 1 more"
 ],
 "next_action": {
  "rule_id": "R15",
  "action": "Send compliance-approved market note: hub, peak $/MWh, spike hours, 5-day forward look; no sequence for Act…",
  "owner": "AE",
  "sla": "24h",
  "sla_hours": 24,
  "sequence": null,
  "condition_code": "VOL_TRIGGER_EXPOSED",
  "condition_text": "Active/Expanding/At-Risk account exposed to a volatility trigger in its ISO (Active accounts get a note, no…",
  "sla_breached": true
 },
 "queue": {
  "priority": 7.5,
  "urgency": 1.5,
  "k_stage": 0.1,
  "balance_weight": 1.15,
  "stall": false,
  "trigger_id": "CAISO-SP15-20261003"
 },
 "qbr": {
  "utilization_by_tenor": {
   "HOURLY": 0.8,
   "DAILY_PEAK": 0.175,
   "WEEKLY_PEAK": 0.025
  },
  "isos_traded": [
   "CAISO",
   "PJM"
  ],
  "contracts_90d": 40,
  "fees_90d": 10.0,
  "last_qbr": null,
  "growth_plays": []
 }
}
```

### POST /outreach/draft  `{"account_id":…, "trigger_id":"ERCOT-HB_HOUSTON-20261002", "kind":"volatility"}`

```json
{
 "draft_id": 1,
 "account_id": 178,
 "kind": "volatility",
 "trigger_id": "ERCOT-HB_HOUSTON-20261002",
 "template_id": "VOL_REP_SCARCITY",
 "subject": "HB_HOUSTON, Oct 2, 2026: 9 hours of scarcity pricing and the week ahead",
 "body": "Hi Ingrid,\n\nOn Oct 2, 2026, ERCOT real-time prices at HB_HOUSTON reached $4,800/MWh, with 9 hours of scarci…",
 "engine": "template",
 "facts": {
  "first_name": "Ingrid",
  "account_name": "Caddo Bend Energy Services",
  "rep_name": "Maya Castillo",
  "hub": "HB_HOUSTON",
  "iso": "ERCOT",
  "event_peak_price": "$4,800",
  "event_hours": 9,
  "event_date": "Oct 2, 2026",
  "regime_label": "scarcity pricing",
  "exposure_line": "serves fixed-price retail load settled at HB_HOUSTON; every scarcity hour it buys back in real time comes s…",
  "contract_suggestion": "the HB_HOUSTON DAILY_PEAK contract (16 MWh: 1 MW across the 16 on-peak hours)",
  "forecast_line": "The 5-day model forecast issued Oct 4 shows a daily peak of $1,650/MWh at HB_HOUSTON on Oct 7; forecasts ar…",
  "walkthrough_cta": "If a 20-minute walkthrough with your trading or risk lead would help, reply with two times that suit and I …",
  "kind": "volatility",
  "template_id": "VOL_REP_SCARCITY",
  "segment": "REP",
  "direction": "hurt",
  "regime": "scarcity",
  "trigger_id": "ERCOT-HB_HOUSTON-20261002",
  "event_peak_lmp": 4800.0,
  "event_start_ts": "2026-10-02T15:00:00",
  "forecast_peak_lmp": 1650.0,
  "forecast_date": "2026-10-07",
  "first_product": "DAILY_PEAK"
 },
 "compliance": {
  "passed": true,
  "flags": []
 },
 "status": "pending_review"
}
```

### POST /outreach/{id}/approve → /queue

```json
{"draft_id": 1, "status": "approved", "activity_id": null, "account_id": null, "trigger_id": null, "logged_at": null}
{"draft_id": 1, "status": "queued", "activity_id": 11655, "account_id": 178, "trigger_id": "ERCOT-HB_HOUSTON-20261002", "logged_at": "2026-10-05T00:00:00"}
```

Calling `/queue` before `/approve`, approving a draft with a `block` flag, or queueing twice → `409`.

### Compliance flag shape

```json
{"rule": "R02_BANNED_PHRASE_BLOCK", "phrase": "guaranteed", "level": "block",
 "message": "Banned phrase “guaranteed” (promissory / advice / endorsement language). Edit and re-lint."}
```
