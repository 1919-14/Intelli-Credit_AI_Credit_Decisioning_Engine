"""
Step 8 — Risk-Based Pricing Engine
Translates final credit score → interest rate using RBI-linked pricing table.
"""
from typing import Dict, Any


# Base rate = RBI Repo + Bank Spread
BASE_RATE = 8.00   # 6.50% repo + 1.50% spread

PRICING_TABLE = [
    (750, 900,  2.00,  "Very Low Risk"),    # 10.00%
    (650, 749,  3.50,  "Low Risk"),         # 11.50%
    (550, 649,  5.50,  "Moderate Risk"),    # 13.50%
    (450, 549,  8.00,  "High Risk"),        # 16.00%
    (300, 449, 11.00,  "Very High Risk"),   # 19.00%
]


def compute_pricing(
    final_score: int,
    uncertainty_level: str,
    pricing_buffer_bps: int,
    conditions: list,
) -> Dict[str, Any]:
    """Compute final interest rate from score band + buffers + conditions."""
    # Find band rate
    band_spread = 11.00   # default worst
    band_label = "Very High Risk"
    for lo, hi, spread, label in PRICING_TABLE:
        if lo <= final_score <= hi:
            band_spread = spread
            band_label = label
            break

    band_rate = BASE_RATE + band_spread
    unc_buffer = pricing_buffer_bps / 100   # bps → percentage
    cond_penalty = min(len(conditions) * 0.50, 1.50)   # +0.50% per HC, max 1.50%

    final_rate = round(band_rate + unc_buffer + cond_penalty, 2)
    processing_fee = 1.00   # 1% standard

    print(f"  Step 8 Pricing: Base {BASE_RATE}% + Spread {band_spread}% + "
          f"Unc {unc_buffer}% + Cond {cond_penalty}% = {final_rate}%")

    return {
        "base_rate": BASE_RATE,
        "band_spread": band_spread,
        "band_rate": band_rate,
        "uncertainty_buffer_pct": unc_buffer,
        "conditional_penalty_pct": cond_penalty,
        "final_interest_rate": final_rate,
        "rate_type": "Floating (linked to RBI repo rate, reset quarterly)",
        "processing_fee_pct": processing_fee,
        "band_label": band_label,
    }
