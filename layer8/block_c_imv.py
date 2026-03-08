"""
Block C: Independent Model Validation (IMV)
RBI MRM Circular — MANDATORY, Annual Minimum

Performed by team SEPARATE from model developers.
For hackathon: mock "IMV team" role.
"""
import json
from datetime import datetime
from typing import Dict, Any, List


def run_imv_check(db_conn, model_id: str = "XGB_CREDIT_V4.3") -> Dict[str, Any]:
    """
    Run a mock Independent Model Validation.
    In production this would be executed by a separate team.

    Scope per RBI circular:
      1. Assumption Validation
      2. Data Accuracy Review
      3. Out-of-Time (OOT) Backtesting
      4. Compliance Review
      5. Bias & Fairness Review
    """
    report = {
        "model_id": model_id,
        "validation_date": datetime.now().isoformat(),
        "validator": "IMV Team (Mock)",
        "scope": [
            "Assumption Validation",
            "Data Accuracy Review",
            "OOT Backtesting",
            "Compliance Review",
            "Bias & Fairness Review",
        ],
        "sections": {},
    }

    # 1. Assumption Validation
    report["sections"]["assumption_validation"] = {
        "status": "PASS",
        "findings": [
            "All 25 features remain appropriate for MSME credit scoring.",
            "DSCR threshold (< 1.0 = reject) validated against FY24 default data.",
            "Sector risk mapping reviewed — no stale sectors detected.",
        ],
        "recommendations": [
            "Consider adding 'digital payments ratio' as new feature in next version.",
        ],
    }

    # 2. Data Accuracy Review
    report["sections"]["data_accuracy"] = {
        "status": "PASS",
        "findings": [
            "Layer 2 extraction accuracy: 96.2% (sampled 50 cases).",
            "GST 2A/3B gap calculation verified against manual computation.",
            "Bank statement OD utilisation matches source PDFs.",
        ],
        "recommendations": [],
    }

    # 3. OOT Backtesting
    report["sections"]["oot_backtesting"] = {
        "status": "PASS",
        "in_sample_auc": 0.84,
        "oot_auc": 0.81,
        "auc_drop_pct": 3.6,
        "threshold": 5.0,
        "findings": [
            "OOT AUC drop of 3.6% is within acceptable 5% threshold.",
            "KS statistic in OOT period: 0.44 (vs in-sample 0.47).",
        ],
    }

    # 4. Compliance Review
    report["sections"]["compliance_review"] = {
        "status": "PASS",
        "findings": [
            "Model compliant with RBI MRM Circular Aug 2024.",
            "No new circulars requiring model changes since last validation.",
            "DPDP Act 2023 right-to-explanation endpoint operational.",
        ],
    }

    # 5. Bias & Fairness
    report["sections"]["bias_fairness"] = {
        "status": "PASS",
        "findings": [
            "No sector shows approval rate < 50% of average.",
            "Micro/Small/Medium disparity ratio: 0.82 (above 0.7 threshold).",
            "Override rates within acceptable bands across all sectors.",
        ],
    }

    # Overall
    all_pass = all(
        s.get("status") == "PASS"
        for s in report["sections"].values()
    )
    report["overall_status"] = "PASS" if all_pass else "FAIL"
    report["next_validation_due"] = "2027-03-01"

    return report


def save_imv_report(db_conn, report: Dict) -> int:
    """Persist IMV report to database."""
    cur = db_conn.cursor()
    cur.execute("""
        INSERT INTO imv_reports
            (model_id, validation_date, validator, overall_status,
             report_json, next_validation_due)
        VALUES (%s, NOW(), %s, %s, %s, %s)
    """, (
        report["model_id"],
        report.get("validator", "IMV Team"),
        report["overall_status"],
        json.dumps(report),
        report.get("next_validation_due"),
    ))
    db_conn.commit()
    rid = cur.lastrowid
    cur.close()
    return rid


def get_imv_reports(db_conn, limit: int = 10) -> List[Dict]:
    """Return latest IMV reports."""
    cur = db_conn.cursor(dictionary=True)
    cur.execute(
        "SELECT * FROM imv_reports ORDER BY validation_date DESC LIMIT %s",
        (limit,))
    rows = cur.fetchall()
    cur.close()
    for r in rows:
        for k in ("validation_date", "next_validation_due", "created_at"):
            if r.get(k) and hasattr(r[k], "isoformat"):
                r[k] = r[k].isoformat()
        if isinstance(r.get("report_json"), str):
            try:
                r["report_json"] = json.loads(r["report_json"])
            except Exception:
                pass
    return rows
