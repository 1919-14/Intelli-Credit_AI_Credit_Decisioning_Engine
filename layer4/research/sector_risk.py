"""
Block C3: Sector Risk Intelligence
Tavily (fetch) + Groq (synthesise)
"""
import os
import json
from typing import Dict, Any
from layer4.research.tavily_client import TavilySearchClient


def _call_groq(prompt: str, content: str) -> dict:
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
        print(f"  ⚠ Groq error: {e}")
        return {}


def run_sector_risk(data: Dict[str, Any]) -> Dict[str, Any]:
    """C3: Sector risk intelligence scan."""
    ids = data.get("company_identifiers", {})
    sector = ids.get("industry", "") or ids.get("sector", "") or "manufacturing"

    tavily = TavilySearchClient()
    queries = [
        f"{sector} sector India credit risk outlook 2024-25",
        f"{sector} India commodity price volatility SME impact 2024",
        f"RBI {sector} NBFC credit watchlist caution circular"
    ]

    all_results = tavily.search_batch(queries, max_results=3)
    combined = ""
    snippets = []
    for q, results in all_results.items():
        for r in results:
            combined += f"Query: {q}\nTitle: {r['title']}\nURL: {r['url']}\n{r['content']}\n\n"
            snippets.append({"query": q, "title": r["title"], "url": r["url"], "content": r["content"][:200]})

    if not combined.strip():
        data["sector_risk"] = {
            "sector_risk_score": 0.3, "headwinds": [], "tailwinds": [],
            "rbi_sector_flag": False, "sector": sector,
            "summary": "No sector-specific risk intelligence found",
            "alerts": [{"alert_id": "C3-001", "type": "SECTOR_NEUTRAL",
                        "severity": "GREEN", "description": "No specific sector warnings",
                        "score_penalty": 0, "source": "Sector risk scan"}]
        }
        return data

    prompt = f"""You are an Indian corporate credit analyst. Analyse the following search results about the {sector} sector.
Return JSON:
{{
  "sector_risk_score": float 0.0 (low risk) to 1.0 (high risk),
  "headwinds": ["list of negative trends/risks"],
  "tailwinds": ["list of positive trends"],
  "rbi_sector_flag": true if RBI has issued any sector warning/circular, else false,
  "summary": "2-3 sentence sector outlook summary",
  "key_data_points": ["specific stats or facts from search results"]
}}"""

    result = _call_groq(prompt, combined[:3000])

    alerts = []
    score = result.get("sector_risk_score", 0.3)
    rbi_flag = result.get("rbi_sector_flag", False)

    if rbi_flag:
        alerts.append({"alert_id": "C3-002", "type": "RBI_SECTOR_CAUTION",
                        "severity": "RED", "description": "RBI has issued sector caution notice",
                        "score_penalty": -8, "source": "Sector risk intelligence"})
    elif score > 0.7:
        alerts.append({"alert_id": "C3-003", "type": "HIGH_SECTOR_RISK",
                        "severity": "AMBER", "description": f"Sector risk score {score:.2f} — elevated headwinds",
                        "score_penalty": -5, "source": "Sector risk intelligence"})
    else:
        alerts.append({"alert_id": "C3-004", "type": "SECTOR_STABLE",
                        "severity": "GREEN", "description": f"Sector risk manageable (score: {score:.2f})",
                        "score_penalty": 0, "source": "Sector risk intelligence"})

    result["alerts"] = alerts
    result["raw_snippets"] = snippets
    result["searches_performed"] = len(queries)
    result["sector"] = sector
    data["sector_risk"] = result
    return data
