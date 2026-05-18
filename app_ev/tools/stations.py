"""Public-charging station lookup + economics."""
from __future__ import annotations

from app_ev.tools.data_loader import stations


def list_stations(
    district: str | None = None,
    highway_only: bool = False,
    site_class: str | None = None,
) -> dict:
    data = stations()
    rows = data["stations"]
    if district:
        rows = [s for s in rows if s["district"].lower() == district.lower()]
    if highway_only:
        rows = [s for s in rows if s.get("highway")]
    if site_class:
        rows = [s for s in rows if s.get("site_class") == site_class]
    return {
        "as_of": data["as_of"],
        "source": data["source"],
        "count": len(rows),
        "stations": rows,
    }


def station_detail(station_id: str) -> dict | None:
    for s in stations()["stations"]:
        if s["id"].lower() == station_id.lower():
            return s
    return None


def station_economics(station_id: str | None = None) -> dict:
    """Per-station P&L for last 30 days. If station_id omitted, returns portfolio."""
    data = stations()
    if station_id:
        s = station_detail(station_id)
        if not s:
            return {"error": f"station {station_id} not found"}
        return _econ_row(s)
    return {
        "as_of": data["as_of"],
        "portfolio": [_econ_row(s) for s in data["stations"]],
        "totals": data["summary"],
    }


def portfolio_summary() -> dict:
    """Total charging stations breakdown: counts by site class, connector type, installed kW."""
    data = stations()
    rows = data["stations"]
    total = len(rows)
    by_site = {
        "chennai_city": sum(1 for s in rows if s["district"] == "Chennai" and not s.get("highway") and s.get("site_class") != "it_park"),
        "highway":      sum(1 for s in rows if s.get("highway")),
        "it_park":      sum(1 for s in rows if s.get("site_class") == "it_park"),
        "other_city":   sum(1 for s in rows if s["district"] != "Chennai" and not s.get("highway") and s.get("site_class") != "it_park"),
    }
    by_district: dict[str, int] = {}
    for s in rows:
        by_district[s["district"]] = by_district.get(s["district"], 0) + 1

    connector_bays: dict[str, int] = {}
    connector_kw: dict[str, float] = {}
    total_installed_kw = 0.0
    total_bays = 0
    for s in rows:
        for c in s["connectors"]:
            key = c["type"]
            connector_bays[key] = connector_bays.get(key, 0) + c["count"]
            connector_kw[key] = connector_kw.get(key, 0) + c["kw"] * c["count"]
            total_installed_kw += c["kw"] * c["count"]
            total_bays += c["count"]

    return {
        "as_of": data["as_of"],
        "source": data["source"],
        "total_charging_stations": total,
        "total_bays": total_bays,
        "total_installed_kw": int(total_installed_kw),
        "by_site_class": by_site,
        "by_district": dict(sorted(by_district.items(), key=lambda kv: -kv[1])),
        "connectors": [
            {"type": t, "bays": connector_bays[t], "installed_kw": int(connector_kw[t])}
            for t in sorted(connector_bays, key=lambda k: -connector_bays[k])
        ],
        "totals_30d": data["summary"],
    }


def _econ_row(s: dict) -> dict:
    rev = s["revenue_30d"]
    exp = s["expenses_30d"]
    sessions = s["sessions_30d"]
    return {
        "id": s["id"],
        "name": s["name"],
        "district": s["district"],
        "highway": s.get("highway", False),
        "sessions_30d": sessions,
        "revenue_30d_inr": rev,
        "expenses_30d_inr": exp,
        "gross_margin_inr": rev - exp,
        "gross_margin_pct": round((rev - exp) / rev * 100, 1) if rev else 0,
        "revenue_per_session_inr": round(rev / sessions, 1) if sessions else 0,
        "uptime_pct": s["uptime_pct"],
    }
