"""LangGraph orchestration for the live agent path.

State machine:

    START -> agent ─tool_use─▶ tools ─▶ agent ...
                  └─end──▶ END

`agent` node calls Claude with the running message list and the typed tool
schemas. `tools` node executes the requested tools through the ToolContext
dispatcher, appends results, and loops back. The terminal `submit_memo` tool
is short-circuited so we never re-enter `agent` after submission.
"""
from __future__ import annotations

import json
import time
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.critic import review_memo
from app.agent.prompts import SYSTEM_PROMPT
from app.schemas import LoanApplication, MemoCitation, UnderwritingMemo
from app.tools.registry import TOOL_SCHEMAS, ToolContext

MODEL = "claude-opus-4-7"
MAX_TURNS = 8
MAX_REVISIONS = 1


def _append(left: list, right: list) -> list:
    return (left or []) + (right or [])


class AgentState(TypedDict, total=False):
    application: LoanApplication
    ctx: ToolContext
    messages: Annotated[list[dict], _append]
    tool_calls: Annotated[list[dict], _append]
    tokens_in: int
    tokens_out: int
    turns: int
    draft_memo: UnderwritingMemo | None
    final_memo: UnderwritingMemo | None
    revisions: int
    critic_issues: Annotated[list[str], _append]
    stop_reason: str
    client: Any  # anthropic.Anthropic — typed loosely to keep the import lazy


def _agent_node(state: AgentState) -> dict:
    client = state["client"]
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        tools=TOOL_SCHEMAS,
        messages=state["messages"],
    )
    delta_msg = [{"role": "assistant", "content": resp.content}]
    return {
        "messages": delta_msg,
        "tokens_in": state.get("tokens_in", 0) + resp.usage.input_tokens,
        "tokens_out": state.get("tokens_out", 0) + resp.usage.output_tokens,
        "turns": state.get("turns", 0) + 1,
        "stop_reason": resp.stop_reason,
    }


def _tools_node(state: AgentState) -> dict:
    ctx: ToolContext = state["ctx"]
    last = state["messages"][-1]["content"]
    tool_results: list[dict] = []
    tool_calls_delta: list[dict] = []
    draft_memo: UnderwritingMemo | None = None

    for block in last:
        if getattr(block, "type", None) != "tool_use":
            continue
        tool_calls_delta.append({"name": block.name, "input": block.input})

        if block.name == "submit_memo":
            draft_memo = UnderwritingMemo(
                application_id=state["application"].application_id,
                decision=block.input["decision"],
                rationale=block.input["rationale"],
                ratios=ctx.ratios,   # type: ignore[arg-type]
                risk=ctx.risk,       # type: ignore[arg-type]
                adverse_action_codes=block.input.get("adverse_action_codes", []),
                citations=[MemoCitation(**c) for c in block.input.get("citations", [])],
            )
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps({"status": "submitted, pending critic"}),
            })
            continue

        try:
            result = ctx.dispatch(block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })
        except Exception as e:
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps({"error": str(e)}),
                "is_error": True,
            })

    return {
        "messages": [{"role": "user", "content": tool_results}],
        "tool_calls": tool_calls_delta,
        "draft_memo": draft_memo,
    }


def _critic_node(state: AgentState) -> dict:
    draft = state["draft_memo"]
    assert draft is not None
    verdict = review_memo(draft, state["application"], state.get("client"))

    if verdict.status == "pass":
        return {"final_memo": draft, "critic_issues": []}

    revisions = state.get("revisions", 0)
    # If we're out of revision budget, accept the draft and log the issues —
    # never block a decision indefinitely; downstream review will catch it.
    if revisions >= MAX_REVISIONS:
        return {"final_memo": draft, "critic_issues": verdict.issues}

    feedback = (
        "The critic rejected the draft memo. Address these issues and call "
        "`submit_memo` again:\n- " + "\n- ".join(verdict.issues)
    )
    if verdict.suggested_fix:
        feedback += f"\n\nSuggested fix: {verdict.suggested_fix}"
    return {
        "messages": [{"role": "user", "content": feedback}],
        "critic_issues": verdict.issues,
        "revisions": revisions + 1,
        "draft_memo": None,
    }


def _route_after_agent(state: AgentState) -> str:
    if state.get("turns", 0) >= MAX_TURNS:
        return END
    if state.get("stop_reason") != "tool_use":
        return END
    return "tools"


def _route_after_tools(state: AgentState) -> str:
    if state.get("draft_memo") is not None:
        return "critic"
    return "agent"


def _route_after_critic(state: AgentState) -> str:
    if state.get("final_memo") is not None:
        return END
    return "agent"


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("agent", _agent_node)
    g.add_node("tools", _tools_node)
    g.add_node("critic", _critic_node)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", _route_after_agent, {"tools": "tools", END: END})
    g.add_conditional_edges("tools", _route_after_tools,
                            {"agent": "agent", "critic": "critic"})
    g.add_conditional_edges("critic", _route_after_critic,
                            {"agent": "agent", END: END})
    return g.compile()


def run_live_graph(application: LoanApplication) -> tuple[UnderwritingMemo, dict]:
    import anthropic

    graph = build_graph()
    init: AgentState = {
        "application": application,
        "ctx": ToolContext(application),
        "messages": [{
            "role": "user",
            "content": (
                "Underwrite this application.\n\n"
                f"```json\n{application.model_dump_json(indent=2)}\n```"
            ),
        }],
        "tool_calls": [],
        "tokens_in": 0,
        "tokens_out": 0,
        "turns": 0,
        "client": anthropic.Anthropic(),
    }
    t0 = time.perf_counter()
    final: AgentState = graph.invoke(init, config={"recursion_limit": 2 * MAX_TURNS + 4})
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    if final.get("final_memo") is None:
        raise RuntimeError("agent terminated without submitting a memo")
    trace = {
        "tool_calls": final.get("tool_calls", []),
        "tokens_in": final.get("tokens_in", 0),
        "tokens_out": final.get("tokens_out", 0),
        "latency_ms": elapsed_ms,
        "turns": final.get("turns", 0),
        "revisions": final.get("revisions", 0),
        "critic_issues": final.get("critic_issues", []),
    }
    return final["final_memo"], trace  # type: ignore[return-value]
