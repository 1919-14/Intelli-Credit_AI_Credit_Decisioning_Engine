"""
Step 2 — Hard Rule Pre-Filter
Binary overrides BEFORE the ML model runs.
Implements 6 Hard Reject (HR) + 5 Hard Conditional (HC) rules.
"""
from typing import Dict, Any, List


def evaluate_hard_rules(
    features: Dict[str, float],
    forensics_report: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Evaluate all 11 rules against validated features + forensics.
    Returns:
      gate: PROCEED | CONDITIONAL_PROCEED | HARD_REJECT
      rule_log: list of {rule_id, condition, result, reason}
      conditions: list of condition dicts (for CONDITIONAL)
      rejection_reason: string (for REJECT)
    """
    rule_log: List[Dict] = []
    conditions: List[Dict] = []
    rejected = False
    rejection_reason = ""

    dscr = features.get("dscr_proxy", 1.5)
    bounce = features.get("cheque_bounce_frequency", 0)
    compliance = features.get("revenue_gst_alignment", 0.8)
    adverse = features.get("adverse_news_sentiment", 0.5)
    din_score = features.get("promoter_din_score", 1.0)
    od_util = features.get("bank_od_utilisation_pct", 50)
    recon_gap = features.get("gst_2a_vs_3b_gap_pct", 0)
    litigation = features.get("promoter_litigation_count", 0)
    # Company age approximation — use working_capital_cycle_days as proxy if no explicit age
    company_age = features.get("company_age_years", 5)

    # Count RED alerts from forensics
    alerts = forensics_report.get("alerts", [])
    red_alerts = [a for a in alerts if a.get("severity") == "RED"]

    # ─── HARD REJECT RULES (HR) ──────────────────────────────────

    # HR-01: DSCR < 1.0
    hr01 = dscr < 1.0
    rule_log.append({
        "rule_id": "HR-01", "condition": f"DSCR ({dscr:.2f}) < 1.0",
        "result": "REJECT" if hr01 else "PASS",
        "reason": f"Insufficient debt service capacity — DSCR = {dscr:.2f}" if hr01 else "DSCR adequate"
    })
    if hr01:
        rejected = True
        rejection_reason = f"HR-01: Insufficient debt service capacity — DSCR = {dscr:.2f}"

    # HR-02: DIN Disqualification (din_score == 0 means disqualified)
    hr02 = din_score == 0 or din_score < 0.1
    rule_log.append({
        "rule_id": "HR-02", "condition": f"DIN score ({din_score}) indicates disqualification",
        "result": "REJECT" if hr02 else "PASS",
        "reason": "Director disqualification detected — regulatory ineligibility" if hr02 else "No DIN issues"
    })
    if hr02 and not rejected:
        rejected = True
        rejection_reason = "HR-02: Director disqualification detected — regulatory ineligibility"

    # HR-03: Active RED forensic alert
    hr03 = len(red_alerts) > 0
    rule_log.append({
        "rule_id": "HR-03", "condition": f"{len(red_alerts)} RED forensic alert(s)",
        "result": "REJECT" if hr03 else "PASS",
        "reason": f"Critical forensic alert — {red_alerts[0].get('description', '')}" if hr03 else "No RED alerts"
    })
    if hr03 and not rejected:
        rejected = True
        rejection_reason = f"HR-03: Critical forensic alert — {red_alerts[0].get('description', 'fraud signal detected')}"

    # HR-04: Bounce rate > 25%
    hr04 = bounce > 0.25
    rule_log.append({
        "rule_id": "HR-04", "condition": f"Bounce rate ({bounce:.2%}) > 25%",
        "result": "REJECT" if hr04 else "PASS",
        "reason": f"Severe payment dishonor — bounce rate = {bounce:.1%}" if hr04 else "Bounce rate acceptable"
    })
    if hr04 and not rejected:
        rejected = True
        rejection_reason = f"HR-04: Severe payment dishonor pattern — bounce rate = {bounce:.1%}"

    # HR-05: Filing compliance < 0.40
    hr05 = compliance < 0.40
    rule_log.append({
        "rule_id": "HR-05", "condition": f"Filing compliance ({compliance:.2f}) < 0.40",
        "result": "REJECT" if hr05 else "PASS",
        "reason": f"GST filing compliance critically low — score = {compliance:.2f}" if hr05 else "Compliance adequate"
    })
    if hr05 and not rejected:
        rejected = True
        rejection_reason = f"HR-05: GST filing compliance critically low — score = {compliance:.2f}"

    # HR-06: Adverse media > 0.80
    hr06 = adverse > 0.80
    rule_log.append({
        "rule_id": "HR-06", "condition": f"Adverse media ({adverse:.2f}) > 0.80",
        "result": "REJECT" if hr06 else "PASS",
        "reason": f"Severe adverse media — score = {adverse:.2f}" if hr06 else "Adverse media within limits"
    })
    if hr06 and not rejected:
        rejected = True
        rejection_reason = f"HR-06: Severe adverse media — promoter risk score = {adverse:.2f}"

    if rejected:
        print(f"  Step 2 Hard Rules: HARD_REJECT — {rejection_reason}")
        return {
            "gate": "HARD_REJECT",
            "rule_log": rule_log,
            "conditions": [],
            "rejection_reason": rejection_reason,
        }

    # ─── HARD CONDITIONAL RULES (HC) ─────────────────────────────

    # HC-01: DSCR 1.0–1.20
    hc01 = 1.0 <= dscr < 1.20
    if hc01:
        conditions.append({
            "rule_id": "HC-01",
            "condition": f"Marginal DSCR ({dscr:.2f}) — 1.0 to 1.20",
            "action": "Maximum loan limit capped at 60% of computed limit",
            "cap_multiplier": 0.60,
        })
    rule_log.append({
        "rule_id": "HC-01", "condition": f"DSCR ({dscr:.2f}) between 1.0–1.20",
        "result": "CONDITIONAL" if hc01 else "PASS",
        "reason": "Marginal debt service — cap at 60%" if hc01 else "DSCR above 1.20"
    })

    # HC-02: OD utilisation > 75%
    hc02 = od_util > 75
    if hc02:
        conditions.append({
            "rule_id": "HC-02",
            "condition": f"OD/CC utilisation ({od_util:.1f}%) > 75%",
            "action": "Require additional collateral or guarantor",
        })
    rule_log.append({
        "rule_id": "HC-02", "condition": f"OD utilisation ({od_util:.1f}%) > 75%",
        "result": "CONDITIONAL" if hc02 else "PASS",
        "reason": "Working capital dependency — extra collateral required" if hc02 else "OD within limits"
    })

    # HC-03: GST-Bank recon gap > 10%
    hc03 = recon_gap > 10
    if hc03:
        conditions.append({
            "rule_id": "HC-03",
            "condition": f"GST-Bank reconciliation gap ({recon_gap:.1f}%) > 10%",
            "action": "Require CA-certified explanation + audited accounts",
        })
    rule_log.append({
        "rule_id": "HC-03", "condition": f"Recon gap ({recon_gap:.1f}%) > 10%",
        "result": "CONDITIONAL" if hc03 else "PASS",
        "reason": "Revenue declaration concern — CA cert required" if hc03 else "Gap within limits"
    })

    # HC-04: Active litigation > 3
    hc04 = litigation > 3
    if hc04:
        conditions.append({
            "rule_id": "HC-04",
            "condition": f"Active litigation count ({litigation}) > 3",
            "action": "Legal opinion required before disbursal",
        })
    rule_log.append({
        "rule_id": "HC-04", "condition": f"Litigation count ({litigation}) > 3",
        "result": "CONDITIONAL" if hc04 else "PASS",
        "reason": "Potential liability risk — legal opinion needed" if hc04 else "Within limits"
    })

    # HC-05: Company age < 2 years
    hc05 = company_age < 2
    if hc05:
        conditions.append({
            "rule_id": "HC-05",
            "condition": f"Company age ({company_age:.1f} years) < 2 years",
            "action": "Reduce loan limit by 40%; require personal guarantee",
            "cap_multiplier": 0.60,
        })
    rule_log.append({
        "rule_id": "HC-05", "condition": f"Company age ({company_age:.1f}y) < 2",
        "result": "CONDITIONAL" if hc05 else "PASS",
        "reason": "Insufficient history — limit reduced 40%" if hc05 else "Adequate history"
    })

    gate = "CONDITIONAL_PROCEED" if conditions else "PROCEED"
    print(f"  Step 2 Hard Rules: {gate} | {len(conditions)} conditions")

    return {
        "gate": gate,
        "rule_log": rule_log,
        "conditions": conditions,
        "rejection_reason": "",
    }
