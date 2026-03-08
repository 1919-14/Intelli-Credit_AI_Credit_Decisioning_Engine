"""
Block A: Model Inventory & Governance Register
RBI MRM Circular Aug 2024 — MANDATORY

A1: Model Inventory Register — maintained per RBI requirement
A2: Change Control Process — log, approve, shadow, promote
"""
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List


# ─── Default Model Entry (seeded on first load) ──────────────────────────────
DEFAULT_MODEL = {
    "model_id": "XGB_CREDIT_V4.3",
    "model_name": "IntelliCredit XGBoost Scoring Engine",
    "model_type": "Credit Scoring (PD model)",
    "deployment_date": "2025-03-01",
    "developer_team": "IntelliCredit ML Team",
    "model_owner": "Chief Risk Officer",
    "rmcb_approval_date": "2025-02-15",
    "rmcb_resolution_no": "RMCB-2025-012",
    "last_validation_date": "2025-09-01",
    "next_validation_due": "2026-09-01",
    "model_risk_rating": "HIGH",
    "is_third_party": False,
    "status": "LIVE",
}


def seed_model_inventory(db_conn):
    """Insert the default model record if none exists."""
    cur = db_conn.cursor(dictionary=True)
    cur.execute("SELECT COUNT(*) AS cnt FROM model_inventory")
    if cur.fetchone()["cnt"] == 0:
        cur.execute("""
            INSERT INTO model_inventory
                (model_id, model_name, model_type, deployment_date,
                 developer_team, model_owner, rmcb_approval_date,
                 rmcb_resolution_no, last_validation_date, next_validation_due,
                 model_risk_rating, is_third_party, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            DEFAULT_MODEL["model_id"],
            DEFAULT_MODEL["model_name"],
            DEFAULT_MODEL["model_type"],
            DEFAULT_MODEL["deployment_date"],
            DEFAULT_MODEL["developer_team"],
            DEFAULT_MODEL["model_owner"],
            DEFAULT_MODEL["rmcb_approval_date"],
            DEFAULT_MODEL["rmcb_resolution_no"],
            DEFAULT_MODEL["last_validation_date"],
            DEFAULT_MODEL["next_validation_due"],
            DEFAULT_MODEL["model_risk_rating"],
            0,  # is_third_party
            DEFAULT_MODEL["status"],
        ))
        db_conn.commit()
    cur.close()


def get_model_inventory(db_conn) -> List[Dict]:
    """Return all models in the inventory."""
    cur = db_conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM model_inventory ORDER BY id DESC")
    rows = cur.fetchall()
    cur.close()
    for r in rows:
        for k in ("deployment_date", "rmcb_approval_date",
                   "last_validation_date", "next_validation_due", "created_at"):
            if r.get(k) and hasattr(r[k], "isoformat"):
                r[k] = r[k].isoformat()
        r["is_third_party"] = bool(r.get("is_third_party"))
    return rows


def update_model_status(db_conn, model_id: str, new_status: str,
                        updated_by: str = "system") -> bool:
    """Update status (LIVE / SHADOW / RETIRED) for a model."""
    valid = {"LIVE", "SHADOW", "RETIRED"}
    if new_status not in valid:
        return False
    cur = db_conn.cursor()
    cur.execute("UPDATE model_inventory SET status=%s WHERE model_id=%s",
                (new_status, model_id))
    db_conn.commit()
    affected = cur.rowcount
    cur.close()

    # Also log the change
    log_change_request(db_conn, {
        "model_id": model_id,
        "change_type": "STATUS_CHANGE",
        "description": f"Status changed to {new_status}",
        "impact_assessment": "Model status update",
        "requested_by": updated_by,
    })
    return affected > 0


def get_model_risk_rating(exposure_lakhs: float, is_automated: bool) -> str:
    """
    Model Risk Rating criteria per RBI:
      HIGH:   automated credit decisions > ₹25L
      MEDIUM: advisory / pricing only
      LOW:    monitoring / reporting only
    """
    if is_automated and exposure_lakhs > 25:
        return "HIGH"
    elif is_automated:
        return "MEDIUM"
    return "LOW"


# ─── A2: Change Control ──────────────────────────────────────────────────────

def log_change_request(db_conn, change: Dict[str, Any]) -> int:
    """
    Log a change request.  Required keys:
      model_id, change_type, description, impact_assessment, requested_by
    """
    cur = db_conn.cursor()
    cur.execute("""
        INSERT INTO model_change_log
            (model_id, change_type, description, impact_assessment,
             requested_by, status)
        VALUES (%s,%s,%s,%s,%s,'PENDING')
    """, (
        change["model_id"],
        change["change_type"],
        change["description"],
        change.get("impact_assessment", ""),
        change.get("requested_by", "system"),
    ))
    db_conn.commit()
    change_id = cur.lastrowid
    cur.close()
    return change_id


def approve_change(db_conn, change_id: int, approved_by: str) -> bool:
    """Mark a change request as APPROVED by RMCB/IMV."""
    cur = db_conn.cursor()
    cur.execute("""
        UPDATE model_change_log
        SET status='APPROVED', approved_by=%s, approved_at=NOW()
        WHERE id=%s
    """, (approved_by, change_id))
    db_conn.commit()
    ok = cur.rowcount > 0
    cur.close()
    return ok


def get_change_log(db_conn, model_id: Optional[str] = None) -> List[Dict]:
    """Return change control log, optionally filtered by model."""
    cur = db_conn.cursor(dictionary=True)
    if model_id:
        cur.execute(
            "SELECT * FROM model_change_log WHERE model_id=%s ORDER BY created_at DESC",
            (model_id,))
    else:
        cur.execute("SELECT * FROM model_change_log ORDER BY created_at DESC")
    rows = cur.fetchall()
    cur.close()
    for r in rows:
        for k in ("created_at", "approved_at"):
            if r.get(k) and hasattr(r[k], "isoformat"):
                r[k] = r[k].isoformat()
    return rows
