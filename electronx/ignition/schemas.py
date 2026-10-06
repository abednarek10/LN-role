"""Pydantic models for small request/response shapes (big payloads are dicts)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: str
    as_of: str
    db: str
    warmed: bool
    version: int
    claude_enabled: bool


class DraftRequest(BaseModel):
    account_id: int
    trigger_id: str | None = None
    kind: Literal["volatility", "activation", "qbr"] = "activation"


class Flag(BaseModel):
    rule: str
    phrase: str | None = None
    level: Literal["block", "caution"]
    message: str


class Compliance(BaseModel):
    passed: bool
    flags: list[Flag]


class DraftResponse(BaseModel):
    draft_id: int
    account_id: int
    kind: str
    trigger_id: str | None
    template_id: str
    subject: str
    body: str
    engine: Literal["claude", "template"]
    facts: dict[str, Any]
    compliance: Compliance
    status: str


class DraftStatus(BaseModel):
    draft_id: int
    status: str
    activity_id: int | None = None
    account_id: int | None = None
    trigger_id: str | None = None
    logged_at: str | None = None


class CompSimRequest(BaseModel):
    plan_id: str | None = None
    params: dict[str, Any] | None = Field(default=None, description="Partial plan params merged over the stored plan")
