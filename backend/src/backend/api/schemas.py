"""Request and response models for the public API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AgentInfo",
    "AgentListResponse",
    "ErrorBody",
    "ErrorResponse",
    "HealthResponse",
    "ReadyResponse",
    "RunRequest",
    "RunResponse",
    "UsageInfo",
]


class StrictModel(BaseModel):
    """Base model that rejects unknown fields, so typos fail loudly."""

    model_config = ConfigDict(extra="forbid")


# ---- Requests ------------------------------------------------------------


class RunRequest(StrictModel):
    prompt: str = Field(
        min_length=1,
        description="The instruction to send to the agent.",
        examples=["Draft a 30-day marketing plan for a new condo listing."],
    )
    session_id: str | None = Field(
        default=None,
        max_length=128,
        description="Opaque caller-supplied conversation id. Logged; not yet persisted.",
    )


# ---- Responses -----------------------------------------------------------


class UsageInfo(StrictModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    requests: int


class RunResponse(StrictModel):
    agent: str
    model: str
    output: str
    usage: UsageInfo
    duration_ms: int
    request_id: str


class AgentInfo(StrictModel):
    name: str
    description: str
    model: str


class AgentListResponse(StrictModel):
    agents: list[AgentInfo]
    default: str


class HealthResponse(StrictModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str


class ReadyResponse(StrictModel):
    status: Literal["ready", "degraded"]
    checks: dict[str, str]


class ErrorBody(StrictModel):
    code: str
    message: str
    request_id: str
    details: list[dict[str, object]] | None = None


class ErrorResponse(StrictModel):
    error: ErrorBody
