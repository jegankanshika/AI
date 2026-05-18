# scripts/

Utility scripts that aren't part of the runtime services.

| Script | Purpose |
|---|---|
| `make_sample_pdfs.py` | Generates sample paystub/W2/bank-statement PDFs for the Credit Co-Pilot UI. |
| `scrape_vahan_tn.py` | Playwright scraper for the VAHAN dashboard — outputs Tamil Nadu EV registrations in the schema `app_ev` consumes. Run daily on CI and publish to a static URL; point `VAHAN_TN_URL` at that URL so the EV agent's refresh loop picks up fresh data. |

## VAHAN scraper — quick start

```bash
pip install playwright
playwright install chromium

# smoke test against a handful of RTOs
python scripts/scrape_vahan_tn.py --out tn_ev_registrations.json --limit-rtos 4 --headed

# full scrape (~5-10 minutes)
python scripts/scrape_vahan_tn.py --out tn_ev_registrations.json
```

The script:

- Drives `vahan.parivahan.gov.in/vahan4dashboard/vahan/view/reportview.xhtml`
  (the dashboard has no documented JSON API; it's a JSF/PrimeFaces page).
- Selects State = **Tamil Nadu (TN)**, Fuel = **ELECTRIC (BOV)**, X-Axis =
  **Vehicle Class**, Y-Axis = **Registrations**, year range **2020 → current**.
- Iterates every TN RTO (see `RTO_TO_DISTRICT` for the mapping), parses the
  result table, and rolls counts up to district + vehicle-class buckets.
- Validates the output (district count, sum invariants) before writing.
- Emits JSON matching `app_ev/data/tn_ev_registrations.json` exactly, so the
  refresh loop can swap it in atomically.

## Hosting the output

`.github/workflows/refresh-snapshots.yml` runs the scraper daily at 03:00 IST
and publishes the JSON to an orphan `data-snapshots` branch. Once the workflow
has run once, the raw URL is:

```
https://raw.githubusercontent.com/<owner>/<repo>/data-snapshots/tn/tn_ev_registrations.json
```

Wire it into the EV agent:

```bash
export VAHAN_TN_URL="https://raw.githubusercontent.com/<owner>/<repo>/data-snapshots/tn/tn_ev_registrations.json"
# restart the EV API — the daily refresh loop will pull from here from now on,
# or trigger immediately:
curl -X POST http://localhost:8001/refresh
```

## Maintenance

VAHAN periodically tweaks the dashboard's DOM (form IDs, table structure). When
that happens, only the small **selectors block** in `scrape_vahan_tn.py` needs
updating — the data shape and downstream agent code stay unchanged. Check
these spots first if a run fails:

- `select_filter()` — assumes PrimeFaces `<li role="option">` items.
- `scrape_rto()` — assumes the result table id is `#groupingTable_data` and the
  vehicle-class label sits in the second column.
