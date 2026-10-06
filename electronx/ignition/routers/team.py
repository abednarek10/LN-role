from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import definitions as D
from ..schemas import CompSimRequest
from ..services import team
from .deps import state

router = APIRouter(prefix="/team", tags=["team"])


@router.get("/scorecards")
def scorecards(st=Depends(state)):
    return team.scorecards(st)


@router.get("/comp-plans")
def comp_plans():
    return {"as_of": D.AS_OF_DATE.isoformat(), "plans": team.plans()}


@router.post("/comp-sim")
def comp_sim(body: CompSimRequest | None = None, st=Depends(state)):
    body = body or CompSimRequest()
    try:
        return team.simulate(st, body.plan_id, body.params)
    except KeyError as exc:
        raise HTTPException(404, f"unknown plan_id {body.plan_id!r}") from exc
    except team.CompParamError as exc:
        raise HTTPException(422, str(exc)) from exc
