"""Synthetic loan-application dataset generator for Credit Co-Pilot.

The generated CSV mirrors the production application + bureau + outcome join.
Use only for plumbing tests, schema validation, prompt/regression evals, and
demos. Never train production models on this data.

Usage:
    python generate_synthetic_data.py --rows 10000 --seed 42 \
        --out synthetic_loans.csv
"""
from __future__ import annotations

import argparse
import math
import uuid
from datetime import date, timedelta

import numpy as np
import pandas as pd

US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY",
]

EMP = ["employed", "self_employed", "retired", "unemployed", "student"]
EMP_P = [0.70, 0.10, 0.10, 0.05, 0.05]

PRODUCTS = ["personal_loan", "auto", "mortgage", "sm_business"]
PRODUCT_P = [0.45, 0.25, 0.20, 0.10]

PURPOSES = [
    "debt_consolidation", "home_improvement", "auto",
    "medical", "business", "other",
]


def sample_dates(n: int, rng: np.random.Generator) -> list[date]:
    today = date(2025, 12, 31)
    days = rng.integers(0, 365 * 3, size=n)
    return [today - timedelta(days=int(d)) for d in days]


def generate(rows: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    age = rng.integers(18, 81, size=rows)
    state = rng.choice(US_STATES, size=rows)
    emp = rng.choice(EMP, size=rows, p=EMP_P)

    # tenure: longer for older applicants, 0 if unemployed/student
    base_tenure = np.clip(rng.normal(loc=(age - 22) * 0.4, scale=4), 0, 45)
    base_tenure = np.where(np.isin(emp, ["unemployed", "student"]), 0.0, base_tenure)
    years_employed = np.round(base_tenure, 1)

    # income: log-normal, scaled by tenure and a noise factor
    income_log = rng.normal(loc=10.9, scale=0.55, size=rows) + 0.015 * years_employed
    income_log = np.where(emp == "unemployed", income_log - 0.8, income_log)
    income_log = np.where(emp == "student", income_log - 1.0, income_log)
    annual_income = np.round(np.exp(income_log), 2)

    monthly_income = annual_income / 12.0
    monthly_housing_cost = np.round(
        monthly_income * np.clip(rng.normal(0.28, 0.07, size=rows), 0.05, 0.65), 2
    )

    product = rng.choice(PRODUCTS, size=rows, p=PRODUCT_P)
    purpose = rng.choice(PURPOSES, size=rows)

    requested_amount = np.where(
        product == "mortgage",
        np.round(np.exp(rng.normal(12.6, 0.45, size=rows)), 2),       # ~$300k
        np.where(
            product == "auto",
            np.round(np.exp(rng.normal(10.3, 0.35, size=rows)), 2),   # ~$30k
            np.where(
                product == "sm_business",
                np.round(np.exp(rng.normal(11.2, 0.55, size=rows)), 2),  # ~$80k
                np.round(np.exp(rng.normal(9.4, 0.45, size=rows)), 2),    # ~$12k
            ),
        ),
    )

    term_months = np.where(
        product == "mortgage", rng.choice([180, 240, 360], size=rows),
        np.where(
            product == "auto", rng.choice([36, 48, 60, 72], size=rows),
            np.where(
                product == "sm_business", rng.choice([24, 36, 60, 84], size=rows),
                rng.choice([24, 36, 60], size=rows),
            ),
        ),
    )

    # credit score correlated with income + tenure + bankruptcies
    bankruptcies_7y = rng.binomial(1, 0.04, size=rows) * rng.integers(1, 3, size=rows)
    cs_base = 580 + 0.0007 * (annual_income - 50000) + 4 * years_employed
    cs_noise = rng.normal(0, 40, size=rows)
    credit_score = np.clip(np.round(cs_base + cs_noise - 80 * bankruptcies_7y), 300, 850).astype(int)

    revolving_utilization = np.clip(rng.beta(2, 5, size=rows) * 1.3, 0, 1.5).round(3)
    open_trades = rng.integers(0, 25, size=rows)
    delinquencies_24m = rng.poisson(lam=np.where(credit_score < 620, 1.5, 0.2)).astype(int)
    inquiries_6m = rng.poisson(lam=1.2, size=rows).astype(int)
    oldest_trade_months = np.clip(
        np.round(rng.normal(loc=(age - 18) * 10, scale=40)), 0, 600
    ).astype(int)

    # interest rate offered: tier-based
    tier_rate = np.where(
        credit_score >= 740, rng.normal(6.5, 0.6, size=rows),
        np.where(
            credit_score >= 670, rng.normal(9.5, 1.0, size=rows),
            np.where(
                credit_score >= 580, rng.normal(14.0, 1.8, size=rows),
                rng.normal(22.0, 3.0, size=rows),
            ),
        ),
    )
    interest_rate_offered = np.round(np.clip(tier_rate, 4.0, 35.0), 2)

    # monthly payment (simple amortization)
    r = interest_rate_offered / 100.0 / 12.0
    n = term_months
    payment = np.where(
        r > 0,
        requested_amount * (r * (1 + r) ** n) / ((1 + r) ** n - 1),
        requested_amount / n,
    )
    pti = np.round(payment / np.maximum(monthly_income, 1.0), 4)

    other_debt = np.clip(rng.normal(0.18, 0.10, size=rows), 0, 0.9)
    dti = np.round(np.clip(pti + other_debt, 0, 2.0), 4)

    ltv = np.where(
        np.isin(product, ["mortgage", "auto"]),
        np.round(np.clip(rng.normal(0.85, 0.10, size=rows), 0.3, 1.4), 3),
        np.nan,
    )

    # PD via hand-coded logistic on a few features (+ noise)
    z = (
        -3.2
        + 0.012 * (640 - credit_score)
        + 1.8 * dti
        + 0.25 * delinquencies_24m
        + 0.6 * (emp == "unemployed").astype(float)
        + 0.3 * (revolving_utilization)
        + 0.4 * bankruptcies_7y
    )
    pd_true = 1.0 / (1.0 + np.exp(-z))
    default_within_12m = (rng.random(size=rows) < pd_true).astype(int)

    # outcome categorical
    outcome = np.where(
        default_within_12m == 1,
        rng.choice(["default", "charged_off"], size=rows, p=[0.6, 0.4]),
        rng.choice(["paid", "current", "delinquent"], size=rows, p=[0.45, 0.50, 0.05]),
    )

    lgd = np.where(default_within_12m == 1,
                   np.clip(rng.normal(0.55, 0.15, size=rows), 0.05, 1.0).round(3),
                   np.nan)
    ead = np.where(default_within_12m == 1,
                   np.round(requested_amount * rng.uniform(0.5, 1.0, size=rows), 2),
                   np.nan)

    # deterministic UUIDs derived from the seeded rng
    def _uuid_from_rng() -> str:
        return str(uuid.UUID(int=int(rng.integers(0, 2**63, dtype=np.uint64)) << 64
                              | int(rng.integers(0, 2**63, dtype=np.uint64))))

    df = pd.DataFrame({
        "application_id": [_uuid_from_rng() for _ in range(rows)],
        "applicant_id": [_uuid_from_rng() for _ in range(rows)],
        "application_date": sample_dates(rows, rng),
        "age": age,
        "state": state,
        "employment_status": emp,
        "years_employed": years_employed,
        "annual_income": annual_income,
        "monthly_housing_cost": monthly_housing_cost,
        "product": product,
        "requested_amount": np.round(requested_amount, 2),
        "term_months": term_months.astype(int),
        "purpose": purpose,
        "interest_rate_offered": interest_rate_offered,
        "credit_score": credit_score,
        "revolving_utilization": revolving_utilization,
        "open_trades": open_trades.astype(int),
        "delinquencies_24m": delinquencies_24m,
        "inquiries_6m": inquiries_6m,
        "bankruptcies_7y": bankruptcies_7y.astype(int),
        "oldest_trade_months": oldest_trade_months,
        "dti": dti,
        "pti": pti,
        "ltv": ltv,
        "outcome": outcome,
        "default_within_12m": default_within_12m,
        "lgd": lgd,
        "ead": ead,
    })

    return df


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rows", type=int, default=100, help="Number of rows to generate.")
    p.add_argument("--seed", type=int, default=42, help="RNG seed for determinism.")
    p.add_argument("--out", type=str, default="synthetic_loans.csv", help="Output CSV path.")
    args = p.parse_args()

    df = generate(args.rows, args.seed)
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df):,} rows -> {args.out}")
    print(f"Default rate: {df['default_within_12m'].mean():.2%}")


if __name__ == "__main__":
    main()
