"""Shared router dependencies and param validation."""
from __future__ import annotations

from fastapi import HTTPException

from .. import definitions as D
from ..services import cache


def state():
    return cache.get_state()


def check_segment(v: str | None) -> str | None:
    v = v or None
    if v is not None and v not in D.SEGMENTS:
        raise HTTPException(422, f"unknown segment {v!r}; one of {list(D.SEGMENTS)}")
    return v


def check_iso(v: str | None) -> str | None:
    v = v or None
    if v is not None and v not in D.ISOS:
        raise HTTPException(422, f"unknown iso {v!r}; one of {list(D.ISOS)}")
    return v


def check_stage(v: str | None) -> str | None:
    v = v or None
    if v is not None and v not in D.STAGES:
        raise HTTPException(422, f"unknown stage {v!r}; one of {D.STAGES}")
    return v


def check_tenor(v: str | None) -> str | None:
    v = v or None
    if v is not None and v not in D.TENORS:
        raise HTTPException(422, f"unknown tenor {v!r}; one of {list(D.TENORS)}")
    return v
