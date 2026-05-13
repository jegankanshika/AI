"""Document extraction.

Two backends, same interface:

  * `text_pdf` (default) — pypdf extracts text, regex picks out fields.
    Works for digitally-generated paystubs (the synthetic fixture and the
    common ADP/Paychex/Gusto exports). Cheap, deterministic, no network.
  * `textract` — placeholder that would call AWS Textract for scanned /
    image-based PDFs. Enabled by setting `IDP_BACKEND=textract` and the
    AWS env vars; falls back to `text_pdf` if the SDK or credentials are
    missing. Real impl is out of scope for this slice.

Both produce a typed `ExtractionResult`. Schema validation is enforced by
Pydantic; missing required fields become warnings + reduced confidence.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from pypdf import PdfReader

from app.idp.schemas import (
    DocumentRef, ExtractionResult, PayFrequency, Paystub,
)

PERIODS_PER_YEAR: dict[PayFrequency, int] = {
    "weekly": 52, "biweekly": 26, "semimonthly": 24, "monthly": 12,
}

_MONEY = r"\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)"
_DATE = r"([0-9]{1,2}[/\-][0-9]{1,2}[/\-][0-9]{2,4})"


def _to_float(s: str) -> float:
    return float(s.replace(",", "").replace("$", ""))


def _to_date(s: str) -> Optional[date]:
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


# ---- Paystub extraction --------------------------------------------------

_RE_EMPLOYER = re.compile(r"(?:Employer|Company)\s*[:\-]?\s*(.+)", re.IGNORECASE)
_RE_EMPLOYEE = re.compile(r"Employee\s*[:\-]?\s*(.+)", re.IGNORECASE)
_RE_PAY_PERIOD = re.compile(
    rf"Pay\s*Period\s*[:\-]?\s*{_DATE}\s*(?:-|to|through|–)\s*{_DATE}", re.IGNORECASE,
)
_RE_PAY_DATE = re.compile(rf"Pay\s*Date\s*[:\-]?\s*{_DATE}", re.IGNORECASE)
_RE_FREQ = re.compile(r"(weekly|biweekly|bi-weekly|semimonthly|semi-monthly|monthly)",
                      re.IGNORECASE)
_RE_GROSS = re.compile(rf"Gross\s*Pay\s*[:\-]?\s*{_MONEY}", re.IGNORECASE)
_RE_NET = re.compile(rf"Net\s*Pay\s*[:\-]?\s*{_MONEY}", re.IGNORECASE)
_RE_YTD = re.compile(rf"YTD\s*Gross\s*[:\-]?\s*{_MONEY}", re.IGNORECASE)


def _normalize_freq(raw: str) -> PayFrequency:
    s = raw.lower().replace("-", "")
    if s == "biweekly":
        return "biweekly"
    if s == "semimonthly":
        return "semimonthly"
    if s == "monthly":
        return "monthly"
    return "weekly"


def _extract_paystub(text: str) -> tuple[Optional[Paystub], list[str], float]:
    warnings: list[str] = []

    employer = _RE_EMPLOYER.search(text)
    employee = _RE_EMPLOYEE.search(text)
    period = _RE_PAY_PERIOD.search(text)
    pay_date_m = _RE_PAY_DATE.search(text)
    freq = _RE_FREQ.search(text)
    gross = _RE_GROSS.search(text)
    net = _RE_NET.search(text)
    ytd = _RE_YTD.search(text)

    required_missing = []
    if not employer: required_missing.append("employer_name")
    if not freq:     required_missing.append("pay_frequency")
    if not gross:    required_missing.append("gross_pay")
    if not net:      required_missing.append("net_pay")
    if required_missing:
        warnings.append(f"missing required field(s): {required_missing}")
        return None, warnings, 0.0

    frequency = _normalize_freq(freq.group(1))
    gross_v = _to_float(gross.group(1))
    net_v = _to_float(net.group(1))
    annualized = round(gross_v * PERIODS_PER_YEAR[frequency], 2)

    if not ytd:
        warnings.append("missing optional field: ytd_gross")
    if not period:
        warnings.append("missing optional field: pay_period")

    confidence = 1.0
    confidence -= 0.1 * len(warnings)
    confidence = max(0.0, min(1.0, confidence))

    paystub = Paystub(
        employer_name=employer.group(1).strip().splitlines()[0],
        employee_name=(employee.group(1).strip().splitlines()[0] if employee else None),
        pay_period_start=_to_date(period.group(1)) if period else None,
        pay_period_end=_to_date(period.group(2)) if period else None,
        pay_date=_to_date(pay_date_m.group(1)) if pay_date_m else None,
        pay_frequency=frequency,
        gross_pay=gross_v,
        net_pay=net_v,
        ytd_gross=_to_float(ytd.group(1)) if ytd else None,
        annualized_income=annualized,
    )
    return paystub, warnings, confidence


# ---- Public API ----------------------------------------------------------


def extract(ref: DocumentRef) -> ExtractionResult:
    path = Path(ref.path)
    if not path.exists():
        return ExtractionResult(
            doc_id=ref.doc_id, doc_type=ref.doc_type,
            backend="text_pdf", confidence=0.0,
            fields={}, warnings=[f"file not found: {ref.path}"],
        )

    backend = os.environ.get("IDP_BACKEND", "text_pdf")
    # textract path intentionally falls back: real impl is out of slice scope
    if backend == "textract":
        try:
            import boto3  # noqa: F401
        except Exception:
            backend = "text_pdf"

    sha = ref.sha256 or _sha256(path)
    text = _read_pdf_text(path)

    if ref.doc_type == "paystub":
        paystub, warnings, confidence = _extract_paystub(text)
        fields = json.loads(paystub.model_dump_json()) if paystub else {}
        return ExtractionResult(
            doc_id=ref.doc_id, doc_type=ref.doc_type,
            backend="text_pdf",
            confidence=confidence,
            fields={**fields, "sha256": sha},
            warnings=warnings,
        )

    return ExtractionResult(
        doc_id=ref.doc_id, doc_type=ref.doc_type,
        backend="text_pdf", confidence=0.0,
        fields={"sha256": sha},
        warnings=[f"doc_type {ref.doc_type!r} not yet supported"],
    )
