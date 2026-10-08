from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import definitions as D
from ..services import propensity
from .deps import state

router = APIRouter(prefix="/scoring", tags=["scoring"])


@router.get("/model")
def model(st=Depends(state)):
    rep = st.cached(("model_report",), lambda: propensity.model_report(st.bundle))
    # short machine key for the tile; the full definition travels alongside
    # short machine key for the tile; the full definition travels alongside. Headline auc = gap AUC (X11).
    honest = rep.get("honest") or {}
    out = {"as_of": D.AS_OF_DATE.isoformat()} | rep | {"target": "active_60d", "target_description": rep["target"]}
    if honest.get("auc_gap") is not None:
        out["auc"] = honest["auc_gap"]
    return out
