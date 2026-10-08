"""Team & Comp: AE scorecards (``content/scorecard.json``) and the comp simulator
implementing each plan's ``formula`` from ``content/comp_plans.json``.

Plan period = YTD 2026 (2026-01-01 → AS_OF). Quota Q = quota_funded_annual ×
days_elapsed / 365 (prorated YTD, as the formulas state). Reps = AE + STRATEGIC
(the roles that carry a book). Accounts are credited by ``accounts.rep_id``.
"""
from __future__ import annotations

import copy
from datetime import datetime

import numpy as np
import pandas as pd

from .. import definitions as D
from . import features
from .common import AS_OF_TS, content, num

PERIOD_START = pd.Timestamp(datetime(2026, 1, 1))
DAYS_ELAPSED = (AS_OF_TS - PERIOD_START).days
YTD_FRAC = DAYS_ELAPSED / 365.0

# Milestone → (rule, SLA hours) used for SLA adherence (scorecard.json "sla_adherence").
SLA_EVENTS = {"signed_at": 24, "kyc_approved_at": 24, "funded_at": 48, "first_trade_at": 48}


def _book_reps(frames) -> pd.DataFrame:
    r = frames.reps
    return r[r["role"].isin(D.QUOTA_ROLES)].copy()


def _sla_deadline(ts: pd.Timestamp, hours: int) -> pd.Timestamp:
    """SLA clock in business hours: weekends don't count."""
    d = ts + pd.Timedelta(hours=hours)
    while d.dayofweek >= 5:
        d += pd.Timedelta(days=1)
    return d


# ---------------------------------------------------------------------------
# Scorecards
# ---------------------------------------------------------------------------
def _component(actual, target, direction: str) -> float:
    if actual is None or (isinstance(actual, float) and np.isnan(actual)):
        return 0.0
    if direction == "higher":
        return min(actual / target, 1.5) if target else 0.0
    return 1.5 if actual <= 0 else min(target / actual, 1.5)


def scorecards(state) -> dict:
    return state.cached(("scorecards",), lambda: _scorecards(state))


def _scorecards(state) -> dict:
    f = state.frames
    acc = state.accounts
    sc = content("scorecard")
    metrics = {m["key"]: m for m in sc["metrics"]}
    fa = features.first_active_at(f.trades[f.trades["ts"] < AS_OF_TS])
    acts = f.activities[(f.activities["ts"] <= AS_OF_TS) & f.activities["kind"].isin(
        ["email", "call", "meeting", "demo", "linkedin", "triggered_email", "walkthrough", "qbr"])]
    out = []
    for rep in _book_reps(f).itertuples(index=False):
        book = acc[acc["rep_id"] == rep.id]
        start = max(PERIOD_START, pd.Timestamp(rep.start_date))
        q_ytd = rep.quota_funded_annual * max((AS_OF_TS - start).days, 0) / 365.0
        fy = book[book["funded_at"].notna() & (book["funded_at"] >= PERIOD_START) & (book["funded_at"] < AS_OF_TS)]
        funded_credit = float(np.where(fy["is_liquidity_partner"], 0.25, 1.0).sum())
        att = funded_credit / q_ytd if q_ytd else None

        mat = book[book["funded_at"].notna() & (book["funded_at"] <= AS_OF_TS - pd.Timedelta(days=60))]
        fa_m = fa.reindex(mat.index)
        ok = fa_m.notna() & ((fa_m - mat["funded_at"]) <= pd.Timedelta(days=60))
        act_rate = float(ok.mean()) if len(mat) else None

        book_adv = float(book.loc[~book["is_liquidity_partner"].astype(bool), "adv_20td"].sum())
        adv_ratio = book_adv / rep.quota_adv if rep.quota_adv else None

        tq = book[book["first_qualifying_trade_at"].notna() & (book["first_qualifying_trade_at"] >= AS_OF_TS - pd.Timedelta(days=180))]
        dd = (tq["first_qualifying_trade_at"] - tq["signed_at"]).dt.total_seconds() / 86400
        med_days = float(dd.median()) if len(dd) else None

        pipe = int(book["stage"].isin(["QUALIFIED", "SIGNED"]).sum())
        cov = pipe / (rep.quota_funded_annual * 90 / 365.0) if rep.quota_funded_annual else None

        # SLA adherence: milestones in the trailing 30 d whose follow-up touch landed within the rule SLA
        due = met = 0
        acts_b = acts[acts["account_id"].isin(book.index)]
        by_acct = {a: g["ts"].sort_values().to_numpy() for a, g in acts_b.groupby("account_id")}
        for col, hours in SLA_EVENTS.items():
            ev = book[book[col].notna() & (book[col] >= AS_OF_TS - pd.Timedelta(days=30)) & (book[col] < AS_OF_TS)]
            for aid, ts in zip(ev.index, ev[col]):
                deadline = _sla_deadline(pd.Timestamp(ts), hours)
                if deadline > AS_OF_TS:
                    continue  # not yet due
                due += 1
                tss = by_acct.get(aid)
                if tss is not None and ((tss >= np.datetime64(ts)) & (tss <= np.datetime64(deadline))).any():
                    met += 1
        sla = met / due if due else None

        actual = {"funded_vs_quota": att, "activation_rate": act_rate, "book_adv_vs_target": adv_ratio,
                  "median_days_sign_to_trade": med_days, "pipeline_coverage": cov, "sla_adherence": sla}
        comps, ratios, red = {}, {}, []
        score = 0.0
        for key, m in metrics.items():
            c = _component(actual[key], m["target"], m["direction"])
            ratios[key] = round(c, 3)
            pts = m["weight"] * c * 100
            comps[key] = round(pts, 1)
            score += pts
            if c < 0.5:
                red.append(key)
        out.append({
            "rep_id": int(rep.id), "name": rep.name, "role": rep.role, "region": rep.region,
            "funded_ytd": round(funded_credit, 2), "quota_ytd": round(q_ytd, 1), "attainment": num(att),
            "activation_rate": num(act_rate), "activation_n": int(len(mat)), "book_adv": round(book_adv, 1),
            "quota_adv": float(rep.quota_adv), "book_adv_vs_target": num(adv_ratio),
            "median_days_sign_to_trade": num(med_days, 1), "pipeline_coverage": num(cov, 2), "pipeline_accounts": pipe,
            "sla_adherence": num(sla), "sla_items": due,
            "score": round(score, 1), "components": comps, "component_ratios": ratios, "red_flags": red,
        })
    out.sort(key=lambda r: -r["score"])
    return {"as_of": D.AS_OF_DATE.isoformat(), "scoring": sc.get("scoring"),
            "weights": {k: m["weight"] for k, m in metrics.items()}, "reps": out}


# ---------------------------------------------------------------------------
# Comp simulator
# ---------------------------------------------------------------------------
PARAM_KEYS = ("per_account_unit", "adv_kicker_per_1k", "adv_kicker_cap", "adv_kicker_accel", "accelerator",
              "clawback_pct", "clawback_days", "lp_kicker_credit", "volume_target_contracts_annual", "quota_funded_annual",
              "accelerator_min_book_activation", "lp_milestone_credit")
FRACTION_KEYS = ("clawback_pct", "lp_kicker_credit", "accelerator_min_book_activation", "lp_milestone_credit")
MULT_KEYS = ("signed", "funded", "active_60d", "active_21d_bonus")


class CompParamError(ValueError):
    pass


def plans() -> list[dict]:
    out = []
    for p in content("comp_plans")["plans"]:
        q = copy.deepcopy(p)
        q.setdefault("name", q.get("label", q["plan_id"]))
        out.append(q)
    return out


def reporting() -> dict:
    return content("comp_plans").get("reporting", {})


def merge_params(plan: dict, params: dict | None) -> dict:
    """Merge a (possibly partial) params dict over a stored plan (contract note #9).

    ``quota_funded_annual`` in params overrides every rep's own quota (the stored
    plan value is only the AE default and the unit basis)."""
    p = copy.deepcopy(plan)
    p["quota_override"] = False
    if not params:
        return p
    if not isinstance(params, dict):
        raise CompParamError("params must be an object")
    for k, v in params.items():
        if k == "multipliers":
            if not isinstance(v, dict):
                raise CompParamError("multipliers must be an object")
            for mk, mv in v.items():
                if mk not in MULT_KEYS:
                    raise CompParamError(f"unknown multiplier {mk!r}")
                p["multipliers"][mk] = _num(mk, mv)
        elif k in PARAM_KEYS:
            p[k] = _num(k, v)
            if k == "quota_funded_annual":
                p["quota_override"] = True
        # unknown keys (label, behavior, formula...) are ignored: only numbers drive payouts
    for k in FRACTION_KEYS:
        if float(p.get(k) or 0) > 1:
            raise CompParamError(f"{k} is a 0–1 fraction")
    return p


def _num(k, v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError) as exc:
        raise CompParamError(f"{k} must be a number") from exc
    if not np.isfinite(f) or f < 0:
        raise CompParamError(f"{k} must be a finite number ≥ 0")
    return f


def compute_payouts(plan: dict, reps: pd.DataFrame, acc: pd.DataFrame, trades: pd.DataFrame,
                    first_active: pd.Series, as_of=AS_OF_TS, period_start=PERIOD_START) -> list[dict]:
    """Per-rep variable payout under ``plan`` — implements the plans' ``formula`` strings (v1.1).

    * ``frac_r`` = (as_of − max(period_start, rep.start_date)) / 365; ``Q_r`` = rep quota × frac_r
      (a ``quota_funded_annual`` override applies to every rep).
    * ``credit_i`` = ``lp_milestone_credit`` for liquidity partners, else 1.
    * Accelerator: ``a_k`` = accelerator when k > Q_r and the gate is open
      (book_activation ≥ ``accelerator_min_book_activation``); applied to the component named by
      ``accelerator_basis`` (signatures | funded | active_milestones).
    * Clawback = clawback_pct × the funding payment as paid; kicker as before with V_r prorated.

    ``reps``: id, name, role, quota_funded_annual, start_date. ``acc`` (index id): rep_id, signed_at,
    funded_at, first_qualifying_trade_at, is_liquidity_partner. ``trades``: account_id, ts, contracts[, fee_usd].
    """
    as_of = pd.Timestamp(as_of)
    period_start = pd.Timestamp(period_start)
    unit = float(plan["per_account_unit"])
    m = plan["multipliers"]
    accel = float(plan["accelerator"])
    basis = plan.get("accelerator_basis") or ("signatures" if m.get("signed") else "funded")
    gate_min = float(plan.get("accelerator_min_book_activation") or 0.0)
    lp_mc = float(plan.get("lp_milestone_credit", 1.0) if plan.get("lp_milestone_credit") is not None else 1.0)
    per1k = float(plan.get("adv_kicker_per_1k") or 0)
    cap = float(plan.get("adv_kicker_cap") or 0)
    kaccel = float(plan.get("adv_kicker_accel") or 0)
    cb_pct = float(plan.get("clawback_pct") or 0)
    cb_days = float(plan.get("clawback_days") or 0)
    lp_credit = float(plan.get("lp_kicker_credit") or 0)
    has_fee = "fee_usd" in trades.columns
    out = []
    for rep in reps.itertuples(index=False):
        start = max(period_start, pd.Timestamp(getattr(rep, "start_date", period_start)))
        frac = max((as_of - start).days, 0) / 365.0
        q_annual = float(plan["quota_funded_annual"]) if plan.get("quota_override") else float(rep.quota_funded_annual)
        Q = q_annual * frac
        V = float(plan.get("volume_target_contracts_annual") or 0) * frac
        book = acc[acc["rep_id"] == rep.id]
        credit = lambda r: lp_mc if bool(r["is_liquidity_partner"]) else 1.0  # noqa: E731
        bd = {"signatures": 0.0, "funded": 0.0, "activation": 0.0, "speed_bonus": 0.0, "accelerator": 0.0,
              "adv_kicker": 0.0, "kicker_accelerator": 0.0, "clawback": 0.0}
        F = book[book["funded_at"].notna() & (book["funded_at"] >= period_start) & (book["funded_at"] < as_of)].sort_values("funded_at")
        # book activation over funded accounts whose 60-day window has closed
        closed = F[F["funded_at"] + pd.Timedelta(days=60) <= as_of]
        act60 = {}
        for aid, r in F.iterrows():
            fa = first_active.get(aid)
            fat = pd.Timestamp(r["funded_at"])
            ok = fa is not None and pd.notna(fa) and pd.Timestamp(fa) <= as_of and (pd.Timestamp(fa) - fat) <= pd.Timedelta(days=60)
            act60[aid] = (bool(ok), bool(ok and (pd.Timestamp(fa) - fat) <= pd.Timedelta(days=21)))
        book_act = (sum(act60[a][0] for a in closed.index) / len(closed)) if len(closed) else 0.0
        gate = book_act >= gate_min
        applied = False
        # signatures
        S = book[book["signed_at"].notna() & (book["signed_at"] >= period_start) & (book["signed_at"] < as_of)].sort_values("signed_at")
        if m.get("signed", 0):
            for k, (_aid, r) in enumerate(S.iterrows(), start=1):
                base = unit * m["signed"] * credit(r)
                bd["signatures"] += base
                if k > Q and gate and basis == "signatures":
                    bd["accelerator"] += base * (accel - 1)
                    applied = True
        # funded milestones
        sum_capped = 0.0
        n_active = 0
        for k, (aid, r) in enumerate(F.iterrows(), start=1):
            fat = pd.Timestamp(r["funded_at"])
            a60, a21 = act60[aid]
            n_active += int(a60)
            c = credit(r)
            a_k = accel if (k > Q and gate) else 1.0
            funded_pay = unit * m.get("funded", 0) * c
            if basis == "funded" and a_k > 1 and funded_pay:
                bd["accelerator"] += funded_pay * (a_k - 1)
                applied = True
                funded_paid = funded_pay * a_k
            else:
                funded_paid = funded_pay
            bd["funded"] += funded_pay
            act_pay = unit * c * m.get("active_60d", 0) * a60
            bonus_pay = unit * c * m.get("active_21d_bonus", 0) * a21
            bd["activation"] += act_pay
            bd["speed_bonus"] += bonus_pay
            if basis in ("active_milestones", "funded") and a_k > 1 and (act_pay or bonus_pay):
                bd["accelerator"] += (act_pay + bonus_pay) * (a_k - 1)
                applied = True
            if cb_pct and cb_days and fat + pd.Timedelta(days=cb_days) <= as_of:
                fq = r["first_qualifying_trade_at"]
                if fq is None or pd.isna(fq) or (pd.Timestamp(fq) - fat) > pd.Timedelta(days=cb_days):
                    bd["clawback"] -= cb_pct * funded_paid
            if per1k:
                t = trades[(trades["account_id"] == aid) & (trades["ts"] >= fat) & (trades["ts"] < min(as_of, fat + pd.Timedelta(days=365)))]
                E = float(t["contracts"].sum()) * (lp_credit if bool(r["is_liquidity_partner"]) else 1.0)
                base = min(cap, per1k * E / 1000.0) if cap else per1k * E / 1000.0
                bd["adv_kicker"] += base
                sum_capped += base / per1k * 1000.0
        if per1k and kaccel > 1:
            bd["kicker_accelerator"] = (kaccel - 1) * per1k * max(0.0, sum_capped - V) / 1000.0
        total = sum(bd.values())
        bt = trades[trades["account_id"].isin(book.index) & (trades["ts"] >= period_start) & (trades["ts"] < as_of)]
        fees = float(bt["fee_usd"].sum()) if has_fee else None
        out.append({"rep_id": int(rep.id), "name": rep.name, "role": rep.role,
                    "payout_variable": round(total, 2),
                    "payout_breakdown": {k: round(v, 2) for k, v in bd.items() if abs(v) > 1e-9 or k in ("funded", "clawback")},
                    "signed_ytd": int(len(S)), "funded_ytd": int(len(F)), "active_60d": n_active, "quota_ytd": round(Q, 2),
                    "book_activation": round(book_act, 4), "accelerator_applied": bool(applied), "gate_open": bool(gate),
                    "contracts_ytd": float(bt["contracts"].sum()), "fees_ytd": round(fees, 2) if fees is not None else None,
                    "pct_of_fee_revenue": round(total / fees, 4) if fees else None})
    return out


def _sim_inputs(state):
    def build():
        f = state.frames
        tr = f.trades[f.trades["ts"] < AS_OF_TS][["account_id", "ts", "contracts", "fee_usd"]]
        fa = features.first_active_at(tr)
        reps = _book_reps(f)
        acc = state.accounts[["rep_id", "signed_at", "funded_at", "first_qualifying_trade_at", "is_liquidity_partner"]]
        book_ids = acc.index[acc["rep_id"].isin(reps["id"])]
        tr_book = tr[tr["account_id"].isin(book_ids)]
        return {"reps": reps, "acc": acc, "trades": tr_book, "fa": fa}
    return state.cached(("comp_inputs",), build)


def _totals(payouts: list[dict]) -> dict:
    total = sum(p["payout_variable"] for p in payouts)
    act = sum(p["active_60d"] for p in payouts)
    contracts = sum(p["contracts_ytd"] for p in payouts)
    fees = sum(p["fees_ytd"] or 0 for p in payouts)
    return {"variable_cost": round(total, 2),
            "active_accounts": act,
            "per_active_account": round(total / act, 2) if act else None,
            "contracts_ytd": contracts,
            "per_1k_contracts": round(total / (contracts / 1000.0), 2) if contracts else None,
            "fees_ytd": round(fees, 2),
            "pct_of_fee_revenue": round(total / fees, 4) if fees else None}


def simulate(state, plan_id: str | None, params: dict | None) -> dict:
    stored = {p["plan_id"]: p for p in plans()}
    pid = plan_id or "activation_adv"
    if pid not in stored:
        raise KeyError(pid)
    if not params:
        return state.cached(("comp_sim", pid), lambda: _simulate(state, stored, pid, None))
    return _simulate(state, stored, pid, params)


def _simulate(state, stored: dict, pid: str, params: dict | None) -> dict:
    inp = _sim_inputs(state)
    plan = merge_params(stored[pid], params)
    pay = compute_payouts(plan, inp["reps"], inp["acc"], inp["trades"], inp["fa"])
    comparison = []
    for qid, q in stored.items():
        pq = pay if qid == pid else state.cached(
            ("comp_pay", qid), lambda q=q: compute_payouts(merge_params(q, None), inp["reps"], inp["acc"], inp["trades"], inp["fa"]))
        t = _totals(pq)
        comparison.append({"plan_id": qid, "name": q["name"], "variable_cost": t["variable_cost"],
                           "per_active_account": t["per_active_account"], "per_1k_contracts": t["per_1k_contracts"],
                           "pct_of_fee_revenue": t["pct_of_fee_revenue"],
                           "behavior": q.get("behavior"), "simulated_params": qid == pid and bool(params)})
    return {"as_of": D.AS_OF_DATE.isoformat(),
            "period": f"YTD 2026 ({PERIOD_START.date().isoformat()} – {(AS_OF_TS - pd.Timedelta(days=1)).date().isoformat()}), prorated from each rep's start date",
            "plan": {k: plan[k] for k in plan if k not in ("risks",)},
            "reporting": reporting(),
            "reps": pay, "totals": _totals(pay), "comparison": comparison}
