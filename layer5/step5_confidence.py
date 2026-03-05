"""
Step 5 — Confidence Interval Estimation
200 bootstrap iterations with Gaussian noise perturbation.
Reports 10th/90th percentile PD → credit score confidence range.
"""
import random
from typing import Dict, Any


N_BOOTSTRAP = 200
NOISE_STD = 0.03   # standard deviation of Gaussian noise per feature

UNCERTAINTY_LEVELS = [
    (0.05, "LOW",      0),      # < 5% CI width → 0 bps buffer
    (0.15, "MODERATE", 25),     # 5–15% → 25 bps
    (1.00, "HIGH",     50),     # > 15% → 50 bps
]


def estimate_confidence(features: Dict[str, float], pd_point: float) -> Dict[str, Any]:
    """
    Run 200 perturbed predictions to estimate PD confidence interval.
    """
    from layer5.models.xgb_credit_mock import predict

    random.seed(42)   # reproducible for audit trail
    pd_samples = []

    for _ in range(N_BOOTSTRAP):
        perturbed = {}
        for feat, val in features.items():
            if isinstance(val, (int, float)):
                noise = random.gauss(0, NOISE_STD * max(abs(val), 0.01))
                perturbed[feat] = val + noise
            else:
                perturbed[feat] = val
        pd_samples.append(predict(perturbed))

    pd_samples.sort()
    idx_10 = max(0, int(N_BOOTSTRAP * 0.10) - 1)
    idx_90 = min(N_BOOTSTRAP - 1, int(N_BOOTSTRAP * 0.90))

    pd_lower = round(pd_samples[idx_10], 4)
    pd_upper = round(pd_samples[idx_90], 4)
    ci_width = round(pd_upper - pd_lower, 4)

    score_lower = max(300, int(round(900 - (pd_upper * 600))))   # pessimistic PD → lower score
    score_upper = min(900, int(round(900 - (pd_lower * 600))))   # optimistic PD → higher score

    # Classify uncertainty
    uncertainty_level = "HIGH"
    pricing_buffer_bps = 50
    for threshold, level, bps in UNCERTAINTY_LEVELS:
        if ci_width < threshold:
            uncertainty_level = level
            pricing_buffer_bps = bps
            break

    print(f"  Step 5 Confidence: CI width={ci_width:.4f} ({uncertainty_level}) | "
          f"Score range: {score_lower}–{score_upper} | Buffer: +{pricing_buffer_bps}bps")

    return {
        "pd_point_estimate": pd_point,
        "pd_lower_10pct": pd_lower,
        "pd_upper_90pct": pd_upper,
        "ci_width": ci_width,
        "score_lower": score_lower,
        "score_upper": score_upper,
        "uncertainty_level": uncertainty_level,
        "pricing_buffer_bps": pricing_buffer_bps,
        "n_bootstrap_samples": N_BOOTSTRAP,
    }
