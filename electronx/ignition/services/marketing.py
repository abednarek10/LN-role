"""Marketing ROI by channel (``accounts.lead_source`` = marketing channel).

Window = the last ``months`` months of ``marketing_spend`` (through Sep 2026).
Accounts are attributed to the window by ``created_at`` (lead date). signed /
funded = reached that milestone by AS_OF; active = Active now (D2). ADV =
those accounts' 20-td ADV (contracts/day). ``n_small`` when funded < 20 (D11).
"""
from __future__ import annotations

import pandas as pd

from .. import definitions as D
from .common import date_str, num


def roi(state, months: int = 6) -> dict:
    months = int(max(1, min(months, 12)))
    return state.cached(("marketing", months), lambda: _roi(state, months))


def _roi(state, months: int) -> dict:
    ms = state.frames.marketing_spend
    all_months = sorted(ms["month"].unique())
    sel = all_months[-months:]
    lo = pd.Timestamp(sel[0])
    hi = pd.Timestamp(sel[-1]) + pd.offsets.MonthBegin(1)
    w = ms[ms["month"].isin(sel)]
    acc = state.accounts
    cohort = acc[(acc["created_at"] >= lo) & (acc["created_at"] < hi)]
    channels = []
    for ch in D.CHANNELS:
        s = w[w["channel"] == ch]
        c = cohort[cohort["lead_source"] == ch]
        spend = float(s["spend_usd"].sum())
        funded = int(c["funded_at"].notna().sum())
        active = int((c["trading_days_30"] >= D.ACTIVE_MIN_DAYS).sum())
        adv = float(c["adv_20td"].sum())
        channels.append({
            "channel": ch, "spend": round(spend, 2), "leads": int(s["leads"].sum()),
            "accounts": int(len(c)), "signed": int(c["signed_at"].notna().sum()), "funded": funded, "active": active,
            "cac_funded": round(spend / funded, 2) if funded else None,
            "cac_active": round(spend / active, 2) if active else None,
            "adv": round(adv, 1), "adv_per_1k_spend": round(adv / (spend / 1000), 3) if spend else None,
            "n_small": funded < D.SMALL_COHORT_N,
        })
    monthly = [{"month": date_str(r.month), "channel": r.channel, "spend": round(float(r.spend_usd), 2), "leads": int(r.leads),
                "campaign": r.campaign} for r in w.sort_values(["month", "channel"]).itertuples(index=False)]
    return {"as_of": D.AS_OF_DATE.isoformat(), "months": months,
            "window": {"from": date_str(lo), "to": date_str(hi - pd.Timedelta(days=1))},
            "channels": channels, "monthly": monthly,
            "note": "Attribution: lead_source of accounts created in the window; channels with < 20 funded accounts are small-n (directional only)."}
