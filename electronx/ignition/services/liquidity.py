"""Liquidity flywheel: spread series and the elasticity fit spread = a + b/√active.

The fit pools the selected ISO/tenor rows with one intercept per hub × tenor
(fixed effects) and a common ``b``; ``r2`` is reported on the pooled fit.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import definitions as D
from .common import date_str


def fit_elasticity(df: pd.DataFrame) -> dict:
    """OLS of spread on 1/√active with per-(hub, tenor) intercepts."""
    d = df[df["active_accounts"] > 0]
    if len(d) < 5:
        return {"a": None, "b": None, "r2": None, "n": int(len(d))}
    x = 1.0 / np.sqrt(d["active_accounts"].to_numpy(dtype=float))
    y = d["spread_usd_mwh"].to_numpy(dtype=float)
    groups = (d["hub"] + "|" + d["tenor"]).to_numpy()
    levels = sorted(set(groups))
    X = np.column_stack([x] + [(groups == g).astype(float) for g in levels])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ beta
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    a = {g: round(float(c), 4) for g, c in zip(levels, beta[1:])}
    return {"b": round(float(beta[0]), 4), "a": a, "r2": round(1 - ss_res / ss_tot, 4) if ss_tot else None, "n": int(len(d))}


def liquidity(state, iso: str | None = None, tenor: str | None = None) -> dict:
    return state.cached(("liquidity", iso, tenor), lambda: _liquidity(state, iso, tenor))


def _liquidity(state, iso, tenor) -> dict:
    sp = state.frames.spread_snapshots
    if iso:
        sp = sp[sp["iso"] == iso]
    if tenor:
        sp = sp[sp["tenor"] == tenor]
    sp = sp.sort_values(["hub", "tenor", "date"])
    series = [{"date": date_str(r.date), "iso": r.iso, "hub": r.hub, "tenor": r.tenor,
               "spread_usd_mwh": round(float(r.spread_usd_mwh), 4), "uptime_pct": round(float(r.two_sided_uptime_pct), 2),
               "active_accounts": int(r.active_accounts), "lp_quote_share": round(float(r.lp_quote_share), 4),
               "top_depth_contracts": int(r.top_depth_contracts)} for r in sp.itertuples(index=False)]
    fit = fit_elasticity(sp)
    note = None
    if fit["b"] is not None and len(sp):
        hub = D.MAIN_HUB.get(iso or "ERCOT", "HB_NORTH")
        last = sp[sp["hub"] == hub]
        if not len(last):
            last = sp
        n_now = float(last.sort_values("date")["active_accounts"].iloc[-1])
        n_now = max(n_now, 1.0)
        per10 = fit["b"] * (1 / np.sqrt(n_now + 10) - 1 / np.sqrt(n_now))
        note = (f"Spread ≈ a + {fit['b']:.2f}/√active (R² {fit['r2']:.2f}, n={fit['n']}). At {n_now:.0f} active accounts on {hub}, "
                f"each +10 Active accounts tightens the spread by about ${abs(per10):.3f}/MWh — activation is the cheapest spread lever.")
    return {"as_of": D.AS_OF_DATE.isoformat(), "iso": iso, "tenor": tenor, "series": series,
            "elasticity": {"b": fit["b"], "a": fit["a"], "r2": fit["r2"], "n": fit["n"], "note": note}}
