"""
Block B: Model Performance Tracking
B1 — Core Performance Metrics (monthly)
B2 — Score Distribution & Threshold Calibration (weekly)
"""
import json
import math
import numpy as np
from datetime import datetime
from typing import Dict, Any, List, Optional


# ─── B1: Core Performance Metrics ─────────────────────────────────────────────

def _safe_auc(y_true, y_score):
    """Compute AUC-ROC safely, return None if impossible."""
    try:
        from sklearn.metrics import roc_auc_score
        if len(set(y_true)) < 2:
            return None
        return round(float(roc_auc_score(y_true, y_score)), 4)
    except Exception:
        return None


def _safe_ks(y_true, y_score):
    """KS Statistic — maximum separation between cumulative distributions."""
    try:
        pos = sorted([s for s, y in zip(y_score, y_true) if y == 1])
        neg = sorted([s for s, y in zip(y_score, y_true) if y == 0])
        if not pos or not neg:
            return None
        all_scores = sorted(set(y_score))
        max_ks = 0.0
        for thresh in all_scores:
            tpr = sum(1 for p in pos if p <= thresh) / len(pos)
            fpr = sum(1 for n in neg if n <= thresh) / len(neg)
            max_ks = max(max_ks, abs(tpr - fpr))
        return round(max_ks, 4)
    except Exception:
        return None


def _brier_score(y_true, y_prob):
    """Brier Score — calibration of PD estimates."""
    try:
        n = len(y_true)
        if n == 0:
            return None
        return round(sum((p - y) ** 2 for p, y in zip(y_prob, y_true)) / n, 4)
    except Exception:
        return None


def compute_performance_metrics(completed_apps: List[Dict]) -> Dict[str, Any]:
    """
    Compute monthly performance metrics from completed applications.
    Each app dict should have:
      - predicted_pd (float)  from layer5_output → decision_summary → probability_of_default
      - actual_default (0/1)  from loan servicing / SMA classification
      - credit_score          from layer5_output → decision_summary → final_credit_score
      - decision              APPROVE / REJECT / CONDITIONAL
    """
    if not completed_apps:
        return _demo_metrics()

    y_true = [a.get("actual_default", 0) for a in completed_apps]
    y_score = [a.get("predicted_pd", 0.1) for a in completed_apps]

    auc = _safe_auc(y_true, y_score)
    ks = _safe_ks(y_true, y_score)
    gini = round(2 * auc - 1, 4) if auc is not None else None
    brier = _brier_score(y_true, y_score)

    # F1 — use threshold 0.5 for binary classification
    try:
        from sklearn.metrics import f1_score, precision_score, recall_score
        y_pred = [1 if p >= 0.5 else 0 for p in y_score]
        f1 = round(float(f1_score(y_true, y_pred, zero_division=0)), 4)
        precision = round(float(precision_score(y_true, y_pred, zero_division=0)), 4)
        recall = round(float(recall_score(y_true, y_pred, zero_division=0)), 4)
    except Exception:
        f1, precision, recall = None, None, None

    # RAG status
    def auc_status(v):
        if v is None: return "GREY"
        if v >= 0.75: return "GREEN"
        if v >= 0.65: return "AMBER"
        return "RED"

    def ks_status(v):
        if v is None: return "GREY"
        if v >= 0.40: return "GREEN"
        if v >= 0.30: return "AMBER"
        return "RED"

    def brier_status(v):
        if v is None: return "GREY"
        if v <= 0.15: return "GREEN"
        if v <= 0.25: return "AMBER"
        return "RED"

    metrics = {
        "period": datetime.now().strftime("%Y-%m"),
        "sample_size": len(completed_apps),
        "auc_roc": auc,
        "auc_status": auc_status(auc),
        "ks_statistic": ks,
        "ks_status": ks_status(ks),
        "gini_coefficient": gini,
        "gini_status": auc_status(auc),  # Gini follows AUC thresholds
        "f1_score": f1,
        "precision": precision,
        "recall": recall,
        "brier_score": brier,
        "brier_status": brier_status(brier),
        "computed_at": datetime.now().isoformat(),
    }
    return metrics


def _demo_metrics() -> Dict[str, Any]:
    """Return demo/seed metrics when no real data is available."""
    return {
        "period": datetime.now().strftime("%Y-%m"),
        "sample_size": 0,
        "auc_roc": 0.82,
        "auc_status": "GREEN",
        "ks_statistic": 0.47,
        "ks_status": "GREEN",
        "gini_coefficient": 0.64,
        "gini_status": "GREEN",
        "f1_score": 0.78,
        "precision": 0.81,
        "recall": 0.75,
        "brier_score": 0.12,
        "brier_status": "GREEN",
        "computed_at": datetime.now().isoformat(),
        "is_demo": True,
    }


def save_performance_metrics(db_conn, metrics: Dict):
    """Persist monthly metrics to DB."""
    cur = db_conn.cursor()
    cur.execute("""
        INSERT INTO performance_metrics
            (period, sample_size, auc_roc, ks_statistic, gini_coefficient,
             f1_score, precision_val, recall_val, brier_score, computed_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
    """, (
        metrics["period"], metrics["sample_size"],
        metrics.get("auc_roc"), metrics.get("ks_statistic"),
        metrics.get("gini_coefficient"), metrics.get("f1_score"),
        metrics.get("precision"), metrics.get("recall"),
        metrics.get("brier_score"),
    ))
    db_conn.commit()
    cur.close()


def get_performance_history(db_conn, limit: int = 12) -> List[Dict]:
    """Return last N months of performance metrics."""
    cur = db_conn.cursor(dictionary=True)
    cur.execute(
        "SELECT * FROM performance_metrics ORDER BY computed_at DESC LIMIT %s",
        (limit,))
    rows = cur.fetchall()
    cur.close()
    for r in rows:
        for k in ("computed_at",):
            if r.get(k) and hasattr(r[k], "isoformat"):
                r[k] = r[k].isoformat()
    return rows


# ─── B2: Score Distribution & Threshold Calibration ───────────────────────────

def compute_score_distribution(completed_apps: List[Dict]) -> Dict[str, Any]:
    """
    Compute weekly score distribution stats.
    Each app dict should have 'credit_score', 'decision'.
    """
    if not completed_apps:
        return _demo_distribution()

    scores = [a.get("credit_score", 650) for a in completed_apps]
    decisions = [a.get("decision", "PENDING") for a in completed_apps]

    total = len(scores)
    approved = sum(1 for d in decisions if d in ("APPROVE", "CONDITIONAL APPROVE"))

    # Grade bands
    bands = {"A (750+)": 0, "B (700-749)": 0, "C (650-699)": 0, "D (<650)": 0}
    for s in scores:
        if s >= 750: bands["A (750+)"] += 1
        elif s >= 700: bands["B (700-749)"] += 1
        elif s >= 650: bands["C (650-699)"] += 1
        else: bands["D (<650)"] += 1

    band_pct = {k: round(v / total * 100, 1) if total else 0 for k, v in bands.items()}

    return {
        "period": datetime.now().strftime("%Y-W%U"),
        "total_cases": total,
        "mean_score": round(sum(scores) / total, 1) if total else 0,
        "std_score": round(float(np.std(scores)), 1) if total else 0,
        "approval_rate_pct": round(approved / total * 100, 1) if total else 0,
        "grade_band_counts": bands,
        "grade_band_pct": band_pct,
        "computed_at": datetime.now().isoformat(),
    }


def _demo_distribution() -> Dict[str, Any]:
    return {
        "period": datetime.now().strftime("%Y-W%U"),
        "total_cases": 0,
        "mean_score": 694.5,
        "std_score": 42.3,
        "approval_rate_pct": 72.4,
        "grade_band_counts": {"A (750+)": 15, "B (700-749)": 28, "C (650-699)": 22, "D (<650)": 10},
        "grade_band_pct": {"A (750+)": 20.0, "B (700-749)": 37.3, "C (650-699)": 29.3, "D (<650)": 13.3},
        "computed_at": datetime.now().isoformat(),
        "is_demo": True,
    }
