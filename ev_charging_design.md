# EV Charging Co-Pilot — Tamil Nadu

An agent + UI that gives an EV-charging company end-to-end market intelligence
and site-planning for Tamil Nadu. Built as a vertical slice — JSON data
files stand in for live VAHAN / TANGEDCO / BEE PCS / CSMS feeds, the agent is
a deterministic intent router on top, and the FastAPI app serves both the
JSON tools and a single-page browser UI.

> Lives alongside the existing `app/` (Credit Co-Pilot) under `app_ev/`. They
> share the repo's Python deps but are independent services.

---

## 1. Requirements coverage

| # | Requirement | Where it's served |
|---|---|---|
| 1 | District-wise registered EVs in Tamil Nadu with exact registered locations (RTOs) | `app_ev/data/tn_ev_registrations.json` + `tools/registrations.py` + UI **Registered EVs** tab + `GET /registrations` |
| 2 | Installed public EV charging stations with location | `app_ev/data/charging_stations.json` + `tools/stations.py` + UI **Charging Stations** tab + `GET /stations` |
| 3 | Sessions per station + revenue + expenses | Same dataset; `tools/stations.station_economics()` + UI **Station P&L** tab + `GET /economics`, `GET /stations/{id}/economics` |
| 4 | Current challenges + solutions | `app_ev/data/challenges.json` + UI **Challenges** tab + `GET /challenges` |
| 5 | Future predicted sites — inside Chennai + on highways | `app_ev/data/future_locations.json` + UI **Future Locations** tab + `GET /future?scope=chennai\|highway` |
| 6 | Site/host contact details + how to proceed (playbook) | `app_ev/data/partners_contacts.json` + UI **Partners & Contacts** tab + `GET /partners` |
| 7 | Lowest-cost individual setup vs partner-vendor setup | `app_ev/data/setup_plans.json` + UI **Setup Plans** tab + `GET /setup` |
| 8 | Future growth predictions (TN EV stock, charging demand, revenue) | `app_ev/data/growth_forecast.json` + UI **Growth Forecast** tab + `GET /forecast` |
| 9 | All available charger kW types + benefits + best usage timing | `app_ev/data/charger_types.json` + UI **Charger Types** tab + `GET /charger-types` |
| 10 | Customize setup plan by picking chargers/kW; see cost & payback | `tools/charger_catalog.custom_setup()` + UI **Charger Calculator** tab + `POST /setup/custom` |
| 11 | Most-effective charger ranking (ROI-based) | `tools/charger_catalog.effectiveness_ranking()` + UI **Charger Calculator** tab + `GET /setup/effective` |
| 12 | Daily live-data refresh from upstream feeds | `app_ev/refresh.py` + in-process daily scheduler (lifespan task) + `POST /refresh` (manual trigger) |

The natural-language interface is `POST /ask` (UI **Ask the Agent** tab) — it
classifies intent, calls the right tool(s), and returns the structured payload
plus a one-line summary.

---

## 2. Architecture

```
+---------------------------+
|  Browser UI (single page) |  app_ev/ui/index.html
+-------------+-------------+
              |
              v
+---------------------------+
|  FastAPI service          |  app_ev/api/main.py
|  /ask, /registrations,    |
|  /stations, /economics,   |
|  /challenges, /future,    |
|  /partners, /setup,       |
|  /forecast                |
+-------------+-------------+
              |
              v
+---------------------------+
|  Agent runner (offline)   |  app_ev/agent/runner.py
|  intent classify -> tools |
+-------------+-------------+
              |
              v
+---------------------------+    +-----------------------------+
|  Tool surface             |    |  Data layer (JSON, cached)  |
|  registrations, stations, |--->|  app_ev/data/*.json         |
|  intelligence             |    |  (swap for VAHAN/TANGEDCO/  |
+---------------------------+    |   BEE PCS/CSMS APIs)        |
                                 +-----------------------------+
```

### Tool surface

| Tool | Inputs | Returns |
|---|---|---|
| `registrations.list_districts(top_n)` | `top_n?` | All districts ranked by EV count, with RTO offices |
| `registrations.district_detail(district)` | `district` | One district's full breakdown |
| `registrations.state_summary()` | — | TN totals by vehicle class |
| `stations.list_stations(district, highway_only)` | filters | Stations with location, connectors, uptime |
| `stations.station_economics(station_id?)` | optional id | 30-day P&L per station / portfolio |
| `intelligence.list_challenges(severity?)` | optional severity | Active issues + solutions |
| `intelligence.future_chennai_locations(top_n)` | `top_n` | Ranked Chennai sites with config + payback |
| `intelligence.future_highway_locations(top_n)` | `top_n` | Ranked highway sites with config + payback |
| `intelligence.list_partners(category?)` | filter | Site hosts, OEMs, discom, fleet anchors |
| `intelligence.setup_plan(mode)` | `solo\|partner\|all` | Bill of materials, OpEx, payback |
| `intelligence.growth_forecast()` | — | Stock / charger demand / revenue to 2030 |
| `charger_catalog.list_chargers(current_type?)` | `AC \| DC \| DC Fast \| DC Ultra-Fast` | Full kW catalog with benefits + timing |
| `charger_catalog.custom_setup(selections, utilization_pct, site_class)` | mix + scenario | CapEx breakdown, OpEx, monthly revenue, payback |
| `charger_catalog.effectiveness_ranking(site_class, utilization_pct)` | scenario | All chargers ranked by annual ROI; the `most_effective` highlighted |
| `refresh.refresh_all()` | — | Pulls upstream JSON feeds, atomic-writes data files |

### Charger types catalog (`app_ev/data/charger_types.json`)

12 charger SKUs across AC (3.3 / 7.4 / 11 / 22 kW), DC (15 GB/T, 30 / 60 CCS2, 50 CHAdeMO) and DC Fast / Ultra-Fast (120 / 180 / 240 / 350 kW CCS2). Each entry carries:

- electrical spec (voltage / amps / connector / OCPP version),
- per-session profile (hours, kWh),
- equipment CapEx (single unit),
- target vehicle classes (e-2W / e-3W / e-4W / e-LCV / e-HCV / e-bus),
- best-use narrative,
- benefits (3-5 bullets),
- best usage timing window,
- limitations.

### Setup calculator (`tools/charger_catalog.custom_setup`)

Inputs:

```jsonc
{
  "selections": [{"id": "DC-120-CCS2", "count": 2}, {"id": "AC-22-TYPE2", "count": 4}],
  "utilization_pct": 100,           // scales sessions/day vs the per-class default
  "site_class": "city"              // "city" | "highway" | "depot"
}
```

The calculator:

1. Sums equipment CapEx across selections.
2. Adds derived costs: civil (₹70k/bay), panel + cabling (18 % of equipment), transformer share (₹800/kW total), CSMS setup, signage/IoT/CCTV, permits + project mgmt (5 %), contingency (8 %).
3. Computes monthly OpEx: rent (scaled by `site_class`), demand charge (₹80/kW), CSMS subscription, insurance, marketing, technician share.
4. Computes monthly revenue: tariff varies by charger class (AC ₹14, DC slow ₹19, DC Fast ₹23, DC Ultra ₹27/kWh — `+₹2` on highway, `-₹3` on depot); sessions/day adjusted by `utilization_pct` and `site_class`.
5. Returns CapEx total, monthly gross margin, payback months, annual kWh delivered, plus the applicable subsidy stack.

### Daily data refresh (`app_ev/refresh.py`)

Refreshes the bundled JSON files from configured upstream URLs (`VAHAN_TN_URL`, `BEE_PCS_URL`, `CHALLENGES_FEED_URL`, `FORECAST_URL`). Three ways to run it:

1. **In-process daily scheduler** — `app_ev/api/main.py` registers a lifespan task that calls `refresh_all()` every 24 h while the FastAPI service is up.
2. **Cron** — `0 3 * * * cd /srv/ai && python -m app_ev.refresh >> /var/log/ev_refresh.log 2>&1`.
3. **Manual trigger** — `POST /refresh` runs the refresh on demand and returns a status report.

When an upstream env var is unset, that source is **skipped** (bundled snapshot retained) so dev/CI never breaks. Atomic file writes ensure partial failures don't leave corrupted data.

### Agent runner

`app_ev.agent.runner.run(Query)` classifies the question into one of
`registrations | stations | station_economics | challenges | future_locations |
partners | setup_plan | growth_forecast | summary`, calls the matching tool(s)
with extracted parameters (district, highway flag, top_n), and returns an
`AgentResponse` (Pydantic) with `summary`, `data`, `tool_calls`, `citations`.

The router is deterministic — no LLM required — so it runs in CI and inside
the UI without an API key. The same tools can be wrapped as Anthropic
tool-use schemas to drive a live `claude-opus-4-7` path later (mirror the
pattern in `app/agent/graph.py`).

---

## 3. Data dictionary

Each JSON file ships a top-level `source` and `as_of` so callers can show
provenance and freshness in the UI.

- **`tn_ev_registrations.json`** — 30 TN districts, registered EV count by
  class (2W/3W/4W/bus-truck), and the RTO office codes that issued the
  registrations (e.g. `TN01 Mylapore`, `TN02 Anna Nagar`). Provenance:
  vahan.parivahan.gov.in.
- **`charging_stations.json`** — 23 representative stations across Chennai +
  TN highways. Per station: operator, geocoded address, connector mix
  (CCS2 / CHAdeMO / Type2 AC / Ather), kW, sessions/revenue/expenses for
  trailing 30 days, uptime %, highway flag.
- **`challenges.json`** — 8 ranked challenges with description, impact, and
  2-3 concrete solutions each.
- **`future_locations.json`** — Top 10 Chennai sites + top 10 highway sites,
  scored on a demand-weighted formula (EVs within 5 km × traffic AADT ×
  charger gap × HT headroom), each with recommended charger config, CapEx
  estimate, and payback in months.
- **`partners_contacts.json`** — 5 partner categories (mall site hosts, fuel
  retail co-location, discom + govt, charger OEMs / CSMS, fleet anchor
  tenants) — each with a `playbook` (how to proceed) and verified org
  contacts (address, phone, email, notes).
- **`setup_plans.json`** — One lowest-cost individual plan (CapEx ~₹23.2 L,
  payback ~36 months) plus 4 partner-vendor models (CPO franchise,
  white-label CaaS, fuel-retail co-location, PPP govt land).
- **`growth_forecast.json`** — TN EV stock through 2030 (Bass diffusion fit),
  public charging demand, industry revenue / capex (₹ Cr), drivers, risks.

---

## 4. API surface

```
GET  /healthz                  -> {status: ok}
POST /ask                      -> {intent, summary, data, tool_calls, citations}
GET  /registrations            -> all districts (top_n? query)
GET  /registrations?district=X -> one district
GET  /registrations/summary    -> TN totals by class
GET  /stations                 -> all stations (district?, highway_only? filters)
GET  /stations/{id}            -> one station
GET  /stations/{id}/economics  -> single station P&L
GET  /economics                -> portfolio P&L
GET  /challenges               -> all challenges (severity? filter)
GET  /future?scope=chennai|highway&top_n=N
GET  /partners                 -> all partner categories (category? filter)
GET  /setup?mode=solo|partner|all
GET  /forecast                 -> TN EV stock / charging / revenue forecast
GET  /charger-types            -> all charger SKUs (filter: ?current_type=AC|DC|DC Fast|DC Ultra-Fast)
GET  /charger-types/{id}       -> one charger detail
POST /setup/custom             -> body: {selections, utilization_pct, site_class}; returns CapEx + payback
GET  /setup/effective          -> ranking by annual ROI; ?site_class=&utilization_pct=
POST /refresh                  -> trigger immediate refresh from configured upstream feeds
```

---

## 5. Running it

```bash
pip install -r requirements.txt
uvicorn app_ev.api.main:app --reload --port 8001
# UI:  http://localhost:8001/
# Try: curl -s localhost:8001/ask -d '{"question":"How many EVs in Coimbatore?"}' -H content-type:application/json | jq
```

The agent is also reachable from a Claude Code session via the
`/ev-charging` skill (`.claude/skills/ev-charging/SKILL.md`).

---

## 6. Extending — swap in live data

The JSON files are isolated behind `app_ev/tools/data_loader.py`. To plug in
live sources, replace each loader with an API call and keep the schema:

| Loader | Live source |
|---|---|
| `registrations()` | VAHAN dashboard CSV / JSON export (state-wise + district drill) |
| `stations()` | BEE PCS dashboard (data.gov.in) + operator OCPI endpoints |
| `challenges()` | Internal Confluence / ops review feed |
| `future_locations()` | In-house GIS scoring service (overlay VAHAN, traffic AADT, TANGEDCO feeder, competitor CSMS) |
| `partners()` | CRM (Salesforce / HubSpot) account export |
| `setup_plans()` | Finance team's deal-model sheet |
| `growth_forecast()` | Bass-diffusion model output + analyst overrides |

---

## 7. Roadmap

- **Live LLM path** — wrap tools as Anthropic tool-use; replace
  `agent.runner.run` with a graph node that lets `claude-opus-4-7` pick and
  sequence tools. Re-use `app/agent/graph.py` shape.
- **Map view** — render `charging_stations.json` + `future_locations.json` on
  a Leaflet map alongside the tables.
- **Deal pipeline** — convert each future location into a CRM opportunity with
  status (prospect → MoU → fitout → live).
- **Live CSMS plug-in** — pull real-time uptime + sessions from each
  operator's OCPP/OCPI endpoint instead of static fields.
