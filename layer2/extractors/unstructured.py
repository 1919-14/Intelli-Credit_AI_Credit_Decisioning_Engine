import os
import json
import base64
import time
from typing import Dict, Any, List, Optional
from groq import Groq
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

# Simple token estimator to avoid loading heavy tiktoken in hackathons
def estimate_tokens(text: str) -> int:
    return len(text.split()) * 1.3 # Rough heuristic for Llama

class GroqRateLimitError(Exception):
    pass

class GroqExtractor:
    """
    Handles LLM based extraction with precise rate-limit fallbacks and JSON parsing.
    """
    MAX_TPM = 30000
    
    def __init__(self):
        self.api_key = os.getenv("API_KEY", "")
        if not self.api_key:
            print("WARNING: GROQ API_KEY not found in environment.")
        self.client = Groq(api_key=self.api_key)
        self.model = "meta-llama/llama-4-scout-17b-16e-instruct"
        # Track tokens across instance lifecycle (simplified RPM/TPM state)
        self.tokens_used_this_minute = 0 
        self.last_reset_time = time.time()
        
    def _check_rate_limits(self, estimated_tokens: int) -> bool:
        """
        Returns True if safe to proceed, False if we must fallback to EasyOCR to maintain High Latency.
        """
        now = time.time()
        if now - self.last_reset_time > 60:
            self.tokens_used_this_minute = 0
            self.last_reset_time = now
            
        if self.tokens_used_this_minute + estimated_tokens > self.MAX_TPM:
            print(f"RATE LIMIT ALERT: Skipping Groq. {self.tokens_used_this_minute} + {estimated_tokens} > {self.MAX_TPM}")
            return False
            
        return True

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(Exception) # Note: Production code should only catch 429 Http errors here
    )
    def _call_groq_text(self, system_prompt: str, text_chunk: str) -> str:
        
        estimated = estimate_tokens(system_prompt + text_chunk)
        if not self._check_rate_limits(estimated):
            raise GroqRateLimitError("TPM Limit Exceeded - Triggering Fallback")
            
        completion = self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text_chunk}
            ],
            model=self.model,
            response_format={"type": "json_object"} # Forces JSON output
        )
        
        # Approximate tokens used based on actual response if API provides it
        if hasattr(completion, 'usage') and completion.usage:
             self.tokens_used_this_minute += completion.usage.total_tokens
        else:
             self.tokens_used_this_minute += estimated # Fallback
             
        return completion.choices[0].message.content

    def _call_groq_vision(self, system_prompt: str, base64_image: str) -> str:
        """
        Calls Groq with an image.
        """
        estimation = 300 # Vision payloads cost abstract tokens, 300 is safe buffer
        if not self._check_rate_limits(estimation):
             raise GroqRateLimitError("TPM Limit Exceeded for Vision - Triggering Fallback")
             
        completion = self.client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": system_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            model=self.model,
            response_format={"type": "json_object"}
        )
        
        if hasattr(completion, 'usage') and completion.usage:
             self.tokens_used_this_minute += completion.usage.total_tokens
        else:
             self.tokens_used_this_minute += estimation
             
        return completion.choices[0].message.content

    def clean_json(self, raw_str: str) -> Dict[str, Any]:
        """Strip markdown ticks if LLM hallucinated them despite JSON mode"""
        cleaned = raw_str.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {} # Returning empty dict will trigger Pydantic defaults/nulls perfectly

    def extract_json_schema(self, text: str, target_schema: dict) -> Dict[str, Any]:
        """
        Dynamically extracts data matching a specific Pydantic schema structure.
        Forces the LLM to output exact nulls/empty arrays for missing fields.
        """
        schema_str = json.dumps(target_schema, indent=2)
        
        prompt = f"""
        You are an elite financial data extractor building an audit trail.
        Extract the requested metrics from the user's text.
        
        CRITICAL RULES:
        1. Your output MUST be a valid JSON object.
        2. Your output MUST EXACTLY match the keys and structure of this TARGET_SCHEMA.
        3. If a value cannot be found in the text, you MUST output `null` for strings/numbers, or `[]` for lists, exactly as shaped in the TARGET_SCHEMA.
        4. NEVER hallucinate data. If you are unsure, output `null` or `[]`.
        
        TARGET_SCHEMA TO MATCH:
        {schema_str}
        """
        
        try:
            raw_response = self._call_groq_text(prompt, text)
            json_data = self.clean_json(raw_response)
            
            # Wrap the pure output in our Metadata layer 
            wrapped = {}
            for key, val in json_data.items():
                # Don't try to wrap nested lists/objects if the schema expects a pure list (like gstr1_monthly_outward_turnover)
                # We assume the orchestrator will handle the top-level Dict[str, DataPoint] wrapping.
                wrapped[key] = {
                    "value": val if val != [] and val is not None else ( [] if isinstance(target_schema.get(key), list) else None ),
                    "confidence": 0.95 if val else 0.0,
                    "extraction_method": "groq_llm"
                }
            return wrapped
            
        except GroqRateLimitError:
            print("Groq Limit reached: Falling back to RegEx/OCR Engine.")
            return {} # We return empty, signalling `pipeline.py` to trigger EasyOCR fallback logic
        except Exception as e:
            print(f"Extraction failed: {e}")
            return {}
