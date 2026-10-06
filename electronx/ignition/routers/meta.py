from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import definitions as D
from .deps import state

router = APIRouter(tags=["meta"])


@router.get("/meta")
def meta(st=Depends(state)):
    reps = st.frames.reps
    t = dict(D.TARGETS_2026)
    t["speculator_share_adv"] = list(t["speculator_share_adv"])
    return {
        "as_of": D.AS_OF_DATE.isoformat(),
        "week_end": D.WEEK_END.isoformat(),
        "segments": [{"code": c, "label": v["label"], "side": v["side"]} for c, v in D.SEGMENTS.items()],
        "sides": D.SIDES,
        "isos": D.ISOS,
        "main_hubs": D.MAIN_HUB,
        "tenors": D.TENORS,
        "stages": D.STAGES,
        "steps": D.ONBOARDING_STEPS,
        "step_labels": D.STEP_LABELS,
        "channels": D.CHANNELS,
        "regimes": D.REGIME_LABELS,
        "reps": [{"id": int(r.id), "name": r.name, "role": r.role, "region": r.region} for r in reps.itertuples(index=False)],
        "targets": t,
        "definitions": {
            "active_min_days": D.ACTIVE_MIN_DAYS, "active_lookback_d": D.ACTIVE_LOOKBACK_D,
            "qualifying_contracts": D.QUALIFYING_CONTRACTS, "adv_window_td": D.ADV_WINDOW_TD,
            "small_cohort_n": D.SMALL_COHORT_N, "activation_window_d": D.ACTIVATION_WINDOW_D,
        },
        "synthetic": True,
        "watermark": "Synthetic data — illustrative",
    }
