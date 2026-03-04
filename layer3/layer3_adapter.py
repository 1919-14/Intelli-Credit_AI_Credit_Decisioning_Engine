"""
=================================================================
INTELLI-CREDIT AI ENGINE
Layer 3 Adapter: Layer 2 Output → Data Cleaning Pipeline Input
=================================================================

Transforms the flat financial_data dict from Layer 2 (LLM extraction)
into the OCR-envelope format expected by DataCleaningPipeline.process_single().

Layer 2 output format:
    {"revenue_from_operations": "24,259.23", "pan_number": "BFKPK3456M", ...}

Layer 3 input (OCR envelope) format:
    {"revenue": {"value": "24,259.23", "confidence": 0.90}, "pan": {"value": "BFKPK3456M", "confidence": 0.90}, ...}
"""

import json
import logging
from datetime import datetime

from layer3.data_cleaning_pipeline import DataCleaningPipeline

log = logging.getLogger("IntelliCredit.Layer3Adapter")


# ─── Field Mapping: Layer 2 key → Layer 3 (cleaning pipeline) key ────────────
# Maps MASTER_SCHEMA field names to the cleaning pipeline's schema field names.
# Format: (layer2_key, layer3_key)
FIELD_MAP = [
    # Revenue fields (try multiple Layer 2 keys, first non-null wins)
    ("total_revenue",              "revenue"),
    ("revenue_from_operations",    "revenue"),

    # Balance sheet fields
    ("net_worth",                  "net_worth"),
    ("total_liabilities",          "total_debt"),     # total_debt in cleaning schema
    ("total_debt",                 "total_debt"),     # direct match if available

    # Profitability
    ("profit_after_tax",           "pat"),
    ("net_profit_from_business",   "pat"),            # fallback from ITR

    # GST fields
    ("total_taxable_value_domestic", "gstr_3b_sales"),
    ("total_taxable_value_exports",  "gstr_2a_sales"),

    # Date fields
    ("gst_filing_date",            "balance_sheet_date"),
    ("itr_filing_date",            "balance_sheet_date"),

    # Identity fields
    ("company_name",               "borrower_name"),
    ("assessee_name",              "borrower_name"),  # fallback from ITR
    ("pan_number",                 "pan"),
    ("cin",                        "cin"),
]

# Ind-AS / Old-AS indicator fields (pass through if present in Layer 2)
IND_AS_PASSTHROUGH = [
    "other_comprehensive_income",
    "total_comprehensive_income",
    "employee_benefit_obligations",
    "fair_value_through_pnl",
    "right_of_use_asset",
    "lease_liability",
    "deferred_tax_oci",
    "remeasurement_of_defined_benefit",
    "preliminary_expenses",
    "misc_expenditure",
    "deferred_revenue_expenditure",
    "proposed_dividend",
    "share_premium_account",
    "capital_redemption_reserve",
]

# Default confidence for LLM-extracted fields
DEFAULT_CONFIDENCE = 0.90


def _parse_confidence(raw_conf):
    """Convert confidence from various formats to float 0-1.

    Handles: 0.90, "90%", "0.90", 90, None
    """
    if raw_conf is None:
        return DEFAULT_CONFIDENCE

    if isinstance(raw_conf, (int, float)):
        # If > 1, assume percentage
        return raw_conf / 100 if raw_conf > 1 else float(raw_conf)

    if isinstance(raw_conf, str):
        raw_conf = raw_conf.strip().rstrip('%')
        try:
            val = float(raw_conf)
            return val / 100 if val > 1 else val
        except ValueError:
            return DEFAULT_CONFIDENCE

    return DEFAULT_CONFIDENCE


def _wrap_ocr_envelope(value, confidence=None, source="llm"):
    """Wrap a raw value into the OCR envelope format expected by the pipeline."""
    if value is None:
        return None
    return {
        "value": value,
        "confidence": _parse_confidence(confidence),
    }


def adapt_layer2_to_layer3(layer2_data, source_document=None):
    """Transform Layer 2 financial_data dict into cleaning pipeline input format.

    Args:
        layer2_data: dict - the flat financial_data from Layer 2 output.
                     Can also be the full IntelliCreditJSON dict (will auto-extract).
        source_document: str - optional source document name for lineage.

    Returns:
        dict - OCR-envelope formatted record ready for DataCleaningPipeline.process_single()
    """
    # Auto-extract financial_data if given the full Layer 2 JSON
    if isinstance(layer2_data, dict):
        if "extracted" in layer2_data:
            extracted = layer2_data["extracted"]
            if isinstance(extracted, dict) and "financial_data" in extracted:
                layer2_data = extracted["financial_data"] or {}
            else:
                layer2_data = extracted or {}
        elif "financial_data" in layer2_data:
            layer2_data = layer2_data["financial_data"] or {}

    record = {}
    used_l3_keys = set()

    # ─── Map fields using priority order (first non-null wins) ────────────
    for l2_key, l3_key in FIELD_MAP:
        # Skip if we already have a value for this L3 key
        if l3_key in used_l3_keys:
            continue

        raw_val = layer2_data.get(l2_key)
        if raw_val is not None and raw_val != "" and raw_val != []:
            # Handle both direct values and DataField-style dicts
            if isinstance(raw_val, dict) and "value" in raw_val:
                record[l3_key] = {
                    "value": raw_val["value"],
                    "confidence": _parse_confidence(raw_val.get("confidence")),
                }
                if raw_val.get("source_page"):
                    record[l3_key]["source_page"] = raw_val["source_page"]
            else:
                record[l3_key] = _wrap_ocr_envelope(raw_val)

            used_l3_keys.add(l3_key)

    # ─── Pass through Ind-AS / Old-AS indicator fields ────────────────────
    for ind_key in IND_AS_PASSTHROUGH:
        raw_val = layer2_data.get(ind_key)
        if raw_val is not None and raw_val != "" and raw_val != []:
            if isinstance(raw_val, dict) and "value" in raw_val:
                record[ind_key] = {
                    "value": raw_val["value"],
                    "confidence": _parse_confidence(raw_val.get("confidence")),
                }
            else:
                record[ind_key] = _wrap_ocr_envelope(raw_val)

    # ─── Add metadata for lineage tracking ────────────────────────────────
    meta = {"source_document": source_document or "layer2_extraction"}

    # Carry over company name for metadata
    company = layer2_data.get("company_name") or layer2_data.get("assessee_name")
    if company:
        meta["company_name"] = company

    record["_metadata"] = meta

    log.info(
        "Adapted %d Layer 2 fields → %d Layer 3 fields",
        len(layer2_data),
        len(record) - 1,  # exclude _metadata
    )

    return record


def run_layer3_cleaning(layer2_output_json, case_id=None, company_name=None):
    """Full Layer 3 execution: adapt + clean + return results.

    Args:
        layer2_output_json: str or dict - Layer 2 JSON output
        case_id: str - case identifier for lineage
        company_name: str - company name for lineage

    Returns:
        dict with keys:
            - layer3_result: full cleaning pipeline output
            - summary: high-level summary for quick display
    """
    # Parse JSON if string
    if isinstance(layer2_output_json, str):
        layer2_data = json.loads(layer2_output_json)
    else:
        layer2_data = layer2_output_json

    source_doc = f"{case_id}_{company_name}_layer2" if case_id else "layer2_extraction"

    # Step 1: Adapt format
    adapted_record = adapt_layer2_to_layer3(layer2_data, source_document=source_doc)

    # Step 2: Run cleaning pipeline
    pipeline = DataCleaningPipeline()
    result = pipeline.process_single(adapted_record)

    # Step 3: Build summary
    report = result.get("validation_report", {})
    features = result.get("derived_features", {})
    clean = result.get("clean_data", {})

    summary = {
        "status": "completed",
        "case_id": case_id,
        "company_name": company_name,
        "processed_at": result.get("_metadata", {}).get("processed_at"),
        "fields_cleaned": len(clean),
        "auto_fixed_count": report.get("auto_fixed_count", 0),
        "flagged_for_review_count": report.get("flagged_for_review_count", 0),
        "risk_flag_count": report.get("risk_flag_count", 0),
        "review_required": report.get("review_required", False),
        "auto_reject": report.get("auto_reject", False),
        "severity_summary": report.get("severity_summary", {}),
        "accounting_standard": features.get("accounting_standard", "UNKNOWN"),
        "de_ratio": features.get("de_ratio"),
        "dscr_proxy": features.get("dscr_proxy"),
        "is_profitable": features.get("is_profitable"),
    }

    return {
        "layer3_result": result,
        "summary": summary,
    }
