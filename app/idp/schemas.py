"""Document Intelligence schemas — typed extraction targets per doc type."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, NonNegativeFloat

DocumentType = Literal["paystub", "w2", "bank_statement", "photo_id"]
PayFrequency = Literal["weekly", "biweekly", "semimonthly", "monthly"]


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


class ExtractionResult(BaseModel):
    doc_id: str
    doc_type: DocumentType
    backend: Literal["text_pdf", "textract"]
    confidence: float = Field(ge=0.0, le=1.0)
    fields: dict
    warnings: list[str] = Field(default_factory=list)
