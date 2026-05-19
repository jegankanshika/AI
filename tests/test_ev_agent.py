"""Smoke tests for the EV Charging agent + API."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app_ev.agent.runner import run
from app_ev.api.main import app
from app_ev.schemas import Query
from app_ev.tools import charger_catalog, intelligence, registrations, stations

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


def test_stations_portfolio_summary():
    s = stations.portfolio_summary()
    assert s["total_charging_stations"] == len(stations.list_stations()["stations"])
    classes = s["by_site_class"]
    assert classes["chennai_city"] + classes["highway"] + classes["it_park"] + classes["other_city"] == s["total_charging_stations"]
    assert s["total_bays"] > 0 and s["total_installed_kw"] > 0
    assert {"CCS2", "Type2 AC"}.issubset({c["type"] for c in s["connectors"]})


def test_api_stations_summary():
    r = client.get("/stations/summary")
    assert r.status_code == 200
    j = r.json()
    assert j["total_charging_stations"] >= 30


def test_api_stations_it_park_filter():
    r = client.get("/stations", params={"site_class": "it_park"})
    assert r.status_code == 200
    j = r.json()
    assert j["count"] >= 5
    assert all(s.get("site_class") == "it_park" for s in j["stations"])
    assert all(s.get("site_host") for s in j["stations"])


def test_partners_has_it_park_category():
    data = intelligence.list_partners()
    titles = [c["category"].lower() for c in data["categories"]]
    assert any("it park" in t for t in titles)
    it = next(c for c in data["categories"] if "it park" in c["category"].lower())
    assert len(it["contacts"]) >= 5
    assert any("tidel" in (c["name"].lower()) for c in it["contacts"])


def test_agent_routes_it_park_partner_question():
    r = run(Query(question="Who is the leasing contact at TIDEL Park?"))
    assert r.intent == "partners"
    cats = [c["category"].lower() for c in r.data["categories"]]
    assert any("it park" in c for c in cats)


def test_stations_summary_includes_it_park_count():
    data = stations.list_stations()
    # The bundled JSON summary should now include IT-park stations
    assert any(s.get("site_class") == "it_park" for s in data["stations"])



def test_charger_catalog_has_all_classes():
    d = charger_catalog.list_chargers()
    assert d["count"] >= 10
    classes = {c["current_type"] for c in d["chargers"]}
    assert "AC" in classes and "DC Fast" in classes and "DC Ultra-Fast" in classes
    for c in d["chargers"]:
        assert c["best_usage_timing"]
        assert len(c["benefits"]) >= 1


def test_custom_setup_solo_dc60():
    out = charger_catalog.custom_setup([{"id": "DC-60-CCS2", "count": 1}])
    t = out["totals"]
    assert t["bays"] == 1 and t["installed_kw"] == 60
    assert t["capex_total_inr"] > t["equipment_capex_inr"]
    assert t["monthly_revenue_inr"] > 0


def test_custom_setup_mixed_highway():
    out = charger_catalog.custom_setup(
        [{"id": "DC-240-CCS2", "count": 2}, {"id": "DC-120-CCS2", "count": 2}],
        site_class="highway",
    )
    t = out["totals"]
    assert t["bays"] == 4 and t["installed_kw"] == 720
    assert t["payback_months"] is None or t["payback_months"] > 0


def test_effectiveness_ranking_returns_most_effective():
    r = charger_catalog.effectiveness_ranking()
    assert "most_effective" in r and r["most_effective"]["annual_roi_pct"] is not None
    assert r["ranking"][0]["id"] == r["most_effective"]["id"]


def test_api_charger_types():
    r = client.get("/charger-types")
    assert r.status_code == 200 and r.json()["count"] >= 10


def test_api_setup_custom():
    r = client.post(
        "/setup/custom",
        json={"selections": [{"id": "AC-22-TYPE2", "count": 4}], "site_class": "city"},
    )
    assert r.status_code == 200
    assert r.json()["totals"]["bays"] == 4


def test_api_setup_effective():
    r = client.get("/setup/effective", params={"site_class": "highway"})
    assert r.status_code == 200
    assert r.json()["most_effective"]["label"]


def test_refresh_skips_when_envs_unset(monkeypatch):
    for v in ["VAHAN_TN_URL", "BEE_PCS_URL", "CHALLENGES_FEED_URL", "FORECAST_URL"]:
        monkeypatch.delenv(v, raising=False)
    from app_ev import refresh
    out = refresh.refresh_all()
    assert out["errors"] == 0
    assert all(r["status"] == "skipped" for r in out["results"])


def test_api_ask_summary():
    r = client.post("/ask", json={"question": "Give me a market summary"})
    assert r.status_code == 200
    j = r.json()
    assert j["intent"] in {"summary", "registrations"}
    assert j["summary"]
