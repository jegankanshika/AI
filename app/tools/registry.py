"""Tool-use schemas + dispatcher for the agent.

Each entry is a JSON Schema the LLM sees, plus a Python handler that consumes
the validated input and returns a JSON-serializable result.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from app.audit import emit
from app.idp.extractor import extract as extract_document_impl
from app.policy.gates import evaluate_hard_gates
from app.schemas import LoanApplication
from app.tools.income import verify_income
from app.tools.policy import lookup_policy
from app.tools.ratios import compute_ratios
from app.tools.risk import score_pd

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "compute_ratios",
        "description": (
            "Compute DTI, PTI, and (for secured products) LTV for the application. "
            "Always call this before scoring or deciding."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "assumed_apr": {
                    "type": "number",
                    "description": "APR (e.g. 14.99) used to compute the payment. If unsure, omit.",
                },
                "collateral_value": {
                    "type": "number",
                    "description": "Collateral value for secured products. Required for LTV.",
                },
                "other_monthly_debt": {
                    "type": "number",
                    "description": "Other monthly debt obligations beyond housing.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "lookup_policy",
        "description": "Retrieve policy snippets relevant to a free-text query.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3},
            },
            "required": ["query"],
        },
    },
    {
        "name": "score_pd",
        "description": "Run the PD model on the application + computed ratios.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dti": {"type": "number"},
                "pti": {"type": "number"},
            },
            "required": ["dti", "pti"],
        },
    },
    {
        "name": "extract_document",
        "description": (
            "Extract structured fields from a document attached to the "
            "application (paystub, W-2, bank statement, photo ID). "
            "Returns fields + confidence + warnings. Use to verify income "
            "(annualized_income from a paystub) against the stated annual_income."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "id of an attached document"},
            },
            "required": ["doc_id"],
        },
    },
    {
        "name": "verify_income",
        "description": (
            "Cross-check the applicant's stated annual_income against any "
            "extracted paystub / W-2 / bank-statement payroll deposits. "
            "Returns per-source annualized estimates, the max gap, a "
            "material_gap flag (>= 10%), and a recommended_annual_income "
            "(median across sources). Call after extract_document on each "
            "attached income document."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "check_hard_gates",
        "description": (
            "Evaluate deterministic hard-decline rules (sanctions, age, "
            "bankruptcies, delinquency count, DTI/LTV caps). Returns "
            "`passed` and any `violations`. Call before submitting an "
            "approval to make sure you are not contradicting a hard gate."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "submit_memo",
        "description": (
            "Terminal action. Submit the final underwriting memo. "
            "Provide decision, rationale, and adverse-action codes if declining."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["approve", "decline", "refer_to_human"]},
                "rationale": {"type": "string"},
                "adverse_action_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                },
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string"},
                            "detail": {"type": "string"},
                        },
                        "required": ["source", "detail"],
                    },
                    "default": [],
                },
            },
            "required": ["decision", "rationale"],
        },
    },
]


class ToolContext:
    """Carries the validated application + accumulated tool results across the loop."""

    def __init__(self, application: LoanApplication):
        self.application = application
        self.ratios = None  # type: ignore[assignment]
        self.risk = None    # type: ignore[assignment]
        self.policy_hits: list[dict] = []
        self.gate_result = None  # type: ignore[assignment]
        self.extractions: dict[str, dict] = {}
        self.income_verification = None  # type: ignore[assignment]

    def dispatch(self, name: str, args: dict) -> dict:
        emit("tool", f"tool_call.{name}.start", {"input": args})
        try:
            if name == "compute_ratios":
                self.ratios = compute_ratios(self.application, **args)
                result = json.loads(self.ratios.model_dump_json())
            elif name == "lookup_policy":
                res = lookup_policy(args["query"], args.get("k", 3))
                result = json.loads(res.model_dump_json())
                self.policy_hits.extend(result["hits"])
            elif name == "score_pd":
                if self.ratios is None:
                    result = {"error": "call compute_ratios before score_pd"}
                else:
                    self.risk = score_pd(self.application, self.ratios)
                    result = json.loads(self.risk.model_dump_json())
            elif name == "check_hard_gates":
                self.gate_result = evaluate_hard_gates(self.application, self.ratios)
                result = json.loads(self.gate_result.model_dump_json())
            elif name == "extract_document":
                doc_id = args["doc_id"]
                ref = next((d for d in self.application.documents if d.doc_id == doc_id), None)
                if ref is None:
                    result = {"error": f"no document with doc_id={doc_id!r}"}
                else:
                    extraction = extract_document_impl(ref)
                    result = json.loads(extraction.model_dump_json())
                    self.extractions[doc_id] = result
            elif name == "verify_income":
                self.income_verification = verify_income(
                    self.application.annual_income, self.extractions,
                )
                result = json.loads(self.income_verification.model_dump_json())
            else:
                raise ValueError(f"unknown tool {name!r}")
        except Exception as e:
            emit("tool", f"tool_call.{name}.error", {"error": str(e)})
            raise
        emit("tool", f"tool_call.{name}.result", {"output": result})
        return result
