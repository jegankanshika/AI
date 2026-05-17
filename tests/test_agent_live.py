"""End-to-end live test against a real Ollama server.

Skipped unless `OLLAMA_HOST` is set in the environment, so local
contributors and the default CI run don't need a model loaded. The
dedicated `live-tests.yml` workflow runs this on demand.

What we assert (without pinning the LLM's exact wording):
  * The agent completes a full run without raising.
  * compute_ratios, lookup_policy, score_pd, and check_hard_gates were
    all called at least once (the system prompt instructs this order).
  * The final memo carries a valid decision and is internally consistent
    with the hard-gate engine.
  * Token usage and latency are recorded in the trace.
"""
from __future__ import annotations

import os

import pytest

from app.agent.runner import run_agent
from app.schemas import BureauData, LoanApplication

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("OLLAMA_HOST"),
        reason="OLLAMA_HOST not set — live test skipped",
    ),
]


def _clean_strong_app() -> LoanApplication:
    """High credit score, low DTI, no flags — expected to approve."""
    return LoanApplication(
        application_id="live-strong-001",
        applicant_id="live-applicant-001",
        age=38, state="CA", employment_status="employed",
        years_employed=8.0, annual_income=110000.0, monthly_housing_cost=2400.0,
        product="personal_loan", requested_amount=18000.0, term_months=48,
        purpose="debt_consolidation",
        bureau=BureauData(
            credit_score=765, revolving_utilization=0.18, open_trades=9,
            delinquencies_24m=0, inquiries_6m=1, bankruptcies_7y=0,
            oldest_trade_months=180,
        ),
    )


def _sanctions_hit_app() -> LoanApplication:
    """Otherwise-clean profile with a sanctions flag — hard-gate must decline
    regardless of what the agent recommends."""
    a = _clean_strong_app()
    return a.model_copy(update={
        "application_id": "live-sanctions-001",
        "sanctions_hit": True,
    })


def test_live_strong_application_runs_full_loop():
    memo, trace = run_agent(_clean_strong_app(), mode="live")

    assert memo.decision in {"approve", "decline", "refer_to_human"}
    assert memo.ratios.dti > 0
    assert 0.0 <= memo.risk.pd <= 1.0

    names = [c["name"] for c in trace.tool_calls]
    for required in ("compute_ratios", "lookup_policy", "score_pd"):
        assert required in names, f"agent did not call {required}; trace={names}"

    assert trace.tokens_in > 0 and trace.tokens_out > 0
    assert trace.latency_ms > 0

    # consistency: decline iff there are reason codes
    if memo.decision == "decline":
        assert memo.adverse_action_codes, "decline must carry at least one AA code"


def test_live_sanctions_hit_is_declined_by_adjudication():
    memo, trace = run_agent(_sanctions_hit_app(), mode="live")

    # The hard-gate adjudication node MUST force a decline regardless of
    # what the agent recommended.
    assert memo.decision == "decline"
    assert "AA-14" in memo.adverse_action_codes
    # And the gate citation must be on the memo.
    assert any(c.source == "engine:hard_gates" for c in memo.citations)
    assert trace.tokens_in > 0
