"""Hard-gate decision engine — mirrors `policies/hard_gates.rego`.

Two backends:

  * `python` (default) — deterministic in-process evaluator that re-implements
    the Rego rules. Always available.
  * `opa` — shell out to a real `opa eval` binary. Enabled by setting the
    `OPA_BIN` env var to the binary path; the policy file is loaded from
    `policies/hard_gates.rego`. Both backends must produce identical output
    for the test fixtures.

The engine reads `LoanApplication` + computed `Ratios` and returns a
`HardGateResult(passed, violations)`. Used by the LangGraph `adjudicate` node
after the critic to override any agent recommendation that violates a hard
gate. Also exposed to the agent as a tool so it can preempt obvious declines.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from app.schemas import LoanApplication, Ratios

REGO_PATH = Path(__file__).resolve().parents[2] / "policies" / "hard_gates.rego"

STATE_MIN_AGE = {"AL": 19, "NE": 19, "MS": 21}
DTI_CAPS = {"personal_loan": 0.50, "auto": 0.55, "mortgage": 0.50, "sm_business": 0.55}
LTV_CAPS = {"auto": 1.25, "mortgage": 1.05}


class GateViolation(BaseModel):
    code: str
    reason: str


class HardGateResult(BaseModel):
    passed: bool
    violations: list[GateViolation]
    backend: Literal["python", "opa"] = "python"


def _python_evaluate(app: LoanApplication, ratios: Ratios | None) -> HardGateResult:
    v: list[GateViolation] = []

    if app.sanctions_hit:
        v.append(GateViolation(code="AA-14", reason="OFAC / sanctions hit"))
    if app.fraud_flag:
        v.append(GateViolation(code="AA-14", reason="Active fraud flag"))

    min_age = STATE_MIN_AGE.get(app.state, 18)
    if app.age < min_age:
        v.append(GateViolation(
            code="AA-12",
            reason=f"Age {app.age} below state minimum {min_age} for {app.state}",
        ))

    if app.bureau.bankruptcies_7y >= 2:
        v.append(GateViolation(
            code="AA-09",
            reason="Two or more bankruptcies in last 7 years",
        ))

    if app.bureau.delinquencies_24m >= 3:
        v.append(GateViolation(
            code="AA-03",
            reason="Three or more delinquencies in last 24 months",
        ))

    if ratios is not None:
        cap = DTI_CAPS.get(app.product)
        if cap is not None and ratios.dti > cap:
            v.append(GateViolation(
                code="AA-06",
                reason=f"DTI {ratios.dti:.2f} exceeds hard cap {cap:.2f} for {app.product}",
            ))
        if ratios.ltv is not None:
            lcap = LTV_CAPS.get(app.product)
            if lcap is not None and ratios.ltv > lcap:
                v.append(GateViolation(
                    code="AA-10",
                    reason=f"LTV {ratios.ltv:.2f} exceeds hard cap {lcap:.2f} for {app.product}",
                ))

    return HardGateResult(passed=not v, violations=v, backend="python")


def _opa_evaluate(app: LoanApplication, ratios: Ratios | None) -> HardGateResult:
    """Shell out to a real `opa eval`. Used when OPA_BIN is set and points
    to an available binary. Falls back to the python evaluator if the call
    fails for any reason (the audit log captures the fallback)."""
    opa = os.environ.get("OPA_BIN") or shutil.which("opa")
    if not opa or not REGO_PATH.exists():
        return _python_evaluate(app, ratios)

    payload: dict[str, Any] = {
        "application": json.loads(app.model_dump_json()),
        "ratios": json.loads(ratios.model_dump_json()) if ratios else {},
    }
    cmd = [
        opa, "eval", "--format=json",
        "--data", str(REGO_PATH),
        "--stdin-input",
        "data.credit_copilot.gates.result",
    ]
    try:
        proc = subprocess.run(
            cmd, input=json.dumps(payload), capture_output=True,
            text=True, check=True, timeout=5,
        )
        out = json.loads(proc.stdout)
        value = out["result"][0]["expressions"][0]["value"]
        return HardGateResult(
            passed=bool(value["passed"]),
            violations=[GateViolation(**v) for v in value["violations"]],
            backend="opa",
        )
    except Exception:
        return _python_evaluate(app, ratios)


def evaluate_hard_gates(app: LoanApplication, ratios: Ratios | None) -> HardGateResult:
    if os.environ.get("OPA_BIN"):
        return _opa_evaluate(app, ratios)
    return _python_evaluate(app, ratios)
