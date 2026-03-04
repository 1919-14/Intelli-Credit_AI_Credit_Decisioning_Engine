"""
Block G1: Forensic Alert Consolidation
Collects all alerts from Blocks A–F into a unified forensics report.
"""
from typing import Dict, Any, List


def consolidate_alerts(data: Dict[str, Any]) -> Dict[str, Any]:
    """G1: Consolidate all forensic alerts from all blocks."""

    all_alerts = []

    # Collect from all blocks
    for key in ["gst_forensics_alerts", "bank_forensics_alerts"]:
        all_alerts.extend(data.get(key, []))

    for key in ["adverse_media", "litigation", "sector_risk", "mca_checks", "cibil", "officer_analysis"]:
        block_data = data.get(key, {})
        all_alerts.extend(block_data.get("alerts", []))

    # Count severities
    red_count = sum(1 for a in all_alerts if a.get("severity") == "RED")
    amber_count = sum(1 for a in all_alerts if a.get("severity") == "AMBER")
    green_count = sum(1 for a in all_alerts if a.get("severity") == "GREEN")
    total_penalty = sum(a.get("score_penalty", 0) for a in all_alerts)

    # Overall risk level
    if red_count >= 2:
        overall = "RED"
    elif red_count == 1:
        overall = "RED"
    elif amber_count >= 3:
        overall = "AMBER"
    elif amber_count > 0:
        overall = "AMBER"
    else:
        overall = "GREEN"

    forensics_report = {
        "alerts": all_alerts,
        "overall_fraud_risk": overall,
        "red_flag_count": red_count,
        "amber_flag_count": amber_count,
        "green_flag_count": green_count,
        "total_score_penalty": total_penalty,
        "total_alerts": len(all_alerts),
        "alert_summary": {
            "RED": [a for a in all_alerts if a.get("severity") == "RED"],
            "AMBER": [a for a in all_alerts if a.get("severity") == "AMBER"],
            "GREEN": [a for a in all_alerts if a.get("severity") == "GREEN"],
            "INFO": [a for a in all_alerts if a.get("severity") == "INFO"],
        }
    }

    data["forensics_report"] = forensics_report
    return data
