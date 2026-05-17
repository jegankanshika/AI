"""Critic — a small Haiku pass that reviews the draft memo before submit.

Checks:
  * decision is consistent with the computed ratios / PD / hard-decline rules,
  * declines include at least one AA-* code,
  * citations cover policy + tool outputs,
  * no protected attributes appear in the rationale.

Returns a verdict: `pass` -> promote draft to final; `revise` -> bounce back
to the agent with a structured critique. Offline mode runs a deterministic
rule-based critic so tests run without an API key.
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from app.llm import critic_model_name, have_credentials
from app.schemas import LoanApplication, UnderwritingMemo

PROTECTED_TERMS = (
    "race", "ethnic", "gender", " sex ", "marital", "religion",
    "national origin", "public assistance",
)


class CriticVerdict(BaseModel):
    status: Literal["pass", "revise"]
    issues: list[str] = Field(default_factory=list)
    suggested_fix: str | None = None


CRITIC_SYSTEM = """You are an underwriting policy reviewer. Given a draft memo and the supporting
application + tool outputs, return STRICT JSON:

{"status": "pass" | "revise",
 "issues": ["short bullet", ...],
 "suggested_fix": "one sentence" | null}

Reject (status="revise") if any of the following is true:
  - decision is inconsistent with the cited policy or risk score,
  - decision is "decline" but no AA-* adverse action codes are listed,
  - citations are missing or do not reference both a policy and a tool output,
  - rationale references any protected basis (race, gender, marital status,
    national origin, religion, public assistance).

Otherwise return status="pass" with issues=[].
"""


def _offline_critic(memo: UnderwritingMemo) -> CriticVerdict:
    issues: list[str] = []

    if memo.decision == "decline" and not memo.adverse_action_codes:
        issues.append("decline missing adverse-action codes")

    sources = {c.source.split(":", 1)[0] for c in memo.citations}
    if memo.decision != "refer_to_human":
        if "policy" not in sources:
            issues.append("missing policy citation")
        if "tool" not in sources:
            issues.append("missing tool-output citation")

    blob = memo.rationale.lower()
    for term in PROTECTED_TERMS:
        if term.strip() in blob:
            issues.append(f"rationale references protected attribute: {term.strip()!r}")

    # consistency: declines should align with hard rules or elevated PD
    if memo.decision == "approve":
        if memo.ratios.dti > 0.45:
            issues.append("approved despite DTI > 0.45")
        if memo.risk.pd > 0.5:
            issues.append("approved despite PD > 0.5")

    status: Literal["pass", "revise"] = "pass" if not issues else "revise"
    fix = None
    if issues:
        fix = "Address the listed issues and resubmit a corrected memo."
    return CriticVerdict(status=status, issues=issues, suggested_fix=fix)


def _live_critic(memo: UnderwritingMemo,
                 application: LoanApplication,
                 client) -> CriticVerdict:
    payload = {
        "application": json.loads(application.model_dump_json()),
        "draft_memo": json.loads(memo.model_dump_json()),
    }
    resp = client.messages.create(
        model=critic_model_name(),
        max_tokens=400,
        system=CRITIC_SYSTEM,
        messages=[{"role": "user", "content": json.dumps(payload)}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    # Be liberal in what we accept: extract the first JSON object.
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return CriticVerdict(status="pass")  # don't block on critic parse failure
    try:
        data = json.loads(text[start: end + 1])
        return CriticVerdict.model_validate(data)
    except Exception:
        return CriticVerdict(status="pass")


def review_memo(memo: UnderwritingMemo,
                application: LoanApplication,
                client=None) -> CriticVerdict:
    """Always runs the deterministic offline checks; additionally calls Haiku
    in live mode and merges its issues."""
    verdict = _offline_critic(memo)

    if client is None or not have_credentials():
        return verdict

    live = _live_critic(memo, application, client)
    merged_issues = list(dict.fromkeys(verdict.issues + live.issues))
    status: Literal["pass", "revise"] = "pass" if not merged_issues else "revise"
    return CriticVerdict(
        status=status,
        issues=merged_issues,
        suggested_fix=live.suggested_fix or verdict.suggested_fix,
    )
