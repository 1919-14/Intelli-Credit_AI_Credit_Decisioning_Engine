"""
Block D1–D2: MCA21 ROC & Director DIN Checks
Tavily (fetch) + Groq (classify)
"""
import os
import json
from typing import Dict, Any
from layer4.research.tavily_client import TavilySearchClient


def _call_groq(prompt: str, content: str) -> dict:
    try:
        from groq import Groq
        from utils_keys import get_rotated_groq_key
        client = Groq(api_key=get_rotated_groq_key())
        resp = client.chat.completions.create(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": content}
            ],
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            response_format={"type": "json_object"}
        )
        raw = resp.choices[0].message.content
        return json.loads(raw.replace("```json", "").replace("```", "").strip())
    except Exception as e:
        print(f"  ⚠ Groq error: {e}")
        return {}


def run_mca_checks(data: Dict[str, Any]) -> Dict[str, Any]:
    """D1+D2: MCA company status, charges, and director DIN checks."""
    ids = data.get("company_identifiers", {})
    company = ids.get("company_name", "")
    cin = ids.get("cin", "")
    promoter = ids.get("promoter_name", "")
    din = ids.get("din", "")

    if not company and not cin:
        data["mca_checks"] = {
            "company_status": "Unknown", "mca_charge_count": 0,
            "mca_compliance_flag": 1, "promoter_din_score": 1.0,
            "management_stability_score": 0.5,
            "alerts": [{"alert_id": "D-SKIP", "type": "DATA_MISSING",
                        "severity": "INFO", "description": "No CIN/company for MCA check"}]
        }
        return data

    tavily = TavilySearchClient()
    queries = [
        f"{cin or company} MCA ROC charges company status India",
        f"{company} Tofler Zauba company details charges",
        f"{din or promoter} director disqualified MCA21 section 164",
        f"{promoter or company} director DIN status active"
    ]

    all_results = tavily.search_batch(queries, max_results=3)
    combined = ""
    snippets = []
    for q, results in all_results.items():
        for r in results:
            combined += f"Query: {q}\nTitle: {r['title']}\nURL: {r['url']}\n{r['content']}\n\n"
            snippets.append({"query": q, "title": r["title"], "url": r["url"], "content": r["content"][:200]})

    prompt = f"""You are an Indian company law analyst. Analyse the following search results about {company} (CIN: {cin}).
Return JSON:
{{
  "company_status": "Active" or "Struck Off" or "Under Liquidation" or "Unknown",
  "mca_charge_count": number of unsatisfied charges (integer),
  "roc_filings_current": true/false (are annual filings up to date),
  "recent_charges": [{{"lender": "...", "amount_lakhs": N, "status": "satisfied/open"}}],
  "directors": [
    {{"name": "...", "din": "...", "status": "Active/Disqualified/Surrendered",
     "disqualification_reason": null or "reason"}}
  ],
  "summary": "2-3 sentence summary of MCA findings"
}}
If data is not found, provide reasonable defaults (status=Active, charge_count=0)."""

    result = _call_groq(prompt, combined[:3000]) if combined.strip() else {}

    # Compute scores
    company_status = result.get("company_status", "Active")
    charge_count = result.get("mca_charge_count", 0) or 0
    roc_current = result.get("roc_filings_current", True)

    directors = result.get("directors", [])
    active_dins = sum(1 for d in directors if d.get("status", "Active") == "Active")
    total_dins = max(len(directors), 1)
    din_score = round(active_dins / total_dins, 2)

    disqualified = any(d.get("status", "").lower() == "disqualified" for d in directors)
    struck_off_assoc = any("struck" in (d.get("disqualification_reason", "") or "").lower() for d in directors)

    stability = 1.0
    if disqualified:
        stability -= 0.4
    if struck_off_assoc:
        stability -= 0.2
    if not roc_current:
        stability -= 0.1

    alerts = []
    if company_status != "Active":
        alerts.append({"alert_id": "D1-001", "type": "COMPANY_NOT_ACTIVE",
                        "severity": "RED", "description": f"Company status: {company_status}",
                        "score_penalty": -25, "source": "MCA21 company check"})
    if not roc_current:
        alerts.append({"alert_id": "D1-002", "type": "ROC_NON_COMPLIANT",
                        "severity": "AMBER", "description": "ROC filings not current",
                        "score_penalty": -5, "source": "MCA21 filing check"})
    if charge_count > 5:
        alerts.append({"alert_id": "D1-003", "type": "HIGH_CHARGES",
                        "severity": "AMBER", "description": f"{charge_count} unsatisfied charges",
                        "score_penalty": -4, "source": "MCA21 charge registry"})
    if disqualified:
        alerts.append({"alert_id": "D2-001", "type": "DIRECTOR_DISQUALIFIED",
                        "severity": "RED", "description": "Director disqualified under Section 164",
                        "score_penalty": -15, "source": "MCA21 DIN check"})
    if struck_off_assoc:
        alerts.append({"alert_id": "D2-002", "type": "STRUCK_OFF_ASSOC",
                        "severity": "AMBER", "description": "Director associated with struck-off company",
                        "score_penalty": -5, "source": "MCA21 DIN check"})

    if not alerts:
        alerts.append({"alert_id": "D-001", "type": "MCA_CLEAN",
                        "severity": "GREEN", "description": "MCA records clean",
                        "score_penalty": 0, "source": "MCA21 checks"})

    result["mca_compliance_flag"] = 1 if roc_current else 0
    result["promoter_din_score"] = din_score
    result["management_stability_score"] = round(max(stability, 0), 2)
    result["alerts"] = alerts
    result["raw_snippets"] = snippets
    data["mca_checks"] = result
    return data
