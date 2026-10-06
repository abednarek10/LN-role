"""Segments: segment × ISO penetration / activation / ADV and coverage advice.

TAM = every account in the synthetic universe (600). Liquidity partners are
excluded from cells and segment rows (separate motion) and summarised in
``liquidity_partners``. ADV = 20-td ADV as of AS_OF (contracts/day).
"""
from __future__ import annotations

from .. import definitions as D
from .common import num


def _coverage(tam: int, pen: float, act_rate: float | None, adv_share: float, adv_per_active: float | None, side: str) -> str:
    if adv_share >= 0.25 and (adv_per_active or 0) >= 150:
        return "Strategic Sales named coverage + QBRs (whales; concentration risk)"
    if act_rate is not None and act_rate < 0.5:
        return "Activation focus: RevOps KYC chases + AE hub walkthroughs before new logos"
    if pen < 0.5 and tam >= 50:
        return ("Add AE capacity + event-triggered outbound (balance weight on)" if side == "hedger"
                else "Partner/LP intros + API-first outbound")
    if pen < 0.5:
        return "Marketing-led nurture tied to Market Pulse events"
    return "Maintain: AE coverage, expansion plays (2nd ISO / hourly)"


def segments(state) -> dict:
    return state.cached(("segments",), lambda: _segments(state))


def _segments(state) -> dict:
    acc = state.accounts
    nonlp = acc[~acc["is_liquidity_partner"].astype(bool)]
    total_adv = float(nonlp["adv_20td"].sum())
    cells = []
    for seg in D.SEGMENT_CODES:
        for iso in D.ISO_CODES:
            c = nonlp[(nonlp["segment"] == seg) & (nonlp["primary_iso"] == iso)]
            if not len(c):
                continue
            signed = int(c["signed_at"].notna().sum())
            funded = int(c["funded_at"].notna().sum())
            active = int((c["trading_days_30"] >= D.ACTIVE_MIN_DAYS).sum())
            adv = float(c["adv_20td"].sum())
            cells.append({
                "segment": seg, "iso": iso, "tam_accounts": int(len(c)), "signed": signed, "funded": funded, "active": active,
                "penetration": round(signed / len(c), 4),
                "activation_rate": round(active / funded, 4) if funded else None,
                "adv_per_active": round(adv / active, 1) if active else None,
                "adv_total": round(adv, 1),
            })
    segs = []
    for seg in D.SEGMENT_CODES:
        c = nonlp[nonlp["segment"] == seg]
        signed = int(c["signed_at"].notna().sum())
        funded = int(c["funded_at"].notna().sum())
        active = int((c["trading_days_30"] >= D.ACTIVE_MIN_DAYS).sum())
        adv = float(c["adv_20td"].sum())
        share = adv / total_adv if total_adv else 0.0
        pen = signed / len(c) if len(c) else 0.0
        ar = active / funded if funded else None
        apa = adv / active if active else None
        side = D.SEGMENTS[seg]["side"]
        segs.append({
            "segment": seg, "label": D.SEGMENTS[seg]["label"], "side": side,
            "tam": int(len(c)), "signed": signed, "funded": funded, "active": active,
            "penetration": round(pen, 4), "activation_rate": num(ar), "adv": round(adv, 1),
            "adv_share": round(share, 4), "adv_per_active": num(apa, 1),
            "recommended_coverage": _coverage(len(c), pen, ar, share, apa, side),
        })
    lp = acc[acc["is_liquidity_partner"].astype(bool)]
    return {
        "as_of": D.AS_OF_DATE.isoformat(), "cells": cells, "segments": segs,
        "liquidity_partners": {"accounts": int(len(lp)),
                               "active": int((lp["trading_days_30"] >= D.ACTIVE_MIN_DAYS).sum()),
                               "adv": round(float(lp["adv_20td"].sum()), 1)},
        "note": "Liquidity partners excluded from segment cells (separate motion); ADV = 20-td contracts/day.",
    }
