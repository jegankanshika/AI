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
    BankStatement, DocumentRef, ExtractionResult, PayFrequency, Paystub,
    Transaction, W2,
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


# ---- W-2 extraction ------------------------------------------------------

_RE_W2_EMPLOYER = re.compile(
    r"(?:c\s*Employer's\s*name|Employer)\s*[:\-]?\s*(.+)", re.IGNORECASE,
)
_RE_W2_EMPLOYEE = re.compile(r"(?:Employee'?s?\s*name|Employee)\s*[:\-]?\s*(.+)",
                             re.IGNORECASE)
_RE_W2_YEAR = re.compile(r"(?:Tax\s*Year|Form\s*W-?2\s*\(?(\d{4})\)?|For\s*Year)\s*[:\-]?\s*(\d{4})?",
                         re.IGNORECASE)
_RE_W2_SSN4 = re.compile(r"SSN\s*[:\-]?\s*[\*\-\s]+(\d{4})", re.IGNORECASE)
_RE_W2_EIN = re.compile(r"EIN\s*[:\-]?\s*([0-9]{2}-?[0-9]{7})", re.IGNORECASE)
_RE_W2_BOX1 = re.compile(rf"(?:Box\s*1|1\s*Wages,?\s*tips,?\s*other\s*comp(?:ensation)?)\s*[:\-]?\s*{_MONEY}",
                         re.IGNORECASE)
_RE_W2_BOX2 = re.compile(rf"(?:Box\s*2|2\s*Federal\s*income\s*tax\s*withheld)\s*[:\-]?\s*{_MONEY}",
                         re.IGNORECASE)
_RE_W2_BOX3 = re.compile(rf"(?:Box\s*3|3\s*Social\s*security\s*wages)\s*[:\-]?\s*{_MONEY}",
                         re.IGNORECASE)
_RE_W2_BOX5 = re.compile(rf"(?:Box\s*5|5\s*Medicare\s*wages\s*and\s*tips)\s*[:\-]?\s*{_MONEY}",
                         re.IGNORECASE)


def _extract_w2(text: str) -> tuple[Optional[W2], list[str], float]:
    warnings: list[str] = []

    employer = _RE_W2_EMPLOYER.search(text)
    employee = _RE_W2_EMPLOYEE.search(text)
    box1 = _RE_W2_BOX1.search(text)
    box2 = _RE_W2_BOX2.search(text)
    box3 = _RE_W2_BOX3.search(text)
    box5 = _RE_W2_BOX5.search(text)
    ssn4 = _RE_W2_SSN4.search(text)
    ein = _RE_W2_EIN.search(text)

    # Year: try matching either group, then fall back to a bare 4-digit year on a "Tax Year" line.
    year_m = _RE_W2_YEAR.search(text)
    year: Optional[int] = None
    if year_m:
        year = int(year_m.group(1) or year_m.group(2) or 0) or None
    if year is None:
        bare = re.search(r"(?:Tax\s*Year|For\s*Year)\s*[:\-]?\s*(\d{4})", text, re.IGNORECASE)
        if bare:
            year = int(bare.group(1))

    missing = []
    if not employer: missing.append("employer_name")
    if not box1:     missing.append("wages_box1")
    if year is None: missing.append("tax_year")
    if missing:
        warnings.append(f"missing required field(s): {missing}")
        return None, warnings, 0.0

    if not box2: warnings.append("missing optional field: federal_tax_withheld")
    if not box3: warnings.append("missing optional field: social_security_wages")
    if not ssn4: warnings.append("missing optional field: employee_ssn_last4")

    confidence = max(0.0, min(1.0, 1.0 - 0.08 * len(warnings)))

    w2 = W2(
        employer_name=employer.group(1).strip().splitlines()[0],
        employee_name=(employee.group(1).strip().splitlines()[0] if employee else None),
        employee_ssn_last4=ssn4.group(1) if ssn4 else None,
        tax_year=year,
        wages_box1=_to_float(box1.group(1)),
        federal_tax_withheld=_to_float(box2.group(1)) if box2 else None,
        social_security_wages=_to_float(box3.group(1)) if box3 else None,
        medicare_wages=_to_float(box5.group(1)) if box5 else None,
        ein=ein.group(1) if ein else None,
    )
    return w2, warnings, confidence


# ---- Bank-statement extraction ------------------------------------------

# Require the colon — the heading line on a statement often ends with the
# word "Bank" without one, which would otherwise grab the next line.
_RE_BS_BANK = re.compile(r"(?:^|\n)\s*(?:Bank|Institution)\s*[:\-]\s*(.+)",
                         re.IGNORECASE)
_RE_BS_HOLDER = re.compile(r"Account\s*Holder\s*[:\-]?\s*(.+)", re.IGNORECASE)
_RE_BS_ACCT4 = re.compile(r"Account\s*(?:No\.|#|Number)?\s*[:\-]?\s*\*{3,}\-?\*?(\d{4})",
                          re.IGNORECASE)
_RE_BS_PERIOD = re.compile(
    rf"Statement\s*Period\s*[:\-]?\s*{_DATE}\s*(?:-|to|through|–)\s*{_DATE}", re.IGNORECASE,
)
_RE_BS_OPEN = re.compile(rf"Opening\s*Balance\s*[:\-]?\s*{_MONEY}", re.IGNORECASE)
_RE_BS_CLOSE = re.compile(rf"Closing\s*Balance\s*[:\-]?\s*{_MONEY}", re.IGNORECASE)
_RE_BS_TOT_DEP = re.compile(rf"Total\s*Deposits\s*[:\-]?\s*{_MONEY}", re.IGNORECASE)
_RE_BS_TOT_WD = re.compile(rf"Total\s*Withdrawals\s*[:\-]?\s*{_MONEY}", re.IGNORECASE)
# A txn line: "MM/DD/YYYY  DESCRIPTION   $123.45  C"  (last token C=credit, D=debit)
_RE_BS_TXN = re.compile(
    rf"^\s*{_DATE}\s+(.+?)\s+\$?([0-9]{{1,3}}(?:,[0-9]{{3}})*(?:\.[0-9]{{1,2}})?)\s+(C|D|CREDIT|DEBIT)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _extract_bank_statement(text: str) -> tuple[Optional[BankStatement], list[str], float]:
    warnings: list[str] = []

    bank = _RE_BS_BANK.search(text)
    period = _RE_BS_PERIOD.search(text)
    opening = _RE_BS_OPEN.search(text)
    closing = _RE_BS_CLOSE.search(text)
    tot_dep = _RE_BS_TOT_DEP.search(text)
    tot_wd = _RE_BS_TOT_WD.search(text)
    holder = _RE_BS_HOLDER.search(text)
    acct4 = _RE_BS_ACCT4.search(text)

    missing = []
    if not bank:    missing.append("bank_name")
    if not period:  missing.append("statement_period")
    if not opening: missing.append("opening_balance")
    if not closing: missing.append("closing_balance")
    if not tot_dep: missing.append("total_deposits")
    if not tot_wd:  missing.append("total_withdrawals")
    if missing:
        warnings.append(f"missing required field(s): {missing}")
        return None, warnings, 0.0

    txns: list[Transaction] = []
    for m in _RE_BS_TXN.finditer(text):
        d = _to_date(m.group(1))
        if d is None:
            continue
        desc = m.group(2).strip()
        amount = _to_float(m.group(3))
        kind_raw = m.group(4).upper()
        kind: TxnKind = "credit" if kind_raw in ("C", "CREDIT") else "debit"
        signed = amount if kind == "credit" else -amount
        txns.append(Transaction(txn_date=d, description=desc, amount=signed, kind=kind))

    opening_v = _to_float(opening.group(1))
    closing_v = _to_float(closing.group(1))
    tot_dep_v = _to_float(tot_dep.group(1))
    tot_wd_v = _to_float(tot_wd.group(1))
    expected_close = round(opening_v + tot_dep_v - tot_wd_v, 2)
    reconciles = abs(expected_close - round(closing_v, 2)) < 0.01
    if not reconciles:
        warnings.append(
            f"reconciliation mismatch: opening+deposits-withdrawals={expected_close} "
            f"vs closing_balance={closing_v}"
        )

    if not holder: warnings.append("missing optional field: account_holder")
    if not acct4:  warnings.append("missing optional field: account_last4")

    confidence = max(0.0, min(1.0, 1.0 - 0.05 * len(warnings)))

    statement = BankStatement(
        bank_name=bank.group(1).strip().splitlines()[0],
        account_holder=(holder.group(1).strip().splitlines()[0] if holder else None),
        account_last4=acct4.group(1) if acct4 else None,
        statement_start=_to_date(period.group(1)),  # type: ignore[arg-type]
        statement_end=_to_date(period.group(2)),    # type: ignore[arg-type]
        opening_balance=opening_v,
        closing_balance=closing_v,
        total_deposits=tot_dep_v,
        total_withdrawals=tot_wd_v,
        deposit_count=sum(1 for t in txns if t.kind == "credit"),
        withdrawal_count=sum(1 for t in txns if t.kind == "debit"),
        transactions=txns,
        reconciles=reconciles,
    )
    return statement, warnings, confidence


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

    if ref.doc_type == "w2":
        w2, warnings, confidence = _extract_w2(text)
        fields = json.loads(w2.model_dump_json()) if w2 else {}
        return ExtractionResult(
            doc_id=ref.doc_id, doc_type=ref.doc_type,
            backend="text_pdf",
            confidence=confidence,
            fields={**fields, "sha256": sha},
            warnings=warnings,
        )

    if ref.doc_type == "bank_statement":
        stmt, warnings, confidence = _extract_bank_statement(text)
        fields = json.loads(stmt.model_dump_json()) if stmt else {}
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
