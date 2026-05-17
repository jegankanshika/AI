"""LangGraph live-path test using a fake LLM client.

Exercises the agent + tools nodes and the routing edges without hitting a
real model. Confirms tool dispatch, accumulated trace, and terminal submit_memo.
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


_GOOD_MEMO_INPUT = {
    "decision": "approve",
    "rationale": "Within tier; low PD.",
    "citations": [
        {"source": "policy:personal_loan", "detail": "tier table"},
        {"source": "tool:score_pd", "detail": "PD low"},
    ],
}

_BAD_MEMO_INPUT = {
    # missing tool citation -> critic should reject on first pass
    "decision": "approve",
    "rationale": "Within tier; low PD.",
    "citations": [{"source": "policy:personal_loan", "detail": "tier table"}],
}


def _scripted_client(submit_inputs: list[dict]):
    """Build a scripted fake client that walks the standard tool sequence then
    issues one `submit_memo` per entry in `submit_inputs`."""

    class _C:
        def __init__(self) -> None:
            self.calls = 0
            self.messages = self
            self._submits = list(submit_inputs)

        def create(self, **_kw):
            self.calls += 1
            if self.calls == 1:
                content = [_ToolBlock("compute_ratios", {}, "t1")]
            elif self.calls == 2:
                content = [_ToolBlock("lookup_policy", {"query": "personal loan tier"}, "t2")]
            elif self.calls == 3:
                content = [_ToolBlock("score_pd", {"dti": 0.2, "pti": 0.05}, "t3")]
            else:
                payload = self._submits.pop(0) if self._submits else _GOOD_MEMO_INPUT
                content = [_ToolBlock("submit_memo", payload, f"s{self.calls}")]
            return SimpleNamespace(content=content, stop_reason="tool_use", usage=_Usage(50, 20))

    return _C()


def _invoke(client) -> dict:
    app_ = _app()
    graph = build_graph()
    return graph.invoke(
        {
            "application": app_,
            "ctx": ToolContext(app_),
            "messages": [{"role": "user", "content": "go"}],
            "tool_calls": [],
            "tokens_in": 0,
            "tokens_out": 0,
            "turns": 0,
            "revisions": 0,
            "client": client,
        },
        config={"recursion_limit": 30},
    )


def test_graph_passes_critic_on_clean_memo():
    state = _invoke(_scripted_client([_GOOD_MEMO_INPUT]))
    memo = state["final_memo"]
    assert memo is not None and memo.decision == "approve"
    names = [c["name"] for c in state["tool_calls"]]
    assert names == ["compute_ratios", "lookup_policy", "score_pd", "submit_memo"]
    assert state.get("revisions", 0) == 0
    assert state.get("critic_issues") == []


def test_graph_critic_triggers_revision_then_accepts():
    # First submit is missing tool citation (revise); second is clean (pass).
    state = _invoke(_scripted_client([_BAD_MEMO_INPUT, _GOOD_MEMO_INPUT]))
    memo = state["final_memo"]
    assert memo is not None and memo.decision == "approve"
    names = [c["name"] for c in state["tool_calls"]]
    assert names.count("submit_memo") == 2
    assert state["revisions"] == 1
    # final memo is the clean one
    sources = {c.source.split(":", 1)[0] for c in memo.citations}
    assert {"policy", "tool"}.issubset(sources)


def test_graph_critic_accepts_after_max_revisions():
    # Both submits are bad; critic still rejects, but we run out of revision
    # budget and the draft is accepted with critic_issues recorded.
    state = _invoke(_scripted_client([_BAD_MEMO_INPUT, _BAD_MEMO_INPUT]))
    memo = state["final_memo"]
    assert memo is not None
    assert state["revisions"] == 1
    assert any("tool-output citation" in i for i in state["critic_issues"])
