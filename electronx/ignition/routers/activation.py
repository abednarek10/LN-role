from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..services import activation
from .deps import check_iso, check_segment, check_stage, state

router = APIRouter(prefix="/activation", tags=["activation"])


@router.get("/queue")
def queue(limit: int = Query(50, ge=1, le=1000), segment: str | None = None, iso: str | None = None,
          rep_id: int | None = None, stage: str | None = None, st=Depends(state)):
    return activation.queue(st, limit, check_segment(segment), check_iso(iso), rep_id, check_stage(stage))


@router.get("/rules")
def rules():
    return {"rules": activation.rules()}
