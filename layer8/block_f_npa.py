"""
Block F: NPA Early Warning & CRILC Reporting
RBI MANDATORY for exposures ≥ ₹5 Crore

F1 — SMA Classification Engine
F2 — CRILC Quarterly Reporting
"""
import json
from datetime import datetime
from typing import Dict, Any, List, Optional


# ─── F1: SMA Classification ──────────────────────────────────────────────────

SMA_CLASSES = {
    "SMA-0": {"min_dpd": 1,  "max_dpd": 30,  "severity": "WATCH", "color": "AMBER"},
    "SMA-1": {"min_dpd": 31, "max_dpd": 60,  "severity": "ALERT", "color": "AMBER"},
    "SMA-2": {"min_dpd": 61, "max_dpd": 90,  "severity": "CRITICAL", "color": "RED"},
    "NPA":   {"min_dpd": 91, "max_dpd": 9999, "severity": "NPA", "color": "RED"},
}


def classify_sma(dpd: int) -> Dict[str, Any]:
    """
    Classify based on Days Past Due:
      SMA-0: 1–30 days
      SMA-1: 31–60 days
      SMA-2: 61–90 days
      NPA:   > 90 days
    """
    if dpd <= 0:
        return {"classification": "REGULAR", "severity": "NORMAL", "color": "GREEN", "dpd": dpd}
    for cls_name, bounds in SMA_CLASSES.items():
        if bounds["min_dpd"] <= dpd <= bounds["max_dpd"]:
            return {
                "classification": cls_name,
                "severity": bounds["severity"],
                "color": bounds["color"],
                "dpd": dpd,
                "crilc_trigger": cls_name == "SMA-2",
            }
    return {"classification": "NPA", "severity": "NPA", "color": "RED", "dpd": dpd, "crilc_trigger": True}


# ─── Early Warning Signals ───────────────────────────────────────────────────

def check_early_warning_signals(loan_data: Dict) -> List[Dict[str, Any]]:
    """
    EWS triggers BEFORE SMA classification:
      - CC utilisation spike > 95%
      - Cheque bounce after sanction
      - GST filing missed post-sanction
      - Adverse media on promoter
      - Score degradation > 50 points
    """
    alerts = []

    cc_util = loan_data.get("cc_utilisation_pct", 0)
    if cc_util > 95:
        alerts.append({
            "signal": "CC_UTILISATION_SPIKE",
            "description": f"CC utilisation at {cc_util}% (> 95% threshold)",
            "severity": "HIGH",
            "action": "Immediate credit officer review",
        })

    if loan_data.get("cheque_bounce_post_sanction", False):
        alerts.append({
            "signal": "CHEQUE_BOUNCE",
            "description": "Cheque bounce detected post-sanction",
            "severity": "HIGH",
            "action": "Alert credit officer + review repayment capacity",
        })

    if loan_data.get("gst_filing_missed", False):
        alerts.append({
            "signal": "GST_FILING_MISSED",
            "description": "GST filing missed post-sanction",
            "severity": "MEDIUM",
            "action": "Contact borrower for compliance update",
        })

    if loan_data.get("adverse_media", False):
        alerts.append({
            "signal": "ADVERSE_MEDIA",
            "description": "Adverse media alert on promoter post-sanction",
            "severity": "HIGH",
            "action": "Escalate to credit committee for review",
        })

    score_drop = loan_data.get("score_degradation", 0)
    if score_drop > 50:
        alerts.append({
            "signal": "SCORE_DEGRADATION",
            "description": f"Score dropped by {score_drop} points on re-scoring",
            "severity": "HIGH",
            "action": "Trigger re-evaluation and potential SMA upgrade",
        })

    return alerts


# ─── SMA Dashboard Data ─────────────────────────────────────────────────────

def get_sma_dashboard(db_conn) -> Dict[str, Any]:
    """Get SMA counts and recent early warnings."""
    cur = db_conn.cursor(dictionary=True)

    # SMA counts
    cur.execute("""
        SELECT sma_classification, COUNT(*) as cnt
        FROM sma_monitoring
        GROUP BY sma_classification
    """)
    sma_rows = cur.fetchall()
    sma_counts = {r["sma_classification"]: r["cnt"] for r in sma_rows}

    # Recent alerts
    cur.execute("""
        SELECT * FROM sma_monitoring
        WHERE sma_classification IN ('SMA-1', 'SMA-2', 'NPA')
        ORDER BY updated_at DESC LIMIT 10
    """)
    recent_alerts = cur.fetchall()
    for r in recent_alerts:
        for k in ("updated_at", "created_at"):
            if r.get(k) and hasattr(r[k], "isoformat"):
                r[k] = r[k].isoformat()

    cur.close()

    return {
        "sma_counts": {
            "REGULAR": sma_counts.get("REGULAR", 0),
            "SMA-0": sma_counts.get("SMA-0", 0),
            "SMA-1": sma_counts.get("SMA-1", 0),
            "SMA-2": sma_counts.get("SMA-2", 0),
            "NPA": sma_counts.get("NPA", 0),
        },
        "total_monitored": sum(sma_counts.values()) if sma_counts else 0,
        "recent_alerts": recent_alerts,
        "computed_at": datetime.now().isoformat(),
    }


def update_sma_status(db_conn, case_id: str, dpd: int,
                      outstanding_lakhs: float = 0) -> Dict:
    """Update or create SMA record for a sanctioned loan."""
    classification = classify_sma(dpd)
    cur = db_conn.cursor(dictionary=True)

    cur.execute("SELECT id FROM sma_monitoring WHERE case_id=%s", (case_id,))
    existing = cur.fetchone()

    if existing:
        cur.execute("""
            UPDATE sma_monitoring
            SET dpd=%s, sma_classification=%s, severity=%s,
                outstanding_lakhs=%s, updated_at=NOW()
            WHERE case_id=%s
        """, (dpd, classification["classification"], classification["severity"],
              outstanding_lakhs, case_id))
    else:
        cur.execute("""
            INSERT INTO sma_monitoring
                (case_id, dpd, sma_classification, severity, outstanding_lakhs)
            VALUES (%s, %s, %s, %s, %s)
        """, (case_id, dpd, classification["classification"],
              classification["severity"], outstanding_lakhs))

    db_conn.commit()
    cur.close()
    return classification


# ─── F2: CRILC Reporting ─────────────────────────────────────────────────────

def check_crilc_eligible(outstanding_cr: float) -> bool:
    """CRILC mandatory for exposures ≥ ₹5 Crore."""
    return outstanding_cr >= 5.0


def trigger_crilc_report(db_conn, case_id: str, borrower_name: str,
                         outstanding_cr: float, sma_status: str) -> Optional[int]:
    """Create CRILC submission record if exposure ≥ ₹5Cr."""
    if not check_crilc_eligible(outstanding_cr):
        return None

    cur = db_conn.cursor()
    quarter = f"{datetime.now().year}-Q{(datetime.now().month-1)//3+1}"
    cur.execute("""
        INSERT INTO crilc_submissions
            (case_id, borrower_name, outstanding_cr, sma_status,
             quarter, submission_status)
        VALUES (%s, %s, %s, %s, %s, 'PENDING')
    """, (case_id, borrower_name, outstanding_cr, sma_status, quarter))
    db_conn.commit()
    rid = cur.lastrowid
    cur.close()
    return rid


def get_crilc_submissions(db_conn, quarter: Optional[str] = None) -> List[Dict]:
    """List CRILC submissions, optionally for a specific quarter."""
    cur = db_conn.cursor(dictionary=True)
    if quarter:
        cur.execute(
            "SELECT * FROM crilc_submissions WHERE quarter=%s ORDER BY created_at DESC",
            (quarter,))
    else:
        cur.execute("SELECT * FROM crilc_submissions ORDER BY created_at DESC LIMIT 20")
    rows = cur.fetchall()
    cur.close()
    for r in rows:
        for k in ("created_at", "submitted_at"):
            if r.get(k) and hasattr(r[k], "isoformat"):
                r[k] = r[k].isoformat()
    return rows


def get_demo_sma_dashboard() -> Dict[str, Any]:
    """Demo SMA data when no real data exists."""
    return {
        "sma_counts": {
            "REGULAR": 42,
            "SMA-0": 8,
            "SMA-1": 3,
            "SMA-2": 1,
            "NPA": 0,
        },
        "total_monitored": 54,
        "recent_alerts": [
            {"case_id": "APP-2025-00012", "sma_classification": "SMA-1", "dpd": 45, "severity": "ALERT", "outstanding_lakhs": 125.0},
            {"case_id": "APP-2025-00008", "sma_classification": "SMA-2", "dpd": 72, "severity": "CRITICAL", "outstanding_lakhs": 340.0},
        ],
        "early_warnings": [
            {"signal": "CC_UTILISATION_SPIKE", "case_id": "APP-2025-00015", "description": "CC utilisation at 97%", "severity": "HIGH"},
            {"signal": "GST_FILING_MISSED", "case_id": "APP-2025-00019", "description": "Q3 GST filing missed", "severity": "MEDIUM"},
        ],
        "computed_at": datetime.now().isoformat(),
        "is_demo": True,
    }


def get_demo_crilc() -> List[Dict]:
    """Demo CRILC submissions."""
    return [
        {"case_id": "APP-2025-00003", "borrower_name": "ABC Industries Ltd", "outstanding_cr": 8.5, "sma_status": "REGULAR", "quarter": "2026-Q1", "submission_status": "SUBMITTED"},
        {"case_id": "APP-2025-00007", "borrower_name": "XYZ Exports Pvt Ltd", "outstanding_cr": 12.2, "sma_status": "SMA-0", "quarter": "2026-Q1", "submission_status": "PENDING"},
    ]
