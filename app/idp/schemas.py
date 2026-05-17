"""Document Intelligence schemas — typed extraction targets per doc type."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, NonNegativeFloat, NonNegativeInt

DocumentType = Literal["paystub", "w2", "bank_statement", "photo_id"]
PayFrequency = Literal["weekly", "biweekly", "semimonthly", "monthly"]
TxnKind = Literal["debit", "credit"]


class DocumentRef(BaseModel):
    """Reference to a document attached to an application. The `path` is local
    for the slice; in production this would be an `s3://` URI plus a SHA256
    content hash for tamper detection."""

    doc_id: str
    doc_type: DocumentType
    path: str
    sha256: Optional[str] = None


class Paystub(BaseModel):
    employer_name: str
    employee_name: Optional[str] = None
    pay_period_start: Optional[date] = None
    pay_period_end: Optional[date] = None
    pay_date: Optional[date] = None
    pay_frequency: PayFrequency
    gross_pay: NonNegativeFloat
    net_pay: NonNegativeFloat
    ytd_gross: Optional[NonNegativeFloat] = None
    annualized_income: NonNegativeFloat = Field(
        description="gross_pay × periods/year, computed deterministically."
    )


class W2(BaseModel):
    employer_name: str
    employee_name: Optional[str] = None
    employee_ssn_last4: Optional[str] = Field(default=None, max_length=4)
    tax_year: int = Field(ge=1990, le=2100)
    wages_box1: NonNegativeFloat
    federal_tax_withheld: Optional[NonNegativeFloat] = None
    social_security_wages: Optional[NonNegativeFloat] = None
    medicare_wages: Optional[NonNegativeFloat] = None
    ein: Optional[str] = None


class Transaction(BaseModel):
    txn_date: date
    description: str
    amount: float        # signed: positive = credit, negative = debit
    kind: TxnKind


class BankStatement(BaseModel):
    bank_name: str
    account_holder: Optional[str] = None
    account_last4: Optional[str] = Field(default=None, max_length=4)
    statement_start: date
    statement_end: date
    opening_balance: float
    closing_balance: float
    total_deposits: NonNegativeFloat
    total_withdrawals: NonNegativeFloat
    deposit_count: NonNegativeInt = 0
    withdrawal_count: NonNegativeInt = 0
    transactions: list[Transaction] = Field(default_factory=list)
    reconciles: bool = Field(
        description="opening + deposits - withdrawals == closing (within $0.01)"
    )


class ExtractionResult(BaseModel):
    doc_id: str
    doc_type: DocumentType
    backend: Literal["text_pdf", "textract"]
    confidence: float = Field(ge=0.0, le=1.0)
    fields: dict
    warnings: list[str] = Field(default_factory=list)
