# EV Charging Co-Pilot — Tamil Nadu

An agent + browser UI that gives an EV-charging company end-to-end market
intelligence and site-planning for Tamil Nadu. Covers district-wise EV
registrations, public charging stations with per-station P&L, ranked
challenges + solutions, demand-weighted future site recommendations
(Chennai + highway + IT-park / Tech-SEZ), partner contacts with
playbooks, lowest-cost setup plans and partner-vendor comparison, a
charger-type catalog with cost / payback calculator, and a 2030 TN EV
stock + charging-demand forecast.

See `ev_charging_design.md` for the full design, data dictionary, and
roadmap.

---

## Run

```bash
pip install -r requirements.txt
uvicorn app_ev.api.main:app --reload --port 8001
# UI:  http://localhost:8001/
```

Try the natural-language interface:

```bash
curl -s localhost:8001/ask \
  -H "content-type: application/json" \
  -d '{"question":"Show me future highway charging locations"}' | jq
```

Or hit any tool endpoint directly:

| Tool | Endpoint |
|---|---|
| TN state summary | `GET /registrations/summary` |
| District-wise EV counts + RTO locations | `GET /registrations` (or `?district=Chennai`) |
| All public stations | `GET /stations` (filters: `?district=`, `?highway_only=true`, `?site_class=it_park`) |
| Total charging stations breakdown | `GET /stations/summary` |
| Portfolio P&L | `GET /economics` |
| Challenges + solutions | `GET /challenges` |
| Future site recommendations | `GET /future?scope=chennai\|highway` |
| Partner contacts + playbooks | `GET /partners` (filter `?category=it+park`, `fuel`, `mall`, `oem`, `fleet`, `discom`) |
| Charger-type catalog | `GET /charger-types` |
| Lowest-cost setup plan | `GET /setup?mode=solo\|partner\|all` |
| Custom setup plan calculator | `POST /setup/custom` |
| Most-effective charger ranking | `GET /setup/effective` |
| TN EV growth forecast to 2030 | `GET /forecast` |
| Manual data refresh | `POST /refresh` |

---

## Tests

```bash
pytest                                # 29 smoke tests
```

CI runs the same suite on Python 3.11 and 3.12 on every push and PR
against `main`.

---

## Data refresh

`app_ev/refresh.py` pulls upstream JSON daily into the bundled snapshots
in `app_ev/data/*.json`. Three run modes:

1. **In-process scheduler** — the FastAPI app starts a 24 h asyncio loop
   on startup (`app_ev/api/main.py` lifespan).
2. **Cron** — `0 3 * * * cd /srv/ai && python -m app_ev.refresh`.
3. **Manual** — `POST /refresh`.

A Playwright scraper at `scripts/scrape_vahan_tn.py` produces the VAHAN
TN registrations JSON in the exact schema the agent consumes. A GitHub
Actions workflow at `.github/workflows/refresh-snapshots.yml` runs it
daily at 03:00 IST and publishes to an orphan `data-snapshots` branch
so `VAHAN_TN_URL` can point at a stable raw URL.

When an upstream URL env var is unset, that source is skipped and the
bundled snapshot is retained — dev / CI never breaks.

---

## Layout

| Path | What's there |
|---|---|
| `app_ev/` | Agent vertical slice — schemas, deterministic tools, intent router, FastAPI service, single-page UI. |
| `app_ev/data/` | Bundled JSON datasets (VAHAN, BEE PCS, challenges, future sites, partners, setup plans, charger catalog, growth forecast). |
| `app_ev/refresh.py` | Daily upstream-pull job. |
| `app_ev/api/main.py` | FastAPI service + UI mount. |
| `app_ev/ui/index.html` | Single-page UI to browse every slice. |
| `ev_charging_design.md` | Design doc — architecture, data dictionary, roadmap. |
| `scripts/scrape_vahan_tn.py` | Playwright scraper for the VAHAN dashboard. |
| `.claude/skills/ev-charging/SKILL.md` | Skill for invoking the agent from Claude Code. |
| `.github/workflows/ci.yml` | Pytest matrix on Python 3.11 / 3.12. |
| `.github/workflows/refresh-snapshots.yml` | Daily VAHAN scrape + publish to `data-snapshots` branch. |
| `tests/test_ev_agent.py` | Pytest smoke suite over the tools, agent, and API. |
