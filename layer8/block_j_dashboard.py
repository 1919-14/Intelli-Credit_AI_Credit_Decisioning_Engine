"""
Block J: Dashboard Data Aggregation
Single endpoint to feed all 6 monitoring panels.
"""
import json
from datetime import datetime
from typing import Dict, Any

from layer8.block_b_performance import compute_performance_metrics, _demo_metrics, compute_score_distribution, _demo_distribution
from layer8.block_d_drift import get_demo_drift_report
from layer8.block_f_npa import get_demo_sma_dashboard, get_demo_crilc
from layer8.block_h_retrain import get_demo_retraining_status


def get_dashboard_data(db_conn) -> Dict[str, Any]:
    """
    Aggregate data for all 6 monitoring panels:
      Panel 1: Model Health (AUC/KS/Gini/Brier)
      Panel 2: PSI Drift (25 features heatmap)
      Panel 3: Override Pattern chart
      Panel 4: SMA Dashboard (SMA-0/1/2/NPA counts)
      Panel 5: Retraining status + IMV due date
      Panel 6: CRILC submission status
    """
    # Try to load real data; fall back to demo
    try:
        from layer8.block_b_performance import get_performance_history
        perf_history = get_performance_history(db_conn, limit=1)
        if perf_history:
            panel1 = perf_history[0]
        else:
            panel1 = _demo_metrics()
    except Exception:
        panel1 = _demo_metrics()

    # Panel 2: Drift
    try:
        from layer8.block_d_drift import get_drift_history
        drift_history = get_drift_history(db_conn, limit=1)
        if drift_history and drift_history[0].get("report_json"):
            panel2 = drift_history[0]["report_json"]
        else:
            panel2 = get_demo_drift_report()
    except Exception:
        panel2 = get_demo_drift_report()

    # Panel 3: Override patterns (from completed apps)
    try:
        cur = db_conn.cursor(dictionary=True)
        cur.execute("""
            SELECT decision, COUNT(*) as cnt
            FROM applications
            WHERE status = 'completed'
            GROUP BY decision
        """)
        decision_rows = cur.fetchall()
        cur.close()
        
        total = sum(r["cnt"] for r in decision_rows)
        if total > 0:
            overrides = sum(r["cnt"] for r in decision_rows if "CONDITIONAL" in r["decision"] or "REJECT" in r["decision"])
            panel3 = {
                "decisions": {r["decision"]: r["cnt"] for r in decision_rows},
                "total_decisions": total,
                "override_count": overrides,
                "override_rate_pct": round((overrides / total) * 100, 1),
                "is_demo": False
            }
        else:
            raise ValueError("No decisions found")
    except Exception:
        panel3 = {
            "decisions": {"APPROVE": 35, "CONDITIONAL APPROVE": 22, "REJECT": 18},
            "total_decisions": 75,
            "override_count": 12,
            "override_rate_pct": 16.0,
            "is_demo": True,
        }

    # Panel 4: SMA
    try:
        from layer8.block_f_npa import get_sma_dashboard
        panel4 = get_sma_dashboard(db_conn)
        if panel4.get("total_monitored", 0) == 0:
            panel4 = get_demo_sma_dashboard()
    except Exception:
        panel4 = get_demo_sma_dashboard()

    # Panel 5: Retraining
    try:
        from layer8.block_h_retrain import get_retraining_status
        panel5 = get_retraining_status(db_conn)
        if not panel5.get("history"):
            panel5 = get_demo_retraining_status()
    except Exception:
        panel5 = get_demo_retraining_status()

    # Panel 6: CRILC
    try:
        from layer8.block_f_npa import get_crilc_submissions
        panel6_data = get_crilc_submissions(db_conn)
        if not panel6_data:
            panel6_data = get_demo_crilc()
        panel6 = {
            "submissions": panel6_data,
            "total": len(panel6_data),
            "pending": sum(1 for s in panel6_data if isinstance(s, dict) and s.get("submission_status") == "PENDING"),
            "submitted": sum(1 for s in panel6_data if isinstance(s, dict) and s.get("submission_status") == "SUBMITTED"),
        }
    except Exception:
        crilc_demo = get_demo_crilc()
        panel6 = {
            "submissions": crilc_demo,
            "total": len(crilc_demo),
            "pending": 1,
            "submitted": 1,
            "is_demo": True,
        }

    # Model inventory summary
    try:
        from layer8.block_a_model_registry import get_model_inventory
        inventory = get_model_inventory(db_conn)
    except Exception:
        inventory = [{
            "model_id": "XGB_CREDIT_V4.3",
            "model_name": "IntelliCredit XGBoost Scoring Engine",
            "status": "LIVE",
            "model_risk_rating": "HIGH",
            "next_validation_due": "2026-09-01",
        }]

    return {
        "model_inventory": inventory[0] if inventory else {},
        "panel1_model_health": panel1,
        "panel2_psi_drift": panel2,
        "panel3_override_patterns": panel3,
        "panel4_sma_dashboard": panel4,
        "panel5_retraining": panel5,
        "panel6_crilc": panel6,
        "generated_at": datetime.now().isoformat(),
    }
