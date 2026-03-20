"""
Step 12 — Output Package Builder
Assembles the complete Layer 5 output for Layer 6 (CAM / Presentation).
"""
from datetime import datetime, timezone, timedelta
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
    layer2_data: Dict = None,
) -> Dict[str, Any]:
    """Assemble final layer5_output dict for DB storage and Layer 6."""

    l2 = layer2_data or {}

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
            "llm_decision_summary": decision_result.get("llm_decision_summary", ""),
            "green_financing": {
                "eligible": bool(pricing_result.get("green_eligible")),
                "discount_applied_pct": pricing_result.get("green_discount_pct", 0),
                "esg_transition_risk": l2.get("esg_transition_risk", "N/A"),
                "carbon_footprint_mt": l2.get("carbon_footprint_mt", "N/A"),
            },
        },

        # ─── Score Breakdown ───────────────────────────────
        "score_breakdown": fusion_result.get("score_breakdown", {}),
        "fusion_narrative": fusion_result.get("fusion_narrative", ""),

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

        # ─── Decision Audit Trail (Self-Explainability) ─────
        "decision_audit_trail": _build_audit_trail(
            validation_result, hard_rules_result, xgb_result, shap_result,
            confidence_result, llm_result, fusion_result, pricing_result,
            decision_result, loan_result, l2
        ),
    }

    decision = output["decision_summary"]["decision"]
    score = output["decision_summary"]["final_credit_score"]
    print(f"  Step 12 Output: {decision} | Score={score} | "
          f"Rs.{output['decision_summary']['sanction_amount_lakhs']}L @ "
          f"{output['decision_summary']['interest_rate']}%")

    return output


def _build_audit_trail(val, hr, xgb, shap, conf, llm, fusion, pricing, decision, loan, l2):
    """Build a complete, human-readable chain of reasoning for every decision."""
    try:
        # Score journey
        score_journey = fusion.get("fusion_narrative", "")

        # Hard rules summary
        rule_log = hr.get("rule_log", [])
        passed = sum(1 for r in rule_log if r.get("passed", True))
        failed = sum(1 for r in rule_log if not r.get("passed", True))
        conditions = hr.get("conditions", [])
        if failed == 0 and not conditions:
            hr_summary = f"All {passed} hard rules passed. No blocks."
        elif failed > 0:
            hr_summary = f"{failed} of {passed + failed} hard rules FAILED. Gate: {hr.get('gate', 'UNKNOWN')}."
        else:
            hr_summary = (f"All {passed} hard rules passed with {len(conditions)} conditional flag(s): "
                         + ", ".join(c.get("rule_id", "") for c in conditions))

        # Pricing explanation
        base = pricing.get("base_rate", 0)
        spread = pricing.get("band_spread", 0)
        unc = pricing.get("uncertainty_buffer_pct", 0)
        cond_pen = pricing.get("conditional_penalty_pct", 0)
        green_disc = pricing.get("green_discount_pct", 0)
        final_rate = pricing.get("final_interest_rate", 0)
        pricing_expl = (f"Base {base}% + Band spread {spread}% + Uncertainty {unc}% "
                       f"+ Condition penalty {cond_pen}%")
        if green_disc > 0:
            pricing_expl += f" − Green discount {green_disc}%"
        pricing_expl += f" = {final_rate}%"

        # ESG impact
        green = pricing.get("green_eligible", False)
        if green:
            esg_impact = (f"Green financing eligible → {green_disc}% rate discount applied. "
                         f"COV-07 ESG covenant added.")
        else:
            esg_impact = "No ESG/Climate report provided or green eligibility not established."

        # Statutory check
        filed = l2.get("annual_return_filed")
        declared = l2.get("declared_indebtedness")
        borr = l2.get("total_outstanding_borrowings")
        statutory = "No Annual Return data available."
        if filed is not None:
            filed_str = "✅ Filed" if (filed is True or str(filed).lower() == "true") else "⚠️ Not Filed"
            statutory = f"Annual Return: {filed_str}."
            if declared and borr:
                try:
                    d, b = float(declared), float(borr)
                    if b > 0:
                        gap = abs(d - b) / b * 100
                        statutory += f" Indebtedness mismatch: {gap:.1f}%"
                        statutory += " (within 5% tolerance)." if gap <= 5 else " ⚠️ EXCEEDS 5% tolerance."
                except (ValueError, TypeError):
                    pass

        # Key SHAP drivers
        pos = shap.get("top_positive_drivers", [])
        neg = shap.get("top_negative_drivers", [])
        key_drivers = []
        for d in pos[:3]:
            key_drivers.append(f"{d.get('label', '?')} = {d.get('value', '?')} (strength)")
        for d in neg[:3]:
            key_drivers.append(f"{d.get('label', '?')} = {d.get('value', '?')} (concern)")

        # Decision reason
        dec = decision.get("decision", "UNKNOWN")
        score = fusion.get("final_score", 0)
        band = fusion.get("final_band", "?")
        pd_val = fusion.get("final_pd", 0)
        reason = f"{dec} — Score {score} ({band}), PD {pd_val*100:.1f}%"
        amt = loan.get("approved_amount_lakhs")
        if amt:
            reason += f", Sanction ₹{amt}L @ {final_rate}%"

        ist = timezone(timedelta(hours=5, minutes=30))

        return {
            "score_journey": score_journey,
            "hard_rules_summary": hr_summary,
            "pricing_explanation": pricing_expl,
            "esg_impact": esg_impact,
            "statutory_check": statutory,
            "key_drivers": key_drivers,
            "decision_reason": reason,
            "llm_override_flag": llm.get("override_flag", "MAINTAIN"),
            "llm_biggest_risk": llm.get("biggest_risk", ""),
            "llm_biggest_strength": llm.get("biggest_strength", ""),
            "timestamp": datetime.now(ist).isoformat(),
        }
    except Exception as e:
        return {"error": f"Audit trail generation failed: {e}", "timestamp": datetime.now().isoformat()}

