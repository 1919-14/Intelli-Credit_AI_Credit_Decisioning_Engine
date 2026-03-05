"""
Step 10 — Loan Limit Formula & Structuring
Three-pathway limit + Nayak Committee MPBF (Method II).
"""
import math
from typing import Dict, Any


def compute_loan_structure(
    features: Dict[str, float],
    final_rate: float,
    conditions: list,
    layer2_data: Dict[str, Any],
    requested_amount_lakhs: float = 75.0,
) -> Dict[str, Any]:
    """
    Compute loan limit via 3 methods + MPBF.
    Binding constraint = min of all applicable limits.
    """
    dscr = features.get("dscr_proxy", 1.5)
    od_util = features.get("bank_od_utilisation_pct", 50)
    recon_gap = features.get("gst_2a_vs_3b_gap_pct", 0)
    collateral_cov = features.get("collateral_coverage_ratio", 1.0)
    ebitda_margin = features.get("ebitda_margin", 0.10)
    gst_cagr = features.get("gst_turnover_cagr", 0)

    # Extract balance sheet items from Layer 2
    l2 = layer2_data or {}
    monthly_credits = float(l2.get("avg_monthly_credits", 0) or l2.get("monthly_credits_avg", 22.0) or 22.0)
    emi_ratio = float(l2.get("emi_obligation_ratio", 0.30) or 0.30)

    # Net worth from L2 (rough: current_ratio × estimated current liabilities)
    net_worth = float(l2.get("net_worth", 0) or l2.get("tangible_net_worth", 0) or 89.45)

    # Balance sheet components for MPBF
    inventory = float(l2.get("inventory", 0) or l2.get("closing_stock", 0) or 0)
    debtors = float(l2.get("sundry_debtors", 0) or l2.get("trade_receivables", 0) or 0)
    advances = float(l2.get("advances", 0) or l2.get("loans_and_advances", 0) or 0)
    cash = float(l2.get("cash_and_bank", 0) or l2.get("cash_balance", 0) or 0)
    creditors = float(l2.get("sundry_creditors", 0) or l2.get("trade_payables", 0) or 0)
    provisions = float(l2.get("provisions", 0) or 0)
    other_cl = float(l2.get("other_current_liabilities", 0) or 0)
    bank_borrowings = float(l2.get("bank_borrowings", 0) or l2.get("cc_od_limit", 0) or 0)

    tenure_months = 48
    rate_monthly = final_rate / 100 / 12

    # ─── Method A: DSCR-Based Limit ──────────────────────────────
    monthly_disposable = monthly_credits * (1 - emi_ratio)
    dscr_discount = min(1.0, max(0, dscr - 1.0))
    max_emi = monthly_disposable * dscr_discount

    if rate_monthly > 0 and max_emi > 0:
        dscr_limit = max_emi * ((1 - (1 + rate_monthly) ** (-tenure_months)) / rate_monthly)
    else:
        dscr_limit = max_emi * tenure_months
    dscr_limit = round(dscr_limit, 2)

    # ─── Method B: GST Revenue Multiplier ─────────────────────────
    gst_annual = monthly_credits * 12   # approximate annual revenue
    recon_penalty = recon_gap / 100
    gst_multiplier = 0.20 * (1 - recon_penalty)
    gst_limit = round(gst_annual * gst_multiplier, 2)

    # ─── Method C: Collateral-Based Limit ─────────────────────────
    collateral_value = net_worth * 2.5 * min(collateral_cov, 1.5)
    ltv_cap = 0.65
    collateral_limit = round(collateral_value * ltv_cap, 2)

    # ─── Method D: Nayak Committee MPBF (Method II) ───────────────
    current_assets = inventory + debtors + advances + cash
    current_liab_excl_bank = creditors + provisions + other_cl
    working_capital_gap = current_assets - current_liab_excl_bank
    mpbf = round(0.75 * max(0, working_capital_gap), 2)
    borrower_margin = round(0.25 * max(0, working_capital_gap), 2)

    mpbf_breakdown = {
        "current_assets": {
            "inventory": inventory,
            "debtors": debtors,
            "advances": advances,
            "cash": cash,
            "total": current_assets,
        },
        "current_liabilities_excl_bank": {
            "creditors": creditors,
            "provisions": provisions,
            "other_cl": other_cl,
            "total": current_liab_excl_bank,
            "bank_borrowings_excluded": bank_borrowings,
        },
        "working_capital_gap": working_capital_gap,
        "mpbf_75pct": mpbf,
        "borrower_margin_25pct": borrower_margin,
        "rbi_method": "Nayak Committee Method II",
    }

    # ─── HC condition caps ────────────────────────────────────────
    cap_multiplier = 1.0
    for cond in conditions:
        cm = cond.get("cap_multiplier")
        if cm and cm < cap_multiplier:
            cap_multiplier = cm

    limits = {
        "dscr_limit": dscr_limit,
        "gst_limit": gst_limit,
        "collateral_limit": collateral_limit,
        "mpbf_limit": mpbf,
    }

    # Binding constraint = min of the 4 methods
    binding = min(limits.values()) if all(v > 0 for v in limits.values()) else max(limits.values())
    binding_key = min(limits, key=lambda k: limits[k]) if all(v > 0 for v in limits.values()) else "dscr_limit"

    sanction_limit = round(binding * cap_multiplier, 2)
    approved_amount = min(requested_amount_lakhs, sanction_limit)

    # ─── Loan Structure ──────────────────────────────────────────
    term_pct = 0.60
    wc_pct = 0.40
    term_amount = round(approved_amount * term_pct, 2)
    wc_amount = round(approved_amount * wc_pct, 2)

    # EMI calculation
    if rate_monthly > 0:
        emi = term_amount * rate_monthly * (1 + rate_monthly) ** tenure_months / \
              ((1 + rate_monthly) ** tenure_months - 1)
    else:
        emi = term_amount / tenure_months
    emi = round(emi, 2)

    print(f"  Step 10 Loan: DSCR={dscr_limit:.0f}L | GST={gst_limit:.0f}L | "
          f"Collateral={collateral_limit:.0f}L | MPBF={mpbf:.0f}L | "
          f"Binding={binding_key} | Sanction={sanction_limit:.0f}L | Approved={approved_amount:.0f}L")

    return {
        "limits": limits,
        "binding_constraint": binding_key.replace("_limit", "").upper(),
        "sanction_limit_lakhs": sanction_limit,
        "requested_amount_lakhs": requested_amount_lakhs,
        "approved_amount_lakhs": approved_amount,
        "cap_multiplier": cap_multiplier,
        "mpbf": mpbf_breakdown,
        "loan_structure": {
            "term_loan": {
                "amount_lakhs": term_amount,
                "rate": final_rate,
                "tenure_months": tenure_months,
                "emi_lakhs": emi,
                "product": "Term Loan (Equipment / Expansion)",
            },
            "working_capital": {
                "amount_lakhs": wc_amount,
                "rate": round(final_rate + 0.75, 2),   # WC OD typically +75bps
                "tenure_months": 12,
                "product": "Working Capital OD (Revolving)",
                "drawing_power": "Based on monthly stock + debtors statement",
            },
            "total_sanctioned_lakhs": approved_amount,
            "first_repayment": "1st of month following disbursal + 30-day moratorium",
            "repayment_reserve": "1 month EMI held in escrow",
        },
        "limit_details": {
            "dscr": {
                "monthly_disposable": round(monthly_disposable, 2),
                "dscr_discount_factor": round(dscr_discount, 3),
                "max_emi": round(max_emi, 2),
                "limit": dscr_limit,
            },
            "gst": {
                "annual_revenue": round(gst_annual, 2),
                "multiplier": round(gst_multiplier, 4),
                "recon_penalty": round(recon_penalty, 4),
                "limit": gst_limit,
            },
            "collateral": {
                "net_worth": net_worth,
                "collateral_value": round(collateral_value, 2),
                "ltv_cap": ltv_cap,
                "limit": collateral_limit,
            },
        },
    }
