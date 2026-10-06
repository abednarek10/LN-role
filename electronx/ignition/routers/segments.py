from __future__ import annotations

from fastapi import APIRouter, Depends

from ..services import segments
from .deps import state

router = APIRouter(tags=["segments"])


@router.get("/segments")
def get_segments(st=Depends(state)):
    return segments.segments(st)
