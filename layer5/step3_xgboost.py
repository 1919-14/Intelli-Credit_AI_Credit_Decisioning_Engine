"""
Step 3 — XGBoost Credit Score Computation
Calls the model, transforms PD → 300–900 credit score, assigns band.
"""
from typing import Dict, Any
from datetime import datetime, timezone


SCORE_BANDS = [
    (750, 900, "Very Low Risk"),
    (650, 749, "Low Risk"),
    (550, 649, "Moderate Risk"),
    (450, 549, "High Risk"),
    (300, 449, "Very High Risk"),
]


def _assign_band(score: int) -> str:
    for lo, hi, label in SCORE_BANDS:
        if lo <= score <= hi:
            return label
    return "Very High Risk"


def compute_credit_score(features: Dict[str, float]) -> Dict[str, Any]:
    """
    Run mock XGBoost → PD → credit score → band.
    """
    from layer5.models.xgb_credit_mock import predict, get_model_metadata

    pd_score = predict(features)
    credit_score = int(round(900 - (pd_score * 600)))
    credit_score = max(300, min(900, credit_score))
    band = _assign_band(credit_score)
    meta = get_model_metadata()

    print(f"  Step 3 XGBoost: PD={pd_score:.4f} → Score={credit_score} ({band})")

    return {
        "pd_score": round(pd_score, 4),
        "credit_score": credit_score,
        "score_band": band,
        "model_version": meta["model_version"],
        "model_hash": meta["model_hash"],
        "is_mock_model": meta["is_mock"],
        "inference_timestamp": datetime.now(timezone.utc).isoformat(),
        "model_metadata": meta,
    }
