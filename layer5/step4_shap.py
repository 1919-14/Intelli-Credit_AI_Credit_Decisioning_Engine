"""
Step 4 — SHAP TreeExplainer Decomposition
Decomposes the credit score into per-feature contributions.
Uses surrogate SHAP for the mock model; real shap.TreeExplainer when a real model is loaded.
"""
from typing import Dict, Any, List, Tuple


# Human-readable labels for narrative generation
FEATURE_LABELS = {
    "promoter_litigation_count": "Promoter litigation exposure",
    "mca_charge_count": "Registered charges on company",
    "adverse_news_sentiment": "Adverse media risk",
    "promoter_din_score": "Promoter/director compliance",
    "dscr_proxy": "Debt Service Coverage Ratio",
    "bank_od_utilisation_pct": "OD/CC utilisation level",
    "cc_utilisation_volatility": "Credit line utilisation volatility",
    "gst_turnover_cagr": "GST turnover growth (YoY)",
    "current_ratio": "Current ratio (liquidity)",
    "debt_to_equity": "Debt-to-equity leverage",
    "return_on_net_worth": "Return on net worth",
    "ebitda_margin": "EBITDA margin",
    "collateral_coverage_ratio": "Collateral coverage",
    "gst_2a_vs_3b_gap_pct": "GST-bank reconciliation gap",
    "revenue_gst_alignment": "Filing compliance / revenue alignment",
    "itc_mismatch_flag": "ITC mismatch / overclaiming",
    "circular_trading_ratio": "Circular trading ratio",
    "cheque_bounce_frequency": "Cheque bounce frequency",
    "related_party_txn_pct": "Related party transaction exposure",
    "working_capital_cycle_days": "Working capital cycle length",
    "factory_operational_flag": "Factory operational status",
    "capacity_utilisation_pct": "Capacity utilisation",
    "succession_risk_flag": "Succession / key-man risk",
    "sector_risk_score": "Sector risk level",
    "management_stability_score": "Management stability",
}


def compute_shap_decomposition(
    features: Dict[str, float],
    pd_score: float
) -> Dict[str, Any]:
    """
    Compute surrogate SHAP values = weight × (value − mean) per feature.
    The sum of all SHAP values + base_pd ≈ final PD.
    """
    from layer5.models.xgb_credit_mock import get_feature_weights, get_feature_means, BASE_PD

    weights = get_feature_weights()
    means = get_feature_means()

    shap_values: Dict[str, float] = {}
    for feat, w in weights.items():
        val = features.get(feat, means.get(feat, 0))
        mean = means.get(feat, 0)
        shap_val = w * (val - mean)
        shap_values[feat] = round(shap_val, 6)

    # Sort: positive SHAP = increased PD (bad), negative SHAP = decreased PD (good)
    sorted_positive = sorted(
        [(k, v) for k, v in shap_values.items() if v < 0],
        key=lambda x: x[1]
    )  # most negative first = strongest credit boosters

    sorted_negative = sorted(
        [(k, v) for k, v in shap_values.items() if v > 0],
        key=lambda x: x[1], reverse=True
    )  # most positive first = strongest credit detractors

    top_positive = sorted_positive[:3]   # score boosters
    top_negative = sorted_negative[:3]   # score detractors

    # Generate waterfall narrative
    total_positive_shap = sum(v for _, v in sorted_positive)
    total_negative_shap = sum(v for _, v in sorted_negative)
    narrative = _build_waterfall_narrative(
        BASE_PD, pd_score, top_positive, top_negative,
        total_positive_shap, total_negative_shap
    )

    # Build labelled explanations
    top_positive_labeled = [
        {
            "feature": f, "shap_value": v,
            "label": FEATURE_LABELS.get(f, f),
            "value": features.get(f, 0),
            "direction": "POSITIVE", "magnitude": _magnitude(v),
        }
        for f, v in top_positive
    ]
    top_negative_labeled = [
        {
            "feature": f, "shap_value": v,
            "label": FEATURE_LABELS.get(f, f),
            "value": features.get(f, 0),
            "direction": "NEGATIVE", "magnitude": _magnitude(v),
        }
        for f, v in top_negative
    ]

    print(f"  Step 4 SHAP: {len(shap_values)} features decomposed | "
          f"Boosters: {[f for f,_ in top_positive]} | Detractors: {[f for f,_ in top_negative]}")

    return {
        "shap_values": shap_values,
        "base_value": BASE_PD,
        "top_positive_drivers": top_positive_labeled,
        "top_negative_drivers": top_negative_labeled,
        "waterfall_narrative": narrative,
        "is_surrogate": True,
    }


def _magnitude(shap_val: float) -> str:
    """Classify SHAP magnitude."""
    v = abs(shap_val)
    if v >= 0.04:
        return "STRONG"
    elif v >= 0.015:
        return "MODERATE"
    else:
        return "MILD"


def _build_waterfall_narrative(
    base_pd: float, final_pd: float,
    top_pos: List[Tuple[str, float]],
    top_neg: List[Tuple[str, float]],
    total_pos: float, total_neg: float
) -> str:
    """Generate a 3–5 sentence SHAP waterfall narrative."""
    pos_pct = abs(total_pos * 100)
    neg_pct = abs(total_neg * 100)
    final_score = int(round(900 - (final_pd * 600)))

    sentences = []
    sentences.append(
        f"Starting from the average MSME default rate of {base_pd*100:.0f}%, "
        f"the model identifies both risk-reducing and risk-increasing factors."
    )

    if top_pos:
        labels = [FEATURE_LABELS.get(f, f) for f, _ in top_pos[:2]]
        sentences.append(
            f"The strongest credit-positive drivers — {labels[0]} and "
            f"{labels[1] if len(labels) > 1 else 'other factors'} — "
            f"push the default probability down by {pos_pct:.1f} percentage points."
        )

    if top_neg:
        labels = [FEATURE_LABELS.get(f, f) for f, _ in top_neg[:2]]
        sentences.append(
            f"Conversely, {labels[0]} and "
            f"{labels[1] if len(labels) > 1 else 'other factors'} "
            f"increase default risk by {neg_pct:.1f} percentage points."
        )

    sentences.append(
        f"The net result is a PD of {final_pd*100:.1f}%, translating to a "
        f"credit score of {final_score} ({_band_label(final_score)} band)."
    )

    return " ".join(sentences)


def _band_label(score: int) -> str:
    if score >= 750: return "Very Low Risk"
    if score >= 650: return "Low Risk"
    if score >= 550: return "Moderate Risk"
    if score >= 450: return "High Risk"
    return "Very High Risk"
