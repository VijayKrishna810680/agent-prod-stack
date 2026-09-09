"""Pydantic contracts for every boundary the agent crosses.

Problem this solves: a downstream billing/CRM/ticketing system cannot consume
"the model usually returns JSON like this." These schemas are the enforced contract
on the way in (what a caller may ask) and the way out (what the agent is allowed to
return), so a malformed or hallucinated shape is rejected before it reaches anything
that depends on it.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class AgentRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    user_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., min_length=1, max_length=8000)
    require_human_approval: bool = Field(
        default=False,
        description="If true, the graph pauses at the approval node before taking any action.",
    )

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must not be blank")
        return v


class AgentStatus(StrEnum):
    completed = "completed"
    awaiting_human_approval = "awaiting_human_approval"
    failed = "failed"


class ToolCall(BaseModel):
    name: str
    arguments: dict
    result: str | None = None
    succeeded: bool | None = None


class AgentResponse(BaseModel):
    session_id: str
    status: AgentStatus
    reply: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    trace_id: str | None = Field(
        default=None, description="Correlates this response with the observability backend."
    )


class ApprovalDecision(BaseModel):
    session_id: str
    approved: bool
    note: str | None = None
    # No reviewer_id here on purpose: the reviewer's identity comes from the
    # authenticated bearer token (app/auth.py), never from a self-reported field.


class AuditEntry(BaseModel):
    trace_id: str | None
    session_id: str
    reviewer_id: str
    approved: bool
    note: str | None
    status: str
    recorded_at: str
