"""Offline EV agent — deterministic intent router over the tool surface.

Routes a natural-language question to one or more tools and returns an
AgentResponse. Designed to run without an LLM (CI/UI). A live LLM path can be
swapped in by reusing the same tool functions through Anthropic tool-use.
"""
from __future__ import annotations

import re

from app_ev.schemas import AgentResponse, Query, ToolCall
from app_ev.tools import intelligence, registrations, stations

_DISTRICT_RX = re.compile(r"\b(?:in|for|at)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)")


def _detect_district(q: str) -> str | None:
    m = _DISTRICT_RX.search(q)
    if not m:
        return None
    candidate = m.group(1).strip()
    for d in registrations.list_districts()["districts"]:
        if d["district"].lower() == candidate.lower():
            return d["district"]
    return None


def classify(q: str, district: str | None = None) -> str:
    s = q.lower()
    if any(w in s for w in ["forecast", "predict", "growth", "2030", "future market", "projection"]):
        return "growth_forecast"
    if ("future" in s and any(w in s for w in ["location", "site", "place", "station"])) or any(
        w in s for w in ["new location", "where to start", "site selection", "siting", "expansion plan", "best location", "next station"]
    ):
        return "future_locations"
    if any(w in s for w in ["partner", "contact", "vendor", "tata power", "ather", "hpcl", "iocl", "bpcl", "tangedco", "site host", "it park", "tech park", "sez", "tidel"]):
        return "partners"
    if any(w in s for w in ["setup", "capex", "opex", "lowest cost", "cheap", "franchise", "setup plan", "build a station"]):
        return "setup_plan"
    if any(w in s for w in ["challenge", "issue", "problem", "risk", "solution"]):
        return "challenges"
    if any(w in s for w in ["revenue", "profit", "expense", "session", "p&l", "economics", "uptime", "margin"]):
        return "station_economics"
    if any(w in s for w in ["station", "charger", "charging point", "where can i charge"]):
        return "stations"
    if any(w in s for w in ["registered", "registration", "ev count", "ev penetration", "district wise", "vahan", "rto", "how many ev", "no of ev", "number of ev"]):
        return "registrations"
    if district:
        return "registrations"
    return "summary"


def run(query: Query) -> AgentResponse:
    district = query.district or _detect_district(query.question)
    intent = classify(query.question, district=district)
    calls: list[ToolCall] = []
    cite = []

    if intent == "registrations":
        if district:
            data = registrations.district_detail(district) or {"error": f"district {district} not found"}
            calls.append(ToolCall(name="district_detail", args={"district": district}))
            summary = (
                f"{district} has {data.get('registered_evs', 0):,} registered EVs across "
                f"{len(data.get('rto_offices', []))} RTO offices."
                if "error" not in data else data["error"]
            )
        else:
            data = registrations.list_districts(query.top_n)
            calls.append(ToolCall(name="list_districts", args={"top_n": query.top_n}))
            summary = (
                f"Tamil Nadu has {data['state_total']:,} registered EVs. "
                f"Top district: {data['districts'][0]['district']} ({data['districts'][0]['registered_evs']:,})."
            )
        cite.append("VAHAN — vahan.parivahan.gov.in")

    elif intent == "stations":
        data = stations.list_stations(district=district, highway_only=query.highway_only)
        calls.append(ToolCall(name="list_stations", args={"district": district, "highway_only": query.highway_only}))
        scope = (district or "Tamil Nadu") + (" (highway only)" if query.highway_only else "")
        summary = f"Found {data['count']} public charging stations in {scope}."
        cite.append("BEE PCS dashboard + operator portals")

    elif intent == "station_economics":
        data = stations.station_economics()
        calls.append(ToolCall(name="station_economics", args={}))
        t = data["totals"]
        summary = (
            f"{t['total_stations']} stations did {t['total_sessions_30d']:,} sessions in last 30d. "
            f"Revenue INR {t['total_revenue_30d_inr']:,}, expenses INR {t['total_expenses_30d_inr']:,}, "
            f"avg uptime {t['avg_uptime_pct']}%."
        )

    elif intent == "challenges":
        data = intelligence.list_challenges()
        calls.append(ToolCall(name="list_challenges", args={}))
        summary = f"{data['count']} active challenges identified across grid, real-estate, utilization, and ops."

    elif intent == "future_locations":
        s = query.question.lower()
        scope = "highway" if "highway" in s or "nh" in s else "chennai"
        data = (intelligence.future_highway_locations(query.top_n or 10)
                if scope == "highway"
                else intelligence.future_chennai_locations(query.top_n or 10))
        calls.append(ToolCall(name=f"future_{scope}_locations", args={"top_n": query.top_n or 10}))
        top = data["locations"][0]
        summary = f"Top recommended {scope} location: {top['name']} (score {top['score']}, payback {top['payback_months']} months)."

    elif intent == "partners":
        cat = None
        s = query.question.lower()
        if "it park" in s or "tech park" in s or "sez" in s or "tidel" in s:
            cat = "it park"
        elif "fuel" in s or "hpcl" in s or "iocl" in s or "bpcl" in s:
            cat = "fuel retail"
        elif "mall" in s or "retail" in s:
            cat = "malls and retail"
        elif "govt" in s or "tangedco" in s or "discom" in s:
            cat = "discom"
        elif "oem" in s or "charger" in s and "vendor" in s:
            cat = "oem"
        elif "fleet" in s or "blusmart" in s or "ola" in s:
            cat = "fleet"
        data = intelligence.list_partners(cat)
        calls.append(ToolCall(name="list_partners", args={"category": cat}))
        total = sum(len(c["contacts"]) for c in data["categories"])
        summary = f"{total} verified partner contacts across {len(data['categories'])} categories."

    elif intent == "setup_plan":
        mode = "solo" if any(w in query.question.lower() for w in ["lowest", "cheap", "solo", "individual"]) else "all"
        data = intelligence.setup_plan(mode)
        calls.append(ToolCall(name="setup_plan", args={"mode": mode}))
        if mode == "solo":
            p = data["plan"]
            summary = (
                f"Solo lean plan: CapEx INR {p['capex_total_inr']:,}, "
                f"monthly OpEx INR {p['monthly_opex_inr']['total']:,}, payback {p['payback_months']} months."
            )
        else:
            summary = f"{len(data['comparison_summary'])} setup options compared (CapEx range INR 3.5L – 23.2L)."

    elif intent == "growth_forecast":
        data = intelligence.growth_forecast()
        calls.append(ToolCall(name="growth_forecast", args={}))
        ev_2030 = data["tn_ev_stock_forecast"][-1]["total"]
        chg_2030 = data["public_charging_demand_forecast"][-1]["public_chargers_needed"]
        summary = (
            f"TN EV stock forecast: {ev_2030:,} by 2030 (8.6x growth). "
            f"Public chargers required: {chg_2030:,}."
        )

    else:  # summary
        reg = registrations.state_summary()
        st = stations.list_stations()
        ch = intelligence.list_challenges()
        data = {
            "registrations": reg,
            "stations": st["count"],
            "challenges": ch["count"],
            "future_chennai_top": intelligence.future_chennai_locations(3)["locations"],
            "future_highway_top": intelligence.future_highway_locations(3)["locations"],
        }
        calls += [
            ToolCall(name="state_summary", args={}),
            ToolCall(name="list_stations", args={}),
            ToolCall(name="list_challenges", args={}),
            ToolCall(name="future_chennai_locations", args={"top_n": 3}),
            ToolCall(name="future_highway_locations", args={"top_n": 3}),
        ]
        summary = (
            f"TN: {reg['total']:,} EVs across {reg['districts_covered']} districts, "
            f"{st['count']} mapped public stations, {ch['count']} known challenges."
        )

    return AgentResponse(
        intent=intent,  # type: ignore[arg-type]
        summary=summary,
        data=data,
        tool_calls=calls,
        citations=cite,
    )
