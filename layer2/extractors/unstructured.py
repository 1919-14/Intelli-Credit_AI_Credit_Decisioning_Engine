import os
import json
import time
import copy
import requests
from typing import Dict, Any, List, Optional
from groq import Groq
from tenacity import retry, wait_exponential, stop_after_attempt


class GroqRateLimitError(Exception):
    """Raised for a transient per-call 429 — the _call_llm rotator handles these internally."""
    pass


class GroqAllKeysExhaustedError(Exception):
    """
    Raised when ALL 6 keys are genuinely exhausted.
      exhaustion_type='tpm'  → temporary; waiting ~seconds_until_reset will fix it
      exhaustion_type='tpd'  → day-long limit hit; only OCR fallback can help
    """
    def __init__(self, message: str, exhaustion_type: str = 'tpm', seconds_until_reset: int = 60):
        super().__init__(message)
        self.exhaustion_type = exhaustion_type
        self.seconds_until_reset = seconds_until_reset
        self.partial_json = None        # Accumulated JSON from completed chunks
        self.failed_chunk_index = 0     # Which chunk to resume from



# ═══════════════════════════════════════════════════════════════════════════════
# API Key Manager — round-robin rotation across 6 Groq keys
# ═══════════════════════════════════════════════════════════════════════════════

class APIKeyManager:
    """
    Manages 6 Groq API keys with per-key TPM (30K tokens/min) and TPD
    (500K tokens/day) tracking.  Rotates to the next available key when
    the current one approaches its limit.
    """

    TPM_LIMIT = 30_000     # tokens per minute per key
    TPD_LIMIT = 500_000    # tokens per day per key
    TPM_BUFFER = 2_000     # leave margin before declaring "full"

    ENV_KEY_NAMES = ["API_KEY"] + [f"API_KEY{i}" for i in range(1, 13)]

    def __init__(self):
        self.keys: List[str] = []
        for name in self.ENV_KEY_NAMES:
            val = os.getenv(name, "").strip()
            if val:
                self.keys.append(val)

        if not self.keys:
            print("WARNING: No Groq API keys found in environment!")

        # Per-key usage tracking
        self._tpm: Dict[int, int] = {i: 0 for i in range(len(self.keys))}
        self._tpd: Dict[int, int] = {i: 0 for i in range(len(self.keys))}
        self._minute_start: Dict[int, float] = {i: time.time() for i in range(len(self.keys))}
        self._day_start: Dict[int, float] = {i: time.time() for i in range(len(self.keys))}

        self._current_idx = 0

    @property
    def total_keys(self) -> int:
        return len(self.keys)

    def _reset_if_due(self, idx: int):
        now = time.time()
        # Reset minute window
        if now - self._minute_start[idx] > 60:
            self._tpm[idx] = 0
            self._minute_start[idx] = now
        # Reset day window
        if now - self._day_start[idx] > 86400:
            self._tpd[idx] = 0
            self._day_start[idx] = now

    def _key_has_capacity(self, idx: int, estimated_tokens: int) -> bool:
        self._reset_if_due(idx)
        tpm_ok = self._tpm[idx] + estimated_tokens <= (self.TPM_LIMIT - self.TPM_BUFFER)
        tpd_ok = self._tpd[idx] + estimated_tokens <= self.TPD_LIMIT
        return tpm_ok and tpd_ok


    def get_exhaustion_info(self, estimated_tokens: int) -> dict:
        """
        Called only when get_client_and_key fails. Returns a dict:
          {
            'type': 'tpm' | 'tpd',      # tpm = temporary, tpd = day-long
            'seconds_until_reset': int,  # seconds until TPM window resets (0 if TPD)
          }
        """
        now = time.time()
        # Check if ANY key has TPD headroom (meaning it's only a TPM problem)
        any_tpd_ok = any(
            self._tpd[i] + estimated_tokens <= self.TPD_LIMIT
            for i in range(len(self.keys))
        )

        if any_tpd_ok:
            # TPM temporary block — find earliest minute window reset
            earliest_reset = min(
                max(0, 60 - int(now - self._minute_start[i]))
                for i in range(len(self.keys))
            )
            return {'type': 'tpm', 'seconds_until_reset': max(earliest_reset, 5)}
        else:
            return {'type': 'tpd', 'seconds_until_reset': 0}

    def get_client_and_key(self, estimated_tokens: int) -> tuple:
        """
        Returns (Groq client, key_index) for the best available key.
        Tries current key first, then round-robins.
        Raises GroqAllKeysExhaustedError if ALL keys are exhausted.
        """
        if not self.keys:
            raise GroqAllKeysExhaustedError("No API keys configured", 'tpd', 0)

        # Try starting from current index, wrapping around
        for offset in range(len(self.keys)):
            idx = (self._current_idx + offset) % len(self.keys)
            if self._key_has_capacity(idx, estimated_tokens):
                self._current_idx = idx
                client = Groq(api_key=self.keys[idx])
                return client, idx

        # ALL keys exhausted — determine type
        info = self.get_exhaustion_info(estimated_tokens)
        raise GroqAllKeysExhaustedError(
            f"All {len(self.keys)} API keys exhausted ({info['type'].upper()})",
            exhaustion_type=info['type'],
            seconds_until_reset=info['seconds_until_reset']
        )

    def record_usage(self, idx: int, tokens: int):
        """Record token usage for a specific key index."""
        self._tpm[idx] += tokens
        self._tpd[idx] += tokens

    def advance_key(self):
        """Force rotate to next key (e.g. after a 429 error)."""
        if self.keys:
            self._current_idx = (self._current_idx + 1) % len(self.keys)

    def get_status(self) -> Dict:
        """Return usage status for all keys (for debugging/logging)."""
        status = {}
        for i in range(len(self.keys)):
            self._reset_if_due(i)
            status[f"key_{i}"] = {
                "tpm_used": self._tpm[i],
                "tpm_remaining": self.TPM_LIMIT - self._tpm[i],
                "tpd_used": self._tpd[i],
                "tpd_remaining": self.TPD_LIMIT - self._tpd[i],
                "is_current": i == self._current_idx,
            }
        return status


# ═══════════════════════════════════════════════════════════════════════════════
# Groq Extractor — LLM extraction with auto key rotation + chunk support
# ═══════════════════════════════════════════════════════════════════════════════

class GroqExtractor:
    """
    Primary LLM extractor using Groq (Llama):
    - Multi-key rotation (6 keys, round-robin)
    - Chunked extraction for large PDFs (10 pages per chunk)
    - Context preservation: sends accumulated JSON with each chunk
    - Auto-retry with next key on 429
    - On all-keys-exhausted: automatically hands off to NvidiaExtractor (40 pages/chunk)
    - Only escalates to human-decision / OCR if Nvidia also fails
    """

    CHUNK_SIZE = 10  # pages per chunk

    def __init__(self):
        self.key_manager = APIKeyManager()
        self.model = "meta-llama/llama-4-scout-17b-16e-instruct"

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate: ~1.3 tokens per whitespace-delimited word."""
        return int(len(text.split()) * 1.3)

    def _call_llm(self, system_prompt: str, user_content: str) -> str:
        """
        Call the LLM with automatic key rotation.
        - On 429 from API: marks key as full, rotates to next, retries
        - On GroqAllKeysExhaustedError: re-raises immediately (caller decides)
        """
        estimated = self._estimate_tokens(system_prompt + user_content)

        for attempt in range(max(self.key_manager.total_keys, 1)):
            try:
                client, key_idx = self.key_manager.get_client_and_key(estimated)
                completion = client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    model=self.model,
                    response_format={"type": "json_object"},
                    max_tokens=8000
                )

                actual_tokens = estimated
                if hasattr(completion, 'usage') and completion.usage:
                    actual_tokens = completion.usage.total_tokens
                self.key_manager.record_usage(key_idx, actual_tokens)

                return completion.choices[0].message.content

            except GroqAllKeysExhaustedError:
                raise  # Propagate immediately — pipeline handles this

            except Exception as e:
                error_str = str(e).lower()
                if 'json_validate_failed' in error_str:
                    print(f"  ⚠️  Model failed to generate valid JSON (likely truncated due to token limits). Skipping chunk.")
                    return "{}"
                if '429' in error_str or 'rate_limit' in error_str or 'rate limit' in error_str:
                    print(f"  ⚠️  Key {key_idx} hit 429 — rotating to next key (attempt {attempt+1})")
                    self.key_manager.record_usage(key_idx, self.key_manager.TPM_LIMIT)  # mark as full
                    self.key_manager.advance_key()
                    time.sleep(1)
                    continue
                else:
                    raise

        # If we exhausted all retries via 429s, re-check exhaustion state
        est_info = self.key_manager.get_exhaustion_info(estimated)
        raise GroqAllKeysExhaustedError(
            f"All keys exhausted after {self.key_manager.total_keys} attempts",
            exhaustion_type=est_info['type'],
            seconds_until_reset=est_info['seconds_until_reset']
        )

    def _parse_json(self, raw: str) -> dict:
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {}

    def _build_prompt(self, doc_type_hint: str, schema_str: str, chunk_info: str = "") -> str:
        """Build the system prompt for extraction."""
        chunk_note = ""
        if chunk_info:
            chunk_note = f"""
NOTE: This is {chunk_info} of a large document.
The JSON template already contains data extracted from PREVIOUS chunks of this same document.
MERGE new findings into the existing data — do NOT clear or overwrite previously extracted values."""

        return f"""You are a precise Indian financial document data extractor.
You are processing a {doc_type_hint} document.{chunk_note}

Below is a JSON template. Some fields already have values from previous documents — DO NOT CHANGE those.

YOUR TASK:
1. Read the document text provided by the user.
2. Fill in any fields that are currently null with data you find in the document.
3. For list fields that are empty [], add entries if you find relevant data.
4. PRESERVE all existing non-null values exactly as they are.
5. Return the COMPLETE JSON with ALL fields.
6. **IMPORTANT — DYNAMIC FIELDS**: If the document contains ANY financial data, metrics,
   ratios, or information NOT listed in the schema, ADD IT as a new key using
   snake_case naming (e.g., "provision_coverage_ratio", "promoter_name", "sector_outlook").
   Do NOT omit relevant data just because it lacks a matching field in the template.

RULES:
- All monetary amounts in RUPEES (exact values, not lakhs/crores unless the field name implies it).
- Dates in YYYY-MM-DD format.
- If you cannot find a value, keep it as null.
- NEVER invent or hallucinate data.
- Return ONLY the JSON object, nothing else.
- For ALM documents: extract maturity bucket data into alm_maturity_buckets as a list of objects.
- For Shareholding: extract top shareholders list with name and percentage.
- For Borrowing Profile: extract lender details into existing_lenders and credit_facilities lists.
- For Portfolio data: extract all PAR, GNPA, collection metrics you find.

JSON TEMPLATE TO FILL:
{schema_str}"""

    def _merge_result(self, current: dict, result: dict) -> dict:
        """Merge LLM result into current JSON, preserving existing values."""
        merged = copy.deepcopy(current)
        for key in merged:
            if key in result:
                old_val = merged[key]
                new_val = result[key]
                if (old_val is None or old_val == [] or old_val == "") and \
                   new_val is not None and new_val != [] and new_val != "":
                    merged[key] = new_val
                elif isinstance(old_val, list) and isinstance(new_val, list) and len(new_val) > len(old_val):
                    merged[key] = new_val

        # Accept NEW keys the LLM discovered (dynamic schema expansion)
        for key, val in result.items():
            if key not in merged and val is not None and val != "" and val != []:
                merged[key] = val

        return merged

    def extract_and_fill(self, full_text: str, current_json: dict, doc_type_hint: str) -> dict:
        """
        Single-call extraction (for small documents).
        Raises GroqRateLimitError if all keys exhausted — processor handles the fallback.
        """
        schema_str = json.dumps(current_json, indent=2, default=str)
        prompt = self._build_prompt(doc_type_hint, schema_str)
        raw = self._call_llm(prompt, full_text)
        result = self._parse_json(raw)

        if not result:
            print(f"  ⚠ LLM returned empty — keeping current data")
            return current_json

        return self._merge_result(current_json, result)

    def extract_chunked(
        self,
        page_texts: List[str],
        current_json: dict,
        doc_type_hint: str,
        progress_callback=None,
        start_chunk: int = 0
    ) -> dict:
        """
        Chunked extraction for large PDFs.
        - page_texts: list of per-page text strings
        - current_json: accumulated JSON from previous documents
        - progress_callback: fn(chunk_idx, total_chunks, start_page, end_page) for UI updates
        - start_chunk: skip to this chunk index (0-based) to resume after rate limit
        Returns: merged JSON with data from all chunks.
        """
        total_pages = len(page_texts)
        chunks = []

        # Build chunks of CHUNK_SIZE pages
        for i in range(0, total_pages, self.CHUNK_SIZE):
            chunk_pages = page_texts[i : i + self.CHUNK_SIZE]
            chunk_text = "\n".join(chunk_pages)
            chunks.append({
                "text": chunk_text,
                "start_page": i + 1,
                "end_page": min(i + self.CHUNK_SIZE, total_pages)
            })

        total_chunks = len(chunks)
        accumulated = copy.deepcopy(current_json)

        if start_chunk > 0:
            print(f"  📑 Resuming from chunk {start_chunk + 1}/{total_chunks} (skipping {start_chunk} already-done chunks)")
        else:
            print(f"  📑 Large PDF: {total_pages} pages → {total_chunks} chunks of {self.CHUNK_SIZE} pages")

        for idx, chunk in enumerate(chunks):
            # Skip already-completed chunks on resume
            if idx < start_chunk:
                continue

            start_pg = chunk["start_page"]
            end_pg = chunk["end_page"]
            chunk_info = f"chunk {idx+1}/{total_chunks} (pages {start_pg}–{end_pg})"

            print(f"  🔄 Processing {chunk_info}...")

            # Notify frontend
            if progress_callback:
                progress_callback(idx + 1, total_chunks, start_pg, end_pg)

            schema_str = json.dumps(accumulated, indent=2, default=str)
            prompt = self._build_prompt(doc_type_hint, schema_str, chunk_info)

            # ── Per-chunk retry loop: Groq → wait for TPM reset → retry Groq ──
            groq_tpm_waits = 0       # How many times we've waited for Groq to reset
            MAX_GROQ_WAITS = 2       # Wait up to 2x for Groq TPM to reset before escalating
            chunk_done = False

            while not chunk_done:
                # ─── Try Groq ───────────────────────────────────────────────────
                try:
                    raw = self._call_llm(prompt, chunk["text"])
                    result = self._parse_json(raw)
                    if result:
                        accumulated = self._merge_result(accumulated, result)
                        print(f"  ✅ [GROQ] Chunk {idx+1}/{total_chunks} merged successfully")
                    else:
                        print(f"  ⚠ [GROQ] Chunk {idx+1}/{total_chunks} returned empty — skipping")
                    chunk_done = True  # Success
                    continue

                except GroqAllKeysExhaustedError as e:
                    if groq_tpm_waits < MAX_GROQ_WAITS:
                        # Wait for the TPM window to reset, then retry Groq directly
                        wait_secs = max(e.seconds_until_reset + 5, 30)
                        groq_tpm_waits += 1
                        print(f"  ⏳ [GROQ] All keys exhausted on chunk {idx+1} — waiting {wait_secs}s for TPM reset (attempt {groq_tpm_waits}/{MAX_GROQ_WAITS})...")
                        time.sleep(wait_secs)
                        # Loop back and retry Groq
                        continue
                    else:
                        print(f"  ❌ [GROQ] Still exhausted after {MAX_GROQ_WAITS} waits — escalating to human decision/OCR.")
                        err = GroqAllKeysExhaustedError(
                            "Groq exhausted after multiple retries",
                            exhaustion_type='tpm',
                            seconds_until_reset=60
                        )
                        err.partial_json = accumulated
                        err.failed_chunk_index = idx
                        raise err

                except Exception as ge:
                    # Network / upstream error from Groq — treat same as exhaustion
                    if groq_tpm_waits < MAX_GROQ_WAITS:
                        groq_tpm_waits += 1
                        print(f"  ⚠ [GROQ] Error on chunk {idx+1}: {ge} — waiting 30s before retry ({groq_tpm_waits}/{MAX_GROQ_WAITS})...")
                        time.sleep(30)
                        continue
                    else:
                        print(f"  ❌ [GROQ] Still failing after {MAX_GROQ_WAITS} retries — escalating to human decision/OCR.")
                        err = GroqAllKeysExhaustedError(
                            "Groq failed after multiple retries",
                            exhaustion_type='tpm',
                            seconds_until_reset=60
                        )
                        err.partial_json = accumulated
                        err.failed_chunk_index = idx
                        raise err

            # Small delay between chunks to ease rate pressure
            if idx < total_chunks - 1:
                time.sleep(5)

        return accumulated



