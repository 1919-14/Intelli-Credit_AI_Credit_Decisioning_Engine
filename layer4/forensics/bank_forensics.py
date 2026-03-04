"""
Block B: Bank Statement Forensics Engine (B1–B3)
Pure Python — no API calls.
"""
import numpy as np
from typing import List, Dict, Any


def cheque_bounce_analysis(
    bounce_entries: List[Dict],
    total_months: int = 12
) -> Dict[str, Any]:
    """
    B1: Analyse cheque bounce events for payment discipline.
    """
    alerts = []
    count = len(bounce_entries or [])
    total_amount = sum(abs(float(b.get("amount", 0) or 0)) for b in (bounce_entries or []))
    largest = max((abs(float(b.get("amount", 0) or 0)) for b in (bounce_entries or [])), default=0)
    frequency = round(count / max(total_months, 1), 2)

    # Check for insufficent funds bounces
    insuff_count = sum(1 for b in (bounce_entries or [])
                       if "insufficient" in (b.get("reason", "") or b.get("narration", "")).lower())

    if count > 5:
        alerts.append({"alert_id": "B1-001", "type": "CHEQUE_BOUNCE_HIGH",
                        "severity": "RED", "description": f"{count} cheque bounces in {total_months} months",
                        "score_penalty": -10, "source": "Bank statement bounces"})
    elif count > 2:
        alerts.append({"alert_id": "B1-002", "type": "CHEQUE_BOUNCE",
                        "severity": "AMBER", "description": f"{count} cheque bounces in {total_months} months",
                        "score_penalty": -5, "source": "Bank statement bounces"})

    if insuff_count > 0:
        alerts.append({"alert_id": "B1-003", "type": "INSUFFICIENT_FUNDS",
                        "severity": "RED", "description": f"{insuff_count} bounces due to insufficient funds — cash flow issue",
                        "score_penalty": -8, "source": "Bank statement bounces"})

    return {
        "bounce_count": count,
        "bounce_amount_total_lakhs": round(total_amount / 100000, 2),
        "largest_bounce_lakhs": round(largest / 100000, 2),
        "cheque_bounce_frequency": frequency,
        "insufficient_funds_bounces": insuff_count,
        "alerts": alerts
    }


def od_cc_utilisation(
    monthly_closing_balances: List[float],
    od_cc_limit: float = 0
) -> Dict[str, Any]:
    """
    B2: CC/OD utilisation analysis.
    """
    alerts = []

    if not monthly_closing_balances or od_cc_limit <= 0:
        return {
            "bank_od_utilisation_pct": None,
            "cc_utilisation_volatility": None,
            "months_near_limit": 0,
            "alerts": [{"alert_id": "B2-SKIP", "type": "DATA_MISSING",
                        "severity": "INFO", "description": "OD/CC data not available"}]
        }

    balances = np.array(monthly_closing_balances, dtype=float)
    utilisation = (od_cc_limit - balances) / od_cc_limit * 100
    utilisation = np.clip(utilisation, 0, 100)

    avg_util = float(np.mean(utilisation))
    volatility = float(np.std(utilisation))
    months_near = int(np.sum(utilisation > 90))

    if avg_util > 85:
        alerts.append({"alert_id": "B2-001", "type": "OD_OVERDRAWN",
                        "severity": "RED", "description": f"Average OD utilisation {avg_util:.0f}% — overdrawn stress",
                        "score_penalty": -8, "source": "CC/OD utilisation"})
    elif avg_util > 70:
        alerts.append({"alert_id": "B2-002", "type": "OD_HIGH_UTIL",
                        "severity": "AMBER", "description": f"Average OD utilisation {avg_util:.0f}%",
                        "score_penalty": -4, "source": "CC/OD utilisation"})

    if volatility > 20:
        alerts.append({"alert_id": "B2-003", "type": "OD_ERRATIC",
                        "severity": "AMBER", "description": f"OD utilisation volatility {volatility:.0f}% — erratic usage",
                        "score_penalty": -3, "source": "CC/OD utilisation"})

    return {
        "bank_od_utilisation_pct": round(avg_util, 2),
        "cc_utilisation_volatility": round(volatility, 2),
        "months_near_limit": months_near,
        "monthly_utilisation_pct": [round(u, 1) for u in utilisation.tolist()],
        "alerts": alerts
    }


def cash_flow_quality(
    monthly_credits: List[float],
    monthly_debits: List[float],
    cash_deposits: List[Dict] = None,
    total_emi_amount: float = 0
) -> Dict[str, Any]:
    """
    B3: Cash flow quality check.
    """
    alerts = []

    if not monthly_credits or not monthly_debits:
        return {
            "cash_deposit_ratio": None,
            "monthly_inflow_volatility": None,
            "emi_to_credit_ratio": None,
            "alerts": [{"alert_id": "B3-SKIP", "type": "DATA_MISSING",
                        "severity": "INFO", "description": "Cash flow data not available"}]
        }

    credits = np.array(monthly_credits, dtype=float)
    debits = np.array(monthly_debits, dtype=float)

    net_flow = credits - debits
    months_negative = int(np.sum(net_flow < 0))
    volatility = float(np.std(credits) / np.mean(credits) * 100) if np.mean(credits) > 0 else 0

    total_credits_sum = float(np.sum(credits))
    cash_total = sum(abs(float(d.get("amount", 0) or 0)) for d in (cash_deposits or []))
    cash_ratio = round(cash_total / total_credits_sum * 100, 2) if total_credits_sum > 0 else 0

    emi_ratio = round(total_emi_amount / total_credits_sum * 100, 2) if total_credits_sum > 0 else 0

    if months_negative > 3:
        alerts.append({"alert_id": "B3-001", "type": "NEGATIVE_CASH_FLOW",
                        "severity": "AMBER", "description": f"{months_negative} months with negative net cash flow",
                        "score_penalty": -4, "source": "Cash flow analysis"})

    if cash_ratio > 30:
        alerts.append({"alert_id": "B3-002", "type": "CASH_HEAVY",
                        "severity": "RED", "description": f"Cash deposits are {cash_ratio}% of credits — cash-based income risk",
                        "score_penalty": -8, "source": "Cash flow analysis"})

    if emi_ratio > 15:
        alerts.append({"alert_id": "B3-003", "type": "HIGH_EMI_BURDEN",
                        "severity": "AMBER", "description": f"EMI payments are {emi_ratio}% of credits — high debt burden",
                        "score_penalty": -4, "source": "Cash flow analysis"})

    return {
        "cash_deposit_ratio": cash_ratio,
        "monthly_inflow_volatility": round(volatility, 2),
        "emi_to_credit_ratio": emi_ratio,
        "months_negative_flow": months_negative,
        "monthly_net_flow": net_flow.tolist(),
        "alerts": alerts
    }


def run_bank_forensics(data: Dict[str, Any]) -> Dict[str, Any]:
    """Run all bank forensic checks. Entry point for LangChain."""
    l2 = data.get("layer2_data", {})
    l3 = data.get("layer3_data", {})

    results = {}

    # B1
    bounces = l2.get("cheque_bounce_entries") or []
    num_bounces = l2.get("num_cheque_bounces") or 0
    if not bounces and num_bounces:
        bounces = [{"amount": 0}] * int(num_bounces)
    results["b1_cheque_bounces"] = cheque_bounce_analysis(bounces)

    # B2
    balances = l2.get("monthly_closing_balance") or []
    if isinstance(balances, list) and all(isinstance(x, dict) for x in balances):
        balances = [float(x.get("value", 0) or 0) for x in balances]
    od_limit = float(l2.get("od_cc_limit") or l2.get("od_cc_limit_sanctioned_inr_lakhs", 0) or 0) * 100000
    results["b2_od_utilisation"] = od_cc_utilisation(balances, od_limit)

    # B3
    m_credits = l2.get("monthly_total_credits") or []
    m_debits = l2.get("monthly_total_debits") or []
    if isinstance(m_credits, list) and all(isinstance(x, dict) for x in m_credits):
        m_credits = [float(x.get("value", 0) or 0) for x in m_credits]
    if isinstance(m_debits, list) and all(isinstance(x, dict) for x in m_debits):
        m_debits = [float(x.get("value", 0) or 0) for x in m_debits]
    cash_deps = l2.get("large_cash_deposits") or []
    emi = float(l2.get("total_emi_amount") or 0)
    results["b3_cash_flow"] = cash_flow_quality(m_credits, m_debits, cash_deps, emi)

    all_alerts = []
    for block in results.values():
        all_alerts.extend(block.get("alerts", []))

    data["bank_forensics"] = results
    data["bank_forensics_alerts"] = all_alerts
    return data
