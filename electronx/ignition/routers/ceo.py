from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from ..services import ceo, memo
from .deps import state

router = APIRouter(prefix="/ceo", tags=["ceo"])


def _we(week_end: str | None):
    try:
        return ceo.parse_week_end(week_end)
    except ceo.WeekEndError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/weekly")
def weekly(week_end: str | None = None, st=Depends(state)):
    return ceo.weekly(st, _we(week_end))


@router.get("/weekly.md", response_class=PlainTextResponse)
def weekly_md(week_end: str | None = None, st=Depends(state)):
    we = _we(week_end)
    return PlainTextResponse(memo.weekly_md(st, we), media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition": f'inline; filename="ignition-ceo-weekly-{we}.md"'})
