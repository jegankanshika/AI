"""Audit-log emission tests — no API key, no filesystem writes (InMemorySink)."""
from __future__ import annotations

import json

from app.agent.graph import build_graph
from app.audit import InMemorySink, audit_run, emit, verify_chain
from app.schemas import BureauData, LoanApplication
from app.tools.registry import ToolContext
from tests.test_agent_graph import _GOOD_MEMO_INPUT, _BAD_MEMO_INPUT, _scripted_client


def _app() -> LoanApplication:
    return LoanApplication(
        application_id="aud-1", applicant_id="aud-u-1",
        age=33, state="NY", employment_status="employed",
        years_employed=4.0, annual_income=75000.0, monthly_housing_cost=1900.0,
        product="personal_loan", requested_amount=12000.0, term_months=36,
        purpose="debt_consolidation",
        bureau=BureauData(
            credit_score=720, revolving_utilization=0.3, open_trades=7,
            delinquencies_24m=0, inquiries_6m=1, bankruptcies_7y=0,
            oldest_trade_months=110,
        ),
    )


def test_emit_is_noop_outside_run_context():
    sink = InMemorySink()
    # No `audit_run`, so emit drops the event.
    emit("system", "stray", {})
    assert sink.events == []


def test_audit_run_emits_start_and_finish_with_hash_chain():
    sink = InMemorySink()
    with audit_run("app-x", sink=sink):
        emit("tool", "tool_call.compute_ratios.start", {"x": 1})
        emit("tool", "tool_call.compute_ratios.result", {"output": {"dti": 0.2}})

    actions = [e.action for e in sink.events]
    assert actions[0] == "run.started"
    assert actions[-1] == "run.finished"
    assert "tool_call.compute_ratios.start" in actions
    assert "tool_call.compute_ratios.result" in actions

    # Chain integrity
    for i, ev in enumerate(sink.events):
        if i == 0:
            assert ev.prev_hash is None
        else:
            assert ev.prev_hash == sink.events[i - 1].hash
        assert ev.application_id == "app-x"
        assert ev.run_id  # populated
    assert verify_chain(sink.events) is True


def test_audit_chain_detects_tampering():
    sink = InMemorySink()
    with audit_run("app-y", sink=sink):
        emit("tool", "tool_call.compute_ratios.result", {"output": {"dti": 0.2}})

    # Tamper with a payload — chain should fail to verify.
    sink.events[1].payload = {"output": {"dti": 0.9}}
    assert verify_chain(sink.events) is False


def test_full_agent_run_emits_expected_events():
    sink = InMemorySink()
    app_ = _app()
    graph = build_graph()
    with audit_run(app_.application_id, sink=sink):
        graph.invoke(
            {
                "application": app_,
                "ctx": ToolContext(app_),
                "messages": [{"role": "user", "content": "go"}],
                "tool_calls": [],
                "tokens_in": 0, "tokens_out": 0, "turns": 0, "revisions": 0,
                "client": _scripted_client([_GOOD_MEMO_INPUT]),
            },
            config={"recursion_limit": 30},
        )

    actions = [e.action for e in sink.events]
    # Expect at least one LLM call, all three tool calls (start+result), draft,
    # critic verdict, finalize.
    assert actions.count("llm_call.start") >= 4
    assert actions.count("llm_call.result") >= 4
    for tool in ("compute_ratios", "lookup_policy", "score_pd"):
        assert f"tool_call.{tool}.start" in actions
        assert f"tool_call.{tool}.result" in actions
    assert "memo.draft_submitted" in actions
    assert "critic.verdict" in actions
    assert "memo.finalized" in actions
    assert verify_chain(sink.events) is True


def test_critic_revision_path_is_audited():
    sink = InMemorySink()
    app_ = _app()
    graph = build_graph()
    with audit_run(app_.application_id, sink=sink):
        graph.invoke(
            {
                "application": app_,
                "ctx": ToolContext(app_),
                "messages": [{"role": "user", "content": "go"}],
                "tool_calls": [],
                "tokens_in": 0, "tokens_out": 0, "turns": 0, "revisions": 0,
                "client": _scripted_client([_BAD_MEMO_INPUT, _GOOD_MEMO_INPUT]),
            },
            config={"recursion_limit": 30},
        )

    actions = [e.action for e in sink.events]
    # Two draft submissions + two critic verdicts (revise then pass).
    assert actions.count("memo.draft_submitted") == 2
    assert actions.count("critic.verdict") == 2
    verdicts = [e.payload["status"] for e in sink.events if e.action == "critic.verdict"]
    assert verdicts == ["revise", "pass"]
