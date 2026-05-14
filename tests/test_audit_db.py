"""SqlAlchemySink tests against an in-memory SQLite database.

Verifies that:
  * events round-trip through the SQL sink with the hash chain intact,
  * list_runs / get_run_events return correct summaries + ordering,
  * the API audit endpoints surface the same data,
  * `DATABASE_URL` selects the SQL sink as the default.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.audit import (
    AuditEvent, SqlAlchemySink, _default_sink, audit_run, emit, verify_chain,
)
from app.audit_db import get_run_events, list_runs, make_engine, make_session_factory


@pytest.fixture
def sqlite_url(tmp_path: Path) -> str:
    # File-backed sqlite so the API endpoint can re-open it via DATABASE_URL.
    db_path = tmp_path / "audit.db"
    return f"sqlite:///{db_path}"


def test_sql_sink_emits_and_chain_verifies(sqlite_url: str):
    sink = SqlAlchemySink(sqlite_url)
    with audit_run("app-A", sink=sink):
        emit("tool", "tool_call.compute_ratios.start", {"x": 1})
        emit("tool", "tool_call.compute_ratios.result", {"output": {"dti": 0.2}})

    from sqlalchemy import select
    from app.audit_db import AuditEventRow
    Session = make_session_factory(make_engine(sqlite_url))
    with Session() as s:
        rows = s.execute(select(AuditEventRow).order_by(AuditEventRow.ts)).scalars().all()

    actions = [r.action for r in rows]
    assert actions[0] == "run.started"
    assert actions[-1] == "run.finished"
    assert "tool_call.compute_ratios.start" in actions
    events = [AuditEvent(
        id=r.id, ts=r.ts,
        run_id=r.run_id, application_id=r.application_id,
        actor=r.actor, action=r.action, payload=r.payload or {},
        prev_hash=r.prev_hash, hash=r.hash,
    ) for r in rows]
    assert verify_chain(events) is True


def test_list_runs_filters_by_application(sqlite_url: str):
    sink = SqlAlchemySink(sqlite_url)
    with audit_run("app-X", sink=sink):
        emit("system", "memo.finalized", {"decision": "approve"})
    with audit_run("app-Y", sink=sink):
        emit("system", "memo.finalized", {"decision": "decline"})

    Session = make_session_factory(make_engine(sqlite_url))
    with Session() as s:
        all_runs = list_runs(s)
        x_runs = list_runs(s, application_id="app-X")

    assert len(all_runs) == 2
    assert len(x_runs) == 1
    assert x_runs[0]["application_id"] == "app-X"
    assert x_runs[0]["decision"] == "approve"


def test_default_sink_picks_sql_when_database_url_set(sqlite_url: str, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", sqlite_url)
    sink = _default_sink()
    assert isinstance(sink, SqlAlchemySink)


def test_default_sink_falls_back_to_jsonl(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.log"))
    from app.audit import JsonlSink
    sink = _default_sink()
    assert isinstance(sink, JsonlSink)


def test_audit_runs_endpoint(sqlite_url: str, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", sqlite_url)
    sink = SqlAlchemySink(sqlite_url)
    run_ids = []
    with audit_run("app-API", sink=sink) as (rid, _):
        run_ids.append(rid)
        emit("system", "memo.finalized", {"decision": "approve"})

    # Re-import fresh app so middleware picks up env (FastAPI doesn't need it,
    # but the endpoint reads DATABASE_URL each call).
    from app.api.main import app as _app
    client = TestClient(_app)

    r = client.get("/audit/runs?application_id=app-API")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["runs"]) == 1
    assert body["runs"][0]["decision"] == "approve"

    r2 = client.get(f"/audit/runs/{run_ids[0]}")
    assert r2.status_code == 200
    detail = r2.json()
    assert detail["chain_verified"] is True
    assert any(e["action"] == "memo.finalized" for e in detail["events"])


def test_audit_runs_endpoint_503_without_db(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app.api.main import app as _app
    client = TestClient(_app)
    r = client.get("/audit/runs")
    assert r.status_code == 503
