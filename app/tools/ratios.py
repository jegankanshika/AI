"""Deterministic ratio calculator. No network, no LLM."""
from __future__ import annotations

from app.schemas import LoanApplication, Ratios


def _monthly_payment(principal: float, annual_rate: float, term_months: int) -> float:
    r = annual_rate / 100.0 / 12.0
    if r == 0:
        return principal / term_months
    return principal * (r * (1 + r) ** term_months) / ((1 + r) ** term_months - 1)


def compute_ratios(app: LoanApplication, assumed_apr: float = 14.99,
                   collateral_value: float | None = None,
                   other_monthly_debt: float | None = None) -> Ratios:
    """Compute DTI, PTI, and (if applicable) LTV.

    - PTI = new monthly loan payment / monthly gross income.
    - DTI = (PTI + other_monthly_debt_ratio + housing/income).
    - LTV only set for secured products (auto, mortgage).
    """
    monthly_income = max(app.annual_income / 12.0, 1.0)
    payment = _monthly_payment(app.requested_amount, assumed_apr, app.term_months)
    pti = payment / monthly_income

    housing_ratio = app.monthly_housing_cost / monthly_income
    other_ratio = (other_monthly_debt or 0.0) / monthly_income
    dti = pti + housing_ratio + other_ratio

    ltv: float | None = None
    if app.product in ("auto", "mortgage") and collateral_value:
        ltv = app.requested_amount / collateral_value

    return Ratios(
        monthly_payment=round(payment, 2),
        pti=round(pti, 4),
        dti=round(dti, 4),
        ltv=round(ltv, 3) if ltv is not None else None,
    )
