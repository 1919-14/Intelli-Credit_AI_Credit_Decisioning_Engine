"""
Block E1: Mock CIBIL Commercial Provider
Simulated — real CIBIL requires TransUnion agreement.
"""
from typing import Dict, Any
import hashlib


# Pre-populated lookup table for test companies
_MOCK_DATA = {
    "default": {
        "cibil_rank": "CMR-5",
        "cibil_score": 650,
        "cibil_rank_score": 0.55,
        "total_live_facilities": 3,
        "overdue_accounts": 0,
        "npa_flag": 0,
        "dpd_30_plus": 1,
        "dpd_60_plus": 0,
        "dpd_90_plus": 0,
        "dpd_flag": 1,
        "enquiry_count_6m": 3,
        "multiple_enquiries_flag": 0,
        "credit_history_months": 48,
        "highest_dpd_days": 27,
        "total_outstanding_lakhs": 245,
        "summary": "Moderate credit profile — CMR-5 rank, 1 instance of DPD <30 days, 3 live facilities, no NPA."
    },
    "good": {
        "cibil_rank": "CMR-3",
        "cibil_score": 750,
        "cibil_rank_score": 0.80,
        "total_live_facilities": 5,
        "overdue_accounts": 0,
        "npa_flag": 0,
        "dpd_30_plus": 0,
        "dpd_60_plus": 0,
        "dpd_90_plus": 0,
        "dpd_flag": 0,
        "enquiry_count_6m": 1,
        "multiple_enquiries_flag": 0,
        "credit_history_months": 72,
        "highest_dpd_days": 0,
        "total_outstanding_lakhs": 180,
        "summary": "Strong credit profile — CMR-3 rank, clean repayment history, no DPD."
    },
    "risky": {
        "cibil_rank": "CMR-7",
        "cibil_score": 520,
        "cibil_rank_score": 0.30,
        "total_live_facilities": 6,
        "overdue_accounts": 2,
        "npa_flag": 1,
        "dpd_30_plus": 3,
        "dpd_60_plus": 1,
        "dpd_90_plus": 1,
        "dpd_flag": 1,
        "enquiry_count_6m": 7,
        "multiple_enquiries_flag": 1,
        "credit_history_months": 24,
        "highest_dpd_days": 120,
        "total_outstanding_lakhs": 520,
        "summary": "High-risk profile — CMR-7 rank, 2 overdue accounts including 1 NPA, DPD 90+ days, 7 credit enquiries in 6 months."
    }
}


class MockCIBILProvider:
    """Simulated CIBIL Commercial Pull. Returns synthetic data."""

    def pull_report(self, pan_or_gstin: str = "", company_name: str = "") -> Dict[str, Any]:
        """
        Returns a mock CIBIL report.
        Uses hash of identifier to deterministically pick a profile variant.
        """
        identifier = (pan_or_gstin or company_name or "unknown").lower().strip()
        # Deterministic variant based on hash
        hash_val = int(hashlib.md5(identifier.encode()).hexdigest(), 16)
        variants = ["default", "good", "risky"]
        variant = variants[hash_val % len(variants)]

        report = dict(_MOCK_DATA[variant])
        report["simulated"] = True
        report["disclaimer"] = "⚠ SIMULATED — Real CIBIL Commercial requires TransUnion CIBIL data-sharing agreement"
        report["query_identifier"] = pan_or_gstin or company_name

        # Generate alerts
        alerts = []
        if report["npa_flag"]:
            alerts.append({"alert_id": "E1-001", "type": "NPA_ACCOUNT",
                            "severity": "RED", "description": "NPA/written-off account detected (SIMULATED)",
                            "score_penalty": -20, "source": "CIBIL Commercial (mock)"})
        if report["dpd_flag"]:
            alerts.append({"alert_id": "E1-002", "type": "DPD_30_PLUS",
                            "severity": "AMBER", "description": f"DPD 30+ days detected — {report['highest_dpd_days']} days highest (SIMULATED)",
                            "score_penalty": -5, "source": "CIBIL Commercial (mock)"})
        if report["multiple_enquiries_flag"]:
            alerts.append({"alert_id": "E1-003", "type": "MULTIPLE_ENQUIRIES",
                            "severity": "AMBER", "description": f"{report['enquiry_count_6m']} enquiries in 6 months (SIMULATED)",
                            "score_penalty": -3, "source": "CIBIL Commercial (mock)"})
        if not alerts:
            alerts.append({"alert_id": "E1-004", "type": "CIBIL_CLEAN",
                            "severity": "GREEN", "description": "Clean credit bureau record (SIMULATED)",
                            "score_penalty": 0, "source": "CIBIL Commercial (mock)"})

        report["alerts"] = alerts
        return report


def run_cibil_mock(data: Dict[str, Any]) -> Dict[str, Any]:
    """E1: Mock CIBIL pull. Entry point for LangChain."""
    ids = data.get("company_identifiers", {})
    pan = ids.get("pan_number", "") or ids.get("pan", "")
    gstin = ids.get("gstin", "")
    company = ids.get("company_name", "")

    provider = MockCIBILProvider()
    report = provider.pull_report(pan_or_gstin=pan or gstin, company_name=company)

    data["cibil"] = report
    return data
