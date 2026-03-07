"""
Layer 5 — Credit Scoring & Decision Engine
Main Orchestrator with Parallel Execution DAG.

Sequential: Step1 → Step2 → [P1: Step3+4 | Step5 | Step6] → Step7 → [P2: Step8 | Step9 | Step10] → Step11 → Step12
"""
import json
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed


def run_layer5(
    layer4_output: Dict[str, Any],
    layer2_data: Dict[str, Any] = None,
    company_name: str = "",
    case_id: str = "",
    requested_amount_lakhs: float = 75.0,
    progress_callback=None,
    hitl_callback=None,
) -> Dict[str, Any]:
    """
    Main Layer 5 entry point.
    Accepts Layer 4 output → returns full scoring + decision package.
    """
    print("\n" + "=" * 60)
    print("📊 LAYER 5: Credit Scoring & Decision Engine")
    print("=" * 60)

    l4 = layer4_output or {}
    l2 = layer2_data or l4.get("layer2_data", {})
    forensics = l4.get("forensics_report", {})

    # ─── STEP 1: Feature Validation Gate ─────────────────────────
    if progress_callback:
        progress_callback("Step 1: Validating feature vector...", 5)
    print("\n🔍 Step 1: Feature Validation Gate")

    from layer5.step1_validation import validate_features
    validation = validate_features(l4)

    if validation["gate_status"] == "FAIL":
        print(f"  ❌ VALIDATION FAILED: {validation['validation_errors']}")
        return {
            "decision_summary": {
                "decision": "FAIL",
                "reason": "Feature validation gate failed",
                "errors": validation["validation_errors"],
            },
            "validation": validation,
        }

    features = validation["validated_features"]

    # ─── STEP 2: Hard Rule Pre-Filter ────────────────────────────
    if progress_callback:
        progress_callback("Step 2: Evaluating hard rules...", 10)
    print("\n⚖️ Step 2: Hard Rule Pre-Filter")

    from layer5.step2_hard_rules import evaluate_hard_rules
    hard_rules = evaluate_hard_rules(features, forensics)

    if hard_rules["gate"] == "HARD_REJECT":
        print(f"  ❌ HARD REJECT: {hard_rules['rejection_reason']}")
        
        if hitl_callback:
            if progress_callback:
                progress_callback("Step 2: HITL Review (Hard Reject)...", 15)
            # Emit HITL reject
            hitl_result = hitl_callback(hard_rules)
            hitl_decision = hitl_result.get("action")
            
            if hitl_decision == "override":
                print(f"  ⚠️ HARD REJECT OVERRIDDEN by user: {hitl_result.get('reason')}")
                hard_rules["gate"] = "HARD_REJECT_OVERRIDDEN"
                hard_rules["rule_log"].append({
                    "rule_id": "HITL-OVERRIDE",
                    "condition": "Officer Override",
                    "result": "PASS",
                    "reason": hitl_result.get('reason')
                })
        
        if hard_rules["gate"] == "HARD_REJECT":
            # Still reject. Call LLM for a proper reason.
            llm_reason = hard_rules["rejection_reason"]
            try:
                from groq import Groq
                import os
                client = Groq(api_key=os.getenv("API_KEY", ""))
                resp = client.chat.completions.create(
                    messages=[{"role": "user", "content": f"You are a credit analyst. Explain this rejection reason clearly and professionally in 2-3 sentences to the customer/officer: {hard_rules['rejection_reason']}."}],
                    model="meta-llama/llama-4-scout-17b-16e-instruct",
                    temperature=0.3, max_tokens=200
                )
                llm_reason = resp.choices[0].message.content.strip()
            except Exception as e:
                print(f"  ⚠ LLM rejection explanation failed: {e}")

            # Build zero-score output for rejection letter and UI
            rejection_output = {
                "decision_summary": {
                    "decision": "REJECT",
                    "reason": llm_reason,
                    "final_credit_score": 0,
                    "risk_band": "VERY HIGH RISK",
                    "probability_of_default": 1.0,
                    "interest_rate": 0,
                    "sanction_amount_lakhs": 0,
                    "conditions": [],
                    "covenants": [],
                },
                "score_breakdown": {
                    "xgboost_raw": 0,
                    "llm_adjustment": 0,
                    "uncertainty_penalty": 0,
                    "amber_alert_penalty": 0,
                    "hc_condition_penalty": 0,
                    "final_score": 0
                },
                "explanation": {
                    "llm_opinion": llm_reason,
                    "biggest_risk": "Critical Regulatory/Policy Failure",
                    "five_cs": {
                        "character": {"rating": "NEGATIVE", "explanation": "Hard rule policy violation."},
                        "capacity": {"rating": "NEGATIVE", "explanation": "Auto-rejected."},
                        "capital": {"rating": "NEGATIVE", "explanation": "Auto-rejected."},
                        "collateral": {"rating": "NEGATIVE", "explanation": "Auto-rejected."},
                        "conditions": {"rating": "NEGATIVE", "explanation": "Auto-rejected."}
                    }
                },
                "confidence": {
                    "score_lower": 0,
                    "score_upper": 0,
                    "uncertainty_level": "N/A",
                },
                "hard_rules": {
                    "gate": "HARD_REJECT",
                    "rule_log": hard_rules["rule_log"],
                    "rejection_reason": hard_rules["rejection_reason"],
                },
                "validation": validation,
            }
            return rejection_output


    # ─── PARALLEL GROUP P1: XGBoost + SHAP | Confidence | LLM ───
    if progress_callback:
        progress_callback("Steps 3-6: ML scoring + LLM analysis (parallel)...", 20)
    print("\n⚡ Steps 3-6: Parallel Group P1")

    from layer5.step3_xgboost import compute_credit_score
    from layer5.step4_shap import compute_shap_decomposition
    from layer5.step5_confidence import estimate_confidence
    from layer5.step6_llm_overlay import run_llm_overlay

    xgb_result = {}
    shap_result = {}
    confidence_result = {}
    llm_result = {}

    def _run_xgb_shap():
        """Steps 3+4: XGBoost → SHAP (sequential dependency)."""
        xgb = compute_credit_score(features)
        shap = compute_shap_decomposition(features, xgb["pd_score"])
        return xgb, shap

    def _run_confidence():
        """Step 5: Bootstrap confidence interval."""
        # Need PD from xgb — use quick predict
        from layer5.models.xgb_credit_mock import predict
        pd = predict(features)
        return estimate_confidence(features, pd)

    def _run_llm():
        """Step 6: LLM qualitative overlay."""
        # Needs xgb result — use quick predict
        from layer5.models.xgb_credit_mock import predict
        pd = predict(features)
        mock_xgb = {
            "pd_score": pd,
            "credit_score": int(round(900 - (pd * 600))),
            "score_band": _band(int(round(900 - (pd * 600)))),
        }
        # SHAP for prompt
        mock_shap = compute_shap_decomposition(features, pd)
        return run_llm_overlay(features, mock_xgb, mock_shap, forensics, l4, company_name)

    with ThreadPoolExecutor(max_workers=3) as pool:
        f_xgb_shap = pool.submit(_run_xgb_shap)
        f_confidence = pool.submit(_run_confidence)
        f_llm = pool.submit(_run_llm)

        try:
            xgb_result, shap_result = f_xgb_shap.result(timeout=30)
        except Exception as e:
            print(f"  ⚠ XGBoost/SHAP failed: {e}")
            xgb_result = {"pd_score": 0.5, "credit_score": 600, "score_band": "Moderate Risk"}
            shap_result = {"shap_values": {}, "top_positive_drivers": [], "top_negative_drivers": [], "waterfall_narrative": ""}

        try:
            confidence_result = f_confidence.result(timeout=30)
        except Exception as e:
            print(f"  ⚠ Confidence estimation failed: {e}")
            confidence_result = {"uncertainty_level": "MODERATE", "pricing_buffer_bps": 25, "score_lower": 600, "score_upper": 700}

        try:
            llm_result = f_llm.result(timeout=60)
        except Exception as e:
            print(f"  ⚠ LLM overlay failed: {e}")
            llm_result = {"score_adjustment": 0, "five_cs": {}, "qualitative_opinion": "", "override_flag": "MAINTAIN"}

    # ─── STEP 7: Score Fusion ────────────────────────────────────
    if progress_callback:
        progress_callback("Step 7: Fusing scores...", 70)
    print("\n🔢 Step 7: Score Fusion")

    from layer5.step7_fusion import fuse_scores
    fusion = fuse_scores(xgb_result, llm_result, confidence_result, hard_rules, forensics)

    # ─── PARALLEL GROUP P2: Pricing | Decision | Loan Structure ──
    if progress_callback:
        progress_callback("Steps 8-10: Pricing + Decision + Loan (parallel)...", 80)
    print("\n⚡ Steps 8-10: Parallel Group P2")

    from layer5.step8_pricing import compute_pricing
    from layer5.step9_decision import make_decision
    from layer5.step10_loan_structure import compute_loan_structure

    pricing_result = {}
    decision_result = {}
    loan_result = {}

    with ThreadPoolExecutor(max_workers=3) as pool:
        f_pricing = pool.submit(
            compute_pricing,
            fusion["final_score"],
            confidence_result.get("uncertainty_level", "MODERATE"),
            confidence_result.get("pricing_buffer_bps", 25),
            hard_rules.get("conditions", []),
        )

        f_decision = pool.submit(
            make_decision,
            fusion["final_score"],
            fusion["final_pd"],
            features,
            hard_rules,
            forensics,
            llm_result,
        )

        # Pricing needed for loan structure — get it first
        try:
            pricing_result = f_pricing.result(timeout=10)
        except Exception as e:
            print(f"  ⚠ Pricing failed: {e}")
            pricing_result = {"final_interest_rate": 13.50}

        try:
            decision_result = f_decision.result(timeout=10)
        except Exception as e:
            print(f"  ⚠ Decision failed: {e}")
            decision_result = {"decision": "CONDITIONAL", "conditions": [], "covenants": []}

    # ─── PARALLEL GROUP P2.5: LLM Decision Summary Narrative ────
    # Generate a bulleted explanation of the decision
    if progress_callback:
        progress_callback("Generating decision narrative summary...", 85)
    
    decision_val = decision_result.get("decision", "CONDITIONAL")
    score_val = fusion["final_score"]
    
    try:
        from groq import Groq
        import os
        client = Groq(api_key=os.getenv("API_KEY", ""))
        
        prompt = f"""You are a senior credit risk officer at Intelli-Credit.
Write a clear, professional decision summary for the following credit application.
CRITICAL INSTRUCTIONS:
- You must ONLY write a bulleted list.
- Start every bullet with a hyphen and a space ("- ").
- Separate every bullet with a newline (\\n).
- DO NOT write any introductory text (e.g. "Decision Summary:").
- DO NOT write any concluding remarks.

Application Context:
- Final Decision: {decision_val}
- Final Credit Score: {score_val} / 900
- Conditions applied: {'; '.join(decision_result.get('conditions', ['None']))}
- Biggest Risk Factor: {llm_result.get('biggest_risk', 'Unknown')}
- Rejection reason (if any): {decision_result.get('reason', 'N/A')}

Required Content:
"""
        if decision_val == "REJECT":
            prompt += "- Provide 2-3 bullet points clearly explaining the exact reasons for rejection.\n- Provide 1-2 bullet points with actionable advice on how the applicant can improve their profile to get approved in the future."
        else:
            prompt += "- Provide 2-3 bullet points explaining why the application was approved, highlighting the core strengths.\n- Provide 1-2 bullet points documenting the primary risk factors (including the biggest risk factor mentioned above) and what conditions or covenants were applied.\n- Provide 1 bullet point with advice on how to improve the credit profile further."
            
        resp = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            temperature=0.3, 
            max_tokens=300
        )
        decision_result["llm_decision_summary"] = resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"  ⚠ Decision Summary LLM failed: {e}")
        decision_result["llm_decision_summary"] = f"- Decision: {decision_val}\n- Automated summary generation failed."


    # Loan structure (needs pricing result)
    try:
        loan_result = compute_loan_structure(
            features,
            pricing_result.get("final_interest_rate", 13.50),
            hard_rules.get("conditions", []),
            l2,
            requested_amount_lakhs,
        )
    except Exception as e:
        print(f"  ⚠ Loan structure failed: {e}")
        loan_result = {"approved_amount_lakhs": 0, "loan_structure": {}, "mpbf": {}}

    # ─── STEP 11: Audit Snapshot ─────────────────────────────────
    if progress_callback:
        progress_callback("Step 11: Building audit snapshot...", 92)
    print("\n📋 Step 11: Audit Snapshot")

    from layer5.step11_snapshot import build_snapshot
    snapshot = build_snapshot(
        features, xgb_result, shap_result, confidence_result,
        fusion, llm_result, decision_result, pricing_result,
        loan_result, validation, hard_rules, case_id,
    )

    # ─── STEP 12: Final Output Package ───────────────────────────
    if progress_callback:
        progress_callback("Step 12: Assembling output...", 96)
    print("\n📦 Step 12: Output Package")

    from layer5.step12_output import build_output_package
    output = build_output_package(
        validation, hard_rules, xgb_result, shap_result,
        confidence_result, llm_result, fusion, pricing_result,
        decision_result, loan_result, snapshot,
    )

    print(f"\n{'='*60}")
    print(f"✅ LAYER 5 COMPLETE")
    print(f"   Decision: {output['decision_summary']['decision']}")
    print(f"   Score: {output['decision_summary']['final_credit_score']} ({output['decision_summary']['risk_band']})")
    print(f"   Rate: {output['decision_summary']['interest_rate']}%")
    print(f"   Sanction: Rs.{output['decision_summary']['sanction_amount_lakhs']}L")
    print(f"{'='*60}")

    if progress_callback:
        progress_callback("Layer 5 complete", 100)

    return output


def _band(score: int) -> str:
    if score >= 750: return "Very Low Risk"
    if score >= 650: return "Low Risk"
    if score >= 550: return "Moderate Risk"
    if score >= 450: return "High Risk"
    return "Very High Risk"
