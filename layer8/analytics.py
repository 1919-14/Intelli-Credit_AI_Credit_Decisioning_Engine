"""
Layer 8 — Accuracy & System Analytics Module
Computes real-time metrics from application data for the analytics dashboard.
"""
import json
from typing import Dict, Any, List


def compute_analytics(applications: List[Dict], audit_logs: List[Dict] = None) -> Dict[str, Any]:
    """
    Compute accuracy metrics across all completed applications.

    Metrics:
      1. AI vs Human Agreement (True Accuracy)
      2. Extraction Completeness (Fill Rate)
      3. Extraction Method Distribution (LLM vs OCR vs Regex)
      4. Processing Time & ROI
    """
    total_cases = len(applications)
    if total_cases == 0:
        return _empty_metrics()

    # Accumulators
    agreement_scores = []
    fill_rates = []
    method_counts = {"LLM": 0, "OCR": 0, "Regex": 0, "Unknown": 0}
    processing_times = []
    decisions = {"APPROVE": 0, "CONDITIONAL": 0, "REJECT": 0, "OTHER": 0}
    per_case = []

    for app in applications:
        case_metrics = {"case_id": app.get("case_id", "?"), "company": app.get("company_name", "?")}

        # ── 1. AI vs Human Agreement ──────────────────────
        hitl_data = _extract_hitl_data(app, audit_logs or [])
        if hitl_data["total_fields"] > 0:
            accuracy = ((hitl_data["total_fields"] - hitl_data["edited_fields"])
                        / hitl_data["total_fields"]) * 100
        else:
            accuracy = 100.0  # No fields reviewed = assume AI was correct
        agreement_scores.append(accuracy)
        case_metrics["agreement_pct"] = round(accuracy, 1)
        case_metrics["fields_edited"] = hitl_data["edited_fields"]

        # ── 2. Fill Rate ──────────────────────────────────
        l2 = _safe_json(app.get("layer2_output"))
        fill = _compute_fill_rate(l2)
        fill_rates.append(fill)
        case_metrics["fill_rate"] = round(fill, 1)

        # ── 3. Extraction Method ──────────────────────────
        method = _detect_extraction_method(l2, app)
        method_counts[method] = method_counts.get(method, 0) + 1
        case_metrics["extraction_method"] = method

        # ── 4. Processing Time ────────────────────────────
        ptime = _get_processing_time(app)
        if ptime > 0:
            processing_times.append(ptime)
        case_metrics["processing_time_sec"] = round(ptime, 1)

        # ── Decision Tracking ─────────────────────────────
        l5 = _safe_json(app.get("layer5_output"))
        dec = l5.get("decision_summary", {}).get("decision", "") if l5 else ""
        if dec in decisions:
            decisions[dec] += 1
        elif dec:
            decisions["OTHER"] += 1
        case_metrics["decision"] = dec

        per_case.append(case_metrics)

    # ── Aggregate ─────────────────────────────────────────
    avg_agreement = sum(agreement_scores) / len(agreement_scores) if agreement_scores else 0
    avg_fill = sum(fill_rates) / len(fill_rates) if fill_rates else 0
    avg_time = sum(processing_times) / len(processing_times) if processing_times else 0

    # Estimate human hours saved (assume manual CAM takes ~4 hours)
    manual_hours_per_case = 4.0
    total_human_hours_saved = total_cases * manual_hours_per_case - (sum(processing_times) / 3600)

    return {
        "summary": {
            "total_cases": total_cases,
            "avg_agreement_pct": round(avg_agreement, 1),
            "avg_fill_rate_pct": round(avg_fill, 1),
            "avg_processing_time_sec": round(avg_time, 1),
            "human_hours_saved": round(max(0, total_human_hours_saved), 1),
        },
        "agreement_trend": [{"case": c["case_id"], "pct": c["agreement_pct"]} for c in per_case],
        "fill_rate_trend": [{"case": c["case_id"], "pct": c["fill_rate"]} for c in per_case],
        "extraction_methods": method_counts,
        "decisions": decisions,
        "processing_times": [{"case": c["case_id"], "sec": c["processing_time_sec"]} for c in per_case],
        "per_case": per_case,
        "accuracy_formula": {
            "name": "AI vs Human Agreement",
            "formula": "((Total Fields - Human Edited Fields) / Total Fields) × 100",
            "description": (
                "When the Credit Officer reviews AI-extracted data in the HITL dashboard, "
                "we track every field they edit. If the AI extracts 100 data points and the "
                "human edits 3 of them, the true AI accuracy for that document is 97%. "
                "This gives us a reliable, production-grade accuracy metric that improves "
                "over time as the model learns from corrections."
            ),
        },
    }


def compute_case_analytics(app: Dict, audit_logs: List[Dict] = None) -> Dict[str, Any]:
    """Compute accuracy metrics for a single case."""
    return compute_analytics([app], audit_logs)


# ── Private helpers ───────────────────────────────────────────────────────────

def _safe_json(val):
    """Parse JSON string or return dict as-is."""
    if val is None:
        return {}
    if isinstance(val, dict):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return {}


def _extract_hitl_data(app, audit_logs):
    """
    Count total fields and edited fields from HITL review.
    Uses audit_logs with action='HITL_CONFIRM', 'L4_HITL_3', etc.
    """
    case_id = app.get("case_id", "")
    total_fields = 0
    edited_fields = 0

    # Count from Layer 2 output (schema fields)
    l2 = _safe_json(app.get("layer2_output"))
    extracted = l2.get("extracted", {}).get("financial_data", {}) or l2
    if isinstance(extracted, dict):
        total_fields = len([k for k, v in extracted.items() if v is not None and v != "" and v != 0])

    # Count edits from audit logs
    for log in audit_logs:
        if log.get("case_id") != case_id:
            continue
        action = log.get("action", "")
        details = _safe_json(log.get("details"))

        if action == "HITL_ADD_CUSTOM_FIELD":
            edited_fields += 1
        elif action == "L4_HITL_3":
            # Feature overrides count
            edited_fields += details.get("overrides", 0)
        elif action == "HITL_CONFIRM":
            edited_fields += details.get("corrections", 0)

    return {"total_fields": max(total_fields, 1), "edited_fields": edited_fields}


def _compute_fill_rate(l2_data: dict) -> float:
    """What % of master schema fields were populated by AI extraction."""
    # Key fields we expect from financial documents
    KEY_FIELDS = [
        "company_name", "pan_number", "gstin", "cin",
        "total_revenue", "revenue_from_operations", "ebitda",
        "profit_after_tax", "net_worth", "total_debt",
        "current_assets", "current_liabilities",
        "promoter_holding_pct", "assessee_name",
        "total_outstanding_borrowings",
    ]

    extracted = l2_data.get("extracted", {}).get("financial_data", {}) or l2_data
    if not isinstance(extracted, dict):
        return 0.0

    filled = sum(1 for f in KEY_FIELDS if extracted.get(f) not in (None, "", 0, "N/A"))
    return (filled / len(KEY_FIELDS)) * 100 if KEY_FIELDS else 0.0


def _detect_extraction_method(l2_data: dict, app: dict) -> str:
    """Detect whether LLM, OCR, or Regex was the primary extraction method."""
    # Check metadata in L2 output
    meta = l2_data.get("metadata", {})
    if isinstance(meta, dict):
        method = meta.get("extraction_method", "")
        if method:
            return method

    # Check per-chunk metadata
    chunks = l2_data.get("chunks", [])
    if isinstance(chunks, list):
        methods = {}
        for ch in chunks:
            if isinstance(ch, dict):
                m = ch.get("extraction_method", ch.get("ocr_engine", ""))
                if m:
                    methods[m] = methods.get(m, 0) + 1
        if methods:
            return max(methods, key=methods.get)

    # Fallback: if L2 output is substantial, assume LLM
    extracted = l2_data.get("extracted", {})
    if extracted and isinstance(extracted, dict) and len(str(extracted)) > 200:
        return "LLM"

    return "Unknown"


def _get_processing_time(app: dict) -> float:
    """Get processing time from app metadata or compute from timestamps."""
    # Check if pipeline_timing was recorded
    l5 = _safe_json(app.get("layer5_output"))
    if l5:
        timing = l5.get("pipeline_timing", {})
        if isinstance(timing, dict) and timing.get("total_seconds"):
            return float(timing["total_seconds"])

    # Compute from created_at to completed_at
    created = app.get("created_at")
    completed = app.get("completed_at")
    if created and completed:
        from datetime import datetime
        try:
            if isinstance(created, str):
                created = datetime.fromisoformat(created)
            if isinstance(completed, str):
                completed = datetime.fromisoformat(completed)
            return (completed - created).total_seconds()
        except (ValueError, TypeError):
            pass

    return 0.0


def _empty_metrics():
    return {
        "summary": {
            "total_cases": 0, "avg_agreement_pct": 0, "avg_fill_rate_pct": 0,
            "avg_processing_time_sec": 0, "human_hours_saved": 0,
        },
        "agreement_trend": [], "fill_rate_trend": [], "extraction_methods": {},
        "decisions": {}, "processing_times": [], "per_case": [],
        "accuracy_formula": {
            "name": "AI vs Human Agreement",
            "formula": "((Total Fields - Human Edited Fields) / Total Fields) × 100",
            "description": "No data available yet. Process at least one application to see metrics.",
        },
    }
