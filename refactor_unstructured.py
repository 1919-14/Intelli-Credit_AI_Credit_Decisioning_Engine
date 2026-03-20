import re
import sys

filepath = r"c:\Users\saina\Videos\AIML Hack\layer2\extractors\unstructured.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Remove the NvidiaExtractor class
# We match from the section header to the end of the file.
content = re.sub(
    r"# ═══════════════════════════════════════════════════════════════════════════════\n# Nvidia NIM Extractor.*?$",
    "", content, flags=re.DOTALL
)

# Replace the inner try/except/while block related to Nvidia Fallback
# We will match the entire while not chunk_done: loop and replace it.
pattern_loop = re.compile(
    r"(# ── Per-chunk retry loop: Groq → wait for TPM reset → retry Groq → Nvidia \(last resort\) ──.*?)(# Small delay between chunks to ease rate pressure)",
    re.DOTALL
)

new_loop = """# ── Per-chunk retry loop: Groq → wait for TPM reset → retry Groq ──
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
                        import time
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
                        import time
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

            """

content = pattern_loop.sub(new_loop + r"\2", content, count=1)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated unstructured.py successfully.")
