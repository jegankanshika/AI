"""Deterministic income cross-check.

After the agent has extracted any combination of paystub, W-2, and
bank-statement documents, this tool computes an annualized-income
estimate from each independent source, compares them against the
applicant's stated `annual_income`, and flags any **material gap**
(default threshold: 10%).

Inputs come from `ToolContext.extractions` — the cache populated by
`extract_document`. The tool is pure: same inputs → same output.
"""
from __future__ import annotations

import re
from datetime import date as _date
from typing import Literal, Optional

from pydantic import BaseModel, Field

SourceKind = Literal["stated", "paystub", "w2", "bank_statement"]

# Payroll-deposit detector — intentionally permissive; tightens up with a real
# transaction classifier (Plaid categorizer or in-house model) in production.
_PAYROLL_RE = re.compile(r"(payroll|salary|direct\s*dep)", re.IGNORECASE)

MATERIAL_GAP_PCT = 0.10


class IncomeSource(BaseModel):
    source: SourceKind
    doc_id: Optional[str] = None
    annualized: float
    gap_pct_vs_stated: float = Field(
        description="(annualized - stated) / max(stated, 1) — signed."
    )
    notes: Optional[str] = None


class IncomeVerification(BaseModel):
    stated_annual_income: float
    sources: list[IncomeSource]
    max_abs_gap_pct: float
    material_gap: bool
    recommended_annual_income: float = Field(
        description="Median of all source estimates including the stated value."
    )
    warnings: list[str] = Field(default_factory=list)


def _annualize_bank_payroll(fields: dict) -> Optional[float]:
    """Sum the credits whose description looks like payroll, then annualize
    by the statement period length. Returns None if either the period or any
    payroll credits are missing."""
    txns = fields.get("transactions") or []
    if not txns:
        return None
    payroll_credits = [
        t["amount"] for t in txns
        if t.get("kind") == "credit"
        and t.get("amount", 0) > 0
        and _PAYROLL_RE.search(t.get("description", "") or "")
    ]
    if not payroll_credits:
        return None
    start = fields.get("statement_start")
    end = fields.get("statement_end")
    if not start or not end:
        return None
    try:
        d0 = _date.fromisoformat(start)
        d1 = _date.fromisoformat(end)
    except ValueError:
        return None
    days = (d1 - d0).days + 1
    if days <= 0:
        return None
    return round(sum(payroll_credits) * (365.0 / days), 2)


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def verify_income(stated_annual_income: float,
                  extractions: dict[str, dict]) -> IncomeVerification:
    sources: list[IncomeSource] = [IncomeSource(
        source="stated",
        doc_id=None,
        annualized=round(stated_annual_income, 2),
        gap_pct_vs_stated=0.0,
        notes=None,
    )]
    warnings: list[str] = []

    for doc_id, payload in extractions.items():
        if not isinstance(payload, dict):
            continue
        doc_type = payload.get("doc_type")
        fields = payload.get("fields") or {}

        if doc_type == "paystub":
            v = fields.get("annualized_income")
            if v:
                sources.append(IncomeSource(
                    source="paystub", doc_id=doc_id,
                    annualized=float(v),
                    gap_pct_vs_stated=_gap(v, stated_annual_income),
                    notes=f"freq={fields.get('pay_frequency')} gross={fields.get('gross_pay')}",
                ))
            else:
                warnings.append(f"paystub {doc_id} missing annualized_income")

        elif doc_type == "w2":
            v = fields.get("wages_box1")
            if v:
                sources.append(IncomeSource(
                    source="w2", doc_id=doc_id,
                    annualized=float(v),
                    gap_pct_vs_stated=_gap(v, stated_annual_income),
                    notes=f"tax_year={fields.get('tax_year')}",
                ))
            else:
                warnings.append(f"w2 {doc_id} missing wages_box1")

        elif doc_type == "bank_statement":
            v = _annualize_bank_payroll(fields)
            if v:
                sources.append(IncomeSource(
                    source="bank_statement", doc_id=doc_id,
                    annualized=v,
                    gap_pct_vs_stated=_gap(v, stated_annual_income),
                    notes="annualized from payroll-tagged credits",
                ))
            else:
                warnings.append(
                    f"bank_statement {doc_id}: no payroll-tagged credits found"
                )

    max_abs = max((abs(s.gap_pct_vs_stated) for s in sources if s.source != "stated"),
                  default=0.0)
    material = max_abs >= MATERIAL_GAP_PCT
    if material:
        warnings.append(
            f"material income gap: max |delta| {max_abs:.1%} ≥ {MATERIAL_GAP_PCT:.0%}"
        )

    rec = _median([s.annualized for s in sources])

    return IncomeVerification(
        stated_annual_income=round(stated_annual_income, 2),
        sources=sources,
        max_abs_gap_pct=round(max_abs, 4),
        material_gap=material,
        recommended_annual_income=round(rec, 2),
        warnings=warnings,
    )


def _gap(annualized: float, stated: float) -> float:
    if stated <= 0:
        return 0.0
    return round((annualized - stated) / stated, 4)
