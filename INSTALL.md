# Install & Run

## 1. Prerequisites

| Tool | Tested |
|---|---|
| Python | 3.11 / 3.12 |
| pip | latest |
| git | any |

## 2. Set up

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Run the agent + UI

```bash
uvicorn app_ev.api.main:app --reload --port 8001
# open http://localhost:8001/
```

## 4. Run the tests

```bash
pytest                              # 29 smoke tests over tools, agent, API
```

## 5. Optional — daily data refresh from real upstream sources

The bundled JSON in `app_ev/data/` is a snapshot. To pull live data,
either run the scraper manually:

```bash
# install Playwright once
pip install playwright
playwright install chromium

python scripts/scrape_vahan_tn.py --out app_ev/data/tn_ev_registrations.json
```

… or let the GitHub Actions workflow at
`.github/workflows/refresh-snapshots.yml` do it daily and publish the
JSON to an orphan `data-snapshots` branch. Then point the agent at the
hosted URL:

```bash
export VAHAN_TN_URL="https://raw.githubusercontent.com/<owner>/<repo>/data-snapshots/tn/tn_ev_registrations.json"
curl -X POST http://localhost:8001/refresh
```

See `scripts/README.md` for the full pipeline.
