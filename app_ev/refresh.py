"""Daily data refresh job.

Pulls live data from configured upstream sources and rewrites the bundled JSON
files in `app_ev/data/`. Falls back to the existing snapshot if an upstream is
unreachable (so we never go to a broken state).

Run once:
    python -m app_ev.refresh

Run as a daily scheduled task — three options:

1. **In-process** (default): the FastAPI app starts a background asyncio loop
   that fires `refresh_all()` every 24 h. See `app_ev/api/main.py` lifespan.
2. **Cron** (recommended for production):
       0 3 * * *  cd /srv/ai && python -m app_ev.refresh >> /var/log/ev_refresh.log 2>&1
3. **systemd timer** — equivalent to cron with journald logging.

Configuration (env vars; all optional):
    VAHAN_TN_URL              JSON feed of TN registrations by district
    BEE_PCS_URL               JSON feed of public charging stations
    TANGEDCO_TARIFF_URL       latest EV charging tariff schedule
    CHALLENGES_FEED_URL       internal ops feed
    FORECAST_URL              analyst forecast endpoint

If a URL env var is not set, the corresponding loader keeps the bundled
snapshot — useful in dev / CI / air-gapped demos.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import sys
from pathlib import Path
from urllib import request
from urllib.error import URLError

log = logging.getLogger("app_ev.refresh")
DATA_DIR = Path(__file__).resolve().parent / "data"
TIMEOUT_SEC = 15


_SOURCES = {
    "tn_ev_registrations.json": "VAHAN_TN_URL",
    "charging_stations.json": "BEE_PCS_URL",
    "challenges.json": "CHALLENGES_FEED_URL",
    "growth_forecast.json": "FORECAST_URL",
}


def _fetch_json(url: str) -> dict | list:
    req = request.Request(url, headers={"user-agent": "app_ev-refresh/1.0"})
    with request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _write_atomic(target: Path, payload: dict | list) -> None:
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(target)


def refresh_one(filename: str, env_var: str) -> dict:
    target = DATA_DIR / filename
    url = os.environ.get(env_var)
    if not url:
        return {"file": filename, "status": "skipped", "reason": f"{env_var} not set"}
    try:
        payload = _fetch_json(url)
        if isinstance(payload, dict):
            payload.setdefault("as_of", _dt.date.today().isoformat())
        _write_atomic(target, payload)
        return {"file": filename, "status": "ok", "url": url}
    except (URLError, json.JSONDecodeError, TimeoutError) as e:
        log.warning("refresh failed for %s: %s — keeping existing snapshot", filename, e)
        return {"file": filename, "status": "error", "url": url, "error": str(e)}


def refresh_all() -> dict:
    results = [refresh_one(f, v) for f, v in _SOURCES.items()]
    # invalidate the lru_cache so subsequent loads pick up new content
    from app_ev.tools.data_loader import _load
    _load.cache_clear()
    return {
        "ran_at": _dt.datetime.utcnow().isoformat() + "Z",
        "results": results,
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
        "errors": sum(1 for r in results if r["status"] == "error"),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    out = refresh_all()
    print(json.dumps(out, indent=2))
    sys.exit(0 if out["errors"] == 0 else 1)
