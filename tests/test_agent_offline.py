"""Agent offline path tests — no Anthropic API key required."""
from __future__ import annotations

from app.agent.runner import run_agent
from app.schemas import BureauData, LoanApplication


def _app(**overrides) -> LoanApplication:
    base = dict(
        application_id="a-2", applicant_id="u-2",
        age=40, state="TX", employment_status="employed",
        years_employed=10.0, annual_income=90000.0, monthly_housing_cost=2000.0,
        product="personal_loan", requested_amount=20000.0, term_months=48,
        purpose="home_improvement",
        bureau=BureauData(
            credit_score=760, revolving_utilization=0.2, open_trades=10,
            delinquencies_24m=0, inquiries_6m=1, bankruptcies_7y=0,
            oldest_trade_months=180,
        ),
    )
    base.update(overrides)
    return LoanApplication(**base)


def test_strong_profile_is_approved():
    memo, trace = run_agent(_app(), mode="offline")
    assert memo.decision == "approve"
    assert memo.risk.pd < 0.3
    assert len(trace.tool_calls) == 3


def test_low_score_is_declined_with_codes():
    memo, _ = run_agent(
        _app(bureau=BureauData(
            credit_score=540, revolving_utilization=0.85, open_trades=8,
            delinquencies_24m=2, inquiries_6m=4, bankruptcies_7y=0,
            oldest_trade_months=60,
        )),
        mode="offline",
    )
    assert memo.decision == "decline"
    assert "AA-01" in memo.adverse_action_codes


def test_high_dti_is_declined():
    memo, _ = run_agent(
        _app(annual_income=24000.0, requested_amount=30000.0, monthly_housing_cost=1200.0),
        mode="offline",
    )
    assert memo.decision == "decline"
    assert "AA-06" in memo.adverse_action_codes


def test_memo_never_mentions_protected_attributes():
    memo, _ = run_agent(_app(), mode="offline")
    forbidden = ["race", "gender", "sex", "marital", "religion", "national origin"]
    blob = (memo.rationale + " " + " ".join(c.detail for c in memo.citations)).lower()
    for term in forbidden:
        assert term not in blob
