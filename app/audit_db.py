"""SQLAlchemy-backed audit persistence.

Schema:
    audit_events (
      id           UUID/string PK,
      ts           timestamptz,
      run_id       UUID/string indexed,
      application_id text indexed nullable,
      actor        text,
      action       text indexed,
      payload      JSONB on postgres / JSON elsewhere,
      prev_hash    text nullable,
      hash         text
    )

Production points `DATABASE_URL` at Postgres (`postgresql+psycopg://...`).
Tests use `sqlite:///:memory:` — the hash chain and query path work the
same either way. JSONB → JSON downgrade on SQLite is automatic via
SQLAlchemy's `with_variant`.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Iterator

from sqlalchemy import (
    JSON, Column, Engine, Index, String, Text, create_engine, select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class AuditEventRow(Base):
    __tablename__ = "audit_events"

    id = Column(String(36), primary_key=True)
    # Stored as the canonical ISO-8601 string so the hash chain round-trips
    # bit-for-bit. UTC ISO sorts lexicographically, so indexed text is fine.
    ts = Column(Text, nullable=False)
    run_id = Column(String(36), nullable=False)
    application_id = Column(String(64), nullable=True)
    actor = Column(String(32), nullable=False)
    action = Column(String(64), nullable=False)
    payload = Column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
    )
    prev_hash = Column(Text, nullable=True)
    hash = Column(Text, nullable=False)

    __table_args__ = (
        Index("ix_audit_events_run_id", "run_id"),
        Index("ix_audit_events_application_id", "application_id"),
        Index("ix_audit_events_action", "action"),
        Index("ix_audit_events_ts", "ts"),
    )


def make_engine(url: str | None = None) -> Engine:
    url = url or os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    return create_engine(url, future=True)


def init_schema(engine: Engine) -> None:
    """Create the audit_events table if it does not exist.

    For production schema migrations, add Alembic; for the slice
    `create_all` is fine — the schema is one append-only table.
    """
    Base.metadata.create_all(engine)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


# ---- Query helpers used by the API + CLI ---------------------------------


def list_runs(session: Session, application_id: str | None = None,
              limit: int = 50) -> list[dict]:
    """Summarize recent runs: one row per (run_id, application_id) with
    earliest ts, decision (from memo.finalized payload, if present), and
    event count."""
    stmt = select(
        AuditEventRow.run_id,
        AuditEventRow.application_id,
    ).distinct().order_by(AuditEventRow.run_id)
    if application_id:
        stmt = stmt.where(AuditEventRow.application_id == application_id)
    rows = session.execute(stmt).all()

    summaries: list[dict] = []
    for run_id, app_id in rows:
        events = session.execute(
            select(AuditEventRow).where(AuditEventRow.run_id == run_id)
            .order_by(AuditEventRow.ts)
        ).scalars().all()
        if not events:
            continue
        decision = None
        for ev in events:
            if ev.action == "memo.finalized":
                decision = ev.payload.get("decision") if isinstance(ev.payload, dict) else None
        summaries.append({
            "run_id": run_id,
            "application_id": app_id,
            "started_at": events[0].ts,
            "ended_at": events[-1].ts,
            "n_events": len(events),
            "decision": decision,
        })

    summaries.sort(key=lambda s: s["started_at"] or "", reverse=True)
    return summaries[:limit]


def get_run_events(session: Session, run_id: str) -> list[AuditEventRow]:
    return session.execute(
        select(AuditEventRow).where(AuditEventRow.run_id == run_id)
        .order_by(AuditEventRow.ts)
    ).scalars().all()


def iter_run_events(session: Session, run_id: str) -> Iterator[AuditEventRow]:
    yield from get_run_events(session, run_id)
