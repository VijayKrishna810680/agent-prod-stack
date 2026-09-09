"""The API layer.

Problem this solves: a script that works for a demo doesn't hold up under concurrent
enterprise load, and doesn't give other systems in the org a stable contract to
integrate against. FastAPI gives an async, OpenAPI-documented surface; every request
and response is validated against the Pydantic contracts in app/schemas.py before it
touches the agent graph.
"""

from __future__ import annotations

import logging

import redis
from fastapi import Depends, FastAPI, HTTPException

from app.agent.graph import build_graph, is_awaiting_approval, resume_after_approval
from app.audit import AuditSink, build_entry, get_audit_sink
from app.auth import require_reviewer
from app.cache import (
    RateLimitExceededError,
    check_rate_limit,
    get_cached_reply,
    get_redis_client,
    set_cached_reply,
)
from app.observability import trace_agent_turn
from app.schemas import (
    AgentRequest,
    AgentResponse,
    AgentStatus,
    ApprovalDecision,
    AuditEntry,
    ToolCall,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Enterprise Agent Service",
    version="0.1.0",
    description="Production scaffold: contracts, workflow, caching, rate limiting, tracing.",
)

_graph = build_graph()


def redis_dependency() -> redis.Redis:
    return get_redis_client()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/v1/agent/invoke", response_model=AgentResponse)
def invoke_agent(
    request: AgentRequest, client: redis.Redis = Depends(redis_dependency)
) -> AgentResponse:
    try:
        check_rate_limit(client, request.user_id)
    except RateLimitExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    if not request.require_human_approval:
        cached = get_cached_reply(client, request.session_id, request.message)
        if cached is not None:
            return AgentResponse(
                session_id=request.session_id, status=AgentStatus.completed, reply=cached
            )

    config = {"configurable": {"thread_id": request.session_id}}

    with trace_agent_turn(request.session_id, request.user_id) as trace_id:
        result = _graph.invoke(
            {
                "session_id": request.session_id,
                "user_id": request.user_id,
                "message": request.message,
                "require_human_approval": request.require_human_approval,
                "approved": None,
            },
            config,
        )

        if is_awaiting_approval(_graph, config):
            return AgentResponse(
                session_id=request.session_id,
                status=AgentStatus.awaiting_human_approval,
                trace_id=trace_id,
            )

        if not request.require_human_approval:
            set_cached_reply(client, request.session_id, request.message, result["reply"])

        return AgentResponse(
            session_id=request.session_id,
            status=AgentStatus.completed,
            reply=result.get("reply"),
            tool_calls=[ToolCall(**tc) for tc in result.get("tool_calls", [])],
            trace_id=trace_id,
        )


@app.post("/v1/agent/approve", response_model=AgentResponse)
def approve_agent(
    decision: ApprovalDecision,
    reviewer_id: str = Depends(require_reviewer),
    audit: AuditSink = Depends(get_audit_sink),
) -> AgentResponse:
    config = {"configurable": {"thread_id": decision.session_id}}

    with trace_agent_turn(decision.session_id, reviewer_id) as trace_id:
        result = resume_after_approval(
            _graph,
            config,
            approved=decision.approved,
            reviewer_id=reviewer_id,
            note=decision.note,
        )

        audit.record(
            build_entry(
                trace_id=trace_id,
                session_id=decision.session_id,
                reviewer_id=reviewer_id,
                approved=decision.approved,
                note=decision.note,
                status=result["status"],
            )
        )

        return AgentResponse(
            session_id=decision.session_id,
            status=AgentStatus(result["status"]),
            reply=result.get("reply"),
            tool_calls=[ToolCall(**tc) for tc in result.get("tool_calls", [])],
            trace_id=trace_id,
        )


@app.get("/v1/agent/audit/{session_id}", response_model=list[AuditEntry])
def get_audit_log(
    session_id: str,
    _reviewer_id: str = Depends(require_reviewer),
    audit: AuditSink = Depends(get_audit_sink),
) -> list[AuditEntry]:
    """Every approval decision made for a session — who, when, and the outcome.

    Gated behind the same reviewer auth as approving, not exposed to anonymous
    callers.
    """
    return [AuditEntry(**entry) for entry in audit.list_for_session(session_id)]
