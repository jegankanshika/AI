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


def _draw_w2(path: Path, *,
             employer: str = "ACME CORP",
             employee: str = "Jane Doe",
             ein: str = "12-3456789",
             ssn_last4: str = "1234",
             tax_year: int = 2025,
             wages_box1: float = 96_500.00,
             federal_tax: float = 12_400.00,
             ss_wages: float = 96_500.00,
             medicare_wages: float = 96_500.00) -> None:
    c = canvas.Canvas(str(path), pagesize=LETTER)
    w, h = LETTER
    y = h - 1 * inch

    def line(text: str, dy: float = 0.25 * inch, bold: bool = False) -> None:
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11)
        c.drawString(1 * inch, y, text)
        y -= dy

    line("Form W-2 Wage and Tax Statement", bold=True)
    line(f"Tax Year: {tax_year}")
    line(f"c Employer's name: {employer}")
    line(f"EIN: {ein}")
    line(f"Employee's name: {employee}")
    line(f"SSN: ***-**-{ssn_last4}")
    y -= 0.2 * inch
    line(f"Box 1 Wages, tips, other compensation: ${wages_box1:,.2f}")
    line(f"Box 2 Federal income tax withheld: ${federal_tax:,.2f}")
    line(f"Box 3 Social security wages: ${ss_wages:,.2f}")
    line(f"Box 5 Medicare wages and tips: ${medicare_wages:,.2f}")
    c.save()


def _draw_bank_statement(path: Path, *,
                         bank: str = "First National Bank",
                         holder: str = "Jane Doe",
                         account_last4: str = "5678",
                         period: tuple[str, str] = ("03/01/2026", "03/31/2026"),
                         opening: float = 5_200.00,
                         deposits: list[tuple[str, str, float]] | None = None,
                         withdrawals: list[tuple[str, str, float]] | None = None) -> None:
    if deposits is None:
        deposits = [
            ("03/05/2026", "ACME CORP PAYROLL", 2_543.18),
            ("03/19/2026", "ACME CORP PAYROLL", 2_543.18),
        ]
    if withdrawals is None:
        withdrawals = [
            ("03/02/2026", "RENT PAYMENT", 1_900.00),
            ("03/15/2026", "GROCERIES", 412.55),
            ("03/22/2026", "AUTO LOAN", 387.20),
        ]
    total_d = sum(a for _, _, a in deposits)
    total_w = sum(a for _, _, a in withdrawals)
    closing = round(opening + total_d - total_w, 2)

    c = canvas.Canvas(str(path), pagesize=LETTER)
    w, h = LETTER
    y = h - 1 * inch

    def line(text: str, dy: float = 0.22 * inch, bold: bool = False) -> None:
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
        c.drawString(0.8 * inch, y, text)
        y -= dy

    line(bank, bold=True)
    line(f"Bank: {bank}")
    line(f"Account Holder: {holder}")
    line(f"Account Number: ****{account_last4}")
    line(f"Statement Period: {period[0]} - {period[1]}")
    y -= 0.15 * inch
    line(f"Opening Balance: ${opening:,.2f}")
    line(f"Total Deposits: ${total_d:,.2f}")
    line(f"Total Withdrawals: ${total_w:,.2f}")
    line(f"Closing Balance: ${closing:,.2f}", bold=True)
    y -= 0.2 * inch
    line("Transactions", bold=True)
    for d, desc, amt in deposits:
        line(f"{d}    {desc}    ${amt:,.2f}    C")
    for d, desc, amt in withdrawals:
        line(f"{d}    {desc}    ${amt:,.2f}    D")
    c.save()


@pytest.fixture
def w2_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "w2_standard.pdf"
    _draw_w2(path)
    return path


@pytest.fixture
def bank_statement_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "bank_statement.pdf"
    _draw_bank_statement(path)
    return path
