"""Offline eval: run the agent on the committed synthetic sample and report
concordance with a baseline rule + headline KPIs.

Usage:
    python -m app.eval.run_eval --csv training_data/synthetic_loans.csv --limit 50
"""
from __future__ import annotations

import argparse
import csv
import time
from collections import Counter
from pathlib import Path

from app.agent.runner import run_agent
from app.schemas import BureauData, LoanApplication


def row_to_application(row: dict) -> LoanApplication:
    return LoanApplication(
        application_id=row["application_id"],
        applicant_id=row["applicant_id"],
        age=int(row["age"]),
        state=row["state"],
        employment_status=row["employment_status"],
        years_employed=float(row["years_employed"]),
        annual_income=float(row["annual_income"]),
        monthly_housing_cost=float(row["monthly_housing_cost"]),
        product=row["product"],
        requested_amount=float(row["requested_amount"]),
        term_months=int(row["term_months"]),
        purpose=row["purpose"],
        bureau=BureauData(
            credit_score=int(row["credit_score"]),
            revolving_utilization=float(row["revolving_utilization"]),
            open_trades=int(row["open_trades"]),
            delinquencies_24m=int(row["delinquencies_24m"]),
            inquiries_6m=int(row["inquiries_6m"]),
            bankruptcies_7y=int(row["bankruptcies_7y"]),
            oldest_trade_months=int(row["oldest_trade_months"]),
        ),
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default="training_data/synthetic_loans.csv")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--mode", choices=["offline", "live", "auto"], default="offline")
    p.add_argument("--product", default="personal_loan",
                   help="Filter to a single product (slice scope).")
    args = p.parse_args()

    rows = list(csv.DictReader(Path(args.csv).open()))
    rows = [r for r in rows if r["product"] == args.product][: args.limit]

    t0 = time.perf_counter()
    decisions = Counter()
    correct_default = 0
    n_eval = 0
    for r in rows:
        app_ = row_to_application(r)
        memo, _ = run_agent(app_, mode=args.mode)
        decisions[memo.decision] += 1
        # crude concordance: declines should correlate with defaulted ground truth
        gt_default = int(r["default_within_12m"]) == 1
        if memo.decision == "decline" and gt_default:
            correct_default += 1
        if memo.decision == "decline":
            n_eval += 1

    elapsed = time.perf_counter() - t0
    print(f"Evaluated {len(rows)} applications ({args.product}) in {elapsed:.1f}s")
    print(f"Decisions: {dict(decisions)}")
    if n_eval:
        prec = correct_default / n_eval
        print(f"Decline precision vs ground-truth default: {prec:.2%}")


if __name__ == "__main__":
    main()
