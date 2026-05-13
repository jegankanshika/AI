"""FastAPI integration tests using the bundled test client."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


_STRONG_APP = {
    "application_id": "api-1",
    "applicant_id": "api-u-1",
    "age": 38, "state": "CA", "employment_status": "employed",
    "years_employed": 8.0, "annual_income": 110000.0, "monthly_housing_cost": 2400.0,
    "product": "personal_loan", "requested_amount": 18000.0, "term_months": 48,
    "purpose": "debt_consolidation",
    "bureau": {
        "credit_score": 765, "revolving_utilization": 0.18, "open_trades": 9,
        "delinquencies_24m": 0, "inquiries_6m": 1, "bankruptcies_7y": 0,
        "oldest_trade_months": 180,
    },
}


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_root_serves_ui():
    r = client.get("/")
    assert r.status_code == 200
    assert "Credit Co-Pilot" in r.text
    assert "/underwrite" in r.text


def test_underwrite_strong_application():
    r = client.post("/underwrite", json=_STRONG_APP)
    assert r.status_code == 200, r.text
    body = r.json()
    memo = body["memo"]
    trace = body["trace"]
    assert memo["decision"] in {"approve", "decline", "refer_to_human"}
    assert memo["ratios"]["dti"] > 0
    assert "tool_calls" in trace
    assert "latency_ms" in trace


def test_underwrite_sanctions_is_forced_decline():
    payload = dict(_STRONG_APP)
    payload["application_id"] = "api-sanctions"
    payload["sanctions_hit"] = True
    r = client.post("/underwrite", json=payload)
    assert r.status_code == 200
    memo = r.json()["memo"]
    assert memo["decision"] == "decline"
    assert "AA-14" in memo["adverse_action_codes"]


def test_underwrite_validates_input():
    bad = dict(_STRONG_APP)
    bad["age"] = 10  # below schema min
    r = client.post("/underwrite", json=bad)
    assert r.status_code == 422
