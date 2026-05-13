"""PD scoring stub.

Deterministic hand-coded logistic that matches the synthetic data DGP. In
production this is replaced by an MLflow-served XGBoost / LightGBM model.
"""
from __future__ import annotations

import math

from app.schemas import LoanApplication, Ratios, RiskScore

MODEL_VERSION = "pd-stub-0.1"


def score_pd(app: LoanApplication, ratios: Ratios) -> RiskScore:
    cs = app.bureau.credit_score
    z = (
        -3.2
        + 0.012 * (640 - cs)
        + 1.8 * ratios.dti
        + 0.25 * app.bureau.delinquencies_24m
        + 0.6 * (1.0 if app.employment_status == "unemployed" else 0.0)
        + 0.3 * app.bureau.revolving_utilization
        + 0.4 * app.bureau.bankruptcies_7y
    )
    pd = 1.0 / (1.0 + math.exp(-z))

    # crude top-factor ranking by contribution magnitude
    contribs = {
        "credit_score": abs(0.012 * (640 - cs)),
        "dti": abs(1.8 * ratios.dti),
        "delinquencies_24m": abs(0.25 * app.bureau.delinquencies_24m),
        "employment_status": 0.6 if app.employment_status == "unemployed" else 0.0,
        "revolving_utilization": abs(0.3 * app.bureau.revolving_utilization),
        "bankruptcies_7y": abs(0.4 * app.bureau.bankruptcies_7y),
    }
    top = sorted(contribs.items(), key=lambda kv: kv[1], reverse=True)
    top_factors = [k for k, v in top[:3] if v > 0]

    return RiskScore(pd=round(pd, 4), model_version=MODEL_VERSION, top_factors=top_factors)
