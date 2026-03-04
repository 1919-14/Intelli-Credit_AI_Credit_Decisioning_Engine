"""
Block F1: NLP Processing of Credit Officer Site-Visit Notes
Groq only — single call to extract structured scores from free text.
"""
import os
import json
from typing import Dict, Any


def run_officer_notes(data: Dict[str, Any]) -> Dict[str, Any]:
    """F1: Extract structured scores from officer notes."""
    notes = data.get("officer_notes", "")

    if not notes or not notes.strip():
        data["officer_analysis"] = {
            "factory_operational_flag": None,
            "capacity_utilisation_percent": None,
            "succession_risk_flag": None,
            "management_depth_score": None,
            "working_capital_management_quality": None,
            "summary": "No officer notes provided — skipped qualitative analysis",
            "alerts": []
        }
        return data

    prompt = """You are a credit risk analyst. Extract structured assessment from a credit officer's site-visit notes.

Return JSON:
{
  "factory_operational_flag": 1 if factory/business is operational, 0 if not, null if not mentioned,
  "capacity_utilisation_percent": estimated utilisation % (0-100), null if not mentioned,
  "succession_risk_flag": 1 if key-man/succession risk noted, 0 if no risk, null if not mentioned,
  "management_depth_score": 1-5 rating (1=weak, 5=excellent), null if not assessable,
  "working_capital_management_quality": "Good" or "Average" or "Poor", null if not mentioned,
  "key_observations": ["list of important observations from notes"],
  "risk_factors": ["list of risk factors identified"],
  "positive_factors": ["list of positive observations"],
  "summary": "2-3 sentence structured summary of officer's assessment"
}

Be conservative — only extract what is explicitly mentioned or clearly implied in the notes."""

    try:
        from groq import Groq
        client = Groq(api_key=os.getenv("API_KEY", ""))
        resp = client.chat.completions.create(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": notes}
            ],
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            response_format={"type": "json_object"}
        )
        raw = resp.choices[0].message.content
        result = json.loads(raw.replace("```json", "").replace("```", "").strip())
    except Exception as e:
        print(f"  ⚠ Officer notes NLP error: {e}")
        result = {"summary": f"Error processing notes: {e}", "alerts": []}

    # Generate alerts
    alerts = []
    if result.get("factory_operational_flag") == 0:
        alerts.append({"alert_id": "F1-001", "type": "FACTORY_NON_OPERATIONAL",
                        "severity": "RED", "description": "Factory/business reported non-operational by officer",
                        "score_penalty": -15, "source": "Officer site-visit notes"})

    util = result.get("capacity_utilisation_percent")
    if util is not None and util < 50:
        alerts.append({"alert_id": "F1-002", "type": "LOW_CAPACITY",
                        "severity": "AMBER", "description": f"Capacity utilisation only {util}%",
                        "score_penalty": -5, "source": "Officer site-visit notes"})

    if result.get("succession_risk_flag") == 1:
        alerts.append({"alert_id": "F1-003", "type": "SUCCESSION_RISK",
                        "severity": "AMBER", "description": "Key-man / succession risk identified",
                        "score_penalty": -4, "source": "Officer site-visit notes"})

    result["alerts"] = alerts
    data["officer_analysis"] = result
    return data
