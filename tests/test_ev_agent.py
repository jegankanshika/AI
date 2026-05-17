"""Smoke tests for the EV Charging agent + API."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app_ev.agent.runner import run
from app_ev.api.main import app
from app_ev.schemas import Query
from app_ev.tools import intelligence, registrations, stations

client = TestClient(app)


def test_registrations_state_total_matches_districts():
    s = registrations.state_summary()
    d = registrations.list_districts()
    assert s["total"] == d["state_total"]
    assert sum(r["registered_evs"] for r in d["districts"]) == s["total"]


def test_district_detail_chennai():
    d = registrations.district_detail("Chennai")
    assert d is not None
    assert d["registered_evs"] > 0
    assert any("TN01" in rto for rto in d["rto_offices"])


def test_stations_have_geo_and_economics():
    data = stations.list_stations()
    assert data["count"] >= 10
    for s in data["stations"]:
        assert -90 <= s["lat"] <= 90
        assert 70 <= s["lng"] <= 90  # TN longitude band
        assert s["revenue_30d"] >= 0


def test_station_economics_portfolio_totals():
    e = stations.station_economics()
    tot = e["totals"]
    assert tot["total_revenue_30d_inr"] > tot["total_expenses_30d_inr"]


def test_challenges_have_solutions():
    c = intelligence.list_challenges()
    assert c["count"] >= 5
    for item in c["challenges"]:
        assert len(item["solutions"]) >= 2


def test_future_locations_chennai_and_highway():
    ch = intelligence.future_chennai_locations(5)
    hw = intelligence.future_highway_locations(5)
    assert len(ch["locations"]) == 5
    assert len(hw["locations"]) == 5
    assert ch["locations"][0]["rank"] == 1
    assert hw["locations"][0]["rank"] == 1


def test_setup_solo_has_payback():
    s = intelligence.setup_plan("solo")
    assert s["plan"]["capex_total_inr"] > 0
    assert s["plan"]["payback_months"] > 0


def test_forecast_grows_monotonically():
    f = intelligence.growth_forecast()
    totals = [r["total"] for r in f["tn_ev_stock_forecast"]]
    assert totals == sorted(totals)


def test_agent_classifies_district_question():
    r = run(Query(question="How many EVs are registered in Coimbatore?"))
    assert r.intent == "registrations"
    assert "Coimbatore" in r.summary


def test_agent_classifies_highway_question():
    r = run(Query(question="What are the best future highway locations for fast chargers?"))
    assert r.intent == "future_locations"


def test_agent_classifies_setup_cost_question():
    r = run(Query(question="What's the lowest cost setup plan for a single station?"))
    assert r.intent == "setup_plan"


def test_api_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200


def test_api_registrations_district():
    r = client.get("/registrations", params={"district": "Madurai"})
    assert r.status_code == 200
    assert r.json()["district"] == "Madurai"


def test_api_stations_highway_only():
    r = client.get("/stations", params={"highway_only": True})
    assert r.status_code == 200
    j = r.json()
    assert all(s["highway"] for s in j["stations"])


def test_api_ask_summary():
    r = client.post("/ask", json={"question": "Give me a market summary"})
    assert r.status_code == 200
    j = r.json()
    assert j["intent"] in {"summary", "registrations"}
    assert j["summary"]
