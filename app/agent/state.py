"""Shared, typed state for the LangGraph workflow.

Problem this solves: enterprise processes are approval chains and escalations spread
across steps and sometimes across teams — not a single prompt. Having the workflow's
state be an explicit, typed object (rather than free-form text passed to the next LLM
call) is what makes the workflow inspectable, testable, and resumable.
"""

from __future__ import annotations

from typing import TypedDict


class AgentState(TypedDict, total=False):
    session_id: str
    user_id: str
    message: str
    require_human_approval: bool
    approved: bool | None
    reviewer_id: str | None
    reviewer_note: str | None
    reply: str | None
    tool_calls: list[dict]
    tool_chain_ok: bool
    status: str
