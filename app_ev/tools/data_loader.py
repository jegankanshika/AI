"""Loads the static JSON data bundled with the agent.

In production these become live calls to VAHAN, BEE PCS dashboard, TANGEDCO and
CSMS APIs. For this slice they are file reads with an lru_cache.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=None)
def _load(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text())


def registrations() -> dict:
    return _load("tn_ev_registrations.json")


def stations() -> dict:
    return _load("charging_stations.json")


def challenges() -> dict:
    return _load("challenges.json")


def future_locations() -> dict:
    return _load("future_locations.json")


def partners() -> dict:
    return _load("partners_contacts.json")


def setup_plans() -> dict:
    return _load("setup_plans.json")


def growth_forecast() -> dict:
    return _load("growth_forecast.json")
