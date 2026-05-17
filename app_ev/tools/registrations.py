"""Registered-EV lookup: district-wise + RTO locations."""
from __future__ import annotations

from app_ev.tools.data_loader import registrations


def list_districts(top_n: int | None = None) -> dict:
    data = registrations()
    rows = sorted(data["districts"], key=lambda d: d["registered_evs"], reverse=True)
    if top_n:
        rows = rows[:top_n]
    return {
        "as_of": data["as_of"],
        "source": data["source"],
        "state_total": data["total_registered_evs"],
        "districts": rows,
    }


def district_detail(district: str) -> dict | None:
    data = registrations()
    for d in data["districts"]:
        if d["district"].lower() == district.lower():
            return {"as_of": data["as_of"], "source": data["source"], **d}
    return None


def state_summary() -> dict:
    data = registrations()
    two = sum(d["two_wheeler"] for d in data["districts"])
    three = sum(d["three_wheeler"] for d in data["districts"])
    four = sum(d["four_wheeler"] for d in data["districts"])
    bus = sum(d["bus_truck"] for d in data["districts"])
    return {
        "as_of": data["as_of"],
        "state": data["state"],
        "total": data["total_registered_evs"],
        "two_wheeler": two,
        "three_wheeler": three,
        "four_wheeler": four,
        "bus_truck": bus,
        "districts_covered": len(data["districts"]),
    }
