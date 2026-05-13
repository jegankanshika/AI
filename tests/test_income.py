"""Income cross-check tool tests."""
from __future__ import annotations

from pathlib import Path

from app.idp.schemas import DocumentRef
from app.schemas import BureauData, LoanApplication
from app.tools.income import MATERIAL_GAP_PCT, verify_income
from app.tools.registry import ToolContext


def _ex(doc_type: str, fields: dict) -> dict:
    return {"doc_type": doc_type, "fields": fields}


def test_stated_only_has_no_gap():
    v = verify_income(80_000.0, {})
    assert v.material_gap is False
    assert v.max_abs_gap_pct == 0.0
    assert v.recommended_annual_income == 80_000.0
    assert [s.source for s in v.sources] == ["stated"]


def test_paystub_matches_stated():
    extractions = {"p1": _ex("paystub", {
        "annualized_income": 80_500.0,
        "pay_frequency": "biweekly",
        "gross_pay": 3_096.15,
    })}
    v = verify_income(80_000.0, extractions)
    assert v.material_gap is False
    assert abs(v.max_abs_gap_pct) < MATERIAL_GAP_PCT
    paystub = [s for s in v.sources if s.source == "paystub"][0]
    assert paystub.annualized == 80_500.0


def test_paystub_with_material_gap_flags():
    extractions = {"p1": _ex("paystub", {
        "annualized_income": 50_000.0,
        "pay_frequency": "biweekly",
        "gross_pay": 1923.08,
    })}
    v = verify_income(80_000.0, extractions)
    assert v.material_gap is True
    assert v.max_abs_gap_pct >= MATERIAL_GAP_PCT
    assert any("material income gap" in w for w in v.warnings)


def test_three_sources_consistent():
    extractions = {
        "p1": _ex("paystub", {"annualized_income": 96_400.0,
                              "pay_frequency": "biweekly", "gross_pay": 3707.69}),
        "w2": _ex("w2", {"wages_box1": 96_500.0, "tax_year": 2025}),
        "bs": _ex("bank_statement", {
            "statement_start": "2026-03-01",
            "statement_end": "2026-03-31",
            "transactions": [
                {"txn_date": "2026-03-05", "description": "ACME CORP PAYROLL",
                 "amount": 4_020.83, "kind": "credit"},
                {"txn_date": "2026-03-19", "description": "ACME CORP PAYROLL",
                 "amount": 4_020.83, "kind": "credit"},
            ],
        }),
    }
    v = verify_income(96_500.0, extractions)
    assert v.material_gap is False
    sources = {s.source for s in v.sources}
    assert sources == {"stated", "paystub", "w2", "bank_statement"}


def test_bank_statement_no_payroll_warns():
    extractions = {"bs": _ex("bank_statement", {
        "statement_start": "2026-03-01",
        "statement_end": "2026-03-31",
        "transactions": [
            {"txn_date": "2026-03-05", "description": "RENT PAYMENT",
             "amount": -1900.0, "kind": "debit"},
        ],
    })}
    v = verify_income(80_000.0, extractions)
    assert any("no payroll-tagged credits" in w for w in v.warnings)
    sources = {s.source for s in v.sources}
    assert "bank_statement" not in sources


def test_w2_low_flags_gap():
    extractions = {"w2": _ex("w2", {"wages_box1": 40_000.0, "tax_year": 2025})}
    v = verify_income(80_000.0, extractions)
    assert v.material_gap is True
    w2_source = [s for s in v.sources if s.source == "w2"][0]
    assert w2_source.gap_pct_vs_stated < 0  # negative gap = doc < stated


def test_recommended_is_median():
    # stated 80k, paystub 78k, w2 82k -> median is 80k (stated)
    extractions = {
        "p1": _ex("paystub", {"annualized_income": 78_000.0,
                              "pay_frequency": "monthly", "gross_pay": 6500.0}),
        "w2": _ex("w2", {"wages_box1": 82_000.0, "tax_year": 2025}),
    }
    v = verify_income(80_000.0, extractions)
    assert v.recommended_annual_income == 80_000.0


def test_dispatch_via_tool_context(paystub_pdf: Path):
    app_ = LoanApplication(
        application_id="inc-1", applicant_id="inc-u-1",
        age=35, state="NY", employment_status="employed",
        years_employed=5.0, annual_income=90000.0, monthly_housing_cost=2100.0,
        product="personal_loan", requested_amount=10000.0, term_months=36,
        purpose="debt_consolidation",
        bureau=BureauData(
            credit_score=730, revolving_utilization=0.2, open_trades=7,
            delinquencies_24m=0, inquiries_6m=1, bankruptcies_7y=0,
            oldest_trade_months=140,
        ),
        documents=[DocumentRef(doc_id="p1", doc_type="paystub", path=str(paystub_pdf))],
    )
    ctx = ToolContext(app_)
    # extract first, then verify
    ctx.dispatch("extract_document", {"doc_id": "p1"})
    out = ctx.dispatch("verify_income", {})
    assert out["stated_annual_income"] == 90_000.0
    assert any(s["source"] == "paystub" for s in out["sources"])
    # fixture paystub annualizes to ~90,000 -> no material gap
    assert out["material_gap"] is False
    assert ctx.income_verification is not None
