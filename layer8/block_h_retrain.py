"""
Block H: Retraining Pipeline
H1 — Auto-Trigger Logic
H2 — Feedback Loop (actual loan outcomes)
H3 — Shadow Mode (mandatory before promote)
H4 — A/B Testing
H5 — RMCB Sign-off Before Promotion
"""
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional


# ─── H1: Auto-Trigger Logic ──────────────────────────────────────────────────

RETRAIN_TRIGGERS = {
    "AUC_DEGRADED": {"threshold": 0.65, "operator": "<", "description": "AUC-ROC below 0.65"},
    "PSI_HIGH": {"threshold": 0.25, "operator": ">", "description": "PSI > 0.25 on any feature"},
    "ADWIN_DRIFT": {"threshold": True, "description": "ADWIN concept drift detected"},
    "OVERRIDE_RATE_HIGH": {"threshold": 0.35, "operator": ">", "description": "Override rate > 35%"},
    "REGULATION_CHANGE": {"description": "New RBI regulation requiring model change"},
    "TIME_ELAPSED": {"threshold_months": 6, "description": "6 months since last retraining"},
}


def check_retrain_triggers(metrics: Dict, drift_report: Dict = None,
                           override_rate: float = 0,
                           last_retrain_date: str = None) -> Dict[str, Any]:
    """
    Check if any retraining trigger condition is met.
    Returns which triggers fired.
    """
    triggered = []

    # AUC check
    auc = metrics.get("auc_roc")
    if auc is not None and auc < 0.65:
        triggered.append({
            "trigger": "AUC_DEGRADED",
            "value": auc,
            "threshold": 0.65,
            "message": f"AUC-ROC ({auc}) below threshold (0.65)",
        })

    # PSI check
    if drift_report:
        red_features = [f for f in drift_report.get("features", []) if f.get("status") == "RED"]
        if red_features:
            triggered.append({
                "trigger": "PSI_HIGH",
                "value": len(red_features),
                "message": f"{len(red_features)} feature(s) with PSI > 0.25",
                "features": [f["feature"] for f in red_features],
            })

        concept = drift_report.get("concept_drift", {})
        if concept.get("status") == "RED":
            triggered.append({
                "trigger": "ADWIN_DRIFT",
                "value": concept.get("gap_pct"),
                "message": f"Concept drift detected — PD gap {concept.get('gap_pct')}%",
            })

    # Override rate
    if override_rate > 0.35:
        triggered.append({
            "trigger": "OVERRIDE_RATE_HIGH",
            "value": round(override_rate * 100, 1),
            "threshold": 35,
            "message": f"Override rate ({override_rate*100:.1f}%) exceeds 35%",
        })

    # Time elapsed
    if last_retrain_date:
        try:
            last_dt = datetime.fromisoformat(last_retrain_date)
            months_elapsed = (datetime.now() - last_dt).days / 30
            if months_elapsed >= 6:
                triggered.append({
                    "trigger": "TIME_ELAPSED",
                    "value": round(months_elapsed, 1),
                    "message": f"{months_elapsed:.0f} months since last retraining (threshold: 6)",
                })
        except Exception:
            pass

    return {
        "should_retrain": len(triggered) > 0,
        "triggers_fired": triggered,
        "trigger_count": len(triggered),
        "checked_at": datetime.now().isoformat(),
    }


# ─── H2/H3/H4: Retraining Events ────────────────────────────────────────────

def log_retrain_event(db_conn, trigger: str, status: str = "INITIATED",
                      details: Dict = None) -> int:
    """Log a retraining event."""
    cur = db_conn.cursor()
    cur.execute("""
        INSERT INTO retraining_log
            (trigger_type, status, details_json)
        VALUES (%s, %s, %s)
    """, (trigger, status, json.dumps(details or {})))
    db_conn.commit()
    rid = cur.lastrowid
    cur.close()
    return rid


def run_shadow_mode_check(shadow_results: Dict) -> Dict[str, Any]:
    """
    H3: Shadow Mode validation.
    New model scores 200+ cases silently.
    Agreement rate > 90% + AUC improvement → promote.
    """
    cases_scored = shadow_results.get("cases_scored", 0)
    agreement_rate = shadow_results.get("agreement_rate", 0)
    new_auc = shadow_results.get("new_model_auc", 0)
    old_auc = shadow_results.get("old_model_auc", 0)

    checks = {
        "min_cases": cases_scored >= 200,
        "agreement_rate": agreement_rate >= 0.90,
        "auc_improvement": new_auc > old_auc,
    }

    return {
        "ready_to_promote": all(checks.values()),
        "cases_scored": cases_scored,
        "agreement_rate_pct": round(agreement_rate * 100, 1),
        "new_auc": new_auc,
        "old_auc": old_auc,
        "auc_improvement": round(new_auc - old_auc, 4),
        "checks": checks,
        "recommendation": "PROMOTE" if all(checks.values()) else "CONTINUE SHADOW",
    }


def get_retraining_status(db_conn) -> Dict[str, Any]:
    """Get current retraining status and history."""
    cur = db_conn.cursor(dictionary=True)
    cur.execute("""
        SELECT * FROM retraining_log
        ORDER BY created_at DESC LIMIT 10
    """)
    history = cur.fetchall()
    cur.close()

    for r in history:
        for k in ("created_at",):
            if r.get(k) and hasattr(r[k], "isoformat"):
                r[k] = r[k].isoformat()
        if isinstance(r.get("details_json"), str):
            try:
                r["details_json"] = json.loads(r["details_json"])
            except Exception:
                pass

    # Find last completed retrain
    last_retrain = None
    for h in history:
        if h.get("status") == "COMPLETED":
            last_retrain = h.get("created_at")
            break

    return {
        "last_retrain_date": last_retrain,
        "history": history,
        "total_events": len(history),
    }


def get_demo_retraining_status() -> Dict[str, Any]:
    """Demo retraining status."""
    return {
        "last_retrain_date": "2025-09-01T00:00:00",
        "next_retrain_due": "2026-03-01T00:00:00",
        "current_model": "XGB_CREDIT_V4.3",
        "shadow_mode_active": False,
        "ab_test_active": False,
        "history": [
            {"trigger_type": "SCHEDULED", "status": "COMPLETED", "created_at": "2025-09-01T10:00:00",
             "details_json": {"old_auc": 0.81, "new_auc": 0.84, "improvement": "+3.7%"}},
            {"trigger_type": "PSI_HIGH", "status": "COMPLETED", "created_at": "2025-06-15T14:30:00",
             "details_json": {"triggered_features": ["gst_2a_3b_gap", "bank_od_utilisation_pct"]}},
        ],
        "triggers_definition": RETRAIN_TRIGGERS,
        "is_demo": True,
    }
