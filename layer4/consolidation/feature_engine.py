"""
Block H1–H2: Feature Engineering
Builds the 25-feature vector from all Layer 4 block outputs.
"""
import numpy as np
from typing import Dict, Any, List
from datetime import datetime, timezone


FEATURE_DEFINITIONS = [
    # CHARACTER
    {"name": "promoter_litigation_count", "source": "C2", "default": 0},
    {"name": "mca_charge_count", "source": "D1", "default": 0},
    {"name": "adverse_news_sentiment", "source": "C1", "default": 0.5},
    {"name": "promoter_din_score", "source": "D2", "default": 1.0},
    # CAPACITY
    {"name": "dscr_proxy", "source": "L3", "default": 1.5},
    {"name": "bank_od_utilisation_pct", "source": "B2", "default": 50},
    {"name": "cc_utilisation_volatility", "source": "B2", "default": 10},
    {"name": "gst_turnover_cagr", "source": "L3", "default": 0},
    # CAPITAL
    {"name": "current_ratio", "source": "L3", "default": 1.0},
    {"name": "debt_to_equity", "source": "L3", "default": 1.0},
    {"name": "return_on_net_worth", "source": "L3", "default": 0.1},
    {"name": "ebitda_margin", "source": "L3", "default": 0.1},
    # COLLATERAL
    {"name": "collateral_coverage_ratio", "source": "L2", "default": 1.0},
    # CONDITIONS
    {"name": "gst_2a_vs_3b_gap_pct", "source": "A2", "default": 0},
    {"name": "revenue_gst_alignment", "source": "A1", "default": 0.8},
    {"name": "itc_mismatch_flag", "source": "A2", "default": 0},
    {"name": "circular_trading_ratio", "source": "A3", "default": 0},
    {"name": "cheque_bounce_frequency", "source": "B1", "default": 0},
    {"name": "related_party_txn_pct", "source": "L3", "default": 0},
    {"name": "working_capital_cycle_days", "source": "L3", "default": 60},
    # EXTRA
    {"name": "factory_operational_flag", "source": "F1", "default": 1},
    {"name": "capacity_utilisation_pct", "source": "F1", "default": 70},
    {"name": "succession_risk_flag", "source": "F1", "default": 0},
    {"name": "sector_risk_score", "source": "C3", "default": 0.3},
    {"name": "management_stability_score", "source": "D2", "default": 0.8},
]


def _safe_float(val, default=0):
    """Safely convert to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def build_feature_vector(data: Dict[str, Any]) -> Dict[str, Any]:
    """H1: Compute all 25 features from block outputs."""

    l2 = data.get("layer2_data", {})
    l3 = data.get("layer3_data", {})
    gst = data.get("gst_forensics", {})
    bank = data.get("bank_forensics", {})
    adverse = data.get("adverse_media", {})
    litigation = data.get("litigation", {})
    sector = data.get("sector_risk", {})
    mca = data.get("mca_checks", {})
    cibil = data.get("cibil", {})
    officer = data.get("officer_analysis", {})

    # Build feature dict
    features = {}

    # CHARACTER
    features["promoter_litigation_count"] = _safe_float(litigation.get("promoter_litigation_count"), 0)
    features["mca_charge_count"] = _safe_float(mca.get("mca_charge_count"), 0)
    features["adverse_news_sentiment"] = _safe_float(adverse.get("sentiment_score"), 0.5)
    features["promoter_din_score"] = _safe_float(mca.get("promoter_din_score"), 1.0)

    # CAPACITY
    l3_features = l3.get("derived_features", {}) if isinstance(l3, dict) else {}
    features["dscr_proxy"] = _safe_float(l3_features.get("dscr_proxy"), 1.5)
    features["bank_od_utilisation_pct"] = _safe_float(
        bank.get("b2_od_utilisation", {}).get("bank_od_utilisation_pct"), 50)
    features["cc_utilisation_volatility"] = _safe_float(
        bank.get("b2_od_utilisation", {}).get("cc_utilisation_volatility"), 10)
    features["gst_turnover_cagr"] = _safe_float(l3_features.get("gst_turnover_cagr"), 0)

    # CAPITAL
    features["current_ratio"] = _safe_float(l3_features.get("current_ratio"), 1.0)
    features["debt_to_equity"] = _safe_float(l3_features.get("de_ratio"), 1.0)
    features["return_on_net_worth"] = _safe_float(l3_features.get("ronw"), 0.1)
    features["ebitda_margin"] = _safe_float(l3_features.get("ebitda_margin"), 0.1)

    # COLLATERAL
    features["collateral_coverage_ratio"] = _safe_float(l2.get("collateral_coverage_ratio"), 1.0)

    # CONDITIONS
    features["gst_2a_vs_3b_gap_pct"] = _safe_float(
        gst.get("a2_itc_mismatch", {}).get("gst_2a_vs_3b_gap_pct"), 0)
    features["revenue_gst_alignment"] = _safe_float(
        gst.get("a1_reconciliation", {}).get("revenue_gst_alignment"), 0.8)
    features["itc_mismatch_flag"] = _safe_float(
        gst.get("a2_itc_mismatch", {}).get("itc_mismatch_flag"), 0)
    features["circular_trading_ratio"] = _safe_float(
        gst.get("a3_circular_trading", {}).get("circular_trading_ratio"), 0)
    features["cheque_bounce_frequency"] = _safe_float(
        bank.get("b1_cheque_bounces", {}).get("cheque_bounce_frequency"), 0)
    features["related_party_txn_pct"] = _safe_float(l3_features.get("related_party_txn_pct"), 0)
    features["working_capital_cycle_days"] = _safe_float(l3_features.get("working_capital_cycle_days"), 60)

    # EXTRA
    features["factory_operational_flag"] = _safe_float(officer.get("factory_operational_flag"), 1)
    features["capacity_utilisation_pct"] = _safe_float(officer.get("capacity_utilisation_percent"), 70)
    features["succession_risk_flag"] = _safe_float(officer.get("succession_risk_flag"), 0)
    features["sector_risk_score"] = _safe_float(sector.get("sector_risk_score"), 0.3)
    features["management_stability_score"] = _safe_float(mca.get("management_stability_score"), 0.8)

    # Build numpy array (ordered by FEATURE_DEFINITIONS)
    vector = np.array([features.get(fd["name"], fd["default"]) for fd in FEATURE_DEFINITIONS])

    # Audit snapshot
    audit_snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "features": features,
        "feature_vector": vector.tolist(),
        "feature_names": [fd["name"] for fd in FEATURE_DEFINITIONS],
        "feature_sources": {fd["name"]: fd["source"] for fd in FEATURE_DEFINITIONS},
    }

    data["feature_vector"] = features
    data["feature_vector_array"] = vector.tolist()
    data["feature_audit_snapshot"] = audit_snapshot
    return data


def consolidate_and_build_features(data: Dict[str, Any]) -> Dict[str, Any]:
    """G1 + H1–H2 combined. Entry point for LangChain final stage."""
    from layer4.consolidation.alert_engine import consolidate_alerts

    data = consolidate_alerts(data)
    data = build_feature_vector(data)

    # Build final output dict (plain dict, no Pydantic)
    data["layer4_output"] = {
        "forensics_report": data.get("forensics_report", {}),
        "feature_vector": data.get("feature_vector", {}),
        "feature_vector_array": data.get("feature_vector_array", []),
        "research_findings": {
            "adverse_media": data.get("adverse_media", {}),
            "litigation": data.get("litigation", {}),
            "sector_risk": data.get("sector_risk", {}),
            "mca_checks": data.get("mca_checks", {}),
            "cibil": data.get("cibil", {}),
        },
        "officer_analysis": data.get("officer_analysis", {}),
        "gst_forensics": data.get("gst_forensics", {}),
        "bank_forensics": data.get("bank_forensics", {}),
        "feature_audit_snapshot": data.get("feature_audit_snapshot", {}),
    }

    return data
