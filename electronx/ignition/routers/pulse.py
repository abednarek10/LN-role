from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..services import pulse
from .deps import check_iso, state

router = APIRouter(prefix="/pulse", tags=["pulse"])


@router.get("/hubs")
def hubs(iso: str | None = None, hours: int = Query(168, ge=24, le=1440), st=Depends(state)):
    return pulse.hubs(st, check_iso(iso), hours)


@router.get("/triggers")
def triggers(st=Depends(state)):
    return pulse.triggers_payload(st)


@router.get("/events")
def events(st=Depends(state)):
    return pulse.events(st)


@router.get("/triggers/{trigger_id}/accounts")
def trigger_accounts(trigger_id: str, view: str = Query("actionable", pattern="^(actionable|all)$"), st=Depends(state)):
    out = pulse.trigger_accounts(st, trigger_id, view)
    if out is None:
        raise HTTPException(404, f"trigger {trigger_id} not found (live triggers only)")
    return out


@router.get("/history")
def history(st=Depends(state)):
    return pulse.history(st)
