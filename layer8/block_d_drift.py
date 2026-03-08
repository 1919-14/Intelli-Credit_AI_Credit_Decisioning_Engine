"""
Block D: Model Drift Detection
D1 — Feature Drift (PSI) every 2 weeks
D2 — Concept Drift (ADWIN) rolling 90-day window
"""
import math
from datetime import datetime
from typing import Dict, Any, List, Optional


# ─── D1: Population Stability Index (PSI) ────────────────────────────────────

def compute_psi(reference_dist: List[float], current_dist: List[float],
                n_bins: int = 10) -> float:
    """
    PSI = Σ (Actual% − Expected%) × ln(Actual% / Expected%)
    < 0.10 GREEN | 0.10–0.25 AMBER | > 0.25 RED
    """
    if not reference_dist or not current_dist:
        return 0.0

    def _bin_counts(data, bins):
        mn, mx = min(data + reference_dist + current_dist), max(data + reference_dist + current_dist)
        if mn == mx:
            return [len(data)]
        step = (mx - mn) / bins
        counts = [0] * bins
        for v in data:
            idx = min(int((v - mn) / step), bins - 1)
            counts[idx] += 1
        return counts

    ref_counts = _bin_counts(reference_dist, n_bins)
    cur_counts = _bin_counts(current_dist, n_bins)
    ref_total = sum(ref_counts) or 1
    cur_total = sum(cur_counts) or 1

    psi = 0.0
    for r, c in zip(ref_counts, cur_counts):
        ref_pct = max(r / ref_total, 0.0001)
        cur_pct = max(c / cur_total, 0.0001)
        psi += (cur_pct - ref_pct) * math.log(cur_pct / ref_pct)

    return round(abs(psi), 4)


def psi_status(psi_value: float) -> str:
    if psi_value < 0.10:
        return "GREEN"
    elif psi_value <= 0.25:
        return "AMBER"
    return "RED"


# Priority features to monitor
PRIORITY_FEATURES = [
    "dscr_proxy", "gst_2a_3b_gap", "sector_risk_score",
    "bank_od_utilisation_pct", "promoter_experience_yrs",
    "turnover_growth_yoy_pct", "net_profit_margin_pct",
    "current_ratio", "debt_equity_ratio", "credit_utilisation_pct",
    "cheque_bounce_rate_pct", "gst_filing_regularity_pct",
    "vintage_years", "collateral_coverage_ratio",
    "bank_balance_avg_lakhs", "revenue_concentration_pct",
    "working_capital_days", "inventory_days",
    "receivable_days", "payable_days",
    "interest_coverage_ratio", "cash_profit_margin_pct",
    "contingent_liability_ratio", "related_party_txn_pct",
    "promoter_credit_score",
]


def run_drift_report(reference_values: Dict[str, List[float]],
                     current_values: Dict[str, List[float]]) -> Dict[str, Any]:
    """
    Run PSI computation for all 25 features.
    reference_values / current_values: {feature_name: [list of values]}
    """
    feature_results = []
    overall_status = "GREEN"

    for feat in PRIORITY_FEATURES:
        ref = reference_values.get(feat, [])
        cur = current_values.get(feat, [])
        if ref and cur:
            psi_val = compute_psi(ref, cur)
            status = psi_status(psi_val)
        else:
            psi_val = 0.0
            status = "GREY"

        feature_results.append({
            "feature": feat,
            "psi": psi_val,
            "status": status,
            "ref_count": len(ref),
            "cur_count": len(cur),
        })

        if status == "RED":
            overall_status = "RED"
        elif status == "AMBER" and overall_status != "RED":
            overall_status = "AMBER"

    return {
        "report_date": datetime.now().isoformat(),
        "overall_status": overall_status,
        "features": feature_results,
        "red_count": sum(1 for f in feature_results if f["status"] == "RED"),
        "amber_count": sum(1 for f in feature_results if f["status"] == "AMBER"),
        "green_count": sum(1 for f in feature_results if f["status"] == "GREEN"),
    }


# ─── D2: Concept Drift (ADWIN-style) ─────────────────────────────────────────

def detect_concept_drift(predicted_pds: List[float],
                         actual_defaults: List[int]) -> Dict[str, Any]:
    """
    Monitor predicted PD vs actual default rate gap.
    Simplified ADWIN-style: compare rolling windows.
    """
    if not predicted_pds or not actual_defaults:
        return {"status": "GREY", "message": "Insufficient data", "gap_pct": 0}

    n = len(actual_defaults)
    avg_predicted = sum(predicted_pds) / len(predicted_pds) * 100
    avg_actual = sum(actual_defaults) / n * 100
    gap = abs(avg_actual - avg_predicted)

    if gap > 10:
        status = "RED"
        action = "RETRAIN recommended — predicted vs actual gap > 10%"
    elif gap > 5:
        status = "AMBER"
        action = "Monitor closely — predicted vs actual gap > 5%"
    else:
        status = "GREEN"
        action = "Model well calibrated"

    return {
        "status": status,
        "avg_predicted_default_pct": round(avg_predicted, 2),
        "avg_actual_default_pct": round(avg_actual, 2),
        "gap_pct": round(gap, 2),
        "sample_size": n,
        "action": action,
        "computed_at": datetime.now().isoformat(),
    }


def save_drift_report(db_conn, report: Dict):
    """Save drift results to database."""
    import json
    cur = db_conn.cursor()
    cur.execute("""
        INSERT INTO drift_psi_log
            (report_date, overall_status, red_count, amber_count, green_count, report_json)
        VALUES (NOW(), %s, %s, %s, %s, %s)
    """, (
        report.get("overall_status", "GREY"),
        report.get("red_count", 0),
        report.get("amber_count", 0),
        report.get("green_count", 0),
        json.dumps(report),
    ))
    db_conn.commit()
    cur.close()


def get_drift_history(db_conn, limit: int = 10) -> List[Dict]:
    """Return recent drift reports."""
    import json
    cur = db_conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM drift_psi_log ORDER BY report_date DESC LIMIT %s", (limit,))
    rows = cur.fetchall()
    cur.close()
    for r in rows:
        for k in ("report_date",):
            if r.get(k) and hasattr(r[k], "isoformat"):
                r[k] = r[k].isoformat()
        if isinstance(r.get("report_json"), str):
            try:
                r["report_json"] = json.loads(r["report_json"])
            except Exception:
                pass
    return rows


def get_demo_drift_report() -> Dict[str, Any]:
    """Demo drift report when no data exists yet."""
    features = []
    import random
    random.seed(42)
    for feat in PRIORITY_FEATURES:
        psi_val = round(random.uniform(0.01, 0.18), 4)
        features.append({
            "feature": feat,
            "psi": psi_val,
            "status": psi_status(psi_val),
            "ref_count": 200,
            "cur_count": 50,
        })
    return {
        "report_date": datetime.now().isoformat(),
        "overall_status": "AMBER",
        "features": features,
        "red_count": sum(1 for f in features if f["status"] == "RED"),
        "amber_count": sum(1 for f in features if f["status"] == "AMBER"),
        "green_count": sum(1 for f in features if f["status"] == "GREEN"),
        "concept_drift": {
            "status": "GREEN",
            "avg_predicted_default_pct": 8.2,
            "avg_actual_default_pct": 9.1,
            "gap_pct": 0.9,
            "action": "Model well calibrated",
        },
        "is_demo": True,
    }
