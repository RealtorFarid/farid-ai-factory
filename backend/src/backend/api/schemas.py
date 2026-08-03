"""Request and response models for the public API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.runtime.runs import Run, RunStatus

__all__ = [
    "AgentInfo",
    "AgentListResponse",
    "ApprovalDecisionRequest",
    "ApprovalRequest",
    "ErrorBody",
    "ErrorResponse",
    "HealthResponse",
    "PendingApprovalInfo",
    "ReadyResponse",
    "RunListResponse",
    "RunRequest",
    "RunResponse",
    "ToolCallInfo",
    "ToolInfo",
    "ToolListResponse",
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
        examples=["What needs my attention today?"],
    )
    session_id: str | None = Field(
        default=None,
        max_length=128,
        description="Opaque caller-supplied conversation id, used to group runs.",
    )


class ApprovalDecisionRequest(StrictModel):
    tool_call_id: str
    approved: bool
    reason: str | None = Field(
        default=None,
        max_length=500,
        description="Shown to the agent when an action is denied.",
    )


class ApprovalRequest(StrictModel):
    decisions: list[ApprovalDecisionRequest] = Field(
        min_length=1,
        description="One decision per pending approval. Anything omitted is denied.",
    )


# ---- Responses -----------------------------------------------------------


class UsageInfo(StrictModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    requests: int


class PendingApprovalInfo(StrictModel):
    tool_call_id: str
    tool_name: str
    args: dict[str, object]
    description: str


class ToolCallInfo(StrictModel):
    tool_name: str
    tool_call_id: str
    args: dict[str, object]
    approved: bool | None


class RunResponse(StrictModel):
    """The full state of a run. The same shape whether it finished or paused."""

    id: str
    agent: str
    model: str
    status: RunStatus
    prompt: str
    session_id: str | None
    output: str | None
    error: str | None
    error_code: str | None
    usage: UsageInfo | None
    duration_ms: int
    created_at: datetime
    updated_at: datetime
    pending_approvals: list[PendingApprovalInfo]
    tool_calls: list[ToolCallInfo]

    @classmethod
    def from_run(cls, run: Run) -> RunResponse:
        return cls(
            id=run.id,
            agent=run.agent,
            model=run.model,
            status=run.status,
            prompt=run.prompt,
            session_id=run.session_id,
            output=run.output,
            error=run.error,
            error_code=run.error_code,
            usage=(
                UsageInfo(
                    input_tokens=run.usage.input_tokens,
                    output_tokens=run.usage.output_tokens,
                    total_tokens=run.usage.total_tokens,
                    requests=run.usage.requests,
                )
                if run.usage
                else None
            ),
            duration_ms=run.duration_ms,
            created_at=run.created_at,
            updated_at=run.updated_at,
            pending_approvals=[
                PendingApprovalInfo(
                    tool_call_id=a.tool_call_id,
                    tool_name=a.tool_name,
                    args=dict(a.args),
                    description=a.description,
                )
                for a in run.pending_approvals
            ],
            tool_calls=[
                ToolCallInfo(
                    tool_name=c.tool_name,
                    tool_call_id=c.tool_call_id,
                    args=dict(c.args),
                    approved=c.approved,
                )
                for c in run.tool_calls
            ],
        )


class RunListResponse(StrictModel):
    runs: list[RunResponse]


class AgentInfo(StrictModel):
    name: str
    description: str
    model: str


class AgentListResponse(StrictModel):
    agents: list[AgentInfo]
    default: str


class ToolInfo(StrictModel):
    name: str
    description: str
    category: str
    requires_approval: bool


class ToolListResponse(StrictModel):
    tools: list[ToolInfo]


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
