"""
Step 9 — Decision Logic
APPROVE / CONDITIONAL / REJECT determination with covenant generation.
"""
from typing import Dict, Any, List


def make_decision(
    final_score: int,
    final_pd: float,
    features: Dict[str, float],
    hard_rules: Dict[str, Any],
    forensics_report: Dict[str, Any],
    llm_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply decision matrix from spec and generate covenants."""

    dscr = features.get("dscr_proxy", 1.5)
    bounce = features.get("cheque_bounce_frequency", 0)
    od_util = features.get("bank_od_utilisation_pct", 50)
    alerts = forensics_report.get("alerts", [])
    red_count = sum(1 for a in alerts if a.get("severity") == "RED")
    amber_count = sum(1 for a in alerts if a.get("severity") == "AMBER")
    conditions = hard_rules.get("conditions", [])

    # ─── REJECT criteria ─────────────────────────────────────────
    if hard_rules.get("gate") == "HARD_REJECT":
        print(f"  Step 9 Decision: REJECT (hard rule)")
        return {
            "decision": "REJECT",
            "reason": hard_rules.get("rejection_reason", "Hard rule triggered"),
            "conditions": [],
            "covenants": [],
        }

    if final_score < 550:
        print(f"  Step 9 Decision: REJECT (score {final_score} < 550)")
        return {
            "decision": "REJECT",
            "reason": f"Credit score {final_score} below minimum threshold of 550",
            "conditions": [],
            "covenants": [],
        }

    if final_pd > 0.60:
        print(f"  Step 9 Decision: REJECT (PD {final_pd:.1%} > 60%)")
        return {
            "decision": "REJECT",
            "reason": f"Probability of default {final_pd:.1%} exceeds 60% threshold",
            "conditions": [],
            "covenants": [],
        }

    if red_count > 0:
        print(f"  Step 9 Decision: REJECT ({red_count} RED alerts)")
        return {
            "decision": "REJECT",
            "reason": f"{red_count} active RED forensic alert(s) present",
            "conditions": [],
            "covenants": [],
        }

    # ─── CONDITIONAL criteria ────────────────────────────────────
    conditional_flags = []
    if 550 <= final_score < 650:
        conditional_flags.append("Credit score in moderate risk band (550–649)")
    if 1.0 <= dscr < 1.20:
        conditional_flags.append(f"Marginal DSCR ({dscr:.2f})")
    if amber_count >= 3:
        conditional_flags.append(f"{amber_count} AMBER forensic alerts")
    if od_util > 75:
        conditional_flags.append(f"OD utilisation {od_util:.0f}% > 75%")
    if len(conditions) >= 1:
        conditional_flags.extend([c.get("condition", "") for c in conditions])

    # ─── APPROVE criteria ────────────────────────────────────────
    is_approve = (
        final_score >= 650 and
        final_pd <= 0.45 and
        dscr >= 1.20 and
        red_count == 0 and
        amber_count <= 2 and
        bounce <= 0.10 and
        not conditional_flags
    )

    decision = "APPROVE" if is_approve else "CONDITIONAL"

    # ─── Generate covenants ──────────────────────────────────────
    covenants = _generate_covenants(features, llm_result, conditions, amber_count, od_util)

    print(f"  Step 9 Decision: {decision} | {len(conditional_flags)} flags | {len(covenants)} covenants")

    return {
        "decision": decision,
        "reason": "" if decision == "APPROVE" else "; ".join(conditional_flags),
        "conditions": conditional_flags,
        "covenants": covenants,
    }


def _generate_covenants(features, llm, conditions, amber_count, od_util):
    """Generate standard + risk-specific covenants."""
    covenants = []

    # Standard covenants
    covenants.append({
        "id": "COV-01",
        "type": "Monitoring",
        "description": "Re-assessment at 12 months — if credit score drops below 650, pricing renegotiation clause applies.",
    })

    # OD-related
    if od_util > 50:
        covenants.append({
            "id": "COV-02",
            "type": "Working Capital",
            "description": f"OD/CC utilisation to be maintained below 70% — quarterly bank statement submission required.",
        })

    # GST recon
    if features.get("gst_2a_vs_3b_gap_pct", 0) > 5:
        covenants.append({
            "id": "COV-03",
            "type": "Compliance",
            "description": "GST-bank reconciliation gap to be explained and certified by CA within 30 days of disbursal.",
        })

    # Key-man (from LLM)
    biggest_risk = (llm.get("biggest_risk", "") or "").lower()
    if "key" in biggest_risk or "succession" in biggest_risk or features.get("succession_risk_flag", 0) > 0:
        covenants.append({
            "id": "COV-04",
            "type": "Insurance",
            "description": "Key-man life insurance policy (sum assured ≥ loan outstanding) to be assigned to lender before disbursal.",
        })

    # HC conditions → covenants
    for cond in conditions:
        rid = cond.get("rule_id", "")
        if rid == "HC-02":
            covenants.append({
                "id": "COV-05",
                "type": "Collateral",
                "description": "Additional collateral or personal guarantee of promoter required before disbursal.",
            })
        elif rid == "HC-04":
            covenants.append({
                "id": "COV-06",
                "type": "Legal",
                "description": "Independent legal opinion on pending litigation required before disbursal.",
            })

    return covenants
