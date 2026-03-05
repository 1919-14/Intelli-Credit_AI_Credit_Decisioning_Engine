"""
Step 12 — Output Package Builder
Assembles the complete Layer 5 output for Layer 6 (CAM / Presentation).
"""
from typing import Dict, Any


def build_output_package(
    validation_result: Dict,
    hard_rules_result: Dict,
    xgb_result: Dict,
    shap_result: Dict,
    confidence_result: Dict,
    llm_result: Dict,
    fusion_result: Dict,
    pricing_result: Dict,
    decision_result: Dict,
    loan_result: Dict,
    snapshot: Dict,
) -> Dict[str, Any]:
    """Assemble final layer5_output dict for DB storage and Layer 6."""

    output = {
        # ─── Decision Summary ──────────────────────────────
        "decision_summary": {
            "decision": decision_result.get("decision"),
            "final_credit_score": fusion_result.get("final_score"),
            "risk_band": fusion_result.get("final_band"),
            "probability_of_default": fusion_result.get("final_pd"),
            "dscr": validation_result.get("validated_features", {}).get("dscr_proxy"),
            "sanction_amount_lakhs": loan_result.get("approved_amount_lakhs"),
            "interest_rate": pricing_result.get("final_interest_rate"),
            "processing_fee_pct": pricing_result.get("processing_fee_pct"),
            "tenure_months": loan_result.get("loan_structure", {}).get("term_loan", {}).get("tenure_months"),
            "conditions": decision_result.get("conditions", []),
            "covenants": decision_result.get("covenants", []),
        },

        # ─── Score Breakdown ───────────────────────────────
        "score_breakdown": fusion_result.get("score_breakdown", {}),

        # ─── Explanation Package ───────────────────────────
        "explanation": {
            "shap_top_positive": shap_result.get("top_positive_drivers", []),
            "shap_top_negative": shap_result.get("top_negative_drivers", []),
            "shap_waterfall": shap_result.get("waterfall_narrative", ""),
            "llm_opinion": llm_result.get("qualitative_opinion", ""),
            "five_cs": llm_result.get("five_cs", {}),
            "biggest_risk": llm_result.get("biggest_risk", ""),
            "biggest_strength": llm_result.get("biggest_strength", ""),
            "llm_adjustment": llm_result.get("score_adjustment", 0),
            "llm_justification": llm_result.get("adjustment_justification", ""),
            "override_flag": llm_result.get("override_flag", "MAINTAIN"),
        },

        # ─── Confidence ────────────────────────────────────
        "confidence": {
            "pd_point": confidence_result.get("pd_point_estimate"),
            "pd_lower": confidence_result.get("pd_lower_10pct"),
            "pd_upper": confidence_result.get("pd_upper_90pct"),
            "score_lower": confidence_result.get("score_lower"),
            "score_upper": confidence_result.get("score_upper"),
            "uncertainty_level": confidence_result.get("uncertainty_level"),
            "pricing_buffer_bps": confidence_result.get("pricing_buffer_bps"),
        },

        # ─── Pricing ────────────────────────────────────────
        "pricing": pricing_result,

        # ─── Loan Structure ─────────────────────────────────
        "loan_structure": loan_result,

        # ─── Validation & Rules ─────────────────────────────
        "validation": {
            "gate_status": validation_result.get("gate_status"),
            "imputation_log": validation_result.get("imputation_log", []),
        },
        "hard_rules": {
            "gate": hard_rules_result.get("gate"),
            "rule_log": hard_rules_result.get("rule_log", []),
            "conditions": hard_rules_result.get("conditions", []),
        },

        # ─── XGBoost Raw ────────────────────────────────────
        "xgboost": xgb_result,

        # ─── Risk Monitoring Triggers ───────────────────────
        "risk_triggers": [
            {"id": "RT-01", "description": "Re-score if credit score drops below 670 at quarterly review"},
            {"id": "RT-02", "description": "Alert if OD utilisation exceeds 70% in any month"},
            {"id": "RT-03", "description": "Alert if GST filing missed for any quarter"},
            {"id": "RT-04", "description": "Alert if bounce rate exceeds 5% in any 3-month window"},
            {"id": "RT-05", "description": "Annual full re-underwriting at 12-month mark"},
        ],

        # ─── Audit Snapshot ─────────────────────────────────
        "audit_snapshot": snapshot,
    }

    decision = output["decision_summary"]["decision"]
    score = output["decision_summary"]["final_credit_score"]
    print(f"  Step 12 Output: {decision} | Score={score} | "
          f"Rs.{output['decision_summary']['sanction_amount_lakhs']}L @ "
          f"{output['decision_summary']['interest_rate']}%")

    return output
