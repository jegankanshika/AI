"""Agent runner — Anthropic tool-use loop plus a deterministic offline mode.

`run_agent(application, mode="live")` calls Claude; `mode="offline"` runs the
same tools in a fixed order and produces a memo without an LLM. Offline mode
exists so tests and CI don't need an API key.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Literal

from app.agent.prompts import SYSTEM_PROMPT
from app.schemas import (
    LoanApplication, MemoCitation, Ratios, RiskScore, UnderwritingMemo,
)
from app.tools.registry import TOOL_SCHEMAS, ToolContext

logger = logging.getLogger(__name__)

MODEL = "claude-opus-4-7"
MAX_TURNS = 8


@dataclass
class AgentTrace:
    tool_calls: list[dict] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0


def _adverse_codes(app: LoanApplication, ratios: Ratios, risk: RiskScore) -> list[str]:
    codes: list[str] = []
    if app.bureau.credit_score < 580:
        codes.append("AA-01")
    if app.bureau.delinquencies_24m >= 1:
        codes.append("AA-03")
    if app.bureau.inquiries_6m >= 6:
        codes.append("AA-04")
    if app.bureau.revolving_utilization > 0.7:
        codes.append("AA-05")
    if ratios.dti > 0.45:
        codes.append("AA-06")
    if app.bureau.bankruptcies_7y >= 1:
        codes.append("AA-09")
    return codes


def _offline_decision(ctx: ToolContext) -> UnderwritingMemo:
    """Rule-based decision matching policy snippets — used in tests/CI."""
    from app.tools.policy import lookup_policy
    from app.tools.ratios import compute_ratios
    from app.tools.risk import score_pd

    app = ctx.application
    ratios = ctx.ratios or compute_ratios(app)
    risk = ctx.risk or score_pd(app, ratios)
    _ = lookup_policy(f"{app.product} eligibility tier")  # populate hits

    decision = "approve"
    rationale_bits = []
    if app.bureau.credit_score < 580:
        decision = "decline"
        rationale_bits.append(f"Credit score {app.bureau.credit_score} below PL-001 minimum 580.")
    elif ratios.dti > 0.45:
        decision = "decline"
        rationale_bits.append(f"DTI {ratios.dti:.2f} exceeds PL-001 maximum 0.45.")
    elif risk.pd > 0.5:
        decision = "refer_to_human"
        rationale_bits.append(f"PD {risk.pd:.2f} is elevated; refer for manual review.")
    else:
        rationale_bits.append(
            f"Within tier (CS={app.bureau.credit_score}, DTI={ratios.dti:.2f}, PD={risk.pd:.2f})."
        )

    codes = _adverse_codes(app, ratios, risk) if decision == "decline" else []
    citations = [
        MemoCitation(source="policy:personal_loan", detail="Tier table + hard declines"),
        MemoCitation(source="tool:compute_ratios", detail=f"DTI={ratios.dti}, PTI={ratios.pti}"),
        MemoCitation(source=f"tool:score_pd@{risk.model_version}", detail=f"PD={risk.pd}"),
    ]
    return UnderwritingMemo(
        application_id=app.application_id,
        decision=decision,  # type: ignore[arg-type]
        rationale=" ".join(rationale_bits),
        ratios=ratios,
        risk=risk,
        adverse_action_codes=codes,
        citations=citations,
    )


def run_offline(application: LoanApplication) -> tuple[UnderwritingMemo, AgentTrace]:
    t0 = time.perf_counter()
    ctx = ToolContext(application)
    ctx.dispatch("compute_ratios", {})
    ctx.dispatch("lookup_policy", {"query": f"{application.product} eligibility"})
    ctx.dispatch("score_pd", {"dti": ctx.ratios.dti, "pti": ctx.ratios.pti})  # type: ignore[union-attr]
    trace = AgentTrace(
        tool_calls=[{"name": "compute_ratios"}, {"name": "lookup_policy"}, {"name": "score_pd"}],
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )
    return _offline_decision(ctx), trace


def run_live(application: LoanApplication) -> tuple[UnderwritingMemo, AgentTrace]:
    import anthropic  # imported lazily so offline path doesn't require the SDK at import time

    client = anthropic.Anthropic()
    ctx = ToolContext(application)
    trace = AgentTrace()
    t0 = time.perf_counter()

    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                "Underwrite this application.\n\n"
                f"```json\n{application.model_dump_json(indent=2)}\n```"
            ),
        }
    ]

    final_memo: UnderwritingMemo | None = None
    for _ in range(MAX_TURNS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,  # type: ignore[arg-type]
            messages=messages,
        )
        trace.tokens_in += resp.usage.input_tokens
        trace.tokens_out += resp.usage.output_tokens
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            break

        tool_results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            trace.tool_calls.append({"name": block.name, "input": block.input})
            if block.name == "submit_memo":
                final_memo = UnderwritingMemo(
                    application_id=application.application_id,
                    decision=block.input["decision"],
                    rationale=block.input["rationale"],
                    ratios=ctx.ratios,             # type: ignore[arg-type]
                    risk=ctx.risk,                 # type: ignore[arg-type]
                    adverse_action_codes=block.input.get("adverse_action_codes", []),
                    citations=[MemoCitation(**c) for c in block.input.get("citations", [])],
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps({"status": "submitted"}),
                })
            else:
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
        messages.append({"role": "user", "content": tool_results})

        if final_memo is not None:
            break

    trace.latency_ms = int((time.perf_counter() - t0) * 1000)
    if final_memo is None:
        raise RuntimeError("agent terminated without submitting a memo")
    return final_memo, trace


def run_agent(application: LoanApplication,
              mode: Literal["live", "offline", "auto"] = "auto"
              ) -> tuple[UnderwritingMemo, AgentTrace]:
    if mode == "auto":
        mode = "live" if os.environ.get("ANTHROPIC_API_KEY") else "offline"
    if mode == "offline":
        return run_offline(application)
    return run_live(application)
