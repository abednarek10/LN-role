from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..services import accounts
from .deps import check_iso, check_segment, check_stage, state

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("")
def list_accounts(segment: str | None = None, iso: str | None = None, stage: str | None = None, rep_id: int | None = None,
                  q: str | None = Query(None, max_length=100), limit: int = Query(50, ge=1, le=600),
                  offset: int = Query(0, ge=0), st=Depends(state)):
    return accounts.list_accounts(st, check_segment(segment), check_iso(iso), check_stage(stage), rep_id, q, limit, offset)


@router.get("/{account_id}")
def account(account_id: int, st=Depends(state)):
    out = accounts.account_360(st, account_id)
    if out is None:
        raise HTTPException(404, f"account {account_id} not found")
    return out
