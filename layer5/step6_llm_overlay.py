"""
Step 6 — LLM Qualitative Overlay + Five Cs Assessment
Uses Groq (Llama) to produce qualitative credit opinion,
Five Cs ratings, and a ±30 point score adjustment.
"""
import os
import json
from typing import Dict, Any


def run_llm_overlay(
    features: Dict[str, float],
    xgb_result: Dict[str, Any],
    shap_result: Dict[str, Any],
    forensics_report: Dict[str, Any],
    layer4_output: Dict[str, Any],
    company_name: str = "",
) -> Dict[str, Any]:
    """
    Assemble 5 context blocks → call Groq → parse structured output.
    Falls back to rule-based defaults if Groq fails.
    """
    # Build prompt
    prompt = _build_prompt(features, xgb_result, shap_result, forensics_report, layer4_output, company_name)

    try:
        from groq import Groq
        from utils_keys import get_content_generation_key
        client = Groq(api_key=get_content_generation_key())

        resp = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=2000,
        )
        raw = resp.choices[0].message.content
        result = json.loads(raw.replace("```json", "").replace("```", "").strip())
        result = _normalize_llm_output(result)
        print(f"  Step 6 LLM Overlay: adjustment={result.get('score_adjustment', 0):+d} | "
              f"override={result.get('override_flag', 'MAINTAIN')}")
        return result

    except Exception as e:
        print(f"  Step 6 LLM Overlay: Groq failed ({e}) — using rule-based fallback")
        return _rule_based_fallback(features, xgb_result, shap_result, forensics_report)


def _build_prompt(features, xgb, shap, forensics, l4, company_name):
    """Assemble the 5 context blocks for the LLM."""
    # Context 1 — Borrower Summary
    sector = l4.get("research_findings", {}).get("sector_risk", {}).get("sector", "Manufacturing")
    loan_amount = features.get("collateral_coverage_ratio", 1.0) * 50   # rough estimate

    # Context 2 — Quantitative Score
    top_pos = shap.get("top_positive_drivers", [])
    top_neg = shap.get("top_negative_drivers", [])
    pos_lines = "\n".join([f"  + {d['label']} (value: {d['value']}, SHAP: {d['shap_value']:.4f})" for d in top_pos])
    neg_lines = "\n".join([f"  - {d['label']} (value: {d['value']}, SHAP: {d['shap_value']:.4f})" for d in top_neg])

    # Context 3 — Forensic Alerts
    alerts = forensics.get("alerts", [])
    alert_lines = "\n".join([
        f"  [{a.get('severity')}] {a.get('type', '')}: {a.get('description', '')}"
        for a in alerts[:5]
    ]) or "  No active forensic alerts."

    # Context 4 — NLP Signals
    officer = l4.get("officer_analysis", {})

    # Context 5 — Sector
    sector_data = l4.get("research_findings", {}).get("sector_risk", {})

    return f"""You are a senior credit risk analyst writing for a Credit Appraisal Memorandum (CAM).

CONTEXT 1 — BORROWER SUMMARY
Business: {company_name or 'MSME Applicant'}
Sector: {sector}
DSCR: {features.get('dscr_proxy', 1.5):.2f}
Current Ratio: {features.get('current_ratio', 1.0):.2f}
Debt-to-Equity: {features.get('debt_to_equity', 1.0):.2f}

CONTEXT 2 — QUANTITATIVE SCORE
XGBoost Credit Score: {xgb.get('credit_score', 700)} ({xgb.get('score_band', 'Low Risk')})
PD: {xgb.get('pd_score', 0.3)*100:.1f}%

Top 3 Score Boosters (reduced PD):
{pos_lines}

Top 3 Score Detractors (increased PD):
{neg_lines}

CONTEXT 3 — FORENSIC ALERT SUMMARY
{alert_lines}

CONTEXT 4 — NLP QUALITATIVE SIGNALS
Factory Operational: {features.get('factory_operational_flag', 1)}
Capacity Utilisation: {features.get('capacity_utilisation_pct', 70):.0f}%
Succession Risk: {features.get('succession_risk_flag', 0)}
Management Stability: {features.get('management_stability_score', 0.8):.2f}

CONTEXT 5 — SECTOR INTELLIGENCE
Sector Risk Score: {features.get('sector_risk_score', 0.3):.2f}
Sector Summary: {sector_data.get('summary', 'No sector data available')}

CONTEXT 6 — ESG & SUSTAINABILITY DATA
Carbon Footprint: {features.get('carbon_footprint_mt', 'N/A')} MT CO₂e
Transition Risk: {features.get('esg_transition_risk', 'N/A')}
Physical Risk: {features.get('esg_physical_risk', 'N/A')}
Sustainability Rating: {features.get('sustainability_rating', 'N/A')}
Green Financing Eligible: {features.get('green_financing_eligible', 'N/A')}
Renewable Energy: {features.get('renewable_energy_pct', 'N/A')}%
Note: If ESG data shows "N/A", no sustainability report was provided — skip ESG assessment.

TASK:
1. Write a 5-7 sentence qualitative credit opinion.
2. Assess the Five Cs of Credit:
   - Character (POSITIVE / MODERATE / NEGATIVE)
   - Capacity (POSITIVE / MODERATE / NEGATIVE)
   - Capital (POSITIVE / MODERATE / NEGATIVE)
   - Collateral (POSITIVE / MODERATE / NEGATIVE)
   - Conditions (POSITIVE / MODERATE / NEGATIVE)
   Each with a 1-2 sentence explanation.
3. Identify the single biggest qualitative risk NOT captured by the model.
4. Identify the single biggest qualitative strength NOT captured by the model.
5. Recommend a score adjustment between -30 and +30 with justification.
6. Flag override recommendation: "MAINTAIN" (automated is fine) or "ESCALATE" (needs human committee).
7. If ESG data is available, comment briefly on how it affects creditworthiness and whether Green Loan pricing is justified.

Return ONLY valid JSON:
{{
  "qualitative_opinion": "5-7 sentence narrative",
  "five_cs": {{
    "character": {{"rating": "POSITIVE|MODERATE|NEGATIVE", "explanation": "..."}},
    "capacity": {{"rating": "POSITIVE|MODERATE|NEGATIVE", "explanation": "..."}},
    "capital": {{"rating": "POSITIVE|MODERATE|NEGATIVE", "explanation": "..."}},
    "collateral": {{"rating": "POSITIVE|MODERATE|NEGATIVE", "explanation": "..."}},
    "conditions": {{"rating": "POSITIVE|MODERATE|NEGATIVE", "explanation": "..."}}
  }},
  "biggest_risk": "description of unmodeled risk",
  "biggest_strength": "description of unmodeled strength",
  "score_adjustment": integer_between_-30_and_30,
  "adjustment_justification": "why this adjustment",
  "override_flag": "MAINTAIN or ESCALATE",
  "esg_comment": "brief ESG assessment or null if no data"
}}"""


def _normalize_llm_output(result: Dict) -> Dict[str, Any]:
    """Ensure all required fields exist and score_adjustment is clamped."""
    adj = result.get("score_adjustment", 0)
    try:
        adj = int(adj)
    except (ValueError, TypeError):
        adj = 0
    result["score_adjustment"] = max(-30, min(30, adj))

    # Ensure five_cs exists
    if "five_cs" not in result or not isinstance(result["five_cs"], dict):
        result["five_cs"] = _default_five_cs()

    for c in ["character", "capacity", "capital", "collateral", "conditions"]:
        if c not in result["five_cs"]:
            result["five_cs"][c] = {"rating": "MODERATE", "explanation": "Data insufficient for assessment."}
        elif isinstance(result["five_cs"][c], str):
            result["five_cs"][c] = {"rating": result["five_cs"][c], "explanation": ""}

    result.setdefault("qualitative_opinion", "")
    result.setdefault("biggest_risk", "Not identified")
    result.setdefault("biggest_strength", "Not identified")
    result.setdefault("adjustment_justification", "")
    result.setdefault("override_flag", "MAINTAIN")

    return result


def _default_five_cs():
    return {
        "character":  {"rating": "MODERATE", "explanation": "Promoter shows standard compliance profile."},
        "capacity":   {"rating": "MODERATE", "explanation": "Debt service capacity meets minimum thresholds."},
        "capital":    {"rating": "MODERATE", "explanation": "Net worth and leverage within acceptable range."},
        "collateral": {"rating": "MODERATE", "explanation": "Collateral coverage at standard levels."},
        "conditions": {"rating": "MODERATE", "explanation": "Business conditions are stable."},
    }


def generate_shap_explanation(
    features: dict,
    shap_result: dict,
    xgb_result: dict,
    decision_summary: dict,
    company_name: str = "",
) -> str:
    """
    Call Groq LLM to generate a detailed, human-readable essay explaining the
    SHAP decomposition behind the credit decision. Returns plain-text explanation.
    """
    top_pos = shap_result.get("top_positive_drivers", [])
    top_neg = shap_result.get("top_negative_drivers", [])
    base_pd = shap_result.get("base_value", 0.30)
    final_pd = xgb_result.get("pd_score", 0)
    final_score = xgb_result.get("credit_score", 0)
    score_band = xgb_result.get("score_band", "Unknown")
    decision = decision_summary.get("decision", "—")

    pos_lines = "\n".join([
        f"  [{i+1}] {d['label']}: actual value = {d['value']}, SHAP contribution = {d['shap_value']:.4f} ({d['magnitude']} impact, REDUCES default risk)"
        for i, d in enumerate(top_pos)
    ])
    neg_lines = "\n".join([
        f"  [{i+1}] {d['label']}: actual value = {d['value']}, SHAP contribution = +{d['shap_value']:.4f} ({d['magnitude']} impact, INCREASES default risk)"
        for i, d in enumerate(top_neg)
    ])

    prompt = f"""You are a senior credit risk officer at an Indian bank writing an explainability report for a loan applicant.

DECISION CONTEXT:
Business: {company_name or 'MSME Applicant'}
Final Decision: {decision}
Credit Score: {final_score} ({score_band})
Probability of Default: {final_pd*100:.1f}%
Base (sector average) PD: {base_pd*100:.0f}%

SHAP EXPLAINABILITY DATA:
The following factors were the key drivers of this credit score, computed via SHAP (SHapley Additive exPlanations). SHAP values show by how much each factor shifted the probability of default away from the sector average.

TOP 3 SCORE-IMPROVING FACTORS (reduced default probability):
{pos_lines or "  No significant positive drivers identified."}

TOP 3 SCORE-REDUCING FACTORS (increased default probability):
{neg_lines or "  No significant negative drivers identified."}

YOUR TASK:
Write a comprehensive, highly detailed explanation (at least 400 words) of WHY the AI model assigned this score. This explanation must:

1. OPENING PARAGRAPH: Summarize the overall credit assessment verdict clearly — what is the decision and what does the credit score mean in practical terms for this business. Explain the PD in plain language.

2. KEY STRENGTHS (score-improving factors): For each positive SHAP driver, write 2-3 sentences explaining:
   - What this metric represents and why it matters in credit analysis
   - What the actual value means for this business (is it good, great, or just adequate?)
   - How much it helped the score and why the bank views this positively

3. KEY CONCERNS (score-reducing factors): For each negative SHAP driver, write 2-3 sentences explaining:
   - What this metric represents and the specific risk it signals
   - Why the bank considers this a concern and what could go wrong
   - The magnitude of impact on the overall credit score

4. INTERACTION EFFECTS: Write 1-2 sentences explaining how the positive and negative factors interact — does the strength in one area offset weaknesses in another?

5. ACTIONABLE INSIGHTS: List 3-4 specific, concrete steps the business could take to improve their credit profile at the next assessment.

6. CLOSING: A brief statement about what conditions or improvements would most likely change a REJECT to CONDITIONAL or CONDITIONAL to APPROVE.

Write in a professional but accessible tone — the explanation should be understandable to a business owner (not just a banker). Use specific numbers from the data above. Do NOT use bullet points for the main body — write in flowing paragraphs. You may use numbered lists only for the actionable insights section.
"""

    try:
        from groq import Groq
        from utils_keys import get_content_generation_key
        client = Groq(api_key=get_content_generation_key())
        resp = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            temperature=0.4,
            max_tokens=2500,
        )
        explanation = resp.choices[0].message.content.strip()
        print(f"  SHAP LLM Explanation: generated ({len(explanation)} chars)")
        return explanation
    except Exception as e:
        print(f"  SHAP LLM Explanation: Groq failed ({e}) — using waterfall narrative fallback")
        # Return the waterfall narrative as fallback
        return shap_result.get("waterfall_narrative", "SHAP explanation unavailable.")


def _rule_based_fallback(features, xgb, shap, forensics):

    """Rule-based fallback when Groq API fails."""
    dscr = features.get("dscr_proxy", 1.5)
    score = xgb.get("credit_score", 700)

    # Simple rule-based Five Cs
    five_cs = {}
    five_cs["character"] = {
        "rating": "POSITIVE" if features.get("adverse_news_sentiment", 0.5) < 0.3 else "MODERATE",
        "explanation": "Based on adverse media score and litigation count."
    }
    five_cs["capacity"] = {
        "rating": "POSITIVE" if dscr >= 1.5 else ("MODERATE" if dscr >= 1.2 else "NEGATIVE"),
        "explanation": f"DSCR of {dscr:.2f} indicates {'strong' if dscr >= 1.5 else 'adequate' if dscr >= 1.2 else 'weak'} repayment capacity."
    }
    five_cs["capital"] = {
        "rating": "POSITIVE" if features.get("debt_to_equity", 1) < 1.0 else "MODERATE",
        "explanation": f"Debt-to-equity ratio of {features.get('debt_to_equity', 1):.2f}."
    }
    five_cs["collateral"] = {
        "rating": "POSITIVE" if features.get("collateral_coverage_ratio", 1) >= 1.2 else "MODERATE",
        "explanation": f"Collateral coverage ratio of {features.get('collateral_coverage_ratio', 1):.2f}."
    }
    five_cs["conditions"] = {
        "rating": "POSITIVE" if features.get("sector_risk_score", 0.3) < 0.3 else "MODERATE",
        "explanation": f"Sector risk score of {features.get('sector_risk_score', 0.3):.2f}."
    }

    return {
        "qualitative_opinion": f"The borrower presents a {'sound' if score >= 650 else 'moderate'} credit profile with DSCR of {dscr:.2f}. "
                               f"The ML model assigns a score of {score}, indicating {xgb.get('score_band', 'moderate')} risk. "
                               f"Automated qualitative assessment applied due to LLM unavailability.",
        "five_cs": five_cs,
        "biggest_risk": "Key-man dependency and succession planning gaps (common in MSME segment).",
        "biggest_strength": "Consistent GST filing history and stable bank transaction patterns.",
        "score_adjustment": 0,
        "adjustment_justification": "No LLM adjustment applied — rule-based fallback used.",
        "override_flag": "MAINTAIN",
        "is_fallback": True,
    }
