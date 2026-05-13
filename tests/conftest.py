"""Shared test fixtures.

`paystub_pdf` generates a deterministic synthetic paystub PDF in a tmp
directory and yields its path. The same data is asserted by the extractor
tests so any change to the layout must be reflected in both.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas


def _draw_paystub(path: Path, *,
                  employer: str = "ACME CORP",
                  employee: str = "Jane Doe",
                  pay_period: tuple[str, str] = ("04/01/2026", "04/14/2026"),
                  pay_date: str = "04/19/2026",
                  pay_frequency: str = "Biweekly",
                  gross_pay: float = 3461.54,
                  net_pay: float = 2543.18,
                  ytd_gross: float = 27692.32) -> None:
    c = canvas.Canvas(str(path), pagesize=LETTER)
    w, h = LETTER
    y = h - 1 * inch

    def line(text: str, dy: float = 0.25 * inch, bold: bool = False) -> None:
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11)
        c.drawString(1 * inch, y, text)
        y -= dy

    line(employer, bold=True)
    line(f"Employer: {employer}")
    line(f"Employee: {employee}")
    line(f"Pay Period: {pay_period[0]} - {pay_period[1]}")
    line(f"Pay Date: {pay_date}")
    line(f"Pay Frequency: {pay_frequency}")
    y -= 0.2 * inch
    line("Earnings")
    line(f"Regular Pay     ${gross_pay:,.2f}")
    y -= 0.1 * inch
    line(f"Gross Pay: ${gross_pay:,.2f}", bold=True)
    line(f"Federal Tax: $415.39")
    line(f"State Tax: $138.46")
    line(f"Social Security: $214.62")
    line(f"Medicare: $50.19")
    line(f"Net Pay: ${net_pay:,.2f}", bold=True)
    line(f"YTD Gross: ${ytd_gross:,.2f}")
    c.save()


@pytest.fixture
def paystub_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "paystub_standard.pdf"
    _draw_paystub(path)
    return path


@pytest.fixture
def paystub_pdf_factory(tmp_path: Path) -> Callable[..., Path]:
    """Builds custom paystub PDFs for edge-case tests."""
    counter = {"n": 0}

    def _make(**overrides) -> Path:
        counter["n"] += 1
        path = tmp_path / f"paystub_{counter['n']}.pdf"
        _draw_paystub(path, **overrides)
        return path

    return _make
