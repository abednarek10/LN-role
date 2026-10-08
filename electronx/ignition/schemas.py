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
    id: str | None = None
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
    kind: str | None
    trigger_id: str | None
    template_id: str | None
    subject: str
    body: str
    engine: Literal["claude", "template"]
    facts: dict[str, Any]
    compliance: Compliance
    status: str
    reviewer: str | None = None
    cleared_flag_ids: list[str] = []
    reject_reason: str | None = None
    created_at: str | None = None


class ApproveRequest(BaseModel):
    reviewer: str = Field(min_length=2, max_length=120)
    cleared_flag_ids: list[str] = []


class RejectRequest(BaseModel):
    reviewer: str = Field(min_length=1, max_length=120)
    reason: str = Field(default="", max_length=2000)


class EditRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)


class DraftStatus(BaseModel):
    draft_id: int
    status: str
    reviewer: str | None = None
    reason: str | None = None
    activity_id: int | None = None
    account_id: int | None = None
    trigger_id: str | None = None
    logged_at: str | None = None


class CompSimRequest(BaseModel):
    plan_id: str | None = None
    params: dict[str, Any] | None = Field(default=None, description="Partial plan params merged over the stored plan")
