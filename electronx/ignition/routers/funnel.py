from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from ..services import funnel
from .deps import check_iso, check_segment, state

router = APIRouter(prefix="/funnel", tags=["funnel"])


@router.get("")
def get_funnel(segment: str | None = None, iso: str | None = None, st=Depends(state)):
    return funnel.funnel(st, check_segment(segment), check_iso(iso))


@router.get("/friction/{index}.md", response_class=PlainTextResponse)
def friction_md(index: int, st=Depends(state)):
    md = funnel.friction_ticket_md(st, index)
    if md is None:
        raise HTTPException(404, f"friction index {index} out of range")
    return PlainTextResponse(md, media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition": f'inline; filename="ignition-roadmap-ticket-{index + 1}.md"'})
