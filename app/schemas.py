"""Typed schemas for application, tool I/O, and the underwriting memo."""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field, NonNegativeFloat, NonNegativeInt

Product = Literal["personal_loan", "auto", "mortgage", "sm_business"]
EmploymentStatus = Literal["employed", "self_employed", "retired", "unemployed", "student"]
Decision = Literal["approve", "decline", "refer_to_human"]


class BureauData(BaseModel):
    credit_score: int = Field(ge=300, le=850)
    revolving_utilization: float = Field(ge=0.0, le=1.5)
    open_trades: NonNegativeInt
    delinquencies_24m: NonNegativeInt
    inquiries_6m: NonNegativeInt
    bankruptcies_7y: NonNegativeInt
    oldest_trade_months: NonNegativeInt


class LoanApplication(BaseModel):
    application_id: str
    applicant_id: str
    age: int = Field(ge=18, le=100)
    state: str = Field(min_length=2, max_length=2)
    employment_status: EmploymentStatus
    years_employed: NonNegativeFloat
    annual_income: NonNegativeFloat
    monthly_housing_cost: NonNegativeFloat
    product: Product
    requested_amount: NonNegativeFloat
    term_months: int = Field(ge=6, le=480)
    purpose: str
    bureau: BureauData


class Ratios(BaseModel):
    monthly_payment: float
    pti: float
    dti: float
    ltv: Optional[float] = None


class PolicyHit(BaseModel):
    policy_id: str
    snippet: str
    score: float


class PolicyResult(BaseModel):
    query: str
    hits: list[PolicyHit]


class RiskScore(BaseModel):
    pd: float = Field(ge=0.0, le=1.0)
    model_version: str
    top_factors: list[str]


class MemoCitation(BaseModel):
    source: str   # e.g., "policy:personal_loan#tier", "tool:compute_ratios"
    detail: str


class UnderwritingMemo(BaseModel):
    application_id: str
    decision: Decision
    rationale: str
    ratios: Ratios
    risk: RiskScore
    adverse_action_codes: list[str] = Field(default_factory=list)
    citations: list[MemoCitation] = Field(default_factory=list)
