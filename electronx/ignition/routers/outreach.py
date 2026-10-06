from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import DraftRequest, DraftResponse, DraftStatus
from ..services import cache, outreach
from .deps import state

router = APIRouter(prefix="/outreach", tags=["outreach"])


def _err(exc: Exception):
    if isinstance(exc, outreach.NotFound):
        return HTTPException(404, str(exc))
    if isinstance(exc, outreach.Conflict):
        return HTTPException(409, str(exc))
    return HTTPException(422, str(exc))


@router.post("/draft", response_model=DraftResponse)
def draft(body: DraftRequest, st=Depends(state), db: Session = Depends(get_db)):
    try:
        out = outreach.create_draft(st, db, body.account_id, body.kind, body.trigger_id)
    except (outreach.NotFound, outreach.OutreachError) as exc:
        raise _err(exc) from exc
    cache.refresh(db, "outreach_drafts")
    return out


@router.get("/{draft_id}")
def get_draft(draft_id: int, db: Session = Depends(get_db)):
    try:
        return outreach.get_draft(db, draft_id)
    except outreach.NotFound as exc:
        raise _err(exc) from exc


@router.post("/{draft_id}/approve", response_model=DraftStatus)
def approve(draft_id: int, db: Session = Depends(get_db)):
    try:
        out = outreach.approve(db, draft_id)
    except (outreach.NotFound, outreach.Conflict) as exc:
        raise _err(exc) from exc
    cache.refresh(db, "outreach_drafts")
    return out


@router.post("/{draft_id}/queue", response_model=DraftStatus)
def queue(draft_id: int, db: Session = Depends(get_db)):
    try:
        out = outreach.queue(db, draft_id)
    except (outreach.NotFound, outreach.Conflict) as exc:
        raise _err(exc) from exc
    cache.refresh(db, "activities", "outreach_drafts")
    return out
