"""FastAPI service for the EV Charging agent.

Run:  uvicorn app_ev.api.main:app --reload --port 8001
UI:   http://localhost:8001/
API:  POST /ask, GET /registrations, /stations, /challenges, /future,
      /partners, /setup, /setup/custom, /setup/effective, /forecast,
      /charger-types, POST /refresh
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query as Q
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app_ev.agent.runner import run
from app_ev.refresh import refresh_all
from app_ev.schemas import Query
from app_ev.tools import charger_catalog, intelligence, registrations, stations

log = logging.getLogger("app_ev.api")

REFRESH_INTERVAL_SEC = 24 * 60 * 60  # daily


async def _daily_refresh_loop() -> None:
    while True:
        try:
            log.info("running scheduled daily data refresh")
            out = refresh_all()
            log.info("daily refresh: %s", out)
        except Exception:
            log.exception("daily refresh loop crashed; will retry next cycle")
        await asyncio.sleep(REFRESH_INTERVAL_SEC)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_daily_refresh_loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="EV Charging Co-Pilot", version="0.2.0", lifespan=lifespan)

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


@app.get("/charger-types")
def charger_types_endpoint(current_type: str | None = None) -> dict:
    return charger_catalog.list_chargers(current_type=current_type)


@app.get("/charger-types/{charger_id}")
def charger_type_endpoint(charger_id: str) -> dict:
    c = charger_catalog.charger_detail(charger_id)
    if not c:
        raise HTTPException(404, f"charger {charger_id!r} not found")
    return c


class SetupSelection(BaseModel):
    id: str
    count: int = 1


class CustomSetupRequest(BaseModel):
    selections: list[SetupSelection] = Field(..., min_length=1)
    utilization_pct: float = 100.0
    site_class: str = Field("city", pattern="^(city|highway|depot)$")


@app.post("/setup/custom")
def setup_custom_endpoint(req: CustomSetupRequest) -> dict:
    out = charger_catalog.custom_setup(
        [s.model_dump() for s in req.selections],
        utilization_pct=req.utilization_pct,
        site_class=req.site_class,
    )
    if "error" in out:
        raise HTTPException(422, out["error"])
    return out


@app.get("/setup/effective")
def setup_effective_endpoint(
    site_class: str = Q("city", pattern="^(city|highway|depot)$"),
    utilization_pct: float = 100.0,
) -> dict:
    return charger_catalog.effectiveness_ranking(
        site_class=site_class, utilization_pct=utilization_pct
    )


@app.post("/refresh")
def refresh_endpoint() -> dict:
    """Trigger an immediate data refresh from configured upstream sources."""
    return refresh_all()
