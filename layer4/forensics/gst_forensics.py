"""
Block A: GST Forensics Engine (A1–A4)
Pure Python — no API calls.
"""
import numpy as np
from typing import List, Dict, Any, Optional


def gst_bank_reconciliation(
    gst_monthly_turnover: List[float],
    bank_monthly_credits: List[float]
) -> Dict[str, Any]:
    """
    A1: Compare monthly GST turnover vs bank credits.
    Returns alignment score and mismatch ratio.
    """
    alerts = []

    if not gst_monthly_turnover or not bank_monthly_credits:
        return {
            "revenue_gst_alignment": None,
            "gst_mismatch_ratio": None,
            "alerts": [{"alert_id": "A1-SKIP", "type": "DATA_MISSING",
                        "severity": "INFO", "description": "GST or bank monthly data not available"}]
        }

    # Align lengths
    min_len = min(len(gst_monthly_turnover), len(bank_monthly_credits))
    gst = np.array(gst_monthly_turnover[:min_len], dtype=float)
    bank = np.array(bank_monthly_credits[:min_len], dtype=float)

    # Correlation
    if np.std(gst) > 0 and np.std(bank) > 0:
        corr = float(np.corrcoef(gst, bank)[0, 1])
    else:
        corr = 0.0

    # Average gap percentage
    with np.errstate(divide='ignore', invalid='ignore'):
        gaps = np.abs(gst - bank) / np.where(gst > 0, gst, 1) * 100
    avg_gap = float(np.nanmean(gaps))

    # Normalized alignment score (0–1, higher is better)
    alignment = max(0, min(1, (corr + 1) / 2)) * max(0, 1 - avg_gap / 100)

    # Flags
    if avg_gap > 35:
        alerts.append({"alert_id": "A1-001", "type": "REVENUE_INFLATION",
                        "severity": "RED", "description": f"GST vs bank gap {avg_gap:.0f}% — serious revenue inflation risk",
                        "score_penalty": -10, "source": "GST vs Bank reconciliation"})
    elif avg_gap > 20:
        alerts.append({"alert_id": "A1-002", "type": "REVENUE_INFLATION",
                        "severity": "AMBER", "description": f"GST vs bank gap {avg_gap:.0f}% — moderate revenue inflation risk",
                        "score_penalty": -5, "source": "GST vs Bank reconciliation"})

    if corr < 0.5:
        alerts.append({"alert_id": "A1-003", "type": "WINDOW_DRESSING",
                        "severity": "RED", "description": f"GST-Bank correlation {corr:.2f} — likely window dressing",
                        "score_penalty": -8, "source": "GST vs Bank reconciliation"})
    elif corr < 0.7:
        alerts.append({"alert_id": "A1-004", "type": "INCONSISTENT_PATTERN",
                        "severity": "AMBER", "description": f"GST-Bank correlation {corr:.2f} — inconsistent patterns",
                        "score_penalty": -3, "source": "GST vs Bank reconciliation"})

    return {
        "revenue_gst_alignment": round(alignment, 4),
        "gst_mismatch_ratio": round(avg_gap, 2),
        "correlation": round(corr, 4),
        "monthly_gaps_pct": [round(g, 2) for g in gaps.tolist()],
        "alerts": alerts
    }


def itc_mismatch_detection(
    gstr2a_available: List[float],
    gstr3b_claimed: List[float]
) -> Dict[str, Any]:
    """
    A2: Compare ITC available (2A) vs ITC claimed (3B).
    Detects aggressive / fraudulent ITC claims.
    """
    alerts = []

    if not gstr2a_available or not gstr3b_claimed:
        return {
            "gst_2a_vs_3b_gap_pct": None,
            "itc_mismatch_flag": 0,
            "alerts": [{"alert_id": "A2-SKIP", "type": "DATA_MISSING",
                        "severity": "INFO", "description": "ITC data not available"}]
        }

    min_len = min(len(gstr2a_available), len(gstr3b_claimed))
    avail = np.array(gstr2a_available[:min_len], dtype=float)
    claimed = np.array(gstr3b_claimed[:min_len], dtype=float)

    mismatch = claimed - avail
    total_avail = np.sum(avail)
    mismatch_ratio = float(np.sum(mismatch) / total_avail * 100) if total_avail > 0 else 0
    months_overclaimed = int(np.sum(claimed > avail))

    itc_flag = 0
    if mismatch_ratio > 25:
        alerts.append({"alert_id": "A2-001", "type": "ITC_FRAUD",
                        "severity": "RED", "description": f"ITC overclaimed by {mismatch_ratio:.0f}% — serious ITC fraud risk",
                        "score_penalty": -10, "source": "GSTR-2A vs 3B"})
        itc_flag = 1
    elif mismatch_ratio > 10:
        alerts.append({"alert_id": "A2-002", "type": "ITC_GAMING",
                        "severity": "AMBER", "description": f"ITC overclaimed by {mismatch_ratio:.0f}% — moderate gaming risk",
                        "score_penalty": -5, "source": "GSTR-2A vs 3B"})
        itc_flag = 1
    elif mismatch_ratio < 0:
        # Conservative ITC — green signal
        alerts.append({"alert_id": "A2-003", "type": "ITC_CONSERVATIVE",
                        "severity": "GREEN", "description": "ITC claimed is LOWER than available — conservative approach",
                        "score_penalty": 0, "source": "GSTR-2A vs 3B"})

    if months_overclaimed > 3:
        alerts.append({"alert_id": "A2-004", "type": "ITC_PATTERN",
                        "severity": "AMBER", "description": f"{months_overclaimed} months of ITC overclaiming",
                        "score_penalty": -3, "source": "GSTR-2A vs 3B"})

    return {
        "gst_2a_vs_3b_gap_pct": round(mismatch_ratio, 2),
        "itc_mismatch_flag": itc_flag,
        "months_overclaimed": months_overclaimed,
        "monthly_mismatch": mismatch.tolist(),
        "alerts": alerts
    }


def circular_trading_check(
    related_parties: List[Dict],
    large_bank_transfers: List[Dict]
) -> Dict[str, Any]:
    """
    A3: Detect circular trading — same entities in both
    related party list AND large bank transfers.
    """
    alerts = []

    rp_names = set()
    for rp in (related_parties or []):
        name = rp.get("name", "") or rp.get("party_name", "")
        if name:
            rp_names.add(name.lower().strip())

    transfer_names = set()
    transfer_total = 0
    circular_volume = 0
    for tx in (large_bank_transfers or []):
        narration = (tx.get("narration", "") or tx.get("description", "")).lower()
        amount = abs(float(tx.get("amount", 0) or 0))
        transfer_total += amount
        transfer_names.add(narration)
        # Check if any related party name appears in bank transfers
        for rp_name in rp_names:
            if rp_name and rp_name in narration:
                circular_volume += amount

    ratio = round(circular_volume / transfer_total * 100, 2) if transfer_total > 0 else 0

    if circular_volume > 0:
        alerts.append({
            "alert_id": "A3-001", "type": "CIRCULAR_TRADING",
            "severity": "AMBER" if ratio < 20 else "RED",
            "description": f"₹{circular_volume/100000:.1f}L in transfers matching related parties ({ratio}% of outflow)",
            "score_penalty": -5 if ratio < 20 else -10,
            "source": "Related party vs bank transfers"
        })

    return {
        "circular_trading_ratio": ratio,
        "circular_volume_lakhs": round(circular_volume / 100000, 2),
        "matching_entities": list(rp_names & {n for n in transfer_names if any(rp in n for rp in rp_names)}),
        "alerts": alerts
    }


def filing_compliance_score(
    filing_dates: List[Dict],
    total_months: int = 12
) -> Dict[str, Any]:
    """
    A4: GST filing compliance — on-time rate and streaks.
    """
    alerts = []

    if not filing_dates:
        return {
            "gst_compliance_score": None,
            "on_time_rate": None,
            "alerts": [{"alert_id": "A4-SKIP", "type": "DATA_MISSING",
                        "severity": "INFO", "description": "Filing dates not available"}]
        }

    on_time = 0
    late_streak = 0
    max_late_streak = 0

    for entry in filing_dates:
        status = (entry.get("status", "") or entry.get("filing_status", "")).lower()
        if "on time" in status or "timely" in status or status == "filed":
            on_time += 1
            late_streak = 0
        else:
            late_streak += 1
            max_late_streak = max(max_late_streak, late_streak)

    on_time_rate = round(on_time / max(len(filing_dates), 1) * 100, 1)
    score = round(on_time_rate / 100, 2)

    if on_time_rate < 50:
        alerts.append({"alert_id": "A4-001", "type": "FILING_NON_COMPLIANCE",
                        "severity": "RED", "description": f"Only {on_time_rate}% GST filings on-time",
                        "score_penalty": -8, "source": "GST filing compliance"})
    elif on_time_rate < 70:
        alerts.append({"alert_id": "A4-002", "type": "FILING_DELAYS",
                        "severity": "AMBER", "description": f"{on_time_rate}% GST filings on-time",
                        "score_penalty": -3, "source": "GST filing compliance"})

    if max_late_streak > 2:
        alerts.append({"alert_id": "A4-003", "type": "FILING_STREAK",
                        "severity": "AMBER", "description": f"{max_late_streak} consecutive late filings",
                        "score_penalty": -3, "source": "GST filing compliance"})

    return {
        "gst_compliance_score": score,
        "on_time_rate": on_time_rate,
        "max_late_streak": max_late_streak,
        "total_filings": len(filing_dates),
        "on_time_filings": on_time,
        "alerts": alerts
    }


def run_gst_forensics(data: Dict[str, Any]) -> Dict[str, Any]:
    """Run all GST forensic checks. Entry point for LangChain."""
    l3 = data.get("layer3_data", {})
    l2 = data.get("layer2_data", {})

    results = {}

    # A1
    gst_turnover = l2.get("gstr1_monthly_outward_turnover") or l3.get("gst_monthly_turnover") or []
    bank_credits = l2.get("monthly_total_credits") or l3.get("bank_monthly_credits") or []
    if isinstance(gst_turnover, list) and all(isinstance(x, dict) for x in gst_turnover):
        gst_turnover = [float(x.get("value", 0) or 0) for x in gst_turnover]
    if isinstance(bank_credits, list) and all(isinstance(x, dict) for x in bank_credits):
        bank_credits = [float(x.get("value", 0) or 0) for x in bank_credits]
    results["a1_reconciliation"] = gst_bank_reconciliation(gst_turnover, bank_credits)

    # A2
    itc_avail = l2.get("gstr2a_monthly_itc_available") or []
    itc_claimed = l2.get("gstr3b_monthly_itc_claimed") or []
    if isinstance(itc_avail, list) and all(isinstance(x, dict) for x in itc_avail):
        itc_avail = [float(x.get("value", 0) or 0) for x in itc_avail]
    if isinstance(itc_claimed, list) and all(isinstance(x, dict) for x in itc_claimed):
        itc_claimed = [float(x.get("value", 0) or 0) for x in itc_claimed]
    results["a2_itc_mismatch"] = itc_mismatch_detection(itc_avail, itc_claimed)

    # A3
    related = l2.get("related_party_transactions") or []
    large_transfers = l2.get("large_cash_deposits", []) + l2.get("large_cash_withdrawals", [])
    results["a3_circular_trading"] = circular_trading_check(related, large_transfers)

    # A4
    filing = l2.get("gst_filing_dates") or []
    results["a4_filing_compliance"] = filing_compliance_score(filing)

    # Collect all alerts
    all_alerts = []
    for block in results.values():
        all_alerts.extend(block.get("alerts", []))

    data["gst_forensics"] = results
    data["gst_forensics_alerts"] = all_alerts
    return data
