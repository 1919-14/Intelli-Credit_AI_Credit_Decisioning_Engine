"""
Block C2: eCourts Litigation History Lookup
Tavily (fetch) + Groq (classify)
"""
import os
import json
from typing import Dict, Any
from layer4.research.tavily_client import TavilySearchClient


def _call_groq_classify(prompt: str, content: str) -> dict:
    try:
        from groq import Groq
        client = Groq(api_key=os.getenv("API_KEY", ""))
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
        print(f"  ⚠ Groq classify error: {e}")
        return {}


def run_litigation_check(data: Dict[str, Any]) -> Dict[str, Any]:
    """C2: Search for litigation history."""
    ids = data.get("company_identifiers", {})
    company = ids.get("company_name", "")
    promoter = ids.get("promoter_name", "")
    cin = ids.get("cin", "")
    din = ids.get("din", "")

    if not company and not promoter:
        data["litigation"] = {
            "litigation_count": 0, "promoter_litigation_count": 0,
            "litigation_risk": "Low", "cases": [],
            "alerts": [{"alert_id": "C2-SKIP", "type": "DATA_MISSING",
                        "severity": "INFO", "description": "No company/promoter name for litigation check"}]
        }
        return data

    tavily = TavilySearchClient()
    queries = [
        f"{company} case eCourts India High Court",
        f"{promoter or company} NCLT IBC insolvency proceedings",
        f"{cin or company} recovery suit bank DRT tribunal"
    ]

    all_results = tavily.search_batch(queries, max_results=3)
    combined = ""
    snippets = []
    for q, results in all_results.items():
        for r in results:
            combined += f"Query: {q}\nTitle: {r['title']}\nURL: {r['url']}\nContent: {r['content']}\n\n"
            snippets.append({"query": q, "title": r["title"], "url": r["url"], "content": r["content"][:200]})

    if not combined.strip():
        data["litigation"] = {
            "litigation_count": 0, "promoter_litigation_count": 0,
            "litigation_risk": "Low", "cases": [],
            "total_exposure_lakhs": 0, "searches_performed": len(queries),
            "summary": "No litigation records found",
            "alerts": [{"alert_id": "C2-001", "type": "NO_LITIGATION",
                        "severity": "GREEN", "description": "No litigation records found",
                        "score_penalty": 0, "source": "eCourts search"}]
        }
        return data

    prompt = """You are an Indian legal analyst. Classify the following search results about a company/promoter's legal history.
Return JSON:
{
  "litigation_count": total active cases (integer),
  "promoter_litigation_count": cases involving promoter personally (integer),
  "litigation_risk": "High" or "Moderate" or "Low",
  "total_exposure_lakhs": estimated total exposure in lakhs (number),
  "cases": [
    {"case_type": "criminal/civil/recovery/NCLT", "severity": "High/Medium/Low",
     "case_status": "pending/disposed/appeal", "summary": "1-line", "source_url": "..."}
  ],
  "summary": "2-3 line overall summary"
}
If no relevant cases found, set litigation_count=0, litigation_risk="Low"."""

    result = _call_groq_classify(prompt, combined[:3000])

    alerts = []
    risk = result.get("litigation_risk", "Low")
    nclt_pending = any(c.get("case_type", "").upper() == "NCLT" and c.get("case_status", "").lower() == "pending"
                       for c in result.get("cases", []))
    drt_high = result.get("total_exposure_lakhs", 0) or 0

    if nclt_pending:
        alerts.append({"alert_id": "C2-002", "type": "NCLT_PENDING",
                        "severity": "RED", "description": "NCLT/IBC case pending — hard rule trigger",
                        "score_penalty": -20, "source": "eCourts litigation search"})
    elif drt_high > 50:
        alerts.append({"alert_id": "C2-003", "type": "DRT_RECOVERY",
                        "severity": "RED", "description": f"DRT recovery exposure ₹{drt_high:.0f}L",
                        "score_penalty": -10, "source": "eCourts litigation search"})
    elif risk == "Moderate":
        alerts.append({"alert_id": "C2-004", "type": "MULTIPLE_CASES",
                        "severity": "AMBER", "description": f"{result.get('litigation_count', 0)} active cases",
                        "score_penalty": -5, "source": "eCourts litigation search"})
    else:
        alerts.append({"alert_id": "C2-005", "type": "CLEAN_LITIGATION",
                        "severity": "GREEN", "description": "No significant litigation",
                        "score_penalty": 0, "source": "eCourts litigation search"})

    result["alerts"] = alerts
    result["raw_snippets"] = snippets
    result["searches_performed"] = len(queries)
    data["litigation"] = result
    return data
