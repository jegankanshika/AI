"""LangGraph live-path test using a fake Anthropic client.

Exercises the agent + tools nodes and the routing edges without hitting the
real API. Confirms tool dispatch, accumulated trace, and terminal submit_memo.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.agent.graph import build_graph
from app.schemas import BureauData, LoanApplication
from app.tools.registry import ToolContext


def _app() -> LoanApplication:
    return LoanApplication(
        application_id="g-1", applicant_id="g-u-1",
        age=35, state="CA", employment_status="employed",
        years_employed=6.0, annual_income=80000.0, monthly_housing_cost=2000.0,
        product="personal_loan", requested_amount=15000.0, term_months=36,
        purpose="debt_consolidation",
        bureau=BureauData(
            credit_score=730, revolving_utilization=0.25, open_trades=8,
            delinquencies_24m=0, inquiries_6m=1, bankruptcies_7y=0,
            oldest_trade_months=140,
        ),
    )


class _Usage:
    def __init__(self, i: int, o: int) -> None:
        self.input_tokens = i
        self.output_tokens = o


class _ToolBlock:
    type = "tool_use"

    def __init__(self, name: str, input_: dict, id_: str) -> None:
        self.name = name
        self.input = input_
        self.id = id_


class _FakeClient:
    """Scripted Anthropic client. Each call returns the next planned response."""

    def __init__(self) -> None:
        self.calls = 0
        self.messages = self  # so client.messages.create works

    def create(self, **_kw):
        self.calls += 1
        if self.calls == 1:
            content = [_ToolBlock("compute_ratios", {}, "t1")]
            stop = "tool_use"
        elif self.calls == 2:
            content = [_ToolBlock("lookup_policy", {"query": "personal loan tier"}, "t2")]
            stop = "tool_use"
        elif self.calls == 3:
            content = [_ToolBlock("score_pd", {"dti": 0.2, "pti": 0.05}, "t3")]
            stop = "tool_use"
        else:
            content = [_ToolBlock(
                "submit_memo",
                {
                    "decision": "approve",
                    "rationale": "Within tier; low PD.",
                    "citations": [{"source": "policy:personal_loan", "detail": "tier table"}],
                },
                "t4",
            )]
            stop = "tool_use"
        return SimpleNamespace(content=content, stop_reason=stop, usage=_Usage(50, 20))


def test_graph_runs_full_tool_sequence_to_memo():
    app_ = _app()
    graph = build_graph()
    state = graph.invoke(
        {
            "application": app_,
            "ctx": ToolContext(app_),
            "messages": [{"role": "user", "content": "go"}],
            "tool_calls": [],
            "tokens_in": 0,
            "tokens_out": 0,
            "turns": 0,
            "client": _FakeClient(),
        },
        config={"recursion_limit": 25},
    )

    memo = state["final_memo"]
    assert memo is not None
    assert memo.decision == "approve"
    assert memo.ratios is not None and memo.risk is not None
    names = [c["name"] for c in state["tool_calls"]]
    assert names == ["compute_ratios", "lookup_policy", "score_pd", "submit_memo"]
    assert state["tokens_in"] > 0 and state["tokens_out"] > 0
