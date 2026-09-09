"""Relational data + vector search in one system (Postgres + pgvector).

Problem this solves: enterprises have structured records (tickets, orders, employee
data) and unstructured knowledge (policies, past cases) that need to be searched
together. Standing up a separate vector database next to the system of record adds
another vendor for security/compliance to review and another thing that can drift
out of sync. Keeping both in Postgres removes that seam until you're at genuine
hyperscale.
"""

from __future__ import annotations

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.settings import get_settings


class Base(DeclarativeBase):
    pass


class KnowledgeDocument(Base):
    """A chunk of enterprise knowledge (policy text, past-case summary, etc.)."""

    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(String)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))


class AuditLogEntry(Base):
    """Durable, queryable record of every human approval decision.

    Backs `app.audit.PostgresAuditSink` — the production wiring for the access
    control gap called out in PROBLEMS_SOLVED.md. Append-only in practice: nothing
    in this codebase updates or deletes a row here.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    reviewer_id: Mapped[str] = mapped_column(String(128))
    approved: Mapped[bool] = mapped_column(Boolean)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    recorded_at: Mapped[str] = mapped_column(String(64))


def get_engine():
    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True)


def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine())


def nearest_documents(session: Session, query_embedding: list[float], limit: int = 5):
    """Semantic search alongside ordinary relational queries — same database, same
    transaction, no second system to keep consistent."""
    return (
        session.query(KnowledgeDocument)
        .order_by(KnowledgeDocument.embedding.cosine_distance(query_embedding))
        .limit(limit)
        .all()
    )
