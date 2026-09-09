"""Tracing hook (Langfuse-compatible; Opik can be swapped in behind the same interface).

Problem this solves: "the model decided to" is not an acceptable answer to a compliance
reviewer or an incident retro. Every agent turn gets a trace_id and a structured record
of inputs, tool calls, and outputs that can be replayed later — this is the audit trail
regulated enterprises are required to produce, not an optional nice-to-have.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager

from app.settings import get_settings

logger = logging.getLogger(__name__)


@contextmanager
def trace_agent_turn(session_id: str, user_id: str):
    """Yields a trace_id. Emits structured start/end log events.

    In a real deployment, swap the log calls for `langfuse.trace(...)` /
    `opik.track(...)` calls — the call sites in main.py and graph.py don't change.
    """
    settings = get_settings()
    trace_id = str(uuid.uuid4())

    logger.info(
        "trace_start",
        extra={"trace_id": trace_id, "session_id": session_id, "user_id": user_id},
    )
    try:
        yield trace_id
    except Exception:
        logger.exception("trace_error", extra={"trace_id": trace_id})
        raise
    finally:
        if settings.tracing_enabled:
            logger.info("trace_end", extra={"trace_id": trace_id})
