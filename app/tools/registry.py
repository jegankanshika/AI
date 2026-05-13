"""Anthropic tool-use schemas + dispatcher for the agent.

Each entry is a JSON Schema the LLM sees, plus a Python handler that consumes
the validated input and returns a JSON-serializable result.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from app.schemas import LoanApplication
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

    def dispatch(self, name: str, args: dict) -> dict:
        if name == "compute_ratios":
            self.ratios = compute_ratios(self.application, **args)
            return json.loads(self.ratios.model_dump_json())
        if name == "lookup_policy":
            res = lookup_policy(args["query"], args.get("k", 3))
            payload = json.loads(res.model_dump_json())
            self.policy_hits.extend(payload["hits"])
            return payload
        if name == "score_pd":
            if self.ratios is None:
                return {"error": "call compute_ratios before score_pd"}
            self.risk = score_pd(self.application, self.ratios)
            return json.loads(self.risk.model_dump_json())
        raise ValueError(f"unknown tool {name!r}")
