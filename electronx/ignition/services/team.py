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
              "clawback_pct", "clawback_days", "lp_kicker_credit", "volume_target_contracts_annual", "quota_funded_annual")
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


def merge_params(plan: dict, params: dict | None) -> dict:
    """Merge a (possibly partial) params dict over a stored plan (contract note #9)."""
    p = copy.deepcopy(plan)
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
        # unknown keys (label, behavior, formula...) are ignored: only numbers drive payouts
    if p["clawback_pct"] > 1 or p["lp_kicker_credit"] > 1:
        raise CompParamError("clawback_pct and lp_kicker_credit are 0–1 fractions")
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
    """Per-rep variable payout under ``plan`` (pure; see the plan's ``formula``).

    ``acc`` needs: id (index), rep_id, signed_at, funded_at, first_qualifying_trade_at,
    is_liquidity_partner. ``trades``: account_id, ts, contracts.
    """
    as_of = pd.Timestamp(as_of)
    frac = (as_of - period_start).days / 365.0
    unit = float(plan["per_account_unit"])
    m = plan["multipliers"]
    accel = float(plan["accelerator"])
    per1k = float(plan.get("adv_kicker_per_1k") or 0)
    cap = float(plan.get("adv_kicker_cap") or 0)
    kaccel = float(plan.get("adv_kicker_accel") or 0)
    V = float(plan.get("volume_target_contracts_annual") or 0) * frac
    cb_pct = float(plan.get("clawback_pct") or 0)
    cb_days = float(plan.get("clawback_days") or 0)
    lp_credit = float(plan.get("lp_kicker_credit") or 0)
    out = []
    for rep in reps.itertuples(index=False):
        Q = float(plan.get("quota_funded_annual", rep.quota_funded_annual)) * frac
        book = acc[acc["rep_id"] == rep.id]
        bd = {"signatures": 0.0, "funded": 0.0, "activation": 0.0, "speed_bonus": 0.0, "accelerator": 0.0,
              "adv_kicker": 0.0, "kicker_accelerator": 0.0, "clawback": 0.0}
        # signatures (plan a): unit × m.signed × min(S,Q) + unit × m.signed × accel × max(S−Q, 0)
        S = int((book["signed_at"].notna() & (book["signed_at"] >= period_start) & (book["signed_at"] < as_of)).sum())
        if m.get("signed", 0):
            bd["signatures"] = unit * m["signed"] * min(S, Q)
            extra = max(S - Q, 0)
            bd["signatures"] += unit * m["signed"] * extra
            bd["accelerator"] += unit * m["signed"] * (accel - 1) * extra
        # funded milestones, ordered by funded_at (k = position)
        F = book[book["funded_at"].notna() & (book["funded_at"] >= period_start) & (book["funded_at"] < as_of)].sort_values("funded_at")
        sum_capped = 0.0
        n_funded = n_active = 0
        for k, (aid, r) in enumerate(F.iterrows(), start=1):
            a_k = accel if k > Q else 1.0
            fat = pd.Timestamp(r["funded_at"])
            fa = first_active.get(aid)
            act60 = fa is not None and pd.notna(fa) and pd.Timestamp(fa) <= as_of and (pd.Timestamp(fa) - fat) <= pd.Timedelta(days=60)
            act21 = act60 and (pd.Timestamp(fa) - fat) <= pd.Timedelta(days=21)
            n_funded += 1
            n_active += int(bool(act60))
            parts = {"funded": unit * m.get("funded", 0), "activation": unit * m.get("active_60d", 0) * act60,
                     "speed_bonus": unit * m.get("active_21d_bonus", 0) * act21}
            for key, v in parts.items():
                bd[key] += v
                bd["accelerator"] += v * (a_k - 1)
            # clawback of the funding payment: no qualifying trade within clawback_days (window closed)
            if cb_pct and cb_days and fat + pd.Timedelta(days=cb_days) <= as_of:
                fq = r["first_qualifying_trade_at"]
                if fq is None or pd.isna(fq) or (pd.Timestamp(fq) - fat) > pd.Timedelta(days=cb_days):
                    bd["clawback"] -= cb_pct * unit * m.get("funded", 0) * a_k
            # ADV kicker on first-365-day contracts
            if per1k:
                t = trades[(trades["account_id"] == aid) & (trades["ts"] >= fat) & (trades["ts"] < min(as_of, fat + pd.Timedelta(days=365)))]
                C = float(t["contracts"].sum())
                E = C * (lp_credit if bool(r["is_liquidity_partner"]) else 1.0)
                base = min(cap, per1k * E / 1000.0) if cap else per1k * E / 1000.0
                bd["adv_kicker"] += base
                sum_capped += base / per1k * 1000.0
        if per1k and kaccel > 1:
            bd["kicker_accelerator"] = (kaccel - 1) * per1k * max(0.0, sum_capped - V) / 1000.0
        total = sum(bd.values())
        out.append({"rep_id": int(rep.id), "name": rep.name, "role": rep.role,
                    "payout_variable": round(total, 2),
                    "payout_breakdown": {k: round(v, 2) for k, v in bd.items() if abs(v) > 1e-9 or k in ("funded", "clawback")},
                    "signed_ytd": S, "funded_ytd": n_funded, "active_60d": n_active, "quota_ytd": round(Q, 2)})
    return out


def _sim_inputs(state):
    def build():
        f = state.frames
        tr = f.trades[f.trades["ts"] < AS_OF_TS][["account_id", "ts", "contracts"]]
        fa = features.first_active_at(tr)
        reps = _book_reps(f)
        acc = state.accounts[["rep_id", "signed_at", "funded_at", "first_qualifying_trade_at", "is_liquidity_partner"]]
        book_ids = acc.index[acc["rep_id"].isin(reps["id"])]
        tr_book = tr[tr["account_id"].isin(book_ids)]
        ytd = tr_book[tr_book["ts"] >= PERIOD_START]
        active_book = int(sum(1 for a in book_ids if a in fa.index
                              and pd.notna(acc.loc[a, "funded_at"]) and acc.loc[a, "funded_at"] >= PERIOD_START))
        return {"reps": reps, "acc": acc, "trades": tr_book, "fa": fa,
                "contracts_ytd": float(ytd["contracts"].sum()), "active_book": active_book}
    return state.cached(("comp_inputs",), build)


def _totals(payouts: list[dict], inp: dict) -> dict:
    total = sum(p["payout_variable"] for p in payouts)
    act = sum(p["active_60d"] for p in payouts)
    return {"variable_cost": round(total, 2),
            "active_accounts": act,
            "per_active_account": round(total / act, 2) if act else None,
            "contracts_ytd": inp["contracts_ytd"],
            "per_1k_contracts": round(total / (inp["contracts_ytd"] / 1000.0), 2) if inp["contracts_ytd"] else None}


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
        pq = pay if qid == pid else state.cached(("comp_pay", qid), lambda q=q: compute_payouts(q, inp["reps"], inp["acc"], inp["trades"], inp["fa"]))
        t = _totals(pq, inp)
        comparison.append({"plan_id": qid, "name": q["name"], "variable_cost": t["variable_cost"],
                           "per_active_account": t["per_active_account"], "per_1k_contracts": t["per_1k_contracts"],
                           "behavior": q.get("behavior"), "simulated_params": qid == pid and bool(params)})
    return {"as_of": D.AS_OF_DATE.isoformat(),
            "period": f"YTD 2026 ({PERIOD_START.date().isoformat()} – {(AS_OF_TS - pd.Timedelta(days=1)).date().isoformat()})",
            "plan": {k: plan[k] for k in plan if k not in ("risks",)},
            "reps": pay, "totals": _totals(pay, inp), "comparison": comparison}
