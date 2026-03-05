"""
Step 11 — Score Snapshot & Audit Storage
Assembles a tamper-evident audit snapshot with SHA-256 hashes.
"""
import hashlib
import json
from typing import Dict, Any
from datetime import datetime, timezone


def build_snapshot(
    features: Dict[str, float],
    xgb_result: Dict,
    shap_result: Dict,
    confidence_result: Dict,
    fusion_result: Dict,
    llm_result: Dict,
    decision_result: Dict,
    pricing_result: Dict,
    loan_result: Dict,
    validation_result: Dict,
    hard_rules_result: Dict,
    case_id: str = "",
) -> Dict[str, Any]:
    """Build RBI-audit-ready snapshot with hashes."""
    ts = datetime.now(timezone.utc).isoformat()

    # Hash feature vector (tamper detection)
    fv_str = json.dumps(features, sort_keys=True, default=str)
    fv_hash = hashlib.sha256(fv_str.encode()).hexdigest()

    # Hash LLM opinion
    llm_opinion = llm_result.get("qualitative_opinion", "")
    llm_hash = hashlib.sha256(llm_opinion.encode()).hexdigest()

    snapshot = {
        "case_metadata": {
            "case_id": case_id,
            "snapshot_timestamp": ts,
        },
        "feature_vector_snapshot": {
            "features": features,
            "feature_count": len(features),
            "imputation_flags": validation_result.get("imputation_log", []),
            "feature_vector_hash_sha256": fv_hash,
        },
        "model_metadata": {
            "model_version": xgb_result.get("model_version", ""),
            "model_hash": xgb_result.get("model_hash", ""),
            "is_mock_model": xgb_result.get("is_mock_model", True),
            "inference_timestamp": xgb_result.get("inference_timestamp", ""),
            "shap_is_surrogate": shap_result.get("is_surrogate", True),
        },
        "score_history": {
            "xgboost_raw_score": xgb_result.get("credit_score"),
            "xgboost_pd": xgb_result.get("pd_score"),
            "llm_adjustment": llm_result.get("score_adjustment", 0),
            "uncertainty_penalty": fusion_result.get("score_breakdown", {}).get("uncertainty_penalty", 0),
            "amber_alert_penalty": fusion_result.get("score_breakdown", {}).get("amber_alert_penalty", 0),
            "hc_condition_penalty": fusion_result.get("score_breakdown", {}).get("hc_condition_penalty", 0),
            "final_adjusted_score": fusion_result.get("final_score"),
            "final_pd": fusion_result.get("final_pd"),
            "pd_lower_bound": confidence_result.get("pd_lower_10pct"),
            "pd_upper_bound": confidence_result.get("pd_upper_90pct"),
            "confidence_range": f"{confidence_result.get('score_lower', 0)}–{confidence_result.get('score_upper', 0)}",
        },
        "decision_record": {
            "hard_rules_evaluated": len(hard_rules_result.get("rule_log", [])),
            "hard_rules_all_pass": hard_rules_result.get("gate") != "HARD_REJECT",
            "decision": decision_result.get("decision"),
            "interest_rate": pricing_result.get("final_interest_rate"),
            "sanction_limit": loan_result.get("sanction_limit_lakhs"),
            "approved_amount": loan_result.get("approved_amount_lakhs"),
            "conditions_count": len(decision_result.get("conditions", [])),
            "covenants_count": len(decision_result.get("covenants", [])),
            "llm_opinion_hash_sha256": llm_hash,
        },
        "auditability": {
            "automated_vs_human": "AUTOMATED",
            "override_applied": False,
            "data_retention_years": 8,
            "encryption_at_rest": "AES-256",
        },
    }

    print(f"  Step 11 Snapshot: hash={fv_hash[:12]}... | {ts}")
    return snapshot
