"""
Block C1: Promoter Adverse Media Scan
Tavily (fetch) + Groq (classify)
"""
import os
import json
from typing import Dict, Any
from layer4.research.tavily_client import TavilySearchClient


def _call_groq_classify(prompt: str, content: str) -> dict:
    """Call Groq LLM to classify search results."""
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
        print(f"  ⚠ Groq classify error: {e}")
        return {}


def run_adverse_media(data: Dict[str, Any]) -> Dict[str, Any]:
    """C1: Search for negative news about promoter/company."""
    ids = data.get("company_identifiers", {})
    promoter = ids.get("promoter_name", "") or ids.get("company_name", "")
    company = ids.get("company_name", "")

    if not promoter and not company:
        data["adverse_media"] = {
            "negative_news_flag": 0, "sentiment_score": 0,
            "adverse_snippets": [], "searches_performed": 0,
            "alerts": [{"alert_id": "C1-SKIP", "type": "DATA_MISSING",
                        "severity": "INFO", "description": "No promoter/company name available"}]
        }
        return data

    tavily = TavilySearchClient()
    queries = [
        f"{promoter} fraud scam case India",
        f"{promoter} RBI SEBI enforcement action",
        f"{company} GST notice tax evasion",
        f"{promoter} director disqualification DIN"
    ]

    all_results = tavily.search_batch(queries, max_results=3)
    combined_text = ""
    all_snippets = []
    for q, results in all_results.items():
        for r in results:
            combined_text += f"Query: {q}\nTitle: {r['title']}\nURL: {r['url']}\nContent: {r['content']}\n\n"
            all_snippets.append({"query": q, "title": r["title"], "url": r["url"], "content": r["content"][:200]})

    if not combined_text.strip():
        data["adverse_media"] = {
            "negative_news_flag": 0, "sentiment_score": 0.5,
            "adverse_snippets": [], "searches_performed": len(queries),
            "summary": "No relevant search results found — clean record",
            "alerts": [{"alert_id": "C1-001", "type": "CLEAN_RECORD",
                        "severity": "GREEN", "description": "No adverse media found",
                        "score_penalty": 0, "source": "Tavily adverse media scan"}]
        }
        return data

    prompt = """You are a credit risk analyst. Classify the following web search results about a loan applicant.
Return JSON:
{
  "negative_news_flag": 0 or 1,
  "sentiment_score": float from -1.0 (very negative) to +1.0 (very positive),
  "risk_category": "Criminal/Fraud" or "Regulatory" or "Civil_Dispute" or "Clean",
  "summary": "1-2 sentence summary of findings",
  "key_concerns": ["list of specific concerns found"],
  "adverse_snippets": [{"title": "...", "url": "...", "concern": "1-line concern summary"}]
}
If no negative info is found, set negative_news_flag=0, sentiment_score=0.5, risk_category="Clean"."""

    result = _call_groq_classify(prompt, combined_text[:3000])

    alerts = []
    risk = result.get("risk_category", "Clean")
    if risk in ["Criminal/Fraud", "Regulatory"]:
        alerts.append({"alert_id": "C1-002", "type": "ADVERSE_MEDIA_CRITICAL",
                        "severity": "RED", "description": result.get("summary", "Critical adverse media found"),
                        "score_penalty": -15, "source": "Tavily + Groq adverse media scan"})
    elif risk == "Civil_Dispute":
        alerts.append({"alert_id": "C1-003", "type": "ADVERSE_MEDIA_CIVIL",
                        "severity": "AMBER", "description": result.get("summary", "Civil disputes found"),
                        "score_penalty": -5, "source": "Tavily + Groq adverse media scan"})
    else:
        alerts.append({"alert_id": "C1-004", "type": "CLEAN_RECORD",
                        "severity": "GREEN", "description": "No significant adverse media",
                        "score_penalty": 0, "source": "Tavily + Groq adverse media scan"})

    result["alerts"] = alerts
    result["searches_performed"] = len(queries)
    result["raw_snippets"] = all_snippets
    data["adverse_media"] = result
    return data
