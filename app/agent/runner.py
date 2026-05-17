"""Agent runner — LangGraph-orchestrated live path plus a deterministic offline mode.

`run_agent(application, mode="live")` runs the LangGraph state machine in
`app.agent.graph`. `mode="offline"` runs the same tools in a fixed order and
produces a memo without an LLM. Offline mode exists so tests and CI don't
need an API key.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Literal

from app.schemas import (
    LoanApplication, MemoCitation, Ratios, RiskScore, UnderwritingMemo,
)
from app.tools.registry import ToolContext

logger = logging.getLogger(__name__)


@dataclass
class AgentTrace:
    tool_calls: list[dict] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    revisions: int = 0
    critic_issues: list[str] = field(default_factory=list)
    extractions: dict[str, dict] = field(default_factory=dict)
    income_verification: dict | None = None


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
    elif ctx.income_verification is not None and ctx.income_verification.material_gap:
        decision = "refer_to_human"
        rationale_bits.append(
            f"Material income gap (max |Δ| {ctx.income_verification.max_abs_gap_pct:.1%}); "
            f"refer for manual review."
        )
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
    from app.agent.critic import review_memo
    from app.audit import audit_run, emit
    from app.policy.gates import evaluate_hard_gates

    t0 = time.perf_counter()
    with audit_run(application.application_id):
        ctx = ToolContext(application)
        # Extract any attached documents and reconcile income before the
        # usual deterministic pipeline so the UI can display them.
        extraction_calls: list[dict] = []
        for doc in application.documents:
            ctx.dispatch("extract_document", {"doc_id": doc.doc_id})
            extraction_calls.append({"name": "extract_document",
                                     "input": {"doc_id": doc.doc_id}})
        if application.documents:
            ctx.dispatch("verify_income", {})
            extraction_calls.append({"name": "verify_income", "input": {}})

        ctx.dispatch("compute_ratios", {})
        ctx.dispatch("lookup_policy", {"query": f"{application.product} eligibility"})
        ctx.dispatch("score_pd", {"dti": ctx.ratios.dti, "pti": ctx.ratios.pti})  # type: ignore[union-attr]
        memo = _offline_decision(ctx)
        verdict = review_memo(memo, application)
        emit("critic", "critic.verdict", {"status": verdict.status, "issues": verdict.issues})

        gates = evaluate_hard_gates(application, ctx.ratios)
        emit("system", "hard_gates.evaluated", {
            "backend": gates.backend, "passed": gates.passed,
            "violations": [v.model_dump() for v in gates.violations],
        })
        if not gates.passed:
            forced_codes = [v.code for v in gates.violations]
            merged_codes = list(dict.fromkeys(memo.adverse_action_codes + forced_codes))
            gate_lines = "\n".join(f"- [{v.code}] {v.reason}" for v in gates.violations)
            memo = memo.model_copy(update={
                "decision": "decline",
                "adverse_action_codes": merged_codes,
                "rationale": (
                    f"Hard-gate override: decision forced to DECLINE.\n{gate_lines}\n\n"
                    f"Original rationale: {memo.rationale}"
                ),
                "citations": memo.citations + [
                    MemoCitation(source="engine:hard_gates", detail=v.reason)
                    for v in gates.violations
                ],
            })
            emit("system", "memo.overridden_by_gates", {
                "violations": [v.model_dump() for v in gates.violations],
            })
        emit("system", "memo.finalized", {"decision": memo.decision})
    base_calls = extraction_calls + [
        {"name": "compute_ratios"}, {"name": "lookup_policy"}, {"name": "score_pd"},
    ]
    trace = AgentTrace(
        tool_calls=base_calls,
        latency_ms=int((time.perf_counter() - t0) * 1000),
        critic_issues=verdict.issues,
        extractions=dict(ctx.extractions),
        income_verification=(
            ctx.income_verification.model_dump() if ctx.income_verification else None
        ),
    )
    return memo, trace


def run_live(application: LoanApplication) -> tuple[UnderwritingMemo, AgentTrace]:
    """Live mode runs the LangGraph state machine defined in app.agent.graph."""
    from app.agent.graph import run_live_graph

    memo, trace_dict = run_live_graph(application)
    return memo, AgentTrace(
        tool_calls=trace_dict["tool_calls"],
        tokens_in=trace_dict["tokens_in"],
        tokens_out=trace_dict["tokens_out"],
        latency_ms=trace_dict["latency_ms"],
        revisions=trace_dict.get("revisions", 0),
        critic_issues=trace_dict.get("critic_issues", []),
        extractions=trace_dict.get("extractions", {}),
        income_verification=trace_dict.get("income_verification"),
    )


def run_agent(application: LoanApplication,
              mode: Literal["live", "offline", "auto"] = "auto"
              ) -> tuple[UnderwritingMemo, AgentTrace]:
    if mode == "auto":
        from app.llm import have_credentials
        mode = "live" if have_credentials() else "offline"
    if mode == "offline":
        return run_offline(application)
    return run_live(application)
