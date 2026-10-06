from __future__ import annotations

from fastapi import APIRouter, Depends

from ..services import liquidity
from .deps import check_iso, check_tenor, state

router = APIRouter(tags=["liquidity"])


@router.get("/liquidity")
def get_liquidity(iso: str | None = None, tenor: str | None = None, st=Depends(state)):
    return liquidity.liquidity(st, check_iso(iso), check_tenor(tenor))
