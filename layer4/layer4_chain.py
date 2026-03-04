"""
Layer 4 LangChain Orchestrator — with 3 HITL pause points.

Stage 1: GST + Bank forensics (pure Python)     → HITL-1 pause
Stage 2: Web research (Tavily + Groq)            → HITL-2 pause
Stage 3: Feature build + officer NLP + finalize  → HITL-3 pause
Stage 4: Feature override + final output
"""
import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from langchain_core.runnables import RunnableLambda

from layer4.forensics.gst_forensics import run_gst_forensics
from layer4.forensics.bank_forensics import run_bank_forensics
from layer4.research.adverse_media import run_adverse_media
from layer4.research.litigation import run_litigation_check
from layer4.research.sector_risk import run_sector_risk
from layer4.research.mca_roc import run_mca_checks
from layer4.research.cibil_mock import run_cibil_mock
from layer4.qualitative.officer_notes import run_officer_notes
from layer4.consolidation.feature_engine import consolidate_and_build_features


# ─── HITL Audit Trail ────────────────────────────────────────────────
def _make_audit_entry(
    hitl_stage: int,
    action: str,            # "DISMISS_ALERT" | "DISMISS_FINDING" | "OVERRIDE_FEATURE" | "CONFIRM"
    officer_id: str,
    item_id: str,           # alert_id, finding_id or feature_name
    original_value: Any,
    new_value: Any,
    reason: str
) -> Dict:
    return {
        "hitl_stage": hitl_stage,
        "action": action,
        "officer_id": officer_id,
        "item_id": item_id,
        "original_value": original_value,
        "new_value": new_value,
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─── Stage 1: Pure Python Forensics ──────────────────────────────────
def run_stage1_forensics(data: Dict[str, Any]) -> Dict[str, Any]:
    """GST + Bank forensics. Fast, no API calls."""
    data = run_gst_forensics(data)
    data = run_bank_forensics(data)
    return data


def apply_hitl1_decisions(
    data: Dict[str, Any],
    dismissed_alert_ids: List[str],
    dismiss_reasons: Dict[str, str],        # alert_id → reason
    officer_id: str = "unknown"
) -> Dict[str, Any]:
    """
    Remove dismissed alerts from gst_forensics_alerts and bank_forensics_alerts.
    Record every decision in the audit trail.
    """
    audit = data.setdefault("hitl_audit_trail", [])
    kept, dismissed = [], []

    all_alerts = (
        data.get("gst_forensics_alerts", []) +
        data.get("bank_forensics_alerts", [])
    )

    for alert in all_alerts:
        aid = alert.get("alert_id", "")
        if aid in dismissed_alert_ids:
            reason = dismiss_reasons.get(aid, "No reason provided")
            audit.append(_make_audit_entry(
                hitl_stage=1,
                action="DISMISS_ALERT",
                officer_id=officer_id,
                item_id=aid,
                original_value=alert.get("severity"),
                new_value="DISMISSED",
                reason=reason
            ))
            dismissed.append({**alert, "dismissed": True, "dismiss_reason": reason})
        else:
            audit.append(_make_audit_entry(
                hitl_stage=1,
                action="CONFIRM_ALERT",
                officer_id=officer_id,
                item_id=aid,
                original_value=alert.get("severity"),
                new_value=alert.get("severity"),
                reason="Confirmed by officer"
            ))
            kept.append(alert)

    # Replace alert lists with filtered versions
    gst_alerts = [a for a in kept if a.get("source", "").lower().startswith("gst") or
                  a.get("alert_id", "").startswith("A")]
    bank_alerts = [a for a in kept if a.get("alert_id", "").startswith("B")]
    # If not clearly separated, keep all kept in both (consolidation deduplicates)
    data["gst_forensics_alerts"] = [a for a in kept if "A" in a.get("alert_id", "")]
    data["bank_forensics_alerts"] = [a for a in kept if "B" in a.get("alert_id", "")]
    data["hitl1_dismissed_alerts"] = dismissed

    print(f"  HITL-1: kept {len(kept)}, dismissed {len(dismissed)} forensic alerts")
    return data


# ─── Stage 2: Web Research ────────────────────────────────────────────
def run_stage2_research(data: Dict[str, Any]) -> Dict[str, Any]:
    """Tavily + Groq research blocks C1–E1."""
    data = run_adverse_media(data)
    data = run_litigation_check(data)
    data = run_sector_risk(data)
    data = run_mca_checks(data)
    data = run_cibil_mock(data)
    return data


def apply_hitl2_decisions(
    data: Dict[str, Any],
    dismissed_findings: List[Dict],         # [{"block": "adverse_media", "finding_id": "...", "reason": "..."}]
    officer_id: str = "unknown"
) -> Dict[str, Any]:
    """
    Remove dismissed research findings and their associated alerts.
    Record decisions in audit trail.
    """
    audit = data.setdefault("hitl_audit_trail", [])
    dismissed_map: Dict[str, List] = {}   # block → list of dismissed finding ids

    for d in (dismissed_findings or []):
        block = d.get("block", "")
        fid = d.get("finding_id", "")
        reason = d.get("reason", "No reason provided")
        dismissed_map.setdefault(block, []).append(fid)

        audit.append(_make_audit_entry(
            hitl_stage=2,
            action="DISMISS_FINDING",
            officer_id=officer_id,
            item_id=f"{block}::{fid}",
            original_value="AI_CLASSIFIED",
            new_value="DISMISSED",
            reason=reason
        ))

    # Remove dismissed snippets from research blocks
    for block, fids in dismissed_map.items():
        block_data = data.get(block, {})
        if not block_data:
            continue
        # Filter raw_snippets
        snips = block_data.get("raw_snippets", [])
        kept_snips = [s for s in snips if s.get("finding_id") not in fids]
        # Filter cases (litigation)
        cases = block_data.get("cases", [])
        kept_cases = [c for c in cases if c.get("finding_id") not in fids]
        # Filter alerts from dismissed findings
        alerts = block_data.get("alerts", [])
        kept_alerts = [a for a in alerts if a.get("finding_id") not in fids]

        block_data["raw_snippets"] = kept_snips
        block_data["cases"] = kept_cases
        block_data["alerts"] = kept_alerts
        block_data["hitl2_dismissed_count"] = len(fids)
        data[block] = block_data

    confirmed_count = sum(1 for d in (dismissed_findings or []) if d.get("action") == "CONFIRM")
    print(f"  HITL-2: {len(dismissed_findings or [])} research findings reviewed")
    return data


# ─── Stage 3: Officer Notes + Feature Build ───────────────────────────
def run_stage3_build(data: Dict[str, Any]) -> Dict[str, Any]:
    """Officer NLP + pre-officer snapshot + consolidation + features."""
    from layer4.consolidation.alert_engine import consolidate_alerts
    from layer4.consolidation.feature_engine import build_feature_vector

    # Pre-officer snapshot
    temp = dict(data)
    temp["officer_analysis"] = {}
    from layer4.consolidation.alert_engine import consolidate_alerts as ca
    from layer4.consolidation.feature_engine import build_feature_vector as bfv
    temp = ca(temp)
    temp = bfv(temp)
    data["pre_officer_features"] = dict(temp.get("feature_vector", {}))
    data["pre_officer_forensics"] = dict(temp.get("forensics_report", {}))

    # Officer NLP
    data = run_officer_notes(data)

    # Full consolidation + feature build
    data = consolidate_and_build_features(data)
    return data


def apply_hitl3_decisions(
    data: Dict[str, Any],
    feature_overrides: List[Dict],          # [{"feature": "...", "new_value": ..., "reason": "..."}]
    officer_id: str = "unknown"
) -> Dict[str, Any]:
    """
    Patch the feature vector with officer overrides.
    Record every change in audit trail.
    """
    audit = data.setdefault("hitl_audit_trail", [])
    features = data.get("feature_vector", {})

    for ov in (feature_overrides or []):
        feat = ov.get("feature")
        new_val = ov.get("new_value")
        reason = ov.get("reason", "No reason provided")
        old_val = features.get(feat)

        if feat is None or new_val is None:
            continue

        try:
            new_val = float(new_val)
        except (ValueError, TypeError):
            continue

        audit.append(_make_audit_entry(
            hitl_stage=3,
            action="OVERRIDE_FEATURE",
            officer_id=officer_id,
            item_id=feat,
            original_value=old_val,
            new_value=new_val,
            reason=reason
        ))
        features[feat] = new_val

    data["feature_vector"] = features

    # Rebuild numpy array after overrides
    import numpy as np
    from layer4.consolidation.feature_engine import FEATURE_DEFINITIONS
    vector = [features.get(fd["name"], fd["default"]) for fd in FEATURE_DEFINITIONS]
    data["feature_vector_array"] = vector

    print(f"  HITL-3: {len(feature_overrides or [])} feature overrides applied")
    return data


# ─── Stage 4: Officer Explanation + Final Output ─────────────────────
def _explain_officer_adjustments(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    LLM explains changes from officer notes AND feature overrides.
    Combines both sets of changes into one unified explanation.
    """
    officer = data.get("officer_analysis", {})
    pre = data.get("pre_officer_features", {})
    post = data.get("feature_vector", {})
    audit = data.get("hitl_audit_trail", [])

    # Collect all changes: officer NLP + HITL-3 overrides
    changes = {}
    for key in post:
        pre_val = pre.get(key)
        post_val = post.get(key)
        if pre_val != post_val and pre_val is not None:
            changes[key] = {"before": pre_val, "after": post_val}

    # Also pick up HITL-3 override reasons for pre-filling explanations
    hitl3_reasons = {
        e["item_id"]: e["reason"]
        for e in audit
        if e.get("action") == "OVERRIDE_FEATURE"
    }

    if not changes:
        data["officer_adjustment_explanation"] = {
            "changes": {},
            "explanations": {},
            "overall_impact": "No feature values changed from defaults.",
            "hitl3_override_count": len(hitl3_reasons),
        }
        return data

    try:
        from groq import Groq
        client = Groq(api_key=os.getenv("API_KEY", ""))

        officer_summary = officer.get("summary", "No officer notes provided")
        override_context = "\n".join([f"- {k}: {v}" for k, v in hitl3_reasons.items()]) or "None"

        prompt = f"""You are a senior credit risk analyst writing for a Credit Appraisal Memorandum (CAM).

OFFICER SITE-VISIT NOTES SUMMARY: {officer_summary}

MANUAL OVERRIDE REASONS PROVIDED BY OFFICER:
{override_context}

FEATURE VALUE CHANGES (before → after officer review):
{json.dumps(changes, indent=2)}

For each changed feature, write a concise, professional 1-2 sentence explanation suitable for a CAM document. Reference the officer's observations or override reasoning directly.

Return JSON:
{{
  "explanations": {{
    "feature_name": "Professional CAM-suitable explanation"
  }},
  "overall_impact": "1 sentence summary of how officer review affected the credit risk profile"
}}"""

        resp = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            response_format={"type": "json_object"}
        )
        raw = resp.choices[0].message.content
        explanation = json.loads(raw.replace("```json", "").replace("```", "").strip())
    except Exception as e:
        explanation = {
            "explanations": {
                k: hitl3_reasons.get(k, f"Changed from {v['before']} to {v['after']} based on officer review")
                for k, v in changes.items()
            },
            "overall_impact": "Officer review and manual overrides adjusted the qualitative risk profile."
        }

    data["officer_adjustment_explanation"] = {
        "changes": changes,
        "hitl3_override_count": len(hitl3_reasons),
        **explanation
    }
    return data


def run_stage4_finalize(
    data: Dict[str, Any],
    dismissed_alert_ids: List[str] = None
) -> Dict[str, Any]:
    """Final output — builds layer4_output with all HITL data."""
    data = _explain_officer_adjustments(data)

    # Remove any remaining dismissed alerts from consolidated report
    if dismissed_alert_ids:
        report = data.get("forensics_report", {})
        all_alerts = report.get("alerts", [])
        report["alerts"] = [a for a in all_alerts if a.get("alert_id") not in dismissed_alert_ids]
        data["forensics_report"] = report

    # Build final output
    l4out = {
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
        # HITL specific
        "officer_adjustment_explanation": data.get("officer_adjustment_explanation", {}),
        "pre_officer_features": data.get("pre_officer_features", {}),
        "pre_officer_forensics": data.get("pre_officer_forensics", {}),
        "hitl_audit_trail": data.get("hitl_audit_trail", []),
        "hitl1_dismissed_alerts": data.get("hitl1_dismissed_alerts", []),
    }

    data["layer4_output"] = l4out
    return data


# ─── Simple Entry Point (non-HITL fallback, used in tests) ───────────
def run_layer4(
    layer2_data: dict,
    layer3_data: dict,
    company_identifiers: dict,
    officer_notes: str = "",
    case_id: str = "",
    company_name: str = "",
    progress_callback=None,
    dismissed_alert_ids: List[str] = None,
    dismissed_research: List[Dict] = None,
    feature_overrides: List[Dict] = None,
    officer_id: str = "system"
) -> dict:
    """
    Main entry point. Runs all 4 stages sequentially.
    HITL decisions can be passed in directly (non-interactive mode).
    """
    print("\n" + "=" * 60)
    print("🔍 LAYER 4: Forensics, Research & Feature Engineering")
    print("=" * 60)

    data = {
        "layer2_data": layer2_data or {},
        "layer3_data": layer3_data or {},
        "company_identifiers": company_identifiers or {},
        "officer_notes": officer_notes or "",
        "case_id": case_id,
        "company_name": company_name,
        "hitl_audit_trail": [],
    }

    if progress_callback:
        progress_callback("Stage 1: GST & Bank forensics...", 10)
    print("\n📊 Stage 1: Forensics...")
    data = run_stage1_forensics(data)

    if dismissed_alert_ids or dismissed_research:
        data = apply_hitl1_decisions(data, dismissed_alert_ids or [], {}, officer_id)

    if progress_callback:
        progress_callback("Stage 2: Web research...", 30)
    print("\n🌐 Stage 2: Web Research...")
    data = run_stage2_research(data)

    if dismissed_research:
        data = apply_hitl2_decisions(data, dismissed_research, officer_id)

    if progress_callback:
        progress_callback("Stage 3: Officer NLP + features...", 70)
    print("\n📋 Stage 3: Officer NLP + Feature Build...")
    data = run_stage3_build(data)

    if feature_overrides:
        data = apply_hitl3_decisions(data, feature_overrides, officer_id)

    if progress_callback:
        progress_callback("Stage 4: Finalizing...", 90)
    print("\n⚡ Stage 4: Finalizing...")
    data = run_stage4_finalize(data, dismissed_alert_ids)

    report = data.get("forensics_report", {})
    print(f"\n{'='*60}")
    print(f"📊 LAYER 4 COMPLETE")
    print(f"   Alerts: {report.get('red_flag_count', 0)} RED, {report.get('amber_flag_count', 0)} AMBER")
    print(f"   HITL audit entries: {len(data.get('hitl_audit_trail', []))}")
    print(f"{'='*60}")

    if progress_callback:
        progress_callback("Layer 4 complete", 100)

    return data.get("layer4_output", data)
