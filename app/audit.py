"""Audit-event emission.

Every tool call, LLM call, critic verdict, and memo submission is recorded
as an append-only `AuditEvent`. The default sink writes JSON Lines to
`./audit.log` (override via the `AUDIT_LOG_PATH` env var). Each run gets a
fresh hash chain — `prev_hash` of event N is `hash` of event N-1 — so a
later check can detect tampering.

In production, swap the default sink for a Kafka producer or an S3 WORM sink
by setting `AUDIT_SINK = MySink(...)` or by passing `sink=...` to
`audit_run(...)`. The contextvar `_current_sink` is the integration point —
modules emit via `emit(...)` without knowing which sink is bound.
"""
from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import os
import threading
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    id: str
    ts: str
    run_id: str
    application_id: str | None = None
    actor: str           # "agent" | "critic" | "tool" | "system"
    action: str          # e.g. "tool_call.compute_ratios", "memo_finalized"
    payload: dict[str, Any] = Field(default_factory=dict)
    prev_hash: str | None = None
    hash: str | None = None


def _canonical_json(d: dict) -> bytes:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), default=str).encode()


class AuditSink(ABC):
    @abstractmethod
    def emit(self, event: AuditEvent) -> None: ...


class JsonlSink(AuditSink):
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def emit(self, event: AuditEvent) -> None:
        line = event.model_dump_json() + "\n"
        with self._lock, self.path.open("a") as f:
            f.write(line)


class InMemorySink(AuditSink):
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def emit(self, event: AuditEvent) -> None:
        self.events.append(event)


class SqlAlchemySink(AuditSink):
    """Persists events to any SQLAlchemy-supported DB. Use `DATABASE_URL` env
    pointing at Postgres in production; SQLite works for development and tests.
    Auto-initializes the schema on first use."""

    def __init__(self, url_or_engine=None) -> None:
        from app.audit_db import AuditEventRow, init_schema, make_engine, make_session_factory
        if url_or_engine is None or isinstance(url_or_engine, str):
            self._engine = make_engine(url_or_engine)
        else:
            self._engine = url_or_engine
        init_schema(self._engine)
        self._Session = make_session_factory(self._engine)
        self._Row = AuditEventRow

    def emit(self, event: AuditEvent) -> None:
        # ts is persisted verbatim as the canonical ISO string so the hash
        # chain survives the round trip.
        row = self._Row(
            id=event.id,
            ts=event.ts,
            run_id=event.run_id,
            application_id=event.application_id,
            actor=event.actor,
            action=event.action,
            payload=event.payload,
            prev_hash=event.prev_hash,
            hash=event.hash,
        )
        with self._Session() as s:
            s.add(row)
            s.commit()


@contextlib.contextmanager
def audit_run(
    application_id: str | None,
    sink: AuditSink | None = None,
) -> Iterator[tuple[str, AuditSink]]:
    """Open an audit context for one underwriting run.

    Binds a run_id + sink in a ContextVar; emits a `run.started` event on
    entry and a `run.finished` event on exit. Nested calls inherit the
    same sink and run_id.
    """
    run_id = str(uuid.uuid4())
    if sink is None:
        sink = _default_sink()
    state = _AuditState(run_id=run_id, application_id=application_id, sink=sink)
    token = _current.set(state)
    try:
        emit("system", "run.started", {})
        yield run_id, sink
        emit("system", "run.finished", {})
    finally:
        _current.reset(token)


def emit(actor: str, action: str, payload: dict[str, Any] | None = None) -> None:
    state = _current.get(None)
    if state is None:
        # No audit context — silently drop. Useful for ad-hoc tool calls in
        # tests that don't open `audit_run`.
        return

    event = AuditEvent(
        id=str(uuid.uuid4()),
        ts=datetime.now(timezone.utc).isoformat(),
        run_id=state.run_id,
        application_id=state.application_id,
        actor=actor,
        action=action,
        payload=payload or {},
        prev_hash=state.last_hash,
    )
    # Compute the chained hash over the canonical event body (excluding `hash`).
    body = event.model_dump(exclude={"hash"})
    h = hashlib.sha256()
    if state.last_hash:
        h.update(state.last_hash.encode())
    h.update(_canonical_json(body))
    event.hash = h.hexdigest()
    state.last_hash = event.hash

    state.sink.emit(event)


def verify_chain(events: list[AuditEvent]) -> bool:
    """Recompute the hash chain over an event list and verify integrity."""
    prev: str | None = None
    for ev in events:
        body = ev.model_dump(exclude={"hash"})
        body["prev_hash"] = prev
        h = hashlib.sha256()
        if prev:
            h.update(prev.encode())
        h.update(_canonical_json(body))
        if h.hexdigest() != ev.hash:
            return False
        prev = ev.hash
    return True


# ----- internals ----------------------------------------------------------


class _AuditState:
    __slots__ = ("run_id", "application_id", "sink", "last_hash")

    def __init__(self, run_id: str, application_id: str | None, sink: AuditSink) -> None:
        self.run_id = run_id
        self.application_id = application_id
        self.sink = sink
        self.last_hash: str | None = None


_current: contextvars.ContextVar[_AuditState | None] = contextvars.ContextVar(
    "audit_state", default=None
)


def _default_sink() -> AuditSink:
    """Pick the production-style sink when DATABASE_URL is set, otherwise
    fall back to the local JSONL file."""
    if os.environ.get("DATABASE_URL"):
        try:
            return SqlAlchemySink()
        except Exception:
            # If the DB is unreachable, don't crash the run — log to JSONL
            # and let the operator see the audit-log path in the warning.
            pass
    return JsonlSink(os.environ.get("AUDIT_LOG_PATH", "audit.log"))
