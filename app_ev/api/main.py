"""FastAPI service for the EV Charging agent.

Run:  uvicorn app_ev.api.main:app --reload --port 8001
UI:   http://localhost:8001/
API:  POST /ask, GET /registrations, /stations, /challenges, /future,
      /partners, /setup, /forecast
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query as Q
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app_ev.agent.runner import run
from app_ev.schemas import Query
from app_ev.tools import intelligence, registrations, stations

app = FastAPI(title="EV Charging Co-Pilot", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_UI = Path(__file__).resolve().parent.parent / "ui" / "index.html"


@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(_UI)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/ask")
def ask(query: Query) -> dict:
    resp = run(query)
    return resp.model_dump()


@app.get("/registrations")
def registrations_endpoint(district: str | None = None, top_n: int | None = None) -> dict:
    if district:
        d = registrations.district_detail(district)
        if not d:
            raise HTTPException(404, f"district {district!r} not found")
        return d
    return registrations.list_districts(top_n=top_n)


@app.get("/registrations/summary")
def registrations_summary() -> dict:
    return registrations.state_summary()


@app.get("/stations")
def stations_endpoint(district: str | None = None, highway_only: bool = False) -> dict:
    return stations.list_stations(district=district, highway_only=highway_only)


@app.get("/stations/{station_id}")
def station_endpoint(station_id: str) -> dict:
    s = stations.station_detail(station_id)
    if not s:
        raise HTTPException(404, f"station {station_id!r} not found")
    return s


@app.get("/stations/{station_id}/economics")
def station_economics_endpoint(station_id: str) -> dict:
    e = stations.station_economics(station_id)
    if "error" in e:
        raise HTTPException(404, e["error"])
    return e


@app.get("/economics")
def portfolio_economics() -> dict:
    return stations.station_economics()


@app.get("/challenges")
def challenges_endpoint(severity: str | None = None) -> dict:
    return intelligence.list_challenges(severity=severity)


@app.get("/future")
def future_endpoint(scope: str = Q("chennai", pattern="^(chennai|highway)$"), top_n: int = 10) -> dict:
    if scope == "highway":
        return intelligence.future_highway_locations(top_n=top_n)
    return intelligence.future_chennai_locations(top_n=top_n)


@app.get("/partners")
def partners_endpoint(category: str | None = None) -> dict:
    return intelligence.list_partners(category=category)


@app.get("/setup")
def setup_endpoint(mode: str = Q("all", pattern="^(solo|partner|all)$")) -> dict:
    return intelligence.setup_plan(mode)


@app.get("/forecast")
def forecast_endpoint() -> dict:
    return intelligence.growth_forecast()
