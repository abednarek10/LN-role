from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..services import marketing
from .deps import state

router = APIRouter(prefix="/marketing", tags=["marketing"])


@router.get("/roi")
def roi(months: int = Query(6, ge=1, le=12), st=Depends(state)):
    return marketing.roi(st, months)
