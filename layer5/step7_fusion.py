"""
Step 7 — Final Score Fusion
Combines XGBoost score + LLM adjustment + penalties → Final Adjusted Credit Score.
"""
from typing import Dict, Any


UNCERTAINTY_PENALTY = {"LOW": 0, "MODERATE": 5, "HIGH": 15}
AMBER_PENALTY_PER_ALERT = -3
MAX_AMBER_PENALTY = -15
HC_PENALTY_PER_CONDITION = -5


def fuse_scores(
    xgb_result: Dict[str, Any],
    llm_result: Dict[str, Any],
    confidence_result: Dict[str, Any],
    hard_rules_result: Dict[str, Any],
    forensics_report: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge all score components into a Final Adjusted Credit Score."""
    raw_score = xgb_result.get("credit_score", 700)
    llm_adj = llm_result.get("score_adjustment", 0)
    uncertainty = confidence_result.get("uncertainty_level", "MODERATE")
    unc_pen = UNCERTAINTY_PENALTY.get(uncertainty, 5)

    # AMBER alert penalty
    alerts = forensics_report.get("alerts", [])
    amber_count = sum(1 for a in alerts if a.get("severity") == "AMBER")
    amber_pen = max(MAX_AMBER_PENALTY, amber_count * AMBER_PENALTY_PER_ALERT)

    # HC condition penalty
    conditions = hard_rules_result.get("conditions", [])
    hc_pen = len(conditions) * HC_PENALTY_PER_CONDITION

    final_score = raw_score + llm_adj - unc_pen + amber_pen + hc_pen
    final_score = max(300, min(900, final_score))
    final_pd = round((900 - final_score) / 600, 4)
    final_band = _band(final_score)

    breakdown = {
        "xgboost_raw": raw_score,
        "llm_adjustment": llm_adj,
        "uncertainty_penalty": -unc_pen,
        "amber_alert_penalty": amber_pen,
        "hc_condition_penalty": hc_pen,
        "final_score": final_score,
    }

    print(f"  Step 7 Fusion: {raw_score} + ({llm_adj:+d}) − {unc_pen} + ({amber_pen}) + ({hc_pen}) = {final_score} ({final_band})")

    fusion_narrative = (
        f"XGBoost raw score {raw_score}"
        f" → LLM qualitative adjustment {llm_adj:+d}"
        f" → Uncertainty penalty -{unc_pen}"
        f" → AMBER alert penalty {amber_pen}"
        f" → Hard-condition penalty {hc_pen}"
        f" → Final Adjusted Score {final_score} ({final_band})"
    )

    return {
        "final_score": final_score,
        "final_band": final_band,
        "final_pd": final_pd,
        "score_breakdown": breakdown,
        "fusion_narrative": fusion_narrative,
        "amber_count": amber_count,
        "hc_count": len(conditions),
    }


def _band(score: int) -> str:
    if score >= 750: return "Very Low Risk"
    if score >= 650: return "Low Risk"
    if score >= 550: return "Moderate Risk"
    if score >= 450: return "High Risk"
    return "Very High Risk"
