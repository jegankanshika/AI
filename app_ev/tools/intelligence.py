"""Challenges, future locations, partners, setup plans, growth forecasts."""
from __future__ import annotations

from app_ev.tools.data_loader import (
    challenges as _challenges,
    future_locations as _future_locations,
    growth_forecast as _growth_forecast,
    partners as _partners,
    setup_plans as _setup_plans,
)


def list_challenges(severity: str | None = None) -> dict:
    data = _challenges()
    rows = data["challenges"]
    if severity:
        rows = [c for c in rows if c["severity"].lower() == severity.lower()]
    return {"as_of": data["as_of"], "count": len(rows), "challenges": rows}


def future_chennai_locations(top_n: int = 10) -> dict:
    data = _future_locations()
    return {
        "as_of": data["as_of"],
        "model": data["model"],
        "scope": "chennai",
        "locations": data["chennai"][:top_n],
    }


def future_highway_locations(top_n: int = 10) -> dict:
    data = _future_locations()
    return {
        "as_of": data["as_of"],
        "model": data["model"],
        "scope": "highway",
        "locations": data["highway"][:top_n],
    }


def list_partners(category: str | None = None) -> dict:
    data = _partners()
    cats = data["categories"]
    if category:
        cats = [c for c in cats if category.lower() in c["category"].lower()]
    return {"as_of": data["as_of"], "categories": cats}


def setup_plan(mode: str = "all") -> dict:
    """mode: 'solo' | 'partner' | 'all'"""
    data = _setup_plans()
    if mode == "solo":
        return {"as_of": data["as_of"], "plan": data["lowest_cost_individual"]}
    if mode == "partner":
        return {"as_of": data["as_of"], "plans": data["partner_vendor_models"]}
    return data


def growth_forecast() -> dict:
    return _growth_forecast()
