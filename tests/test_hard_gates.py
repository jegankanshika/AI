"""Hard-gate engine tests + override-via-graph tests."""
from __future__ import annotations

from app.agent.graph import build_graph
from app.audit import InMemorySink, audit_run
from app.policy.gates import evaluate_hard_gates
from app.schemas import BureauData, LoanApplication, Ratios
from app.tools.registry import ToolContext
from tests.test_agent_graph import _GOOD_MEMO_INPUT, _scripted_client


def _app(**overrides) -> LoanApplication:
    base = dict(
        application_id="g-1", applicant_id="g-u-1",
        age=35, state="CA", employment_status="employed",
        years_employed=5.0, annual_income=80000.0, monthly_housing_cost=2000.0,
        product="personal_loan", requested_amount=15000.0, term_months=36,
        purpose="debt_consolidation",
        bureau=BureauData(
            credit_score=720, revolving_utilization=0.3, open_trades=8,
            delinquencies_24m=0, inquiries_6m=1, bankruptcies_7y=0,
            oldest_trade_months=120,
        ),
    )
    base.update(overrides)
    return LoanApplication(**base)


def _ratios(dti: float = 0.2, ltv: float | None = None) -> Ratios:
    return Ratios(monthly_payment=300.0, pti=0.05, dti=dti, ltv=ltv)


def test_clean_application_passes():
    result = evaluate_hard_gates(_app(), _ratios())
    assert result.passed and result.violations == []


def test_sanctions_hit_fails_AA14():
    result = evaluate_hard_gates(_app(sanctions_hit=True), _ratios())
    assert not result.passed
    assert any(v.code == "AA-14" for v in result.violations)


def test_underage_in_AL_fails_AA12():
    result = evaluate_hard_gates(_app(state="AL", age=18), _ratios())
    assert not result.passed
    assert any(v.code == "AA-12" and "AL" in v.reason for v in result.violations)


def test_two_bankruptcies_fails_AA09():
    bureau = _app().bureau.model_copy(update={"bankruptcies_7y": 2})
    result = evaluate_hard_gates(_app(bureau=bureau), _ratios())
    assert not result.passed
    assert any(v.code == "AA-09" for v in result.violations)


def test_dti_above_cap_fails_AA06():
    result = evaluate_hard_gates(_app(), _ratios(dti=0.62))
    assert not result.passed
    assert any(v.code == "AA-06" for v in result.violations)


def test_auto_ltv_above_cap_fails_AA10():
    result = evaluate_hard_gates(_app(product="auto"), _ratios(ltv=1.40))
    assert not result.passed
    assert any(v.code == "AA-10" for v in result.violations)


def test_graph_overrides_agent_approval_when_gate_fires():
    """Agent + critic agree to approve, but the applicant has a sanctions
    hit. The adjudication node must force the final decision to decline."""
    app_ = _app(sanctions_hit=True)
    sink = InMemorySink()
    graph = build_graph()
    with audit_run(app_.application_id, sink=sink):
        state = graph.invoke(
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

    memo = state["final_memo"]
    assert memo.decision == "decline"
    assert "AA-14" in memo.adverse_action_codes
    actions = [e.action for e in sink.events]
    assert "hard_gates.evaluated" in actions
    assert "memo.overridden_by_gates" in actions


def test_graph_passes_through_when_gates_clear():
    app_ = _app()  # clean
    graph = build_graph()
    sink = InMemorySink()
    with audit_run(app_.application_id, sink=sink):
        state = graph.invoke(
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

    memo = state["final_memo"]
    assert memo.decision == "approve"
    actions = [e.action for e in sink.events]
    assert "hard_gates.evaluated" in actions
    assert "memo.overridden_by_gates" not in actions
