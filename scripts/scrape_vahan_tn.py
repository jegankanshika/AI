"""Scrape Tamil Nadu EV registrations from the VAHAN dashboard.

Outputs JSON in the exact shape `app_ev/tools/data_loader.registrations()`
consumes (see `app_ev/data/tn_ev_registrations.json`). Host the resulting
file at a stable URL (GitHub Pages, S3, raw branch) and point the
`VAHAN_TN_URL` env var at it; `app_ev/refresh.py` will pull it on its daily
cycle.

VAHAN's dashboard is a JSF/PrimeFaces app — there's no documented JSON API,
so this script drives it through Playwright. The selectors below match the
page as of 2026-05; if VAHAN ships a layout change, update the selectors in
``select_filter`` and ``scrape_rto`` (kept small + named for that reason).

Quickstart:
    pip install playwright
    playwright install chromium
    python scripts/scrape_vahan_tn.py --out tn_ev_registrations.json
    # then host the file and point VAHAN_TN_URL at its raw URL

GitHub Actions schedule that publishes to a `data-snapshots` branch is at
``.github/workflows/refresh-snapshots.yml``.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    sys.exit(
        "install playwright first:\n  pip install playwright\n  playwright install chromium"
    )

VAHAN_URL = (
    "https://vahan.parivahan.gov.in/vahan4dashboard/vahan/view/reportview.xhtml"
)

# RTO code -> district mapping for Tamil Nadu.
# Source: TN Transport Department list of RTO offices.
# Keep this stable — VAHAN reports against RTO codes, we roll up to districts.
RTO_TO_DISTRICT: dict[str, str] = {
    "TN01": "Chennai", "TN02": "Chennai", "TN03": "Chennai", "TN04": "Chennai",
    "TN05": "Chennai", "TN06": "Chennai", "TN07": "Chennai", "TN09": "Chennai",
    "TN10": "Chennai", "TN12": "Chennai", "TN13": "Chennai", "TN14": "Chennai",
    "TN18": "Chennai", "TN22": "Chennai",
    "TN20": "Tiruvallur", "TN21": "Kancheepuram", "TN85": "Kancheepuram",
    "TN23": "Vellore", "TN24": "Krishnagiri", "TN70": "Krishnagiri",
    "TN25": "Tiruvannamalai",
    "TN27": "Salem", "TN30": "Salem", "TN54": "Salem",
    "TN28": "Namakkal",
    "TN29": "Dharmapuri",
    "TN31": "Cuddalore",
    "TN32": "Villupuram",
    "TN33": "Erode", "TN34": "Erode", "TN56": "Erode",
    "TN36": "Tiruchirappalli", "TN45": "Tiruchirappalli",
    "TN37": "Coimbatore", "TN38": "Coimbatore", "TN66": "Coimbatore",
    "TN39": "Tiruppur", "TN41": "Tiruppur",
    "TN42": "The Nilgiris", "TN43": "The Nilgiris",
    "TN46": "Perambalur",
    "TN47": "Karur",
    "TN49": "Thanjavur", "TN52": "Thanjavur",
    "TN51": "Nagapattinam",
    "TN55": "Pudukkottai",
    "TN57": "Dindigul",
    "TN58": "Madurai", "TN59": "Madurai", "TN64": "Madurai",
    "TN60": "Theni",
    "TN61": "Ariyalur",
    "TN63": "Sivagangai",
    "TN65": "Ramanathapuram",
    "TN67": "Virudhunagar",
    "TN69": "Thoothukudi",
    "TN72": "Tirunelveli", "TN75": "Tirunelveli", "TN76": "Tirunelveli",
    "TN74": "Kanyakumari",
}

# VAHAN vehicle-class labels -> our schema buckets.
# Treat anything not matched as four_wheeler (the safe default for passenger).
VEH_CLASS_BUCKETS: dict[str, re.Pattern[str]] = {
    "two_wheeler": re.compile(r"(M-CYCLE|MOPED|SCOOTER|TWO WHEELER|MOTOR CYCLE)", re.I),
    "three_wheeler": re.compile(r"(THREE WHEEL|3 WHEEL|E-RICKSHAW|AUTO RICKSHAW|TROLLEY)", re.I),
    "bus_truck": re.compile(r"(BUS|TRUCK|LORRY|GOODS|HEAVY|HCV|MCV|TRACTOR)", re.I),
    "four_wheeler": re.compile(r"(MOTOR CAR|FOUR WHEEL|LMV|JEEP|TAXI|OMNI)", re.I),
}


def bucket(veh_class: str) -> str:
    for k, rx in VEH_CLASS_BUCKETS.items():
        if rx.search(veh_class):
            return k
    return "four_wheeler"


async def select_filter(page, control_selector: str, value: str) -> None:
    """Open a PrimeFaces dropdown and pick the option matching `value`."""
    await page.click(control_selector)
    await page.wait_for_timeout(350)
    await page.click(f"li[role='option']:has-text('{value}')")
    await page.wait_for_timeout(350)


async def scrape_rto(page, rto_code: str) -> dict[str, int]:
    """Returns {vehicle_class_label: count} for the currently selected RTO.

    Assumes state/X-axis/Y-axis/fuel filters are already set. Selects the
    RTO, clicks Refresh, parses the result table.
    """
    await select_filter(page, "#RTOSelectedJ", rto_code)
    await page.click("button:has-text('Refresh')")
    await page.wait_for_selector("#groupingTable_data tr", timeout=30_000)
    out: dict[str, int] = {}
    rows = await page.query_selector_all("#groupingTable_data tr")
    for row in rows:
        cells = await row.query_selector_all("td")
        if len(cells) < 2:
            continue
        label = (await cells[1].inner_text()).strip()
        try:
            count = int((await cells[-1].inner_text()).replace(",", "").strip())
        except ValueError:
            continue
        if label and count:
            out[label] = count
    return out


async def scrape_tn(headless: bool = True, limit_rtos: int | None = None) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(VAHAN_URL, wait_until="networkidle", timeout=60_000)

        # Static filters — set once.
        await select_filter(page, "#stateSelectedJ", "Tamil Nadu(TN)")
        await select_filter(page, "#xaxisVar", "Vehicle Class")
        await select_filter(page, "#yaxisVar", "Registrations")
        await select_filter(page, "#fuelSelectedJ", "ELECTRIC(BOV)")
        await select_filter(page, "#fromYearJ", "2020")
        await select_filter(page, "#toYearJ", str(dt.date.today().year))

        district_totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        district_rtos: dict[str, list[str]] = defaultdict(list)

        rtos = sorted(RTO_TO_DISTRICT)
        if limit_rtos:
            rtos = rtos[:limit_rtos]

        for rto in rtos:
            district = RTO_TO_DISTRICT[rto]
            district_rtos[district].append(rto)
            try:
                counts = await scrape_rto(page, rto)
            except Exception as e:  # noqa: BLE001
                print(f"[warn] {rto} ({district}) failed: {e}", file=sys.stderr)
                continue
            for label, n in counts.items():
                b = bucket(label)
                district_totals[district][b] += n
                district_totals[district]["registered_evs"] += n

        await browser.close()

    districts = []
    for d, totals in sorted(district_totals.items(), key=lambda kv: -kv[1]["registered_evs"]):
        districts.append({
            "district": d,
            "registered_evs": totals["registered_evs"],
            "two_wheeler": totals.get("two_wheeler", 0),
            "three_wheeler": totals.get("three_wheeler", 0),
            "four_wheeler": totals.get("four_wheeler", 0),
            "bus_truck": totals.get("bus_truck", 0),
            "rto_offices": district_rtos[d],
        })

    return {
        "source": "VAHAN dashboard (vahan.parivahan.gov.in) — scraped via Playwright",
        "state": "Tamil Nadu",
        "as_of": dt.date.today().isoformat(),
        "total_registered_evs": sum(d["registered_evs"] for d in districts),
        "districts": districts,
    }


def validate(payload: dict) -> None:
    assert payload["state"] == "Tamil Nadu", "state mismatch"
    assert payload["total_registered_evs"] > 0, "zero total — likely a selector regression"
    assert len(payload["districts"]) >= 20, "too few districts captured"
    for d in payload["districts"]:
        s = d["two_wheeler"] + d["three_wheeler"] + d["four_wheeler"] + d["bus_truck"]
        assert d["registered_evs"] == s, f"sum mismatch for {d['district']}"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, default=Path("tn_ev_registrations.json"))
    p.add_argument("--headed", action="store_true", help="show browser (for debugging)")
    p.add_argument("--limit-rtos", type=int, default=None, help="cap RTOs scraped (smoke test)")
    args = p.parse_args()
    data = asyncio.run(scrape_tn(headless=not args.headed, limit_rtos=args.limit_rtos))
    validate(data)
    args.out.write_text(json.dumps(data, indent=2))
    print(
        f"wrote {args.out} — {data['total_registered_evs']:,} EVs "
        f"across {len(data['districts'])} districts (as_of {data['as_of']})"
    )


if __name__ == "__main__":
    main()
