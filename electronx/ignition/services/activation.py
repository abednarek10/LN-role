"""Activation Queue (spec D4, CRO memo §1–§2) and the next-best-action engine.

Priority = P(Active ≤60d) × E[ADV] × k_stage × U × B

* P       — calibrated propensity (``propensity.score_accounts``).
* E[ADV]  — segment prior × size factor (``common.expected_adv``).
* k_stage — ``definitions.K_STAGE`` (uplift proxy per stage).
* U       — urgency, base 1.0, ×1.5 live volatility trigger in an exposure ISO
            (not in the 14-day triggered cooldown), ×1.25 breached stall
            threshold, ×1.2 forecast peak ≤5 d out (not touched in the last
            5 d); capped at 2.0.
* B       — ×1.15 for hedgers while hedger share of Active accounts < 50%.

NBA rules come from ``content/nba_rules.json``: evaluated in ``priority`` order,
first match wins, honoring ``stages`` and ``segments``. Liquidity partners are
excluded from the queue (separate motion).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .. import definitions as D
from .common import AS_OF_TS, content, num, as_int

QUEUE_STAGES = ("TARGET", "QUALIFIED", "SIGNED", "KYC_APPROVED", "FUNDED", "FIRST_TRADE", "AT_RISK", "DORMANT")
TRIGGER_STAGES = frozenset({"QUALIFIED", "SIGNED", "KYC_APPROVED", "FUNDED", "FIRST_TRADE", "AT_RISK", "DORMANT"})

CONDITION_CODES = frozenset({
    "TOP_DECILE_UNTOUCHED", "QUALIFIED_NO_AGREEMENT_10D", "KYC_NOT_STARTED_3D", "KYC_STALLED_5D",
    "KYC_APPROVED_UNFUNDED_5D", "FUNDED_NO_TRADE_7D", "FUNDED_NO_TRADE_21D", "NO_API_KEY_5D",
    "VOL_TRIGGER_EXPOSED", "NO_SECOND_DAY_10D", "ACTIVE_DECLINING", "EXPANSION_READY", "TOP20_QBR_DUE",
    "DORMANT_30D", "DEFAULT",
})

# CRO §1 stall thresholds (days)
STALL_D = {"QUALIFIED": 30, "SIGNED_NOT_SUBMITTED": 3, "SIGNED_OPEN": 5, "SIGNED_TOTAL": 10,
           "KYC_APPROVED": 5, "FUNDED": 7, "FIRST_TRADE_NO_2ND": 10, "TARGET_UNTOUCHED": 5}


def rules() -> list[dict]:
    """NBA rules sorted by priority (first match wins)."""
    return sorted(content("nba_rules"), key=lambda r: (r.get("priority", 999), r["rule_id"]))


def _days(later, earlier) -> float | None:
    if earlier is None or pd.isna(earlier):
        return None
    return (pd.Timestamp(later) - pd.Timestamp(earlier)).total_seconds() / 86400.0


@dataclass
class NBAContext:
    """Facts shared by every account when evaluating rules."""
    as_of: pd.Timestamp = AS_OF_TS
    triggers: list[dict] = field(default_factory=list)
    top_decile_p: float = 1.0  # p_active threshold for top decile of TARGET accounts
    top20_ids: frozenset = frozenset()

    @property
    def realized(self) -> list[dict]:
        return [t for t in self.triggers if pd.Timestamp(t["start_ts"]) < self.as_of]


def account_trigger(row, ctx: NBAContext) -> dict | None:
    """The live realized trigger relevant to this account (own hub first, then severity)."""
    isos = set(row["isos"])
    cands = [t for t in ctx.realized if t["iso"] in isos]
    if not cands:
        return None
    own = [t for t in cands if t["hub"] == row["hub"]]
    return max(own or cands, key=lambda t: t["severity"])


def forward_risk(row, ctx: NBAContext) -> bool:
    isos = set(row["isos"])
    return any(t.get("forward_risk") and t["iso"] in isos for t in ctx.triggers)


def in_trigger_cooldown(row, ctx: NBAContext) -> bool:
    lt = row.get("last_trig_ts")
    return lt is not None and pd.notna(lt) and _days(ctx.as_of, lt) < D.TRIGGER_COOLDOWN_D


def recently_touched(row, ctx: NBAContext, days: int = D.TOUCH_SUPPRESS_D) -> bool:
    lt = row.get("last_touch_ts")
    return lt is not None and pd.notna(lt) and _days(ctx.as_of, lt) < days


def evaluate_condition(code: str, row, ctx: NBAContext) -> tuple[bool, pd.Timestamp | None]:
    """(matches, condition_since). ``since`` is when the condition first held (for SLA)."""
    t = ctx.as_of
    g = row.get
    if code == "DEFAULT":
        return True, None
    if code == "TOP_DECILE_UNTOUCHED":
        p = g("p_active")
        ok = p is not None and pd.notna(p) and p >= ctx.top_decile_p and int(g("n_touches") or 0) == 0
        return ok, g("created_at")
    if code == "QUALIFIED_NO_AGREEMENT_10D":
        e = g("stage_entry_ts")
        d = _days(t, e)
        return (d is not None and d > 10 and pd.isna(g("signed_at"))), (pd.Timestamp(e) + pd.Timedelta(days=10) if d is not None else None)
    if code == "KYC_NOT_STARTED_3D":
        d = _days(t, g("signed_at"))
        ok = d is not None and d > 3 and pd.isna(g("ob_kyc_submitted"))
        return ok, (pd.Timestamp(g("signed_at")) + pd.Timedelta(days=3)) if d is not None else None
    if code == "KYC_STALLED_5D":
        s = g("ob_kyc_submitted")
        d = _days(t, s)
        ok = d is not None and d > 5 and pd.isna(g("kyc_approved_at"))
        return ok, (pd.Timestamp(s) + pd.Timedelta(days=5)) if d is not None else None
    if code == "KYC_APPROVED_UNFUNDED_5D":
        d = _days(t, g("kyc_approved_at"))
        ok = d is not None and d > 5 and pd.isna(g("funded_at"))
        return ok, (pd.Timestamp(g("kyc_approved_at")) + pd.Timedelta(days=5)) if d is not None else None
    if code in ("FUNDED_NO_TRADE_7D", "FUNDED_NO_TRADE_21D"):
        n = 7 if code.endswith("7D") else 21
        d = _days(t, g("funded_at"))
        fq = g("first_qualifying_trade_at")
        ok = d is not None and d > n and (fq is None or pd.isna(fq))
        return ok, (pd.Timestamp(g("funded_at")) + pd.Timedelta(days=n)) if d is not None else None
    if code == "NO_API_KEY_5D":
        d = _days(t, g("funded_at"))
        ok = d is not None and d > 5 and pd.isna(g("ob_api_key_created"))
        return ok, (pd.Timestamp(g("funded_at")) + pd.Timedelta(days=5)) if d is not None else None
    if code == "VOL_TRIGGER_EXPOSED":
        tr = account_trigger(row, ctx)
        ok = tr is not None and not in_trigger_cooldown(row, ctx)
        return ok, (pd.Timestamp(tr["start_ts"]) if tr else None)
    if code == "NO_SECOND_DAY_10D":
        d = _days(t, g("first_trade_at"))
        ok = d is not None and d > 10 and int(g("trade_days_total") or 0) <= 1
        return ok, (pd.Timestamp(g("first_trade_at")) + pd.Timedelta(days=10)) if d is not None else None
    if code == "ACTIVE_DECLINING":
        prior = int(g("td_prior30") or 0)
        now = int(g("trading_days_30") or 0)
        return (prior > 0 and now <= 0.5 * prior), None
    if code == "EXPANSION_READY":
        a = g("active_since")
        d = _days(t, a)
        narrow = len(g("isos_traded_90d") or []) <= 1 or len(g("tenors_traded_90d") or []) <= 1
        multi_iso = len(g("isos") or []) > 1
        ok = d is not None and d >= D.EXPANDING_MIN_ACTIVE_D and narrow and multi_iso
        return ok, (pd.Timestamp(a) + pd.Timedelta(days=60)) if d is not None else None
    if code == "TOP20_QBR_DUE":
        q = g("last_qbr_ts")
        due = q is None or pd.isna(q) or _days(t, q) > 90
        ok = g("id") in ctx.top20_ids and due
        return ok, (pd.Timestamp(q) + pd.Timedelta(days=90)) if (q is not None and pd.notna(q)) else None
    if code == "DORMANT_30D":
        f = g("funded_at")
        d = _days(t, f)
        ok = d is not None and d >= 30 and int(g("trading_days_30") or 0) == 0
        lt = g("last_trade_ts")
        since = max(pd.Timestamp(f) + pd.Timedelta(days=30),
                    (pd.Timestamp(lt) + pd.Timedelta(days=30)) if lt is not None and pd.notna(lt) else pd.Timestamp(f))
        return ok, since if d is not None else None
    raise ValueError(f"unknown condition_code {code!r}")


def _applies(rule: dict, stage: str, segment: str) -> bool:
    stages = rule.get("stages") or [rule.get("stage", "*")]
    if "*" not in stages and stage not in stages:
        return False
    segs = rule.get("segments", "*")
    if segs != "*" and segment not in (segs if isinstance(segs, list) else [segs]):
        return False
    return True


def next_best_action(row, ctx: NBAContext, rule_list: list[dict] | None = None) -> dict:
    """First matching rule → ``{rule_id, action, owner, sla, sequence, ...}``."""
    for rule in rule_list or rules():
        if not _applies(rule, row["stage"], row["segment"]):
            continue
        ok, since = evaluate_condition(rule["condition_code"], row, ctx)
        if not ok:
            continue
        sla_h = float(rule.get("sla_hours") or 0)
        breached = False
        if since is not None and sla_h:
            due = pd.Timestamp(since) + pd.Timedelta(hours=sla_h)
            lt = row.get("last_touch_ts")
            touched_since = lt is not None and pd.notna(lt) and pd.Timestamp(lt) >= pd.Timestamp(since)
            breached = bool(ctx.as_of > due and not touched_since)
        return {
            "rule_id": rule["rule_id"],
            "action": rule["action"],
            "owner": rule["owner"],
            "sla": f"{int(sla_h)}h" if sla_h else None,
            "sla_hours": int(sla_h) if sla_h else None,
            "sequence": rule.get("sequence"),
            "condition_code": rule["condition_code"],
            "condition_text": rule.get("condition_text"),
            "sla_breached": breached,
        }
    return {"rule_id": None, "action": "Review in Account 360", "owner": "AE", "sla": None,
            "sla_hours": None, "sequence": None, "condition_code": "DEFAULT", "condition_text": None,
            "sla_breached": False}


def is_stalled(row, ctx: NBAContext) -> bool:
    """CRO §1 stall flags."""
    t = ctx.as_of
    st = row["stage"]
    g = row.get
    if st == "TARGET":
        p = g("p_active")
        top_q = p is not None and pd.notna(p) and p >= g("_target_q80", 1.0)
        lt = g("last_touch_ts")
        untouched = (lt is None or pd.isna(lt) or _days(t, lt) > STALL_D["TARGET_UNTOUCHED"])
        return bool(top_q and untouched and (_days(t, g("created_at")) or 0) > STALL_D["TARGET_UNTOUCHED"])
    if st == "QUALIFIED":
        return (g("days_in_stage") or 0) > STALL_D["QUALIFIED"]
    if st == "SIGNED":
        d = _days(t, g("signed_at")) or 0
        sub = g("ob_kyc_submitted")
        if sub is None or pd.isna(sub):
            return d > STALL_D["SIGNED_NOT_SUBMITTED"]
        return (_days(t, sub) or 0) > STALL_D["SIGNED_OPEN"] or d > STALL_D["SIGNED_TOTAL"]
    if st == "KYC_APPROVED":
        return (_days(t, g("kyc_approved_at")) or 0) > STALL_D["KYC_APPROVED"]
    if st == "FUNDED":
        return (_days(t, g("funded_at")) or 0) > STALL_D["FUNDED"]
    if st == "FIRST_TRADE":
        lt = g("last_trade_ts")
        return lt is not None and pd.notna(lt) and _days(t, lt) > STALL_D["FIRST_TRADE_NO_2ND"]
    if st in ("ACTIVE", "EXPANDING", "AT_RISK"):
        prior = int(g("td_prior30") or 0)
        return prior > 0 and int(g("trading_days_30") or 0) <= 0.5 * prior
    if st == "DORMANT":
        return True
    return False


def urgency(row, ctx: NBAContext, stalled: bool) -> tuple[float, dict | None, list[str]]:
    """(U, trigger_used, factor labels)."""
    u = D.URGENCY_BASE
    why: list[str] = []
    tr = account_trigger(row, ctx)
    used = None
    if tr is not None and not in_trigger_cooldown(row, ctx):
        u *= D.URGENCY_TRIGGER
        used = tr
        why.append(f"trigger ×{D.URGENCY_TRIGGER}")
    if stalled:
        u *= D.URGENCY_STALL
        why.append(f"stall ×{D.URGENCY_STALL}")
    if forward_risk(row, ctx) and not recently_touched(row, ctx):
        u *= D.URGENCY_FORECAST
        why.append(f"forecast ×{D.URGENCY_FORECAST}")
    return min(u, D.URGENCY_CAP), used, why


def hedger_share_active(acc: pd.DataFrame) -> float:
    """Hedger accounts ÷ all Active accounts (LPs in the denominator, CEO mix)."""
    act = acc[acc["trading_days_30"] >= D.ACTIVE_MIN_DAYS]
    return float((act["side"] == "hedger").mean()) if len(act) else 0.0


def balance_weight(side: str, hedger_share: float) -> float:
    target = float(D.TARGETS_2026["hedger_share_active"])
    return D.BALANCE_WEIGHT_HEDGER if side == "hedger" and hedger_share < target else 1.0


def build_context(acc: pd.DataFrame, triggers: list[dict], as_of=D.AS_OF) -> NBAContext:
    nonlp = acc[~acc["is_liquidity_partner"].astype(bool)]
    tgt = nonlp[nonlp["stage"] == "TARGET"]["p_active"].dropna()
    thr = float(tgt.quantile(0.9)) if len(tgt) else 1.0
    top20 = nonlp.sort_values("adv_20td", ascending=False)
    top20 = top20[top20["adv_20td"] > 0].head(20)
    return NBAContext(as_of=pd.Timestamp(as_of), triggers=triggers, top_decile_p=thr,
                      top20_ids=frozenset(int(i) for i in top20["id"]))


def score_rows(acc: pd.DataFrame, triggers: list[dict], as_of=D.AS_OF) -> pd.DataFrame:
    """Every non-LP account with NBA, stall, U, B, priority (unfiltered, unranked)."""
    ctx = build_context(acc, triggers, as_of)
    hs = hedger_share_active(acc)
    rl = rules()
    nonlp = acc[~acc["is_liquidity_partner"].astype(bool)].copy()
    tgt = nonlp[nonlp["stage"] == "TARGET"]["p_active"].dropna()
    q80 = float(tgt.quantile(0.8)) if len(tgt) else 1.0
    out = []
    for rec in nonlp.to_dict("records"):
        rec["_target_q80"] = q80
        stalled = is_stalled(rec, ctx)
        u, trig, why = urgency(rec, ctx, stalled)
        na = next_best_action(rec, ctx, rl)
        b = balance_weight(rec["side"], hs)
        p = float(rec["p_active"]) if pd.notna(rec["p_active"]) else 0.0
        k = D.K_STAGE.get(rec["stage"], 0.1)
        out.append({
            "account_id": int(rec["id"]),
            "stall": bool(stalled),
            "urgency": round(u, 4),
            "urgency_factors": why,
            "trigger_id": trig["trigger_id"] if trig else None,
            "next_action": na,
            "balance_weight": b,
            "k_stage": k,
            "priority": round(p * float(rec["exp_adv"]) * k * u * b, 3),
        })
    return pd.DataFrame(out).set_index("account_id")


def _rows(state):
    return state.cached(("queue_rows",), lambda: score_rows(state.accounts, state.triggers))


def queue_item(rec: dict, s: dict, rank: int | None = None) -> dict:
    return {
        "rank": rank,
        "account_id": int(rec["id"]),
        "name": rec["name"],
        "segment": rec["segment"],
        "side": rec["side"],
        "iso": rec["primary_iso"],
        "hub": rec["hub"],
        "stage": rec["stage"],
        "rep_id": as_int(rec["rep_id"]),
        "rep_name": rec["rep_name"],
        "days_in_stage": as_int(rec["days_in_stage"]),
        "stall": s["stall"],
        "p_active": num(rec["p_active"]),
        "exp_adv": num(rec["exp_adv"], 1),
        "k_stage": s["k_stage"],
        "urgency": num(s["urgency"], 3),
        "urgency_factors": s["urgency_factors"],
        "balance_weight": s["balance_weight"],
        "priority": num(s["priority"], 2),
        "trigger_id": s["trigger_id"] if isinstance(s["trigger_id"], str) else None,
        "last_touch_days": as_int(rec["last_touch_days"]),
        "next_action": s["next_action"],
        "reasons": rec["reasons"],
    }


def queue(state, limit: int = 50, segment: str | None = None, iso: str | None = None,
          rep_id: int | None = None, stage: str | None = None) -> dict:
    key = ("queue", limit, segment, iso, rep_id, stage)
    return state.cached(key, lambda: _queue(state, limit, segment, iso, rep_id, stage))


def _queue(state, limit, segment, iso, rep_id, stage) -> dict:
    acc = state.accounts
    rows = _rows(state)
    df = acc.loc[rows.index]
    df = df[df["stage"].isin(QUEUE_STAGES)]
    if segment:
        df = df[df["segment"] == segment]
    if iso:
        df = df[df["primary_iso"] == iso]
    if rep_id is not None:
        df = df[df["rep_id"] == rep_id]
    if stage:
        df = df[df["stage"] == stage]
    sub = rows.loc[df.index]
    order = sub.sort_values(["priority", "urgency"], ascending=[False, False]).index
    recs = df.loc[order].to_dict("records")
    items = []
    stalled = breaches = 0
    stake = 0.0
    for i, rec in enumerate(recs, start=1):
        s = sub.loc[rec["id"]].to_dict()
        stalled += int(s["stall"])
        breaches += int(s["next_action"]["sla_breached"])
        p = rec["p_active"] if pd.notna(rec["p_active"]) else 0.0
        stake += float(p) * float(rec["exp_adv"])
        if i <= limit:
            items.append(queue_item(rec, s, i))
    return {
        "as_of": D.AS_OF_DATE.isoformat(),
        "summary": {
            "accounts_in_queue": len(recs),
            "stalled": stalled,
            "sla_breaches": breaches,
            "adv_at_stake": round(stake, 1),
            "with_trigger": int(sub["trigger_id"].map(lambda x: isinstance(x, str)).sum()),
            "hedger_share_active": round(hedger_share_active(acc), 4),
            "balance_weight_on": hedger_share_active(acc) < float(D.TARGETS_2026["hedger_share_active"]),
        },
        "formula": "priority = p_active × exp_adv × k_stage × urgency × balance_weight",
        "items": items,
    }


def account_next_action(state, account_id: int) -> dict | None:
    """NBA for any account (LPs and Active accounts included) — Account 360."""
    acc = state.accounts
    if account_id not in acc.index:
        return None
    rows = _rows(state)
    if account_id in rows.index:
        return rows.loc[account_id, "next_action"]
    ctx = state.cached(("nba_ctx",), lambda: build_context(acc, state.triggers))
    rec = acc.loc[account_id].to_dict()
    return next_best_action(rec, ctx)


def row_for(state, account_id: int) -> dict | None:
    rows = _rows(state)
    return rows.loc[account_id].to_dict() if account_id in rows.index else None
