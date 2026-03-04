"""
=================================================================
INTELLI-CREDIT AI ENGINE
Data Cleaning & Normalization Layer
Version: 1.0.0
=================================================================
Architecture: OCR/LLM → [THIS LAYER] → ML & Decision → CAM Generator

Run: python data_cleaning_pipeline.py
=================================================================
"""

import re
import json
import copy
import logging
import hashlib
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SECTION 1: ENUMS & DATA CLASSES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class Severity(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ActionTaken(Enum):
    AUTO_FIXED = "AUTO_FIXED"
    FLAGGED_FOR_REVIEW = "FLAGGED_FOR_REVIEW"
    REJECTED = "REJECTED"
    PASSED = "PASSED"


@dataclass
class TransformationRecord:
    """Tracks every single change made to a field."""
    field_name: str
    original_value: Any
    cleaned_value: Any
    rule_applied: str
    module: str
    source_page: Optional[int] = None
    source_document: Optional[str] = None
    confidence: Optional[float] = None
    action: str = "AUTO_FIXED"
    timestamp: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )


@dataclass
class ValidationFlag:
    """A risk or quality flag raised during validation."""
    rule_id: str
    field_name: str
    description: str
    severity: str
    current_value: Any = None
    expected_range: str = ""
    auto_reject: bool = False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SECTION 2: CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


DEFAULT_CONFIG = {

    # Pipeline Identity
    "pipeline_version": "2.0.0",
    "pipeline_name": "IntelliCredit-DataCleaning",

    # Schema Version Control
    "schema_version": "2.0.0",

    # Deterministic Processing Timestamp (None = use current time)
    "processing_timestamp": None,

    # Confidence Tiers
    "confidence_auto_fix_threshold": 0.80,
    "confidence_review_threshold": 0.75,
    "confidence_reject_threshold": 0.50,

    # Credit Thresholds
    "de_ratio_warning_threshold": 3.0,
    "de_ratio_reject_threshold": 10.0,
    "gst_mismatch_threshold": 0.20,
    "dscr_warning_threshold": 1.5,
    "dscr_reject_threshold": 1.0,

    # Outlier Ranges (in Lakhs)
    "outlier_ranges": {
        "revenue":    {"min": 0,      "max": 500000},
        "net_worth":  {"min": -10000, "max": 500000},
        "total_debt": {"min": 0,      "max": 1000000},
        "pat":        {"min": -50000, "max": 100000},
    },

    # IQR Outlier Detection Multiplier (default 1.5)
    "iqr_multiplier": 1.5,

    # Data Freshness
    "max_data_age_days": 548,

    # Normalisation Targets
    "target_currency_unit": "lakhs",
    "target_date_format": "%d-%b-%Y",

    # Ind-AS vs Old-AS Detection Indicators
    "ind_as_indicators": [
        "other_comprehensive_income",
        "total_comprehensive_income",
        "employee_benefit_obligations",
        "fair_value_through_pnl",
        "right_of_use_asset",
        "lease_liability",
        "deferred_tax_oci",
        "remeasurement_of_defined_benefit",
    ],
    "old_as_indicators": [
        "preliminary_expenses",
        "misc_expenditure",
        "deferred_revenue_expenditure",
        "proposed_dividend",
        "share_premium_account",
        "capital_redemption_reserve",
    ],

    # Field Schema
    "schema": {
        "revenue": {
            "type": "currency",
            "criticality": "REQUIRED",
            "allow_negative": False,
        },
        "net_worth": {
            "type": "currency",
            "criticality": "REQUIRED",
            "allow_negative": True,
        },
        "total_debt": {
            "type": "currency",
            "criticality": "REQUIRED",
            "allow_negative": False,
        },
        "pat": {
            "type": "currency",
            "criticality": "IMPORTANT",
            "allow_negative": True,
        },
        "gstr_3b_sales": {
            "type": "currency",
            "criticality": "IMPORTANT",
            "allow_negative": False,
        },
        "gstr_2a_sales": {
            "type": "currency",
            "criticality": "IMPORTANT",
            "allow_negative": False,
        },
        "balance_sheet_date": {
            "type": "date",
            "criticality": "REQUIRED",
            "allow_negative": False,
        },
        "borrower_name": {
            "type": "string",
            "criticality": "REQUIRED",
            "allow_negative": False,
        },
        "pan": {
            "type": "pattern",
            "criticality": "REQUIRED",
            "pattern": r"^[A-Z]{5}[0-9]{4}[A-Z]$",
            "allow_negative": False,
        },
        "cin": {
            "type": "pattern",
            "criticality": "OPTIONAL",
            "pattern": r"^[A-Z]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$",
            "allow_negative": False,
        },
    },

    # OCR Character Swap Rules
    "ocr_corrections": {
        "O": "0", "o": "0",
        "S": "5", "s": "5",
        "l": "1", "I": "1",
        "B": "8",
        "G": "6",
        "Z": "2",
    },

    # Currency Unit to Lakhs Multiplier
    "currency_multipliers": {
        "cr": 100, "crore": 100, "crores": 100,
        "lakhs": 1, "lakh": 1, "lac": 1, "lacs": 1,
        "thousand": 0.01, "k": 0.01,
        "million": 10, "mn": 10,
        "billion": 10000, "bn": 10000,
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SCHEMA VERSION REGISTRY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SCHEMA_REGISTRY = {
    "1.0.0": {
        "required_fields": ["revenue", "net_worth", "total_debt",
                            "balance_sheet_date", "borrower_name", "pan"],
        "optional_fields": ["pat", "gstr_3b_sales", "gstr_2a_sales", "cin"],
        "release_note": "Initial schema for hackathon prototype.",
    },
    "2.0.0": {
        "required_fields": ["revenue", "net_worth", "total_debt",
                            "balance_sheet_date", "borrower_name", "pan"],
        "optional_fields": ["pat", "gstr_3b_sales", "gstr_2a_sales", "cin",
                            "other_comprehensive_income",
                            "total_comprehensive_income",
                            "preliminary_expenses",
                            "misc_expenditure"],
        "release_note": "Added Ind-AS/Old-AS indicators, DSCR, IQR outlier, "
                        "schema versioning, data lineage, raw snapshot.",
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SECTION 3: MODULE 1 - SCHEMA VALIDATOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class SchemaValidator:
    """Checks if required fields exist and detects unknown fields."""

    def __init__(self, config):
        self.schema = config.get("schema", {})

    def validate(self, record):
        errors = []

        # Check required fields
        for fname, fspec in self.schema.items():
            if fspec["criticality"] == "REQUIRED":
                raw = record.get(fname)
                if raw is None:
                    errors.append(ValidationFlag(
                        rule_id="SCHEMA_001",
                        field_name=fname,
                        description=f"Required field '{fname}' is missing",
                        severity=Severity.HIGH.value,
                    ))
                elif isinstance(raw, dict) and raw.get("value") is None:
                    errors.append(ValidationFlag(
                        rule_id="SCHEMA_002",
                        field_name=fname,
                        description=f"Required field '{fname}' has null value",
                        severity=Severity.HIGH.value,
                    ))

        # Check unknown fields
        skip = {"_metadata", "record_id"}
        for fname in record:
            if fname not in self.schema and fname not in skip:
                errors.append(ValidationFlag(
                    rule_id="SCHEMA_003",
                    field_name=fname,
                    description=f"Unknown field '{fname}' not in schema",
                    severity=Severity.LOW.value,
                ))

        is_valid = not any(e.auto_reject for e in errors)
        return is_valid, errors


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SECTION 4: MODULE 2a - OCR CHARACTER CORRECTOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class OCRCorrector:
    """Fixes visually similar character swaps like O to 0, S to 5."""

    CURRENCY_WORDS = frozenset([
        "cr", "crore", "crores", "lakhs", "lakh", "lac", "lacs",
        "thousand", "million", "mn", "billion", "bn", "inr",
        "rs", "rs.",
    ])

    def __init__(self, config):
        self.corrections = config.get("ocr_corrections", {})

    def correct_numeric_string(self, value, field_name):
        if not isinstance(value, str):
            return str(value), []

        original = value
        fixes = []

        tokens = re.split(r"(\s+)", value)
        corrected_tokens = []

        for token in tokens:
            # Skip currency words - dont correct them
            if token.strip().lower() in self.CURRENCY_WORDS:
                corrected_tokens.append(token)
                continue

            # Fix characters in numeric parts
            new_token = []
            for ch in token:
                if ch in self.corrections and not ch.isdigit():
                    replacement = self.corrections[ch]
                    new_token.append(replacement)
                    fixes.append(f"{ch}->{replacement}")
                else:
                    new_token.append(ch)
            corrected_tokens.append("".join(new_token))

        result = "".join(corrected_tokens)

        transforms = []
        if result != original:
            transforms.append(TransformationRecord(
                field_name=field_name,
                original_value=original,
                cleaned_value=result,
                rule_applied=f"OCR_CHAR_FIX: {', '.join(fixes)}",
                module="OCRCorrector",
                action=ActionTaken.AUTO_FIXED.value,
            ))

        return result, transforms


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SECTION 5: MODULE 2b - CURRENCY STANDARDIZER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class CurrencyStandardizer:
    """Converts any Indian currency format to float in Lakhs."""

    def __init__(self, config):
        self.multipliers = config.get("currency_multipliers", {})

    def standardize(self, value, field_name):
        if value is None:
            return None, []
        if isinstance(value, (int, float)):
            return float(value), []

        original = str(value).strip()
        if not original:
            return None, []

        cleaned = original

        # Remove currency symbols
        for sym in ("₹", "INR", "Rs.", "Rs"):
            cleaned = cleaned.replace(sym, "")
        cleaned = cleaned.strip()

        # Detect currency unit
        multiplier = 1.0
        detected_unit = None

        for unit in sorted(self.multipliers, key=lambda u: -len(u)):
            if unit.lower() in cleaned.lower():
                multiplier = self.multipliers[unit]
                detected_unit = unit
                cleaned = re.sub(
                    re.escape(unit), "", cleaned, flags=re.IGNORECASE
                ).strip()
                break

        # Remove Indian and Western commas
        cleaned = cleaned.replace(",", "")

        # Keep only digits, dot, minus
        cleaned = re.sub(r"[^\d.\-]", "", cleaned)

        if not cleaned or cleaned in (".", "-", "-."):
            return None, [TransformationRecord(
                field_name=field_name,
                original_value=original,
                cleaned_value=None,
                rule_applied="CURRENCY_PARSE_FAILED",
                module="CurrencyStandardizer",
                action=ActionTaken.FLAGGED_FOR_REVIEW.value,
            )]

        try:
            numeric = float(cleaned)
        except ValueError:
            return None, [TransformationRecord(
                field_name=field_name,
                original_value=original,
                cleaned_value=None,
                rule_applied="CURRENCY_FLOAT_CONVERSION_FAILED",
                module="CurrencyStandardizer",
                action=ActionTaken.FLAGGED_FOR_REVIEW.value,
            )]

        # Apply unit multiplier
        if detected_unit:
            result = numeric * multiplier
        else:
            # Large raw numbers are probably in actual rupees
            if abs(numeric) > 100000:
                result = numeric / 100000
            else:
                result = numeric

        result = round(result, 4)

        return result, [TransformationRecord(
            field_name=field_name,
            original_value=original,
            cleaned_value=result,
            rule_applied=(
                f"CURRENCY->LAKHS: '{original}' -> {result}L "
                f"(unit={detected_unit or 'raw'}, x{multiplier})"
            ),
            module="CurrencyStandardizer",
            action=ActionTaken.AUTO_FIXED.value,
        )]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SECTION 6: MODULE 2c - DATE NORMALIZER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class DateNormalizer:
    """Parses any date format to DD-MMM-YYYY and detects Financial Year."""

    FORMATS = [
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
        "%Y-%m-%d", "%Y/%m/%d",
        "%d %b %Y", "%d-%b-%Y", "%d %B %Y",
        "%d %b %y", "%d-%b-%y",
        "%B %d, %Y", "%b %d, %Y",
    ]

    def __init__(self, config):
        self.target_fmt = config.get("target_date_format", "%d-%b-%Y")
        self.max_age = config.get("max_data_age_days", 548)

    def normalize(self, value, field_name):
        if value is None:
            return None, [], []

        original = str(value).strip()
        if not original:
            return None, [], []

        # Try each known format
        parsed = None
        for fmt in self.FORMATS:
            try:
                parsed = datetime.strptime(original, fmt)
                if parsed.year > 2050:
                    parsed = parsed.replace(year=parsed.year - 100)
                break
            except ValueError:
                continue

        # If no format worked
        if parsed is None:
            return (
                None,
                [TransformationRecord(
                    field_name=field_name,
                    original_value=original,
                    cleaned_value=None,
                    rule_applied="DATE_PARSE_FAILED",
                    module="DateNormalizer",
                    action=ActionTaken.FLAGGED_FOR_REVIEW.value,
                )],
                [ValidationFlag(
                    rule_id="DATE_001",
                    field_name=field_name,
                    description=f"Cannot parse date: '{original}'",
                    severity=Severity.HIGH.value,
                )],
            )

        formatted = parsed.strftime(self.target_fmt)

        transforms = [TransformationRecord(
            field_name=field_name,
            original_value=original,
            cleaned_value=formatted,
            rule_applied=f"DATE_NORM: '{original}' -> '{formatted}'",
            module="DateNormalizer",
            action=ActionTaken.AUTO_FIXED.value,
        )]

        flags = []

        # Check data freshness
        age = (datetime.now() - parsed).days
        if age > self.max_age:
            flags.append(ValidationFlag(
                rule_id="DATE_002",
                field_name=field_name,
                description=f"Data is {age} days old (limit {self.max_age}d)",
                severity=Severity.MEDIUM.value,
                current_value=formatted,
            ))

        # Detect Financial Year for balance sheet
        if field_name == "balance_sheet_date":
            fy = self._detect_fy(parsed)
            transforms.append(TransformationRecord(
                field_name="financial_year",
                original_value=None,
                cleaned_value=fy,
                rule_applied=f"FY_DERIVED: {fy}",
                module="DateNormalizer",
                action=ActionTaken.AUTO_FIXED.value,
            ))

        return formatted, transforms, flags

    @staticmethod
    def _detect_fy(dt):
        """Indian FY: April to March."""
        if dt.month >= 4:
            return f"FY{dt.year}-{str(dt.year + 1)[-2:]}"
        return f"FY{dt.year - 1}-{str(dt.year)[-2:]}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SECTION 7: MODULE 2d - IND-AS vs OLD-AS FORMAT DETECTOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class IndASDetector:
    """Detects whether financial data follows Ind-AS or Old-AS conventions.

    Uses field-name heuristics: if input record contains known Ind-AS
    indicator fields (e.g. other_comprehensive_income, right_of_use_asset)
    it is classified as Ind-AS. Similarly for Old-AS indicators
    (e.g. preliminary_expenses, proposed_dividend).
    """

    def __init__(self, config):
        self.ind_as = set(config.get("ind_as_indicators", []))
        self.old_as = set(config.get("old_as_indicators", []))

    def detect(self, record):
        """Scan record keys for accounting standard indicators.

        Returns:
            result (dict): accounting_standard, ind_as_found, old_as_found
            transforms (list): TransformationRecord entries
            flags (list): ValidationFlag entries
        """
        record_keys = set(record.keys())

        ind_found = sorted(record_keys & self.ind_as)
        old_found = sorted(record_keys & self.old_as)

        if ind_found and old_found:
            standard = "MIXED"
        elif ind_found:
            standard = "Ind-AS"
        elif old_found:
            standard = "Old-AS"
        else:
            standard = "UNKNOWN"

        result = {
            "accounting_standard": standard,
            "ind_as_indicators_found": ind_found,
            "old_as_indicators_found": old_found,
        }

        transforms = [TransformationRecord(
            field_name="accounting_standard",
            original_value=None,
            cleaned_value=standard,
            rule_applied=(
                f"INDAS_DETECT: {standard} "
                f"(ind={len(ind_found)}, old={len(old_found)})"
            ),
            module="IndASDetector",
            action=ActionTaken.AUTO_FIXED.value,
        )]

        flags = []

        if standard == "MIXED":
            flags.append(ValidationFlag(
                rule_id="INDAS_001",
                field_name="accounting_standard",
                description=(
                    f"Mixed accounting indicators: "
                    f"Ind-AS={ind_found}, Old-AS={old_found}"
                ),
                severity=Severity.HIGH.value,
            ))

        if standard == "UNKNOWN":
            flags.append(ValidationFlag(
                rule_id="INDAS_002",
                field_name="accounting_standard",
                description="Could not determine accounting standard",
                severity=Severity.LOW.value,
            ))

        return result, transforms, flags


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SECTION 8: MODULE 2e - SCHEMA VERSION CONTROL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class SchemaVersionControl:
    """Validates and tracks schema versions.

    Checks whether incoming records declare a schema_version and
    whether it matches the current pipeline schema. Logs migrations
    and incompatibilities.
    """

    def __init__(self, config):
        self.current_version = config.get("schema_version", "2.0.0")
        self.registry = SCHEMA_REGISTRY

    def validate(self, record):
        """Check schema version compatibility.

        Returns:
            version_info (dict): current_version, record_version, compatible
            transforms (list): TransformationRecord entries
            flags (list): ValidationFlag entries
        """
        transforms = []
        flags = []

        # Check if record declares a version
        meta = record.get("_metadata", {})
        record_version = meta.get("schema_version") if isinstance(meta, dict) else None

        compatible = True

        if record_version is None:
            # No version declared — assume compatible but log it
            transforms.append(TransformationRecord(
                field_name="schema_version",
                original_value=None,
                cleaned_value=self.current_version,
                rule_applied=(
                    f"SCHEMA_VER_ASSIGN: No version declared, "
                    f"assigned {self.current_version}"
                ),
                module="SchemaVersionControl",
                action=ActionTaken.AUTO_FIXED.value,
            ))
        elif record_version != self.current_version:
            compatible = record_version in self.registry
            transforms.append(TransformationRecord(
                field_name="schema_version",
                original_value=record_version,
                cleaned_value=self.current_version,
                rule_applied=(
                    f"SCHEMA_VER_MIGRATE: {record_version} -> "
                    f"{self.current_version}"
                ),
                module="SchemaVersionControl",
                action=ActionTaken.AUTO_FIXED.value,
            ))
            if not compatible:
                flags.append(ValidationFlag(
                    rule_id="SCHEMA_VER_001",
                    field_name="schema_version",
                    description=(
                        f"Unknown schema version '{record_version}' "
                        f"not in registry"
                    ),
                    severity=Severity.HIGH.value,
                ))
            else:
                flags.append(ValidationFlag(
                    rule_id="SCHEMA_VER_002",
                    field_name="schema_version",
                    description=(
                        f"Schema migration: {record_version} -> "
                        f"{self.current_version}"
                    ),
                    severity=Severity.LOW.value,
                ))
        else:
            transforms.append(TransformationRecord(
                field_name="schema_version",
                original_value=record_version,
                cleaned_value=record_version,
                rule_applied="SCHEMA_VER_OK: Version matches",
                module="SchemaVersionControl",
                action=ActionTaken.PASSED.value,
            ))

        version_info = {
            "current_schema_version": self.current_version,
            "record_schema_version": record_version,
            "compatible": compatible,
            "registry_versions": list(self.registry.keys()),
        }

        return version_info, transforms, flags


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SECTION 9: MODULE 3 - MISSING VALUE HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class MissingValueHandler:
    """Flags missing values based on field criticality."""

    def __init__(self, config):
        self.schema = config.get("schema", {})

    def handle(self, clean_data):
        transforms = []
        flags = []

        for fname, fspec in self.schema.items():
            val = clean_data.get(fname)
            is_missing = val is None or (isinstance(val, str) and not val.strip())

            clean_data[f"{fname}_missing"] = is_missing

            if is_missing:
                sev = (
                    Severity.HIGH.value
                    if fspec["criticality"] == "REQUIRED"
                    else Severity.MEDIUM.value
                )
                flags.append(ValidationFlag(
                    rule_id="MISSING_001",
                    field_name=fname,
                    description=f"Missing {fspec['criticality']} field '{fname}'",
                    severity=sev,
                    auto_reject=(fspec["criticality"] == "REQUIRED"),
                ))
                transforms.append(TransformationRecord(
                    field_name=fname,
                    original_value=None,
                    cleaned_value=None,
                    rule_applied=f"MISSING_FLAGGED ({fspec['criticality']})",
                    module="MissingValueHandler",
                    action=ActionTaken.FLAGGED_FOR_REVIEW.value,
                ))

        return clean_data, transforms, flags


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SECTION 10: MODULE 4 - OUTLIER DETECTOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class OutlierDetector:
    """Detects values outside expected domain ranges and IQR-based outliers."""

    def __init__(self, config):
        self.ranges = config.get("outlier_ranges", {})
        self.iqr_multiplier = config.get("iqr_multiplier", 1.5)

    def detect(self, clean_data):
        """Per-record domain range outlier detection."""
        flags = []

        for fname, bounds in self.ranges.items():
            val = clean_data.get(fname)
            if val is None or not isinstance(val, (int, float)):
                continue

            lo = bounds.get("min", float("-inf"))
            hi = bounds.get("max", float("inf"))

            # Range check
            if val < lo or val > hi:
                sev = (
                    Severity.HIGH.value
                    if abs(val) > hi * 10
                    else Severity.MEDIUM.value
                )
                flags.append(ValidationFlag(
                    rule_id="OUTLIER_001",
                    field_name=fname,
                    description=f"{val} outside [{lo}, {hi}] Lakhs",
                    severity=sev,
                    current_value=val,
                    expected_range=f"[{lo}, {hi}]",
                ))

            # Trailing zero check (possible extra zero from OCR)
            if val > 0 and val >= 1000:
                s = f"{val:.0f}"
                trailing_zeros = len(s) - len(s.rstrip("0"))
                if trailing_zeros >= 4:
                    flags.append(ValidationFlag(
                        rule_id="OUTLIER_002",
                        field_name=fname,
                        description=(
                            f"{val} has {trailing_zeros} trailing zeros "
                            f"- possible extra-zero OCR error"
                        ),
                        severity=Severity.LOW.value,
                        current_value=val,
                    ))

        return flags

    def detect_iqr(self, batch_clean_data):
        """IQR-based statistical outlier detection across a batch.

        Uses numpy to compute Q1, Q3, IQR for each numeric field
        across all records. Flags values outside [Q1 - k*IQR, Q3 + k*IQR].

        Args:
            batch_clean_data: list of clean_data dicts from batch processing.

        Returns:
            dict: {field_name: list of ValidationFlags}
        """
        if not batch_clean_data or len(batch_clean_data) < 3:
            return {}  # Need at least 3 records for meaningful IQR

        # Collect numeric field values
        numeric_fields = {}
        for idx, record in enumerate(batch_clean_data):
            for fname, val in record.items():
                if isinstance(val, (int, float)) and not fname.endswith("_missing"):
                    if fname not in numeric_fields:
                        numeric_fields[fname] = []
                    numeric_fields[fname].append((idx, val))

        iqr_flags = {}
        k = self.iqr_multiplier

        for fname, indexed_vals in numeric_fields.items():
            vals = np.array([v for _, v in indexed_vals])
            if len(vals) < 3:
                continue

            q1 = np.percentile(vals, 25)
            q3 = np.percentile(vals, 75)
            iqr = q3 - q1

            lower_bound = q1 - k * iqr
            upper_bound = q3 + k * iqr

            field_flags = []
            for idx, val in indexed_vals:
                if val < lower_bound or val > upper_bound:
                    field_flags.append(ValidationFlag(
                        rule_id="OUTLIER_IQR_001",
                        field_name=fname,
                        description=(
                            f"Record {idx}: {val} outside IQR bounds "
                            f"[{lower_bound:.2f}, {upper_bound:.2f}] "
                            f"(Q1={q1:.2f}, Q3={q3:.2f}, IQR={iqr:.2f})"
                        ),
                        severity=Severity.MEDIUM.value,
                        current_value=val,
                        expected_range=f"[{lower_bound:.2f}, {upper_bound:.2f}]",
                    ))

            if field_flags:
                iqr_flags[fname] = field_flags

        return iqr_flags


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SECTION 11: MODULE 5 - CROSS-FIELD CREDIT VALIDATOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class CrossFieldValidator:
    """Validates relationships between financial fields."""

    def __init__(self, config):
        self.de_warn = config.get("de_ratio_warning_threshold", 3.0)
        self.de_rej = config.get("de_ratio_reject_threshold", 10.0)
        self.gst_thr = config.get("gst_mismatch_threshold", 0.20)
        self.dscr_warn = config.get("dscr_warning_threshold", 1.5)
        self.dscr_rej = config.get("dscr_reject_threshold", 1.0)

    def validate(self, cd):
        derived = {}
        flags = []

        debt = cd.get("total_debt")
        nw = cd.get("net_worth")
        rev = cd.get("revenue")
        pat = cd.get("pat")
        g3b = cd.get("gstr_3b_sales")
        g2a = cd.get("gstr_2a_sales")

        # ── 1. Debt-to-Equity Ratio ──
        if debt is not None and nw is not None and nw != 0:
            de = round(debt / nw, 4)
            derived["de_ratio"] = de

            if nw < 0:
                flags.append(ValidationFlag(
                    rule_id="CREDIT_001",
                    field_name="net_worth",
                    description=f"Negative net worth ({nw}L) - capital erosion",
                    severity=Severity.CRITICAL.value,
                    current_value=nw,
                ))
                derived["high_leverage_flag"] = True

            elif de > self.de_rej:
                flags.append(ValidationFlag(
                    rule_id="CREDIT_002",
                    field_name="de_ratio",
                    description=f"D/E {de} > reject limit {self.de_rej}",
                    severity=Severity.CRITICAL.value,
                    current_value=de,
                    auto_reject=True,
                ))
                derived["high_leverage_flag"] = True

            elif de > self.de_warn:
                flags.append(ValidationFlag(
                    rule_id="CREDIT_003",
                    field_name="de_ratio",
                    description=f"D/E {de} > warning limit {self.de_warn}",
                    severity=Severity.HIGH.value,
                    current_value=de,
                ))
                derived["high_leverage_flag"] = True
            else:
                derived["high_leverage_flag"] = False
        else:
            derived["de_ratio"] = None
            derived["high_leverage_flag"] = None

        # ── 2. DSCR (Debt Service Coverage Ratio) Proxy ──
        # Best proxy without interest/principal breakdown:
        # DSCR ≈ PAT / Total Debt (annualised)
        if pat is not None and debt is not None and debt > 0:
            dscr = round(pat / debt, 4)
            derived["dscr_proxy"] = dscr

            if dscr < self.dscr_rej:
                flags.append(ValidationFlag(
                    rule_id="CREDIT_007",
                    field_name="dscr_proxy",
                    description=(
                        f"DSCR proxy {dscr} < reject limit "
                        f"{self.dscr_rej} - debt repayment at risk"
                    ),
                    severity=Severity.CRITICAL.value,
                    current_value=dscr,
                    auto_reject=False,
                ))
            elif dscr < self.dscr_warn:
                flags.append(ValidationFlag(
                    rule_id="CREDIT_008",
                    field_name="dscr_proxy",
                    description=(
                        f"DSCR proxy {dscr} < warning limit "
                        f"{self.dscr_warn}"
                    ),
                    severity=Severity.HIGH.value,
                    current_value=dscr,
                ))
        else:
            derived["dscr_proxy"] = None

        # ── 3. GST Mismatch ──
        if g3b and g2a and g3b > 0:
            mm = round(abs(g2a - g3b) / g3b, 4)
            derived["gst_mismatch_ratio"] = mm
            if mm > self.gst_thr:
                flags.append(ValidationFlag(
                    rule_id="CREDIT_004",
                    field_name="gst_mismatch",
                    description=(
                        f"GST mismatch {mm:.1%} > {self.gst_thr:.0%} "
                        f"(3B={g3b}L, 2A={g2a}L)"
                    ),
                    severity=Severity.HIGH.value,
                    current_value=mm,
                ))
        else:
            derived["gst_mismatch_ratio"] = None

        # ── 4. Revenue Sanity ──
        if rev is not None and rev <= 0:
            flags.append(ValidationFlag(
                rule_id="CREDIT_005",
                field_name="revenue",
                description=f"Revenue {rev}L <= 0",
                severity=Severity.HIGH.value,
                current_value=rev,
            ))

        # ── 5. Debt >= 0 Check ──
        if debt is not None and debt < 0:
            flags.append(ValidationFlag(
                rule_id="CREDIT_009",
                field_name="total_debt",
                description=f"Debt {debt}L < 0 (must be non-negative)",
                severity=Severity.HIGH.value,
                current_value=debt,
            ))

        # ── 6. Revenue vs GST Alignment ──
        if rev and g3b and rev > 0:
            ratio = round(g3b / rev, 4)
            derived["revenue_gst_alignment"] = ratio
            if ratio < 0.5 or ratio > 2.0:
                flags.append(ValidationFlag(
                    rule_id="CREDIT_006",
                    field_name="revenue_gst_alignment",
                    description=(
                        f"Revenue ({rev}L) vs GST ({g3b}L) "
                        f"ratio {ratio:.2f} outside 0.5-2.0"
                    ),
                    severity=Severity.MEDIUM.value,
                    current_value=ratio,
                ))
        else:
            derived["revenue_gst_alignment"] = None

        return derived, flags


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SECTION 10: MODULE 6 - CONFIDENCE EVALUATOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ConfidenceEvaluator:
    """Evaluates OCR confidence scores to decide fix vs review vs reject."""

    def __init__(self, config):
        self.auto_fix = config.get("confidence_auto_fix_threshold", 0.80)
        self.review = config.get("confidence_review_threshold", 0.75)
        self.reject = config.get("confidence_reject_threshold", 0.50)

    def evaluate(self, raw, schema):
        review_fields = []
        transforms = []

        for fname in schema:
            fd = raw.get(fname)
            if not isinstance(fd, dict):
                continue
            conf = fd.get("confidence")
            if conf is None:
                continue

            if conf < self.reject:
                review_fields.append(fname)
                transforms.append(TransformationRecord(
                    field_name=fname,
                    original_value=fd.get("value"),
                    cleaned_value=None,
                    rule_applied=f"CONF_REJECT: {conf} < {self.reject}",
                    module="ConfidenceEvaluator",
                    confidence=conf,
                    action=ActionTaken.REJECTED.value,
                ))
            elif conf < self.review:
                review_fields.append(fname)
                transforms.append(TransformationRecord(
                    field_name=fname,
                    original_value=fd.get("value"),
                    cleaned_value=fd.get("value"),
                    rule_applied=f"CONF_REVIEW: {conf} < {self.review}",
                    module="ConfidenceEvaluator",
                    confidence=conf,
                    action=ActionTaken.FLAGGED_FOR_REVIEW.value,
                ))

        return review_fields, transforms


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SECTION 11: MODULE 7 - FEATURE ENGINEER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class FeatureEngineer:
    """Generates ML-ready features from cleaned data."""

    def generate(self, cd, cross, review_fields, ind_as_result=None):

        rev = cd.get("revenue")
        nw = cd.get("net_worth")
        debt = cd.get("total_debt")
        pat = cd.get("pat")

        feat = {
            # Direct features
            "revenue_lakhs": rev,
            "net_worth_lakhs": nw,
            "debt_lakhs": debt,
            "pat_lakhs": pat,

            # Cross-field features
            "de_ratio": cross.get("de_ratio"),
            "dscr_proxy": cross.get("dscr_proxy"),
            "gst_mismatch_ratio": cross.get("gst_mismatch_ratio"),
            "high_leverage_flag": cross.get("high_leverage_flag"),
            "revenue_gst_alignment": cross.get("revenue_gst_alignment"),
        }

        # PAT to Debt ratio
        if pat is not None and debt and debt > 0:
            feat["pat_to_debt_ratio"] = round(pat / debt, 4)
        else:
            feat["pat_to_debt_ratio"] = None

        # Return on Net Worth
        if pat is not None and nw and nw > 0:
            feat["return_on_net_worth"] = round(pat / nw, 4)
        else:
            feat["return_on_net_worth"] = None

        # Profitability flag
        if pat is not None:
            feat["is_profitable"] = pat > 0
        else:
            feat["is_profitable"] = None

        # Accounting standard (from IndASDetector)
        if ind_as_result:
            feat["accounting_standard"] = ind_as_result.get(
                "accounting_standard", "UNKNOWN"
            )
        else:
            feat["accounting_standard"] = "UNKNOWN"

        # Data quality features for ML
        feat["review_required_flag"] = len(review_fields) > 0
        feat["fields_needing_review"] = review_fields
        feat["missing_field_count"] = sum(
            1 for k, v in cd.items()
            if k.endswith("_missing") and v is True
        )

        return feat


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SECTION 14: MAIN PIPELINE ORCHESTRATOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class DataCleaningPipeline:
    """
    Main orchestrator - runs all modules in sequence.

    Pipeline Order:
    Schema Version → Schema → Confidence → Ind-AS → OCR Fix →
    Currency → Dates → Missing → Outliers → Cross-Field →
    Features → Report
    """

    def __init__(self, config=None):
        self.config = config or DEFAULT_CONFIG
        self.version = self.config["pipeline_version"]

        # Deterministic timestamp: use config value or current time
        ts = self.config.get("processing_timestamp")
        self._processing_ts = ts or datetime.now().isoformat()

        # Initialize all modules
        self.schema_ver = SchemaVersionControl(self.config)
        self.schema_val = SchemaValidator(self.config)
        self.ocr_fix = OCRCorrector(self.config)
        self.curr_std = CurrencyStandardizer(self.config)
        self.date_norm = DateNormalizer(self.config)
        self.ind_as = IndASDetector(self.config)
        self.miss_hnd = MissingValueHandler(self.config)
        self.out_det = OutlierDetector(self.config)
        self.xfield = CrossFieldValidator(self.config)
        self.conf_eval = ConfidenceEvaluator(self.config)
        self.feat_eng = FeatureEngineer()

        self.log = logging.getLogger("IntelliCredit.Cleaning")

    def process_single(self, raw):
        """Process one OCR record through full pipeline."""

        all_tx = []    # all transformations
        all_fl = []    # all flags
        clean = {}     # cleaned data

        # ── RAW SNAPSHOT (Audit: Raw + Cleaned Data) ──
        raw_snapshot = copy.deepcopy(raw)

        # Extract source document for lineage tracking
        src_doc = None
        if isinstance(raw.get("_metadata"), dict):
            src_doc = raw["_metadata"].get("source_document")

        self.log.info("Pipeline v%s - start", self.version)

        # ── STEP 0: Schema Version Control ──
        ver_info, ver_tx, ver_fl = self.schema_ver.validate(raw)
        for t in ver_tx:
            t.source_document = src_doc
            t.timestamp = self._processing_ts
        all_tx.extend(ver_tx)
        all_fl.extend(ver_fl)

        # ── STEP 1: Schema Validation ──
        _, schema_fl = self.schema_val.validate(raw)
        all_fl.extend(schema_fl)

        # ── STEP 2: Confidence Evaluation ──
        review_flds, conf_tx = self.conf_eval.evaluate(
            raw, self.config["schema"]
        )
        for t in conf_tx:
            t.source_document = src_doc
            t.timestamp = self._processing_ts
        all_tx.extend(conf_tx)

        # ── STEP 3: Ind-AS vs Old-AS Detection ──
        ind_as_result, ind_tx, ind_fl = self.ind_as.detect(raw)
        for t in ind_tx:
            t.source_document = src_doc
            t.timestamp = self._processing_ts
        all_tx.extend(ind_tx)
        all_fl.extend(ind_fl)
        clean["accounting_standard"] = ind_as_result.get(
            "accounting_standard", "UNKNOWN"
        )

        # ── STEP 4: Field-by-Field Cleaning ──
        schema = self.config["schema"]

        for fname, fspec in schema.items():
            fd = raw.get(fname)

            if fd is None:
                clean[fname] = None
                continue

            # Unwrap OCR envelope {value, confidence, source_page}
            if isinstance(fd, dict):
                rv = fd.get("value")
                conf = fd.get("confidence")
                page = fd.get("source_page")
            else:
                rv, conf, page = fd, None, None

            if rv is None:
                clean[fname] = None
                continue

            ftype = fspec.get("type", "string")

            # ── 4a: OCR Character Fix (numeric fields only) ──
            if ftype in ("currency", "numeric"):
                rv, ocr_tx = self.ocr_fix.correct_numeric_string(str(rv), fname)
                for t in ocr_tx:
                    t.source_page = page
                    t.source_document = src_doc
                    t.confidence = conf
                    t.timestamp = self._processing_ts
                all_tx.extend(ocr_tx)

            # ── 4b: Type-Specific Standardization ──
            if ftype == "currency":
                std, cur_tx = self.curr_std.standardize(rv, fname)
                for t in cur_tx:
                    t.source_page = page
                    t.source_document = src_doc
                    t.confidence = conf
                    t.timestamp = self._processing_ts
                all_tx.extend(cur_tx)

                # Block negative values where not allowed
                if (
                    std is not None
                    and not fspec.get("allow_negative", False)
                    and std < 0
                ):
                    all_fl.append(ValidationFlag(
                        rule_id="SIGN_001",
                        field_name=fname,
                        description=f"Negative {std} in non-negative field",
                        severity=Severity.MEDIUM.value,
                        current_value=std,
                    ))
                    std = abs(std)

                clean[fname] = std

            elif ftype == "date":
                norm, dt_tx, dt_fl = self.date_norm.normalize(rv, fname)
                for t in dt_tx:
                    t.source_page = page
                    t.source_document = src_doc
                    t.confidence = conf
                    t.timestamp = self._processing_ts
                all_tx.extend(dt_tx)
                all_fl.extend(dt_fl)
                clean[fname] = norm

                # Extract Financial Year if detected
                fy_rec = next(
                    (t for t in dt_tx if t.field_name == "financial_year"),
                    None,
                )
                if fy_rec:
                    clean["financial_year"] = fy_rec.cleaned_value

            elif ftype == "pattern":
                pat = fspec.get("pattern", "")
                if pat and not re.match(pat, str(rv)):
                    all_fl.append(ValidationFlag(
                        rule_id="PATTERN_001",
                        field_name=fname,
                        description=f"'{rv}' fails pattern {pat}",
                        severity=Severity.MEDIUM.value,
                        current_value=rv,
                    ))
                clean[fname] = str(rv).strip()

            else:  # string type
                clean[fname] = str(rv).strip()

        # ── STEP 5: Missing Value Handling ──
        clean, miss_tx, miss_fl = self.miss_hnd.handle(clean)
        for t in miss_tx:
            t.source_document = src_doc
            t.timestamp = self._processing_ts
        all_tx.extend(miss_tx)
        all_fl.extend(miss_fl)

        # ── STEP 6: Outlier Detection (domain ranges) ──
        out_fl = self.out_det.detect(clean)
        all_fl.extend(out_fl)

        # ── STEP 7: Cross-Field Credit Validation ──
        xder, xfl = self.xfield.validate(clean)
        all_fl.extend(xfl)

        # ── STEP 8: Feature Engineering ──
        features = self.feat_eng.generate(
            clean, xder, review_flds, ind_as_result
        )

        # ── STEP 9: Generate Report ──
        report = self._build_report(all_fl, all_tx, review_flds)

        # ── BUILD FINAL OUTPUT ──
        output = {
            "clean_data": {
                k: v for k, v in clean.items()
                if not k.endswith("_missing")
            },
            "derived_features": features,
            "validation_report": report,
            "transformation_log": [asdict(t) for t in all_tx],
            "raw_snapshot": raw_snapshot,
            "_metadata": {
                "pipeline_version": self.version,
                "schema_version": ver_info.get("current_schema_version"),
                "processed_at": self._processing_ts,
                "record_hash": self._hash(raw),
                "source_document": src_doc,
                "accounting_standard": ind_as_result.get(
                    "accounting_standard", "UNKNOWN"
                ),
                "total_transformations": len(all_tx),
                "total_flags": len(all_fl),
            },
        }

        self.log.info(
            "Done - %d transforms, %d flags",
            len(all_tx), len(all_fl),
        )
        return output

    def process_batch(self, records):
        """Process multiple records with error isolation + IQR outlier detection."""
        results = []

        for idx, rec in enumerate(records):
            try:
                out = self.process_single(rec)
                out["_metadata"]["batch_index"] = idx
                results.append(out)
            except Exception as exc:
                self.log.error("Record %d failed: %s", idx, exc)
                results.append({
                    "clean_data": {},
                    "derived_features": {},
                    "validation_report": {
                        "pipeline_error": str(exc),
                        "review_required": True,
                        "auto_reject": True,
                    },
                    "transformation_log": [],
                    "raw_snapshot": rec,
                    "_metadata": {
                        "pipeline_version": self.version,
                        "schema_version": self.config.get("schema_version"),
                        "processed_at": self._processing_ts,
                        "batch_index": idx,
                        "processing_error": True,
                    },
                })

        # ── IQR Outlier Detection (batch-level statistical analysis) ──
        batch_clean = [r["clean_data"] for r in results if r["clean_data"]]
        iqr_flags = self.out_det.detect_iqr(batch_clean)

        if iqr_flags:
            # Attach IQR flags to batch metadata
            iqr_summary = {
                field: [asdict(f) for f in flags]
                for field, flags in iqr_flags.items()
            }
            for res in results:
                res["_metadata"]["iqr_outlier_flags"] = iqr_summary

        return results

    def to_dataframe(self, results):
        """Convert batch results to a pandas DataFrame for ML consumption.

        Flattens clean_data and derived_features into a single DataFrame
        row per record, suitable for XGBoost / SHAP pipelines.
        """
        rows = []
        for res in results:
            row = {}
            row.update(res.get("clean_data", {}))
            row.update(res.get("derived_features", {}))
            # Add metadata columns
            meta = res.get("_metadata", {})
            row["_batch_index"] = meta.get("batch_index")
            row["_review_required"] = res.get(
                "validation_report", {}
            ).get("review_required", False)
            row["_auto_reject"] = res.get(
                "validation_report", {}
            ).get("auto_reject", False)
            rows.append(row)

        df = pd.DataFrame(rows)
        return df

    def _build_report(self, flags, txs, review):
        """Generate validation summary report."""

        auto = [
            asdict(t) for t in txs
            if t.action == ActionTaken.AUTO_FIXED.value
        ]
        flagged = [
            asdict(t) for t in txs
            if t.action == ActionTaken.FLAGGED_FOR_REVIEW.value
        ]

        return {
            "auto_fixed_count": len(auto),
            "auto_fixed_fields": auto,
            "flagged_for_review_count": len(flagged),
            "flagged_for_review_fields": flagged,
            "risk_flags": [asdict(f) for f in flags],
            "risk_flag_count": len(flags),
            "schema_errors": [
                asdict(f) for f in flags
                if f.rule_id.startswith("SCHEMA")
            ],
            "review_required": (
                len(review) > 0
                or any(f.severity == Severity.CRITICAL.value for f in flags)
            ),
            "auto_reject": any(f.auto_reject for f in flags),
            "review_fields": review,
            "severity_summary": {
                s.value: sum(1 for f in flags if f.severity == s.value)
                for s in Severity
            },
        }

    @staticmethod
    def _hash(record):
        blob = json.dumps(record, sort_keys=True, default=str)
        return hashlib.md5(blob.encode()).hexdigest()
