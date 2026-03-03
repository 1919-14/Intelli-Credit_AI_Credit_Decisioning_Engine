import os
import json
import time
import copy
from typing import Dict, Any
from groq import Groq
from tenacity import retry, wait_exponential, stop_after_attempt


class GroqRateLimitError(Exception):
    """Raised when rate limit is hit — signals processor to switch to OCR fallback."""
    pass


class GroqExtractor:
    """
    Simple LLM extractor:
    - ONE call per document, full text, exact JSON schema
    - Raises GroqRateLimitError instead of sleeping so the processor
      can fall back to EasyOCR immediately
    """

    MAX_TPM = 30000

    def __init__(self):
        self.api_key = os.getenv("API_KEY", "")
        if not self.api_key:
            print("WARNING: GROQ API_KEY not found in environment.")
        self.client = Groq(api_key=self.api_key)
        self.model = "meta-llama/llama-4-scout-17b-16e-instruct"
        self.tokens_used_this_minute = 0
        self.last_reset_time = time.time()

    def _reset_window_if_due(self):
        now = time.time()
        if now - self.last_reset_time > 60:
            self.tokens_used_this_minute = 0
            self.last_reset_time = now

    def _check_rate_limits(self, estimated_tokens: int) -> bool:
        self._reset_window_if_due()
        return self.tokens_used_this_minute + estimated_tokens <= self.MAX_TPM

    def _call_llm(self, system_prompt: str, user_content: str) -> str:
        estimated = int(len((system_prompt + user_content).split()) * 1.3)
        if not self._check_rate_limits(estimated):
            raise GroqRateLimitError(
                f"TPM limit hit — {self.tokens_used_this_minute} used, {estimated} needed"
            )

        completion = self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            model=self.model,
            response_format={"type": "json_object"}
        )

        if hasattr(completion, 'usage') and completion.usage:
            self.tokens_used_this_minute += completion.usage.total_tokens
        else:
            self.tokens_used_this_minute += estimated

        return completion.choices[0].message.content

    def _parse_json(self, raw: str) -> dict:
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {}

    def extract_and_fill(self, full_text: str, current_json: dict, doc_type_hint: str) -> dict:
        """
        Sends the EXACT JSON schema + document text to LLM.
        LLM fills in null fields, preserves existing values.
        Raises GroqRateLimitError if TPM limit is hit — processor handles the fallback.
        """
        schema_str = json.dumps(current_json, indent=2, default=str)

        prompt = f"""You are a precise Indian financial document data extractor.
You are processing a {doc_type_hint} document.

Below is a JSON template. Some fields already have values from previous documents — DO NOT CHANGE those.

YOUR TASK:
1. Read the document text provided by the user.
2. Fill in any fields that are currently null with data you find in the document.
3. For list fields that are empty [], add entries if you find relevant data.
4. PRESERVE all existing non-null values exactly as they are.
5. Return the COMPLETE JSON with ALL fields.

RULES:
- All monetary amounts in RUPEES (exact values, not lakhs).
- Dates in YYYY-MM-DD format.
- If you cannot find a value, keep it as null.
- NEVER invent or hallucinate data.
- Return ONLY the JSON object, nothing else.

JSON TEMPLATE TO FILL:
{schema_str}"""

        # This may raise GroqRateLimitError — caller handles it
        raw = self._call_llm(prompt, full_text)
        result = self._parse_json(raw)

        if not result:
            print(f"  ⚠ LLM returned empty — keeping current data")
            return current_json

        # Merge: accept null→value upgrades, protect existing values
        merged = copy.deepcopy(current_json)
        for key in merged:
            if key in result:
                old_val = merged[key]
                new_val = result[key]
                if (old_val is None or old_val == [] or old_val == "") and \
                   new_val is not None and new_val != [] and new_val != "":
                    merged[key] = new_val
                elif isinstance(old_val, list) and isinstance(new_val, list) and len(new_val) > len(old_val):
                    merged[key] = new_val

        return merged
