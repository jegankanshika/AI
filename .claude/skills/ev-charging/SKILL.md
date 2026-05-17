---
name: ev-charging
description: EV-charging market intelligence + site planning for Tamil Nadu. Use when the user asks about district-wise registered EVs in TN, public charging stations, station economics (sessions/revenue/expenses/uptime), industry challenges and solutions, future charging-station locations (in Chennai or on highways), partner/vendor contacts, lowest-cost setup plans, or growth forecasts. Routes via the local `app_ev` agent at http://localhost:8001 (start with `uvicorn app_ev.api.main:app --reload --port 8001`).
---

# /ev-charging — EV Charging Co-Pilot (Tamil Nadu)

Invoke this skill to answer EV-charging-company questions about Tamil Nadu.
The agent + UI live under `app_ev/`. Data sources are documented in
`ev_charging_design.md`.

## When to use

Trigger on any of:
- "Registered EVs in TN / Chennai / Coimbatore / <district>"
- "Public charging stations" / "where can I charge" / list stations
- "Revenue / expenses / sessions / uptime / P&L" for stations
- "Challenges" / "issues" / "problems" / "solutions" in EV charging
- "Where should we build the next charging station" / "future locations" /
  "site selection" (inside Chennai or on highways)
- "Partner contacts" / "site host" / "fuel retail co-location" / "OEM"
- "Lowest cost setup" / "individual vs partner" / "franchise" plan
- "Forecast" / "growth" / "2030 prediction"

## How to run

1. **Start the service** if it isn't already running:

   ```bash
   uvicorn app_ev.api.main:app --reload --port 8001
   ```

   Open `http://localhost:8001/` for the browser UI.

2. **Ask the agent** programmatically:

   ```bash
   curl -s localhost:8001/ask \
     -H "content-type: application/json" \
     -d '{"question":"How many EVs are registered in Coimbatore and which RTOs?"}' | jq
   ```

3. **Or call a specific tool endpoint directly** (no NLU step):

   | Need | Endpoint |
   |---|---|
   | District-wise EV counts + RTO locations | `GET /registrations` (or `?district=Chennai`) |
   | TN state summary by vehicle class | `GET /registrations/summary` |
   | All public charging stations | `GET /stations` (filters: `?district=`, `?highway_only=true`) |
   | One station details | `GET /stations/{id}` |
   | Station P&L portfolio | `GET /economics` |
   | Single station P&L | `GET /stations/{id}/economics` |
   | Challenges + solutions | `GET /challenges` (filter `?severity=high|medium|low`) |
   | Future Chennai sites | `GET /future?scope=chennai&top_n=10` |
   | Future highway sites | `GET /future?scope=highway&top_n=10` |
   | Partner contacts + playbook | `GET /partners` (filter `?category=fuel`, `mall`, `oem`, `fleet`, `discom`) |
   | Lowest-cost solo setup plan | `GET /setup?mode=solo` |
   | Partner-vendor setup options | `GET /setup?mode=partner` |
   | TN EV growth forecast to 2030 | `GET /forecast` |

## Output convention

- Always cite the `as_of` field from the response so the user knows data freshness.
- For multi-tool questions, prefer `POST /ask` — the agent will route, summarize, and return the structured payload.
- Surface coordinates as Google Maps links: `https://www.google.com/maps?q={lat},{lng}`.
- When discussing economics, quote both INR figures and per-session unit economics.

## Files

- `app_ev/` — agent code (schemas, tools, agent runner, FastAPI, UI)
- `app_ev/data/*.json` — bundled datasets (swap for live VAHAN / BEE PCS /
  TANGEDCO / CSMS feeds per `ev_charging_design.md` §6)
- `ev_charging_design.md` — full design + data dictionary + roadmap
- `tests/test_ev_agent.py` — smoke tests for the agent and API

## Limits / honesty

The bundled datasets are realistic approximations as of 2024-Q4 — they reflect
public TN/VAHAN/BEE figures rounded to whole numbers, but they are **not** a
live feed. Per-station revenue/expense numbers are operator-class averages,
not audited financials. For decisions, plug in live sources via the loaders
listed in `ev_charging_design.md`.
