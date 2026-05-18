"""Charger-type catalog + custom setup-plan calculator + effectiveness ranking."""
from __future__ import annotations

from app_ev.tools.data_loader import _load


def _catalog() -> dict:
    return _load("charger_types.json")


def list_chargers(current_type: str | None = None) -> dict:
    data = _catalog()
    rows = data["chargers"]
    if current_type:
        ct = current_type.lower()
        rows = [c for c in rows if c["current_type"].lower().startswith(ct)]
    return {"as_of": data["as_of"], "count": len(rows), "chargers": rows}


def charger_detail(charger_id: str) -> dict | None:
    for c in _catalog()["chargers"]:
        if c["id"].lower() == charger_id.lower():
            return c
    return None


_SITE_OVERHEAD = {
    "civil_per_bay_inr": 70000,
    "panel_share_pct": 0.18,
    "transformer_share_inr_per_kw_total": 800,
    "csms_setup_inr": 80000,
    "signage_iot_cctv_inr": 60000,
    "permits_pm_pct": 0.05,
    "contingency_pct": 0.08,
}

_OPEX_MONTHLY = {
    "rent_or_revshare_inr": 60000,
    "csms_subscription_inr": 8000,
    "insurance_inr": 4000,
    "marketing_inr": 5000,
    "technician_share_inr": 12000,
    "demand_charge_inr_per_kw_total": 80,
}

_REV_DEFAULTS = {
    "tariff_inr_per_kwh_ac": 14,
    "tariff_inr_per_kwh_dc_slow": 19,
    "tariff_inr_per_kwh_dc_fast": 23,
    "tariff_inr_per_kwh_dc_ultra": 27,
    "sessions_per_day_ac": 6,
    "sessions_per_day_dc_slow": 10,
    "sessions_per_day_dc_fast": 12,
    "sessions_per_day_dc_ultra": 14,
}


def _tariff_and_sessions(c: dict) -> tuple[float, float]:
    ct = c["current_type"]
    if ct == "AC":
        return _REV_DEFAULTS["tariff_inr_per_kwh_ac"], _REV_DEFAULTS["sessions_per_day_ac"]
    if ct == "DC" and c["kw"] < 50:
        return _REV_DEFAULTS["tariff_inr_per_kwh_dc_slow"], _REV_DEFAULTS["sessions_per_day_dc_slow"]
    if ct == "DC":
        return _REV_DEFAULTS["tariff_inr_per_kwh_dc_slow"], _REV_DEFAULTS["sessions_per_day_dc_slow"]
    if ct == "DC Fast":
        return _REV_DEFAULTS["tariff_inr_per_kwh_dc_fast"], _REV_DEFAULTS["sessions_per_day_dc_fast"]
    return _REV_DEFAULTS["tariff_inr_per_kwh_dc_ultra"], _REV_DEFAULTS["sessions_per_day_dc_ultra"]


def custom_setup(
    selections: list[dict],
    utilization_pct: float = 100.0,
    site_class: str = "city",
) -> dict:
    """Compute CapEx + OpEx + payback for a user-defined charger mix.

    selections: list of {"id": <charger_id>, "count": <int>}
    utilization_pct: 0-100, scales sessions-per-day vs the default for that class.
    site_class: 'city' | 'highway' | 'depot' — modifies rent and tariff.
    """
    chargers = _catalog()["chargers"]
    by_id = {c["id"]: c for c in chargers}

    lines: list[dict] = []
    equipment_capex = 0
    total_kw = 0
    n_bays = 0
    monthly_revenue = 0
    annual_kwh = 0

    if not selections:
        return {"error": "selections empty; provide [{id, count}, ...]"}

    for sel in selections:
        cid = sel["id"]
        n = int(sel.get("count", 1))
        c = by_id.get(cid)
        if not c:
            return {"error": f"charger {cid} not in catalog"}
        tariff, base_sessions = _tariff_and_sessions(c)
        sessions_per_day = base_sessions * (utilization_pct / 100.0)
        if site_class == "highway":
            tariff += 2  # premium tariff
            sessions_per_day *= 0.85
        elif site_class == "depot":
            tariff -= 3
            sessions_per_day *= 1.4

        kwh_per_day = sessions_per_day * c["typical_kwh_per_session"]
        rev_per_unit_month = kwh_per_day * tariff * 30
        line_capex = c["equipment_capex_inr"] * n
        equipment_capex += line_capex
        total_kw += c["kw"] * n
        n_bays += n
        monthly_revenue += rev_per_unit_month * n
        annual_kwh += kwh_per_day * 365 * n
        lines.append({
            "id": cid,
            "label": c["label"],
            "count": n,
            "kw_each": c["kw"],
            "current_type": c["current_type"],
            "tariff_inr_per_kwh": tariff,
            "sessions_per_day_per_unit": round(sessions_per_day, 2),
            "monthly_revenue_per_unit_inr": int(rev_per_unit_month),
            "line_equipment_capex_inr": line_capex,
        })

    overhead = _SITE_OVERHEAD
    civil = overhead["civil_per_bay_inr"] * n_bays
    panel = int(equipment_capex * overhead["panel_share_pct"])
    transformer = int(total_kw * overhead["transformer_share_inr_per_kw_total"])
    csms_setup = overhead["csms_setup_inr"]
    signage = overhead["signage_iot_cctv_inr"]
    base_capex = equipment_capex + civil + panel + transformer + csms_setup + signage
    permits_pm = int(base_capex * overhead["permits_pm_pct"])
    contingency = int((base_capex + permits_pm) * overhead["contingency_pct"])
    capex_total = base_capex + permits_pm + contingency

    rent = _OPEX_MONTHLY["rent_or_revshare_inr"] * (1.6 if site_class == "highway" else 1.0 if site_class == "city" else 0.4)
    demand_charge = total_kw * _OPEX_MONTHLY["demand_charge_inr_per_kw_total"]
    monthly_opex = int(
        rent
        + demand_charge
        + _OPEX_MONTHLY["csms_subscription_inr"]
        + _OPEX_MONTHLY["insurance_inr"]
        + _OPEX_MONTHLY["marketing_inr"]
        + _OPEX_MONTHLY["technician_share_inr"]
    )

    monthly_revenue = int(monthly_revenue)
    monthly_gross = monthly_revenue - monthly_opex
    payback_months = round(capex_total / monthly_gross, 1) if monthly_gross > 0 else None

    return {
        "as_of": _catalog()["as_of"],
        "selections": lines,
        "site_class": site_class,
        "utilization_pct": utilization_pct,
        "totals": {
            "bays": n_bays,
            "installed_kw": total_kw,
            "equipment_capex_inr": equipment_capex,
            "civil_inr": civil,
            "panel_inr": panel,
            "transformer_inr": transformer,
            "csms_setup_inr": csms_setup,
            "signage_iot_cctv_inr": signage,
            "permits_pm_inr": permits_pm,
            "contingency_inr": contingency,
            "capex_total_inr": capex_total,
            "monthly_opex_inr": monthly_opex,
            "monthly_revenue_inr": monthly_revenue,
            "monthly_gross_margin_inr": monthly_gross,
            "annual_kwh_delivered": int(annual_kwh),
            "payback_months": payback_months,
        },
        "applicable_subsidies": [
            "TN EV Policy 2023: 25 % CapEx subsidy (first 5 000 stations)",
            "PM-eDrive highway scheme: up to 70 % CapEx (highway DC only)",
            "100 % SGST refund on charger purchase for 5 years",
        ],
    }


def effectiveness_ranking(site_class: str = "city", utilization_pct: float = 100.0) -> dict:
    """Rank all chargers by ROI proxy: monthly gross margin per ₹ of CapEx."""
    rows = []
    for c in _catalog()["chargers"]:
        plan = custom_setup([{"id": c["id"], "count": 1}], utilization_pct, site_class)
        t = plan["totals"]
        capex = t["capex_total_inr"]
        margin = t["monthly_gross_margin_inr"]
        roi = round(margin * 12 / capex * 100, 1) if capex else 0
        rows.append({
            "id": c["id"],
            "label": c["label"],
            "current_type": c["current_type"],
            "kw": c["kw"],
            "capex_total_inr": capex,
            "monthly_gross_margin_inr": margin,
            "annual_roi_pct": roi,
            "payback_months": t["payback_months"],
            "best_use": c["best_use"],
            "best_usage_timing": c["best_usage_timing"],
        })
    rows.sort(key=lambda r: (r["annual_roi_pct"] is None, -(r["annual_roi_pct"] or -1)))
    most = rows[0]
    return {
        "as_of": _catalog()["as_of"],
        "site_class": site_class,
        "utilization_pct": utilization_pct,
        "most_effective": most,
        "ranking": rows,
    }
