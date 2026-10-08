"""Funnel & Journey (spec §B steps, D10; v1.1 CTO B5, CPO P1-6).

* Population: accounts with a ``contract_signed`` event (funnel starts at signature).
  Optional ``segment`` / ``iso`` (primary ISO) filters.
* Steps: ``definitions.MAIN_PATH_STEPS``. ``n`` = accounts that reached the step.
  ``conv_from_prev`` is computed on **mature cohorts** (B5): among accounts that reached
  the previous step and are old enough to have completed this one — time since the
  previous step ≥ the step's P75 dwell + 30 d, or signed ≥ 90 d ago (``n_mature``) —
  the share that reached the step. Median / P75 days from the previous step use all pairs.
* States: X2 health of funded accounts (not_started, ramping, active, at_risk, dormant).
* Friction: a segment whose mature step conversion is ≥10 pp below the all-segment
  benchmark, or whose median dwell is ≥1.75× (and ≥3 d above) the benchmark, plus KYC
  info-request loops and first-order rejections. Cards are merged per (segment, step),
  kept only with ≥5 accounts affected (stuck past the benchmark dwell), and ranked by
  ADV at stake (Σ P × E[ADV]); the top 6 are returned. Severity = relative gap × log2(1 +
  accounts affected), so a broad KYC-loop leak in low-ADV hedger segments still reads high.
* ``/funnel/friction/{i}.md`` indexes the unfiltered list (contract note #4).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .. import definitions as D
from .common import AS_OF_TS

CONV_GAP = 0.10
DWELL_MULT = 1.75
DWELL_MIN_EXTRA_D = 3.0
MIN_N = 8
MIN_AFFECTED = 5
MAX_CARDS = 6
MATURE_EXTRA_D = 30
MATURE_SIGNED_D = 90

STEP_LABEL = dict(D.STEP_LABELS) | {"activated": "Became Active"}

ROADMAP = {
    "platform_account_created": "Auto-provision the platform account and send invites to every named trader at signature, so no one waits on a manual setup ticket.",
    "first_login": "SSO or magic-link first login from the welcome email, a checklist landing page, and a nudge at 48 hours when no login is recorded.",
    "kyc_submitted": "Embed the KYC upload in the signing flow, pre-filled from the participant agreement (entity, LEI, beneficial owners, authorized traders).",
    "kyc_approved": "Entity-type KYC checklists shown up front (board resolution for co-ops, authority letter for munis, parent guarantee for project companies) and a document-status tracker so each information request names the missing item.",
    "bank_linked": "Self-serve bank linking with instant account verification instead of manual wire-detail forms.",
    "funded": "Collateral funding through existing treasury rails (wire templates, FCM transfer) with in-portal status; project-finance entities get a guided funding call booked at bank link.",
    "order_ticket_opened": "An in-app first-hedge guide on the funded screen: hub, tenor and a size pre-filled from the stated MW, plus a one-click walkthrough booking.",
    "first_order": "A guided first-order ticket in the sandbox, sized from the account's stated exposure, with a scheduled walkthrough before going live.",
    "first_trade": "A pre-trade limit and margin preview in the ticket, plain-language rejection reasons, and a one-click limit-increase request routed to risk.",
    "activated": "A post-first-trade routine builder (for example a weekly peak ladder) with reminders, so a first fill becomes a weekly habit.",
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


def step_stats(first: pd.DataFrame, as_of=AS_OF_TS) -> list[dict]:
    """Pure step math on a pivot (account × step → first ts), conversion on mature cohorts."""
    as_of = pd.Timestamp(as_of)
    out = []
    prev = None
    signed = first["contract_signed"] if "contract_signed" in first.columns else pd.Series(pd.NaT, index=first.index)
    old_signed = signed.notna() & ((as_of - signed).dt.total_seconds() / 86400 >= MATURE_SIGNED_D)
    for step in D.MAIN_PATH_STEPS:
        col = first[step] if step in first.columns else pd.Series(pd.NaT, index=first.index)
        n = int(col.notna().sum())
        row = {"step": step, "label": STEP_LABEL[step], "n": n, "n_mature": None,
               "conv_from_prev": None, "conv_all": None, "median_days_from_prev": None, "p75_days": None}
        if prev is not None:
            pcol = first[prev]
            npv = int(pcol.notna().sum())
            both = col.notna() & pcol.notna()
            dd = ((col[both] - pcol[both]).dt.total_seconds() / 86400.0).clip(lower=0)
            p75 = float(dd.quantile(0.75)) if len(dd) else 0.0
            if len(dd):
                row["median_days_from_prev"] = round(float(dd.median()), 2)
                row["p75_days"] = round(p75, 2)
            age = (as_of - pcol).dt.total_seconds() / 86400.0
            mature = pcol.notna() & ((age >= p75 + MATURE_EXTRA_D) | old_signed)
            nm = int(mature.sum())
            row["n_mature"] = nm
            row["conv_from_prev"] = round(int((mature & col.notna()).sum()) / nm, 4) if nm else None
            row["conv_all"] = round(n / npv, 4) if npv else None
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


def severity_of(rel_gap: float, affected: int) -> str:
    s = min(max(rel_gap, 0.0), 2.0) * math.log2(1 + max(affected, 0))
    if s >= 4.0:
        return "critical"
    if s >= 2.5:
        return "high"
    if s >= 1.2:
        return "medium"
    return "low"


def _stuck(first: pd.DataFrame, ids, prev: str, step: str, min_dwell: float = 0.0, as_of=AS_OF_TS) -> pd.Index:
    """Accounts that reached ``prev`` but not ``step`` and have waited longer than ``min_dwell`` days."""
    f = first.loc[ids]
    age = (pd.Timestamp(as_of) - f[prev]).dt.total_seconds() / 86400.0
    return f.index[f[prev].notna() & f[step].isna() & (age > min_dwell)]


def _stat_text(metric: str, value: float, bench: float) -> str:
    if metric == "conversion":
        return f"{value:.0%} convert vs {bench:.0%} for all segments"
    if metric == "median_days":
        return f"a median {value:.1f} days vs {bench:.1f} days for all segments"
    if metric == "order_rejection_rate":
        return f"{value:.0%} of first orders rejected vs {bench:.0%} overall"
    return f"{value:.2f} KYC information requests per account vs {bench:.2f} overall"


def detect_friction(acc: pd.DataFrame, first: pd.DataFrame, pop: pd.Index, kyc_loops: pd.Series,
                    min_affected: int = MIN_AFFECTED, max_cards: int | None = MAX_CARDS) -> list[dict]:
    overall = {s["step"]: s for s in step_stats(first.loc[pop])}
    nonlp = acc.loc[pop]
    nonlp = nonlp[~nonlp["is_liquidity_partner"].astype(bool)]
    raw: list[dict] = []

    def add(seg, step, prev, metric, value, bench, affected_ids, rel_gap):
        raw.append({"segment": seg, "step": step, "from_step": prev, "metric": metric, "value": float(value),
                    "benchmark": float(bench), "rel_gap": float(rel_gap), "ids": set(int(i) for i in affected_ids)})

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
            dwell_bench = o["median_days_from_prev"] or 0.0
            if (s.get("n_mature") or 0) >= MIN_N and s["conv_from_prev"] is not None and o["conv_from_prev"] is not None \
                    and s["conv_from_prev"] < o["conv_from_prev"] - CONV_GAP:
                rel = (o["conv_from_prev"] - s["conv_from_prev"]) / max(o["conv_from_prev"], 1e-6)
                add(seg, s["step"], prev, "conversion", s["conv_from_prev"], o["conv_from_prev"],
                    _stuck(first, sids, prev, s["step"], dwell_bench), rel)
            med = s["median_days_from_prev"]
            if s.get("n_pairs", 0) >= 5 and med is not None and o["median_days_from_prev"] is not None \
                    and med >= max(dwell_bench * DWELL_MULT, dwell_bench + DWELL_MIN_EXTRA_D):
                rel = (med - dwell_bench) / max(dwell_bench, 0.5)
                add(seg, s["step"], prev, "median_days", med, dwell_bench, _stuck(first, sids, prev, s["step"], dwell_bench), rel)
        # KYC information-request loops: signed accounts still short of funding that hit ≥1 loop
        seg_loops = float(kyc_loops.reindex(sids).fillna(0).mean())
        all_loops = float(kyc_loops.reindex(nonlp.index).fillna(0).mean())
        if seg_loops >= max(1.5 * all_loops, 0.3):
            f = first.loc[sids]
            looped = kyc_loops.reindex(sids).fillna(0) > 0
            aff = f.index[looped.to_numpy() & f["funded"].isna().to_numpy() & f["contract_signed"].notna().to_numpy()]
            add(seg, "kyc_approved", "kyc_submitted", "kyc_info_requests_per_account", seg_loops, all_loops, aff,
                (seg_loops - all_loops) / max(all_loops, 0.05))
        fo = first.loc[sids, "first_order"].notna()
        rej = first.loc[sids, "order_rejected"].notna()
        all_fo = first.loc[nonlp.index, "first_order"].notna()
        all_rej = first.loc[nonlp.index, "order_rejected"].notna()
        if fo.sum() >= 5 and all_fo.sum():
            r, rb = float(rej[fo].mean()), float(all_rej[all_fo].mean())
            if r >= max(2 * rb, 0.2):
                aff = first.loc[sids].index[(rej & first.loc[sids, "first_trade"].isna()).to_numpy()]
                add(seg, "first_trade", "first_order", "order_rejection_rate", r, rb, aff, (r - rb) / max(rb, 0.05))

    # merge per (segment, step): primary metric = largest relative gap; affected = union
    merged: dict[tuple, dict] = {}
    for c in raw:
        k = (c["segment"], c["step"])
        m = merged.setdefault(k, {"segment": c["segment"], "step": c["step"], "from_step": c["from_step"], "items": [], "ids": set()})
        m["items"].append(c)
        m["ids"] |= c["ids"]
    cards = []
    for (seg, step), m in merged.items():
        prim = max(m["items"], key=lambda c: c["rel_gap"])
        sub = acc.loc[sorted(m["ids"])] if m["ids"] else acc.iloc[0:0]
        sub = sub[~sub["is_liquidity_partner"].astype(bool)]
        n_aff = int(len(sub))
        adv = float((sub["p_active"].fillna(0) * sub["exp_adv"]).sum())
        label = D.SEGMENTS[seg]["label"]
        stats = "; ".join(_stat_text(c["metric"], c["value"], c["benchmark"]) for c in sorted(m["items"], key=lambda c: -c["rel_gap"]))
        ask = ROADMAP.get(step, "Instrument and fix this step.")
        cards.append({
            "step": step, "from_step": prim["from_step"], "step_label": STEP_LABEL[step],
            "from_step_label": STEP_LABEL.get(prim["from_step"], prim["from_step"]),
            "segment": seg, "segment_label": label, "metric": prim["metric"], "metric_label": METRIC_LABEL[prim["metric"]],
            "value": round(prim["value"], 4), "benchmark": round(prim["benchmark"], 4),
            "metrics": [{"metric": c["metric"], "metric_label": METRIC_LABEL[c["metric"]], "value": round(c["value"], 4),
                         "benchmark": round(c["benchmark"], 4)} for c in m["items"]],
            "accounts_affected": n_aff, "adv_at_stake": round(adv, 1),
            "severity": severity_of(prim["rel_gap"], n_aff),
            "ask": ask,
            "roadmap_ask": f"{label}: {stats} at {STEP_LABEL.get(prim['from_step'], prim['from_step'])} → {STEP_LABEL[step]}. Ask: {ask}",
            "affected_account_ids": [int(i) for i in sub.sort_values("p_active", ascending=False).index[:25]],
        })
    rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    cards = [c for c in cards if c["accounts_affected"] >= min_affected]
    cards.sort(key=lambda c: (-c["adv_at_stake"], -rank[c["severity"]], c["segment"], c["step"]))
    return cards[:max_cards] if max_cards else cards


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


STATE_KEYS = ("not_started", "ramping", "active", "at_risk", "dormant")


def _funnel(state, segment, iso) -> dict:
    acc = state.accounts
    first, loops = _base(state)
    pop = _population(acc, first, segment, iso)
    steps = step_stats(first.loc[pop])
    for s in steps:
        s.pop("n_prev", None)
        s.pop("n_pairs", None)
    h = acc.loc[pop]
    states = {k: int((h["health_state"] == k).sum()) for k in STATE_KEYS}
    states["pre_funding"] = int((h["health_state"] == "pre_funding").sum())
    seg_pop = _population(acc, first, None, iso)
    by_segment = []
    for seg in D.SEGMENT_CODES:
        if segment and seg != segment:
            continue
        sids = seg_pop[acc.loc[seg_pop, "segment"] == seg]
        st = step_stats(first.loc[sids])
        by_segment.append({"segment": seg, "label": D.SEGMENTS[seg]["label"], "n": int(len(sids)),
                           "steps": [{"step": x["step"], "n": x["n"], "n_mature": x["n_mature"], "conv_from_prev": x["conv_from_prev"],
                                      "median_days": x["median_days_from_prev"]} for x in st]})
    friction = state.cached(("friction", iso), lambda: detect_friction(acc, first, seg_pop, loops))
    if segment:
        friction = [c for c in friction if c["segment"] == segment]
    return {"as_of": D.AS_OF_DATE.isoformat(), "filters": {"segment": segment, "iso": iso},
            "population": int(len(pop)), "maturity_rule": f"time since previous step ≥ P75 dwell + {MATURE_EXTRA_D} d, or signed ≥ {MATURE_SIGNED_D} d ago",
            "steps": steps, "states": states, "by_segment": by_segment, "friction": friction}


def friction_ticket_md(state, index: int) -> str | None:
    fr = funnel(state)["friction"]
    if index < 0 or index >= len(fr):
        return None
    c = fr[index]
    acc = state.accounts
    seg = c["segment_label"]

    def fmt(metric, v):
        if metric in ("conversion", "order_rejection_rate"):
            return f"{v:.0%}"
        return f"{v:.1f} days" if metric == "median_days" else f"{v:.2f}"
    lines = [
        f"# Roadmap ticket: {seg} friction at {c['from_step_label']} → {c['step_label']}",
        "",
        "> **Synthetic data — illustrative.** Generated by Ignition from synthetic data; not ElectronX numbers.",
        "",
        f"- **Ticket:** FR-{index + 1:03d} (as of {D.AS_OF_DATE.isoformat()})",
        f"- **Severity:** {c['severity']}",
        f"- **Step:** {c['from_step_label']} → {c['step_label']}",
    ]
    for m in c["metrics"]:
        lines.append(f"- **{m['metric_label'].capitalize()}:** {fmt(m['metric'], m['value'])} (all segments: {fmt(m['metric'], m['benchmark'])})")
    lines += [
        f"- **Accounts affected (stuck past the benchmark dwell):** {c['accounts_affected']}",
        f"- **ADV at stake:** about {c['adv_at_stake']:,.0f} contracts/day (sum of P(Active) × E[ADV])",
        "",
        "## Ask",
        "",
        c["ask"],
        "",
        "## Acceptance criteria",
        "",
        f"- {seg} {c['metric_label']} within 5 pp or 20% of the all-segment benchmark for two consecutive months (mature cohorts).",
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
        lines.append(f"| {r['name']} | {r['stage'].replace('_', ' ').title()} | {r['p_display'] or '—'} | {r['exp_adv']:,.0f} |")
    lines += ["", "---", "*Synthetic data — illustrative.*", ""]
    return "\n".join(lines)
