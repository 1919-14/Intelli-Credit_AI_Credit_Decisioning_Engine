"""
Block E: Bias & Fairness Monitoring
RBI Fair Lending + DPDP Act 2023

E1 — Sector-Level Fairness (Quarterly)
E2 — MSME Size Fairness (Quarterly)
E3 — Right to Explanation Endpoint (DPDP Act 2023)
"""
import json
from datetime import datetime
from typing import Dict, Any, List, Optional


# ─── E1: Sector-Level Fairness ───────────────────────────────────────────────

def sector_fairness_report(completed_apps: List[Dict]) -> Dict[str, Any]:
    """
    Compute per-sector approval rate, avg score, and override rate.
    Flag if sector approval rate < 50% of average or override > 40%.
    """
    if not completed_apps:
        return _demo_sector_fairness()

    sectors: Dict[str, Dict] = {}
    for app in completed_apps:
        sector = app.get("sector", "Unknown")
        if sector not in sectors:
            sectors[sector] = {"total": 0, "approved": 0, "overridden": 0, "scores": []}
        sectors[sector]["total"] += 1
        if app.get("decision") in ("APPROVE", "CONDITIONAL APPROVE"):
            sectors[sector]["approved"] += 1
        if app.get("was_overridden"):
            sectors[sector]["overridden"] += 1
        if app.get("credit_score"):
            sectors[sector]["scores"].append(app["credit_score"])

    overall_approval = sum(s["approved"] for s in sectors.values()) / max(sum(s["total"] for s in sectors.values()), 1)

    results = []
    alerts = []
    for sector, data in sectors.items():
        approval_rate = data["approved"] / max(data["total"], 1)
        override_rate = data["overridden"] / max(data["total"], 1)
        avg_score = sum(data["scores"]) / max(len(data["scores"]), 1) if data["scores"] else 0

        status = "GREEN"
        if approval_rate < overall_approval * 0.5:
            status = "AMBER"
            alerts.append(f"Sector '{sector}' approval rate ({approval_rate*100:.1f}%) < 50% of average")
        if override_rate > 0.4:
            status = "RED"
            alerts.append(f"Sector '{sector}' override rate ({override_rate*100:.1f}%) > 40% — bias investigation needed")

        results.append({
            "sector": sector,
            "total_cases": data["total"],
            "approval_rate_pct": round(approval_rate * 100, 1),
            "override_rate_pct": round(override_rate * 100, 1),
            "avg_score": round(avg_score, 1),
            "status": status,
        })

    return {
        "period": datetime.now().strftime("%Y-Q%q") if False else f"{datetime.now().year}-Q{(datetime.now().month-1)//3+1}",
        "overall_approval_rate_pct": round(overall_approval * 100, 1),
        "sectors": results,
        "alerts": alerts,
        "computed_at": datetime.now().isoformat(),
    }


# ─── E2: MSME Size Fairness ──────────────────────────────────────────────────

def msme_size_fairness(completed_apps: List[Dict]) -> Dict[str, Any]:
    """
    Approval rate across Micro / Small / Medium / Large brackets.
    Disparity ratio < 0.7 → AMBER → report to RBI.
    """
    if not completed_apps:
        return _demo_msme_fairness()

    buckets = {"Micro": {"total": 0, "approved": 0},
               "Small": {"total": 0, "approved": 0},
               "Medium": {"total": 0, "approved": 0},
               "Large": {"total": 0, "approved": 0}}

    for app in completed_apps:
        turnover = app.get("turnover_lakhs", 0)
        if turnover <= 500:
            bucket = "Micro"
        elif turnover <= 5000:
            bucket = "Small"
        elif turnover <= 25000:
            bucket = "Medium"
        else:
            bucket = "Large"
        buckets[bucket]["total"] += 1
        if app.get("decision") in ("APPROVE", "CONDITIONAL APPROVE"):
            buckets[bucket]["approved"] += 1

    rates = {}
    for k, v in buckets.items():
        rates[k] = v["approved"] / max(v["total"], 1)

    max_rate = max(rates.values()) if rates else 1
    results = []
    alerts = []
    for k, rate in rates.items():
        disparity = rate / max_rate if max_rate else 1
        status = "GREEN"
        if disparity < 0.7:
            status = "AMBER"
            alerts.append(f"{k} segment disparity ratio {disparity:.2f} < 0.7 — report to RBI")
        results.append({
            "segment": k,
            "total_cases": buckets[k]["total"],
            "approval_rate_pct": round(rate * 100, 1),
            "disparity_ratio": round(disparity, 2),
            "status": status,
        })

    return {
        "period": f"{datetime.now().year}-Q{(datetime.now().month-1)//3+1}",
        "segments": results,
        "alerts": alerts,
        "computed_at": datetime.now().isoformat(),
    }


# ─── E3: Right to Explanation (DPDP Act 2023) ────────────────────────────────

def generate_explanation(case_id: str, db_conn) -> Optional[Dict[str, Any]]:
    """
    Generate plain-English AI explanation for a borrower.
    DPDP Act 2023: rejected / conditional borrowers can request this.
    Pulls data from layer5_output (SHAP + decision).
    """
    cur = db_conn.cursor(dictionary=True)
    cur.execute(
        "SELECT layer5_output, decision, case_id FROM applications WHERE case_id=%s",
        (case_id,))
    row = cur.fetchone()
    cur.close()

    if not row or not row.get("layer5_output"):
        return None

    try:
        l5 = json.loads(row["layer5_output"]) if isinstance(row["layer5_output"], str) else row["layer5_output"]
    except Exception:
        return None

    decision_summary = l5.get("decision_summary", {})
    explanation_data = l5.get("explanation", {})

    # Build primary reason from top negative SHAP driver
    top_neg = explanation_data.get("shap_top_negative", [])
    primary_reason = top_neg[0].get("description", "Multiple risk factors identified") if top_neg else "Risk assessment factors"

    # Supporting reasons from remaining negative drivers
    supporting = [d.get("description", d.get("feature", "")) for d in top_neg[1:4]]

    # What can improve — from top positive drivers inverted
    improvements = []
    if top_neg:
        for d in top_neg[:3]:
            feat = d.get("feature", "")
            if "utilisation" in feat.lower() or "cc_" in feat.lower():
                improvements.append("Reduce CC/OD utilisation below 70%")
            elif "bounce" in feat.lower():
                improvements.append("Clear cheque bounce history")
            elif "circular" in feat.lower() or "related_party" in feat.lower():
                improvements.append("Resolve related party transfer patterns")
            elif "gst" in feat.lower():
                improvements.append("Maintain regular GST filing compliance")
            elif "dscr" in feat.lower():
                improvements.append("Improve Debt Service Coverage Ratio above 1.2")
            else:
                improvements.append(f"Improve {feat.replace('_', ' ')} metrics")

    return {
        "case_id": case_id,
        "decision": decision_summary.get("decision", row.get("decision", "UNKNOWN")),
        "primary_reason": primary_reason,
        "supporting_reasons": supporting,
        "what_can_improve": list(set(improvements))[:4],
        "model_version": l5.get("audit_snapshot", {}).get("model_version", "v4.3"),
        "explanation_generated_at": datetime.now().isoformat(),
        "credit_score": decision_summary.get("final_credit_score"),
        "risk_band": decision_summary.get("risk_band"),
    }


# ─── Demo data ───────────────────────────────────────────────────────────────

def _demo_sector_fairness() -> Dict[str, Any]:
    return {
        "period": f"{datetime.now().year}-Q{(datetime.now().month-1)//3+1}",
        "overall_approval_rate_pct": 72.4,
        "sectors": [
            {"sector": "Manufacturing", "total_cases": 35, "approval_rate_pct": 77.1, "override_rate_pct": 12.0, "avg_score": 712, "status": "GREEN"},
            {"sector": "Trading", "total_cases": 28, "approval_rate_pct": 67.9, "override_rate_pct": 18.0, "avg_score": 685, "status": "GREEN"},
            {"sector": "Services", "total_cases": 22, "approval_rate_pct": 72.7, "override_rate_pct": 9.0, "avg_score": 698, "status": "GREEN"},
            {"sector": "Construction", "total_cases": 15, "approval_rate_pct": 53.3, "override_rate_pct": 27.0, "avg_score": 661, "status": "AMBER"},
        ],
        "alerts": ["Construction sector under monitoring — lower approval rate"],
        "computed_at": datetime.now().isoformat(),
        "is_demo": True,
    }


def _demo_msme_fairness() -> Dict[str, Any]:
    return {
        "period": f"{datetime.now().year}-Q{(datetime.now().month-1)//3+1}",
        "segments": [
            {"segment": "Micro", "total_cases": 20, "approval_rate_pct": 65.0, "disparity_ratio": 0.82, "status": "GREEN"},
            {"segment": "Small", "total_cases": 30, "approval_rate_pct": 73.3, "disparity_ratio": 0.92, "status": "GREEN"},
            {"segment": "Medium", "total_cases": 25, "approval_rate_pct": 80.0, "disparity_ratio": 1.0, "status": "GREEN"},
            {"segment": "Large", "total_cases": 10, "approval_rate_pct": 70.0, "disparity_ratio": 0.88, "status": "GREEN"},
        ],
        "alerts": [],
        "computed_at": datetime.now().isoformat(),
        "is_demo": True,
    }
