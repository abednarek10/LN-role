"""Funnel & Journey (spec §B steps, D10): step conversion, dwell, states, friction.

* Population: accounts with a ``contract_signed`` event (funnel starts at
  signature, D10). Optional ``segment`` / ``iso`` (primary ISO) filters.
* Steps: ``definitions.MAIN_PATH_STEPS`` (non-optional, non-repeatable path).
  ``n`` = accounts that reached the step; ``conv_from_prev`` = n / n(prev);
  median / P75 days from the previous step among accounts that reached both.
* States: health of funded accounts — active / at_risk / dormant (D2 literal).
* Friction: a segment whose step conversion is ≥10 pp below the all-segment
  benchmark, or whose median dwell is ≥1.75× (and ≥3 d above) the benchmark;
  plus KYC info-request loops and first-order rejections. Each card carries
  accounts currently stuck at that step, ADV at stake (Σ P × E[ADV],
  contracts/day), a roadmap ask and a severity string.
* The friction list is always computed across all segments (the benchmark
  needs them); a ``segment`` filter selects cards, it does not recompute them.
  ``/funnel/friction/{i}.md`` indexes the unfiltered list (contract note #4).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import definitions as D
from .common import AS_OF_TS, num

CONV_GAP = 0.10
DWELL_MULT = 1.75
DWELL_MIN_EXTRA_D = 3.0
MIN_N = 8

ROADMAP = {
    "platform_account_created": "Auto-provision the platform account and send invites to every named trader at signature, so no one waits on a manual setup ticket.",
    "first_login": "SSO / magic-link first login from the welcome email plus a checklist landing page; nudge at 48 h when no login is recorded.",
    "kyc_submitted": "Embed the KYC upload in the signing flow, pre-filled from the participant agreement (entity, LEI, UBO, authorized traders).",
    "kyc_approved": "Entity-type KYC checklists (board resolution for co-ops, authority letter for munis, parent guarantee for project companies) shown up front, plus a document-status tracker so each info request names the missing item.",
    "bank_linked": "Self-serve bank linking with instant account verification instead of manual wire-detail forms.",
    "funded": "Collateral funding via existing treasury rails (wire templates, FCM transfer) with in-portal status; project-finance entities get a guided funding call booked at bank-link.",
    "order_ticket_opened": "In-app 'first hedge' guide on the funded screen: hub, tenor and a size pre-filled from the stated MW, plus a one-click walkthrough booking.",
    "first_order": "Guided first-order ticket in the sandbox, sized from the account's stated exposure, with a scheduled walkthrough before going live.",
    "first_trade": "Pre-trade limit and margin preview in the ticket, with plain-language rejection reasons and a one-click limit-increase request routed to risk.",
    "activated": "Post-first-trade routine builder (e.g. weekly peak ladder) with reminders, so a first fill becomes a weekly habit.",
}
METRIC_LABEL = {
    "conversion": "conversion from previous step",
    "median_days": "median days from previous step",
    "kyc_info_requests_per_account": "KYC info requests per signed account",
    "order_rejection_rate": "first-order rejection rate",
}


def _first_steps(frames, ids) -> pd.DataFrame:
    ob = frames.onboarding_events
    ob = ob[(ob["ts"] < AS_OF_TS) & ob["account_id"].isin(ids)]
    return ob.groupby(["account_id", "step"])["ts"].min().unstack().reindex(index=ids, columns=D.ONBOARDING_STEPS)


def step_stats(first: pd.DataFrame) -> list[dict]:
    """Pure step math on a pivot (account × step → first ts)."""
    out = []
    prev = None
    for step in D.MAIN_PATH_STEPS:
        col = first[step] if step in first.columns else pd.Series(pd.NaT, index=first.index)
        n = int(col.notna().sum())
        row = {"step": step, "label": D.STEP_LABELS[step], "n": n,
               "conv_from_prev": None, "median_days_from_prev": None, "p75_days": None}
        if prev is not None:
            pcol = first[prev]
            npv = int(pcol.notna().sum())
            row["conv_from_prev"] = round(n / npv, 4) if npv else None
            both = col.notna() & pcol.notna()
            dd = ((col[both] - pcol[both]).dt.total_seconds() / 86400.0).clip(lower=0)
            if len(dd):
                row["median_days_from_prev"] = round(float(dd.median()), 2)
                row["p75_days"] = round(float(dd.quantile(0.75)), 2)
            row["n_prev"] = npv
            row["n_pairs"] = int(both.sum())
        out.append(row)
        prev = step
    return out


def _population(acc: pd.DataFrame, first: pd.DataFrame, segment=None, iso=None) -> pd.Index:
    ids = first.index[first["contract_signed"].notna()]
    a = acc.loc[ids]
    if segment:
        a = a[a["segment"] == segment]
    if iso:
        a = a[a["primary_iso"] == iso]
    return a.index


def _severity(adv: float, rel_gap: float) -> str:
    s = adv * min(1.0 + max(rel_gap, 0.0), 3.0)
    if s >= 300:
        return "critical"
    if s >= 100:
        return "high"
    if s >= 30:
        return "medium"
    return "low"


def _stuck(first: pd.DataFrame, ids, prev: str, step: str) -> pd.Index:
    f = first.loc[ids]
    return f.index[f[prev].notna() & f[step].isna()]


def detect_friction(acc: pd.DataFrame, first: pd.DataFrame, pop: pd.Index, kyc_loops: pd.Series) -> list[dict]:
    overall = {s["step"]: s for s in step_stats(first.loc[pop])}
    nonlp = acc.loc[pop]
    nonlp = nonlp[~nonlp["is_liquidity_partner"].astype(bool)]
    cards: list[dict] = []

    def card(seg, step, prev, metric, value, bench, affected_ids, rel_gap, extra=""):
        sub = acc.loc[affected_ids]
        sub = sub[~sub["is_liquidity_partner"].astype(bool)]
        adv = float((sub["p_active"].fillna(0) * sub["exp_adv"]).sum())
        label = D.SEGMENTS[seg]["label"]
        if metric == "conversion":
            stat = f"{value:.0%} vs {bench:.0%} for all segments"
        elif metric == "median_days":
            stat = f"median {value:.1f} d vs {bench:.1f} d for all segments"
        elif metric == "order_rejection_rate":
            stat = f"{value:.0%} of first orders rejected vs {bench:.0%} overall"
        else:
            stat = f"{value:.2f} info requests per account vs {bench:.2f} overall"
        cards.append({
            "step": step, "from_step": prev, "segment": seg, "metric": metric,
            "metric_label": METRIC_LABEL[metric],
            "value": round(float(value), 4), "benchmark": round(float(bench), 4),
            "accounts_affected": int(len(sub)),
            "adv_at_stake": round(adv, 1),
            "roadmap_ask": f"{label}: {stat} at '{D.STEP_LABELS[step]}'. Ask: {ROADMAP.get(step, 'Instrument and fix this step.')}{extra}",
            "severity": _severity(adv, rel_gap),
            "affected_account_ids": [int(i) for i in sub.sort_values("p_active", ascending=False).index[:25]],
        })

    for seg in D.SEGMENT_CODES:
        sids = nonlp.index[nonlp["segment"] == seg]
        if len(sids) < MIN_N:
            continue
        stats = step_stats(first.loc[sids])
        for i, s in enumerate(stats):
            if i == 0:
                continue
            prev = stats[i - 1]["step"]
            o = overall[s["step"]]
            if s.get("n_prev", 0) >= MIN_N and s["conv_from_prev"] is not None and o["conv_from_prev"] is not None \
                    and s["conv_from_prev"] < o["conv_from_prev"] - CONV_GAP:
                rel = (o["conv_from_prev"] - s["conv_from_prev"]) / max(o["conv_from_prev"], 1e-6)
                card(seg, s["step"], prev, "conversion", s["conv_from_prev"], o["conv_from_prev"],
                     _stuck(first, sids, prev, s["step"]), rel)
            med, om = s["median_days_from_prev"], o["median_days_from_prev"]
            if s.get("n_pairs", 0) >= 5 and med is not None and om is not None \
                    and med >= max(om * DWELL_MULT, om + DWELL_MIN_EXTRA_D):
                rel = (med - om) / max(om, 0.5)
                card(seg, s["step"], prev, "median_days", med, om, _stuck(first, sids, prev, s["step"]), rel)
        # KYC info-request loops (repeatable step, D10 friction)
        signed = sids
        seg_loops = float(kyc_loops.reindex(signed).fillna(0).mean())
        all_loops = float(kyc_loops.reindex(nonlp.index).fillna(0).mean())
        if seg_loops >= max(1.5 * all_loops, 0.3):
            card(seg, "kyc_approved", "kyc_submitted", "kyc_info_requests_per_account", seg_loops, all_loops,
                 _stuck(first, sids, "kyc_submitted", "kyc_approved"), (seg_loops - all_loops) / max(all_loops, 0.05))
        # first-order rejections
        fo = first.loc[sids, "first_order"].notna()
        rej = first.loc[sids, "order_rejected"].notna()
        all_fo = first.loc[nonlp.index, "first_order"].notna()
        all_rej = first.loc[nonlp.index, "order_rejected"].notna()
        if fo.sum() >= 5 and all_fo.sum():
            r, rb = float(rej[fo].mean()), float(all_rej[all_fo].mean())
            if r >= max(2 * rb, 0.2):
                card(seg, "first_trade", "first_order", "order_rejection_rate", r, rb,
                     _stuck(first, sids, "first_order", "first_trade"), (r - rb) / max(rb, 0.05))

    # one card per (segment, step, metric); rank by ADV at stake then severity
    seen, uniq = set(), []
    for c in cards:
        k = (c["segment"], c["step"], c["metric"])
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    uniq.sort(key=lambda c: (-c["adv_at_stake"], -rank[c["severity"]], c["segment"], c["step"], c["metric"]))
    return uniq


def funnel(state, segment: str | None = None, iso: str | None = None) -> dict:
    return state.cached(("funnel", segment, iso), lambda: _funnel(state, segment, iso))


def _base(state):
    def build():
        acc = state.accounts
        first = _first_steps(state.frames, acc.index)
        ob = state.frames.onboarding_events
        loops = ob[(ob["step"] == "kyc_info_requested") & (ob["ts"] < AS_OF_TS)].groupby("account_id").size()
        return first, loops
    return state.cached(("funnel_base",), build)


def _funnel(state, segment, iso) -> dict:
    acc = state.accounts
    first, loops = _base(state)
    pop = _population(acc, first, segment, iso)
    steps = step_stats(first.loc[pop])
    for s in steps:
        s.pop("n_prev", None)
        s.pop("n_pairs", None)
    h = acc.loc[pop]
    funded = h[h["funded_at"].notna()]
    states = {k: int((funded["state"] == k).sum()) for k in ("active", "at_risk", "dormant")}
    states["funded_new"] = int((funded["state"] == "funded_new").sum())
    seg_pop = _population(acc, first, None, iso)
    by_segment = []
    for seg in D.SEGMENT_CODES:
        sids = seg_pop[acc.loc[seg_pop, "segment"] == seg]
        if segment and seg != segment:
            continue
        st = step_stats(first.loc[sids])
        by_segment.append({"segment": seg, "label": D.SEGMENTS[seg]["label"], "n": int(len(sids)),
                           "steps": [{"step": x["step"], "n": x["n"], "conv_from_prev": x["conv_from_prev"],
                                      "median_days": x["median_days_from_prev"]} for x in st]})
    friction = state.cached(("friction", iso), lambda: detect_friction(acc, first, seg_pop, loops))
    if segment:
        friction = [c for c in friction if c["segment"] == segment]
    return {"as_of": D.AS_OF_DATE.isoformat(), "filters": {"segment": segment, "iso": iso},
            "population": int(len(pop)), "steps": steps, "states": states,
            "by_segment": by_segment, "friction": friction}


def friction_ticket_md(state, index: int) -> str | None:
    fr = funnel(state)["friction"]
    if index < 0 or index >= len(fr):
        return None
    c = fr[index]
    acc = state.accounts
    seg = D.SEGMENTS[c["segment"]]["label"]
    unit = "d" if c["metric"] == "median_days" else ""
    fmt = (lambda v: f"{v:.0%}") if c["metric"] in ("conversion", "order_rejection_rate") else (lambda v: f"{v:.2f}{unit}")
    lines = [
        f"# Roadmap ticket: {seg} friction at '{D.STEP_LABELS[c['step']]}'",
        "",
        "> **Synthetic data — illustrative.** Generated by Ignition from synthetic data; not ElectronX numbers.",
        "",
        f"- **Ticket #:** FR-{index + 1:03d} (as of {D.AS_OF_DATE.isoformat()})",
        f"- **Severity:** {c['severity']}",
        f"- **Step:** `{c['from_step']}` → `{c['step']}`",
        f"- **Metric:** {c['metric_label']} = **{fmt(c['value'])}** (benchmark, all segments: {fmt(c['benchmark'])})",
        f"- **Accounts affected (currently stuck):** {c['accounts_affected']}",
        f"- **ADV at stake:** ~{c['adv_at_stake']:,.0f} contracts/day (Σ P(Active) × E[ADV])",
        "",
        "## Problem",
        "",
        c["roadmap_ask"].split(" Ask: ")[0] + ".",
        "",
        "## Ask",
        "",
        ROADMAP.get(c["step"], "Instrument and fix this step."),
        "",
        "## Acceptance criteria",
        "",
        f"- {seg} {c['metric_label']} within 5 pp / 20% of the all-segment benchmark for two consecutive months.",
        "- Median days at this step reported weekly in Ignition Funnel & Journey.",
        "- No change to KYC/AML standards; only the information flow changes.",
        "",
        "## Affected accounts (top by P(Active))",
        "",
        "| Account | Stage | P(Active) | E[ADV] |",
        "|---|---|---:|---:|",
    ]
    for i in c["affected_account_ids"][:15]:
        r = acc.loc[i]
        p = r["p_active"]
        lines.append(f"| {r['name']} | {r['stage']} | {'—' if pd.isna(p) else f'{p:.0%}'} | {r['exp_adv']:,.0f} |")
    lines += ["", "---", "*Synthetic data — illustrative.*", ""]
    return "\n".join(lines)
