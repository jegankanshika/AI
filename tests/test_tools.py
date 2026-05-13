"""Unit tests for the deterministic tools."""
from __future__ import annotations

from app.schemas import BureauData, LoanApplication
from app.tools.policy import lookup_policy
from app.tools.ratios import compute_ratios
from app.tools.risk import score_pd


def _app(**overrides) -> LoanApplication:
    base = dict(
        application_id="a-1", applicant_id="u-1",
        age=35, state="CA", employment_status="employed",
        years_employed=5.0, annual_income=72000.0, monthly_housing_cost=1800.0,
        product="personal_loan", requested_amount=15000.0, term_months=36,
        purpose="debt_consolidation",
        bureau=BureauData(
            credit_score=720, revolving_utilization=0.3, open_trades=8,
            delinquencies_24m=0, inquiries_6m=1, bankruptcies_7y=0,
            oldest_trade_months=120,
        ),
    )
    base.update(overrides)
    return LoanApplication(**base)


def test_compute_ratios_personal_loan_no_ltv():
    r = compute_ratios(_app())
    assert r.monthly_payment > 0
    assert 0 < r.pti < 0.3
    assert r.ltv is None


def test_compute_ratios_auto_has_ltv_when_collateral_given():
    r = compute_ratios(
        _app(product="auto", requested_amount=25000, term_months=60),
        collateral_value=30000.0,
    )
    assert r.ltv is not None
    assert 0.8 < r.ltv < 0.9


def test_score_pd_monotonic_in_credit_score():
    a_low = _app(bureau=BureauData(
        credit_score=560, revolving_utilization=0.3, open_trades=8,
        delinquencies_24m=0, inquiries_6m=1, bankruptcies_7y=0,
        oldest_trade_months=120,
    ))
    a_high = _app()
    r_low = score_pd(a_low, compute_ratios(a_low))
    r_high = score_pd(a_high, compute_ratios(a_high))
    assert r_low.pd > r_high.pd


def test_policy_lookup_finds_tier_doc():
    res = lookup_policy("personal loan tier APR")
    ids = [h.policy_id for h in res.hits]
    assert "personal_loan" in ids
    assert res.hits[0].score > 0
