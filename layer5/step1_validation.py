"""
Step 1 — Feature Validation Gate
Validates completeness, range, temporal validity, and DSCR presence
before any model is invoked.
"""
from typing import Dict, Any, List, Tuple
from datetime import datetime, timezone, timedelta


# ─── Feature classification ──────────────────────────────────────────
FINANCIAL_FEATURES = [
    "dscr_proxy", "bank_od_utilisation_pct", "cc_utilisation_volatility",
    "gst_turnover_cagr", "current_ratio", "debt_to_equity",
    "return_on_net_worth", "ebitda_margin", "collateral_coverage_ratio",
    "gst_2a_vs_3b_gap_pct", "revenue_gst_alignment", "itc_mismatch_flag",
]

NLP_FEATURES = [
    "factory_operational_flag", "capacity_utilisation_pct",
    "succession_risk_flag", "management_stability_score",
]

SECTOR_DEFAULTS = {
    "factory_operational_flag": 1,
    "capacity_utilisation_pct": 70,
    "succession_risk_flag": 0,
    "management_stability_score": 0.8,
}

# ─── Range constraints ───────────────────────────────────────────────
RANGE_RULES = {
    "gst_2a_vs_3b_gap_pct":     (0.0, 100.0),
    "itc_mismatch_flag":        (0.0, 1.0),
    "revenue_gst_alignment":    (0.0, 1.0),
    "cheque_bounce_frequency":  (0.0, 1.0),
    "bank_od_utilisation_pct":  (0.0, 100.0),
    "adverse_news_sentiment":   (0.0, 1.0),
    "sector_risk_score":        (0.0, 1.0),
    "collateral_coverage_ratio":(0.0, 50000.0),
    "current_ratio":            (0.0, 50000.0),
    "debt_to_equity":           (0.0, 50000.0),
    "ebitda_margin":            (-1.0, 1.0),
    "return_on_net_worth":      (-5.0, 5.0),
}

MAX_STALENESS_HOURS = 72


def validate_features(layer4_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run all 4 validation checks on the feature vector.
    Returns:
      gate_status: PASS | FAIL | PASS_WITH_IMPUTATION
      imputation_log: list of {feature, default_used, reason}
      validated_features: dict of 25 floats (post-imputation)
      errors: list of error strings (empty on PASS)
    """
    features = dict(layer4_output.get("feature_vector", {}))
    audit = layer4_output.get("feature_audit_snapshot", {})
    errors: List[str] = []
    imputation_log: List[Dict] = []

    # ─── Check 1: Completeness ────────────────────────────────────
    for f in FINANCIAL_FEATURES:
        val = features.get(f)
        if val is None:
            errors.append(f"INCOMPLETE_DATA: Financial feature '{f}' is NULL")

    for f in NLP_FEATURES:
        val = features.get(f)
        if val is None:
            default = SECTOR_DEFAULTS.get(f, 0)
            features[f] = default
            imputation_log.append({
                "feature": f,
                "default_used": default,
                "reason": f"NLP feature NULL — imputed with sector average ({default})",
            })

    # ─── Check 2: Range Validation ────────────────────────────────
    for feat, (lo, hi) in RANGE_RULES.items():
        val = features.get(feat)
        if val is not None:
            try:
                fv = float(val)
                if fv < lo or fv > hi:
                    errors.append(f"RANGE_ERROR: '{feat}' = {fv} outside [{lo}, {hi}]")
                    features[feat] = max(lo, min(hi, fv))   # clamp
            except (ValueError, TypeError):
                errors.append(f"TYPE_ERROR: '{feat}' = {val} is not numeric")

    # ─── Check 3: Temporal Validity ───────────────────────────────
    ts_str = audit.get("timestamp", "")
    if ts_str:
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            age = datetime.now(timezone.utc) - ts
            if age > timedelta(hours=MAX_STALENESS_HOURS):
                errors.append(
                    f"STALE_VECTOR: Feature vector is {age.total_seconds()/3600:.1f}h old "
                    f"(max {MAX_STALENESS_HOURS}h)"
                )
        except Exception:
            pass   # non-critical if timestamp is unparseable

    # ─── Check 4: DSCR Presence ───────────────────────────────────
    dscr = features.get("dscr_proxy")
    if dscr is None:
        errors.append("DSCR_MISSING: 'dscr_proxy' not found in feature vector")

    # ─── Gate Decision ────────────────────────────────────────────
    critical_errors = [e for e in errors if e.startswith(("INCOMPLETE_DATA", "DSCR_MISSING"))]

    if critical_errors:
        gate_status = "FAIL"
    elif imputation_log:
        gate_status = "PASS_WITH_IMPUTATION"
    elif errors:
        # range or temporal errors are warnings, not hard fails
        gate_status = "PASS_WITH_IMPUTATION"
    else:
        gate_status = "PASS"

    print(f"  Step 1 Validation: {gate_status} | {len(errors)} issues | {len(imputation_log)} imputations")

    return {
        "gate_status": gate_status,
        "validated_features": features,
        "imputation_log": imputation_log,
        "validation_errors": errors,
    }
