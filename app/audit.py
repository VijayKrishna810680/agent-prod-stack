"""A durable, queryable record of every approval decision.

Problem this solves: "the model decided to" (app/observability.py) covers tracing.
This covers the narrower, compliance-specific question: *who* approved or rejected
a given agent action, when, and why. `PostgresAuditSink` is the production backing
(the same `knowledge_documents`-style table pattern in app/db.py); the in-memory sink
is what tests use so the suite stays offline, and is deliberately the same interface
so swapping one for the other is a one-line change in main.py, not a rewrite.
"""

from __future__ import annotations

import datetime as dt
from typing import Protocol


class AuditSink(Protocol):
    def record(self, entry: dict) -> None: ...

    def list_for_session(self, session_id: str) -> list[dict]: ...


class InMemoryAuditSink:
    """Default sink. Fine for the scaffold and for tests; not durable across restarts."""

    def __init__(self) -> None:
        self._entries: list[dict] = []

    def record(self, entry: dict) -> None:
        self._entries.append(entry)

    def list_for_session(self, session_id: str) -> list[dict]:
        return [e for e in self._entries if e["session_id"] == session_id]


class PostgresAuditSink:
    """Production sink — writes to the `audit_log` table defined in app/db.py.

    Not wired in by default (would require a live Postgres instance for every test
    run); switch `get_audit_sink()` in main.py to return this once a database is
    available in your deployment target.
    """

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def record(self, entry: dict) -> None:
        from app.db import AuditLogEntry

        with self._session_factory() as session:
            session.add(AuditLogEntry(**entry))
            session.commit()

    def list_for_session(self, session_id: str) -> list[dict]:
        from app.db import AuditLogEntry

        with self._session_factory() as session:
            rows = (
                session.query(AuditLogEntry)
                .filter(AuditLogEntry.session_id == session_id)
                .order_by(AuditLogEntry.recorded_at)
                .all()
            )
            return [
                {
                    "trace_id": r.trace_id,
                    "session_id": r.session_id,
                    "reviewer_id": r.reviewer_id,
                    "approved": r.approved,
                    "note": r.note,
                    "status": r.status,
                    "recorded_at": r.recorded_at,
                }
                for r in rows
            ]


_default_sink = InMemoryAuditSink()


def get_audit_sink() -> AuditSink:
    return _default_sink


def build_entry(
    *,
    trace_id: str | None,
    session_id: str,
    reviewer_id: str,
    approved: bool,
    note: str | None,
    status: str,
) -> dict:
    return {
        "trace_id": trace_id,
        "session_id": session_id,
        "reviewer_id": reviewer_id,
        "approved": approved,
        "note": note,
        "status": status,
        "recorded_at": dt.datetime.now(dt.UTC).isoformat(),
    }
