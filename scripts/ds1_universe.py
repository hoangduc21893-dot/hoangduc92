"""DS1 membership; archives remain in performance history, never in setup scans."""
from datetime import date

ACTIVE = ("PVT", "PVS", "MSB", "HAH", "VGC", "DHC", "VPB", "MWG", "HDB",
          "PET", "HPG", "DCM", "GMD", "PLX", "ANV", "VHC", "PHR", "TCB")
ARCHIVED = {
    "BSR": {"added_date": "2026-09-22", "archived_on": "2026-10-22",
            "performance_effective_from": "2026-10-23", "reason": "User-approved archive; continue measuring performance"},
    "GVR": {"added_date": "2026-10-08", "archived_on": "2026-10-22",
            "performance_effective_from": "2026-10-23", "reason": "User-approved archive; continue measuring performance"},
}

def membership(symbol, asof):
    item = ARCHIVED.get(symbol)
    if item and asof >= date.fromisoformat(item["performance_effective_from"]):
        return "ARCHIVED"
    return "ACTIVE"

def annotate_performance(report, asof):
    """Keep legacy 20-name totals; add explicitly scoped current-list summaries."""
    groups = {}
    for row in report["rows"]:
        row["list_membership"] = membership(row["symbol"], asof)
        if row["symbol"] in ARCHIVED:
            row["archive_metadata"] = dict(ARCHIVED[row["symbol"]])
    for name in ("ACTIVE", "ARCHIVED"):
        rows = [r for r in report["rows"] if r["list_membership"] == name]
        complete = bool(rows) and all(r.get("prices_validated") for r in rows)
        ranked = sorted(rows, key=lambda r: (-r["reference_change_pct"], r["symbol"])) if complete else []
        groups[name] = {
            "count": len(rows), "symbols": [r["symbol"] for r in rows],
            "prices_validated_count": sum(bool(r.get("prices_validated")) for r in rows),
            "reference_equal_weight_change_pct": sum(r["reference_change_pct"] for r in rows)/len(rows) if complete else None,
            "reference_up": sum(r["reference_change_pct"] > 0 for r in rows) if complete else None,
            "reference_down": sum(r["reference_change_pct"] < 0 for r in rows) if complete else None,
            "reference_flat": sum(r["reference_change_pct"] == 0 for r in rows) if complete else None,
            "reference_ranking": [r["symbol"] for r in ranked],
        }
    report["performance_scope"] = "All 20 original entries including archives; cohort summaries distinguish the active list."
    report["cohorts"] = groups
    return report
