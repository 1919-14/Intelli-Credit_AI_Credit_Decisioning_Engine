"""
Mock XGBoost Credit Scoring Model
Deterministic weighted-linear model that replicates the interface
of a real XGBoost regressor.  Swap with a real model file later.

Output: Probability of Default (PD) ∈ [0.0, 1.0]
"""
import math
from typing import Dict, List

# ─── Feature weights (calibrated to spec SHAP importance order) ──────
# Negative weight = feature REDUCES PD (credit positive)
# Positive weight = feature INCREASES PD (credit negative)
FEATURE_WEIGHTS = {
    # CHARACTER (reduce PD if good)
    "promoter_litigation_count":  +0.030,    # more litigation → higher PD
    "mca_charge_count":           +0.020,
    "adverse_news_sentiment":     +0.045,    # higher sentiment risk → higher PD
    "promoter_din_score":         -0.060,    # 1.0 = clean → lower PD

    # CAPACITY
    "dscr_proxy":                 -0.120,    # higher DSCR → much lower PD
    "bank_od_utilisation_pct":    +0.002,    # higher OD% → higher PD (per %)
    "cc_utilisation_volatility":  +0.003,
    "gst_turnover_cagr":         -0.002,    # growth → lower PD (per %)

    # CAPITAL
    "current_ratio":             -0.040,
    "debt_to_equity":            +0.035,    # higher leverage → higher PD
    "return_on_net_worth":       -0.050,
    "ebitda_margin":             -0.080,

    # COLLATERAL
    "collateral_coverage_ratio": -0.025,

    # CONDITIONS
    "gst_2a_vs_3b_gap_pct":     +0.004,    # per % gap → higher PD
    "revenue_gst_alignment":    -0.055,     # better alignment → lower PD
    "itc_mismatch_flag":        +0.060,
    "circular_trading_ratio":   +0.070,
    "cheque_bounce_frequency":  +0.150,     # strong negative signal
    "related_party_txn_pct":    +0.030,
    "working_capital_cycle_days":+0.001,    # longer cycle → higher PD

    # EXTRA (NLP / qualitative)
    "factory_operational_flag": -0.035,
    "capacity_utilisation_pct": -0.001,     # per %
    "succession_risk_flag":     +0.040,
    "sector_risk_score":        +0.050,
    "management_stability_score":-0.045,
}

# ─── Feature means (training-set calibration baseline) ───────────────
FEATURE_MEANS = {
    "promoter_litigation_count": 1.2,
    "mca_charge_count": 1.5,
    "adverse_news_sentiment": 0.35,
    "promoter_din_score": 0.85,
    "dscr_proxy": 1.40,
    "bank_od_utilisation_pct": 55.0,
    "cc_utilisation_volatility": 12.0,
    "gst_turnover_cagr": 8.0,
    "current_ratio": 1.30,
    "debt_to_equity": 1.20,
    "return_on_net_worth": 0.12,
    "ebitda_margin": 0.14,
    "collateral_coverage_ratio": 1.10,
    "gst_2a_vs_3b_gap_pct": 6.0,
    "revenue_gst_alignment": 0.78,
    "itc_mismatch_flag": 0.15,
    "circular_trading_ratio": 0.05,
    "cheque_bounce_frequency": 0.04,
    "related_party_txn_pct": 8.0,
    "working_capital_cycle_days": 65.0,
    "factory_operational_flag": 0.90,
    "capacity_utilisation_pct": 68.0,
    "succession_risk_flag": 0.20,
    "sector_risk_score": 0.35,
    "management_stability_score": 0.72,
}

# Base PD (average MSME default rate in training set)
BASE_PD = 0.45

# Model metadata
MODEL_VERSION = "mock_xgb_credit_v4.3"
MODEL_HASH = "a3f7c2e1b9d4a8f0c5e2b1d9f7a3c8e4"
IS_MOCK = True


def _sigmoid(x: float) -> float:
    """Clamp sigmoid to avoid overflow."""
    x = max(-10, min(10, x))
    return 1.0 / (1.0 + math.exp(-x))


def predict(features: Dict[str, float]) -> float:
    """
    Predict Probability of Default (PD).
    Mimics XGBoost regressor output ∈ [0.0, 1.0].
    """
    # Compute linear combination of deviations from mean
    logit_adjustment = 0.0
    for feat, weight in FEATURE_WEIGHTS.items():
        val = features.get(feat, FEATURE_MEANS.get(feat, 0))
        mean = FEATURE_MEANS.get(feat, 0)
        deviation = val - mean
        logit_adjustment += weight * deviation

    # Convert base PD to logit, apply adjustment, convert back
    base_logit = math.log(BASE_PD / (1 - BASE_PD))   # ≈ -0.2007
    adjusted_logit = base_logit + logit_adjustment
    pd_score = _sigmoid(adjusted_logit)

    # Clamp to [0.01, 0.99]
    pd_score = max(0.01, min(0.99, pd_score))
    return pd_score


def get_feature_weights() -> Dict[str, float]:
    """Return weights for SHAP surrogate calculation."""
    return dict(FEATURE_WEIGHTS)


def get_feature_means() -> Dict[str, float]:
    """Return training-set means for SHAP baseline."""
    return dict(FEATURE_MEANS)


def get_model_metadata() -> Dict:
    return {
        "model_version": MODEL_VERSION,
        "model_hash": MODEL_HASH,
        "is_mock": IS_MOCK,
        "n_trees": 300,
        "max_depth": 5,
        "learning_rate": 0.05,
        "base_pd": BASE_PD,
        "training_size": 48320,
        "validation_auc": 0.847,
        "validation_ks": 0.412,
        "gini": 0.694,
    }
