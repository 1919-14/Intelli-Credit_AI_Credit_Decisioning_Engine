import os
import json
import copy
import threading
from datetime import datetime, timezone
import fitz
from pydantic import ValidationError
from typing import Dict, Any, List, Optional

from layer2.utils.dispatcher import DocumentDispatcher
from layer2.extractors.unstructured import GroqExtractor, GroqRateLimitError, GroqAllKeysExhaustedError
from layer2.extractors.ocr_fallback import EasyOCRExtractor
from layer2.schemas.master_schema import MASTER_SCHEMA
from layer2.schemas.models import (
    IntelliCreditJSON, GlobalMeta, ExtractionSummary, ExtractedData, DocumentMetadata
)

DOC_TYPE_LABELS = {
    "SRC_GST": "GST Return (GSTR-1/GSTR-3B)",
    "SRC_ITR": "Income Tax Return (ITR-3/ITR-6)",
    "SRC_BANK": "Bank Statement",
    "SRC_FS": "Financial Statement (P&L / Balance Sheet)",
    "SRC_AR": "Annual Report",
    "SRC_BMM": "Board Meeting Minutes",
    "SRC_RAT": "Credit Rating Report",
    "SRC_SHP": "Shareholding Pattern",
    "SRC_ALM": "Asset-Liability Management (ALM) Report",
    "SRC_BRP": "Borrowing Profile / Debt Schedule",
    "SRC_PRT": "Portfolio Cuts / Performance Data",
    "SRC_ESG": "Sustainability / Climate Report (ESG)",
    "SRC_ANR": "Annual Return (MCA MGT-7 / AOC-4)",
}

# Threshold: PDFs with more pages than this get chunked
LARGE_PDF_THRESHOLD = 10


class IntelliCreditPipeline:
    # Per-case decision events: {case_id: {'event': threading.Event, 'decision': str}}
    _human_decisions: Dict[str, dict] = {}

    def __init__(self, socketio=None):
        self.dispatcher = DocumentDispatcher()
        self.llm_engine = GroqExtractor()
        self._ocr_engine = None  # Lazy-load: only created if all keys exhausted AND user chose OCR
        self.socketio = socketio  # Flask-SocketIO instance for progress updates

    def _get_ocr_engine(self) -> EasyOCRExtractor:
        """Lazy-init OCR engine only when actually needed."""
        if self._ocr_engine is None:
            print("  📷 Initialising EasyOCR fallback engine...")
            self._ocr_engine = EasyOCRExtractor()
        return self._ocr_engine

    def _extract_full_text(self, filepath: str) -> str:
        """Extract ALL text from PDF using PyMuPDF."""
        text = ""
        doc = fitz.open(filepath)
        for page in doc:
            text += page.get_text() + "\n"
        doc.close()
        return text.strip()

    def _extract_page_texts(self, filepath: str) -> List[str]:
        """Extract text from each page individually. Returns list of per-page strings."""
        page_texts = []
        doc = fitz.open(filepath)
        for page in doc:
            page_texts.append(page.get_text())
        doc.close()
        return page_texts

    def _get_page_count(self, filepath: str) -> int:
        """Quick page count without extracting text."""
        doc = fitz.open(filepath)
        count = len(doc)
        doc.close()
        return count

    def _emit_progress(self, case_id: str, event: str, data: dict):
        """Emit a SocketIO event if socketio is available."""
        if self.socketio:
            try:
                self.socketio.emit(event, {**data, 'case_id': case_id})
            except Exception as e:
                print(f"  ⚠ SocketIO emit failed: {e}")

    def _wait_for_human_decision(self, case_id: str, app_id: str, exhaustion: 'GroqAllKeysExhaustedError') -> str:
        """
        Pauses the pipeline thread until the human chooses:
          'wait'  → resume after TPM window resets
          'ocr'   → use EasyOCR fallback (lower accuracy)
        Returns the decision string.
        """
        evt = threading.Event()
        IntelliCreditPipeline._human_decisions[case_id] = {'event': evt, 'decision': None}

        # Tell the frontend
        self._emit_progress(case_id, 'rate_limit_choice', {
            'app_id': app_id,
            'exhaustion_type': exhaustion.exhaustion_type,   # 'tpm' or 'tpd'
            'seconds_until_reset': exhaustion.seconds_until_reset,
            'keys_count': self.llm_engine.key_manager.total_keys,
            'message': (
                f"All {self.llm_engine.key_manager.total_keys} API keys are TPM-limited. "
                f"Waiting ~{exhaustion.seconds_until_reset}s will restore LLM accuracy."
                if exhaustion.exhaustion_type == 'tpm'
                else f"All keys have hit their daily (TPD) limit. "
                     f"LLM extraction is unavailable until tomorrow."
            )
        })

        print(f"  ⏸  Pipeline paused — waiting for human decision on rate limit (case {case_id})")
        # Wait up to 10 minutes for a response
        evt.wait(timeout=600)

        decision = (IntelliCreditPipeline._human_decisions.get(case_id) or {}).get('decision', 'ocr')
        IntelliCreditPipeline._human_decisions.pop(case_id, None)
        print(f"  ✅ Human chose: '{decision}' for case {case_id}")
        return decision

    @classmethod
    def resolve_rate_limit_decision(cls, case_id: str, decision: str):
        """Called by the SocketIO handler when the user clicks 'Wait' or 'Use OCR'."""
        slot = cls._human_decisions.get(case_id)
        if slot:
            slot['decision'] = decision
            slot['event'].set()

    def process_files(
        self,
        filepaths: List[str],
        case_id: str = "IC-2025-001",
        company_name: str = "Unknown",
        app_id: str = ""
    ) -> IntelliCreditJSON:
        """
        Accumulative pipeline:
        - Start with empty master schema
        - For each document:
            → If ≤ LARGE_PDF_THRESHOLD pages: single LLM call (original behavior)
            → If > LARGE_PDF_THRESHOLD pages: chunked extraction (10 pages/chunk)
            → If ALL keys exhausted: pause & ask human (Wait / OCR fallback)
        - Emits SocketIO events for frontend progress tracking
        - Final JSON has data from ALL documents
        """
        doc_metadata_map: Dict[str, DocumentMetadata] = {}
        accumulated_json = copy.deepcopy(MASTER_SCHEMA)
        rate_limited = False   # flip to True once limit hits — stay on OCR for rest

        total_files = len(filepaths)
        file_idx = 0
        while file_idx < total_files:
            fp = filepaths[file_idx]
            meta = self.dispatcher.ingest(fp)
            target_key = meta["target_key"]
            doc_label = DOC_TYPE_LABELS.get(target_key, "Financial Document")
            page_count = meta["pages"]
            print(f"\n📄 [{meta['filename']}] → {target_key} ({doc_label}) — {page_count} pages")

            doc_metadata_map[target_key] = DocumentMetadata(
                filename=meta["filename"],
                file_hash=meta["file_hash"],
                pages=meta["pages"],
                ocr_used=False,
                extraction_confidence=0.0
            )

            # Emit file-level progress
            self._emit_progress(case_id, 'l2_file_progress', {
                'file_index': file_idx + 1,
                'total_files': total_files,
                'filename': meta["filename"],
                'doc_type': doc_label,
                'page_count': page_count,
                'is_chunked': page_count > LARGE_PDF_THRESHOLD,
                'status': 'processing'
            })

            if not rate_limited:
                # ── Decide: single call vs chunked ────────────────────
                if page_count > LARGE_PDF_THRESHOLD:
                    # ═══ CHUNKED EXTRACTION for large PDFs ═══
                    try:
                        page_texts = self._extract_page_texts(fp)
                        total_chars = sum(len(t) for t in page_texts)
                        print(f"  📝 {total_chars} chars extracted across {page_count} pages (chunked mode)")

                        # Emit chunking info
                        chunk_count = (page_count + self.llm_engine.CHUNK_SIZE - 1) // self.llm_engine.CHUNK_SIZE
                        self._emit_progress(case_id, 'l2_chunk_info', {
                            'filename': meta["filename"],
                            'total_pages': page_count,
                            'chunk_size': self.llm_engine.CHUNK_SIZE,
                            'total_chunks': chunk_count,
                        })

                        def chunk_progress(chunk_idx, total_chunks, start_page, end_page):
                            self._emit_progress(case_id, 'l2_chunk_progress', {
                                'filename': meta["filename"],
                                'chunk_index': chunk_idx,
                                'total_chunks': total_chunks,
                                'start_page': start_page,
                                'end_page': end_page,
                                'total_pages': page_count,
                                'status': 'processing'
                            })

                        # Use resume state if available (after rate limit retry)
                        resume_chunk = getattr(self, '_resume_chunk_index', 0)
                        resume_json = getattr(self, '_resume_partial_json', None)

                        accumulated_json = self.llm_engine.extract_chunked(
                            page_texts=page_texts,
                            current_json=resume_json if resume_json is not None else accumulated_json,
                            doc_type_hint=doc_label,
                            progress_callback=chunk_progress,
                            start_chunk=resume_chunk
                        )
                        # Clear resume state on success
                        self._resume_chunk_index = 0
                        self._resume_partial_json = None
                        doc_metadata_map[target_key].extraction_confidence = 0.90

                    except GroqAllKeysExhaustedError as e:
                        print(f"  ⏸  All keys exhausted ({e.exhaustion_type.upper()}) during chunked extraction")
                        decision = self._wait_for_human_decision(case_id, str(app_id), e)
                        if decision == 'wait' and e.exhaustion_type == 'tpm':
                            import time
                            wait_secs = e.seconds_until_reset + 3
                            print(f"  ⏳ Waiting {wait_secs}s for TPM window to reset...")
                            self._emit_progress(case_id, 'rate_limit_waiting', {
                                'seconds': wait_secs, 'reason': 'TPM window resetting'
                            })
                            time.sleep(wait_secs)
                            # Preserve partial state for resume
                            if e.partial_json is not None:
                                self._resume_partial_json = e.partial_json
                                self._resume_chunk_index = e.failed_chunk_index
                                print(f"  🔄 Resuming file {file_idx + 1}/{total_files} from chunk {e.failed_chunk_index + 1}: {meta['filename']}")
                            else:
                                self._resume_chunk_index = 0
                                self._resume_partial_json = None
                                print(f"  🔄 Retrying file {file_idx + 1}/{total_files}: {meta['filename']}")
                            # Do NOT increment file_idx — retry same file
                            continue
                        else:
                            # Use partial data if available before falling back
                            if e.partial_json is not None:
                                accumulated_json = e.partial_json
                            self._resume_chunk_index = 0
                            self._resume_partial_json = None
                            rate_limited = True  # User chose OCR or it's TPD

                else:
                    # ═══ SINGLE CALL for small PDFs ═══
                    try:
                        full_text = self._extract_full_text(fp)
                        print(f"  📝 {len(full_text)} chars extracted ({page_count} pages)")

                        accumulated_json = self.llm_engine.extract_and_fill(
                            full_text=full_text,
                            current_json=accumulated_json,
                            doc_type_hint=doc_label
                        )
                        doc_metadata_map[target_key].extraction_confidence = 0.90

                    except GroqAllKeysExhaustedError as e:
                        print(f"  ⏸  All keys exhausted ({e.exhaustion_type.upper()})")
                        decision = self._wait_for_human_decision(case_id, str(app_id), e)
                        if decision == 'wait' and e.exhaustion_type == 'tpm':
                            import time
                            wait_secs = e.seconds_until_reset + 3
                            print(f"  ⏳ Waiting {wait_secs}s for TPM window to reset...")
                            self._emit_progress(case_id, 'rate_limit_waiting', {
                                'seconds': wait_secs, 'reason': 'TPM window resetting'
                            })
                            time.sleep(wait_secs)
                            print(f"  🔄 Retrying file {file_idx + 1}/{total_files}: {meta['filename']}")
                            # Do NOT increment file_idx — retry same file
                            continue
                        else:
                            rate_limited = True

            if rate_limited:
                # ── Fallback: EasyOCR regex on remaining null fields ──
                full_text = self._extract_full_text(fp)
                ocr = self._get_ocr_engine()
                try:
                    pymupdf_text = full_text
                    char_count = len(pymupdf_text.replace(" ", ""))
                    if char_count < 500:
                        print(f"  📷 Sparse text ({char_count} chars) — running EasyOCR on images...")
                        ocr_text = ocr.extract_text_from_pdf(fp)
                        combined_text = pymupdf_text + "\n" + ocr_text
                    else:
                        combined_text = pymupdf_text

                    before_filled = sum(
                        1 for v in accumulated_json.values()
                        if v is not None and v != [] and v != ""
                    )
                    accumulated_json = ocr.fill_remaining_fields(combined_text, accumulated_json)
                    after_filled = sum(
                        1 for v in accumulated_json.values()
                        if v is not None and v != [] and v != ""
                    )
                    newly_filled = after_filled - before_filled
                    print(f"  🔍 EasyOCR filled {newly_filled} additional fields")
                    doc_metadata_map[target_key].ocr_used = True
                    doc_metadata_map[target_key].extraction_confidence = 0.70

                except Exception as ocr_err:
                    print(f"  ❌ EasyOCR also failed: {ocr_err}")

            filled = sum(
                1 for v in accumulated_json.values()
                if v is not None and v != [] and v != ""
            )
            total = len(accumulated_json)
            print(f"  ✅ Progress: {filled}/{total} fields filled "
                  f"({'LLM' if not rate_limited else 'OCR fallback'})")

            # Emit file completion
            self._emit_progress(case_id, 'l2_file_progress', {
                'file_index': file_idx + 1,
                'total_files': total_files,
                'filename': meta["filename"],
                'doc_type': doc_label,
                'page_count': page_count,
                'fields_filled': filled,
                'total_fields': total,
                'status': 'completed'
            })

            file_idx += 1  # Advance to next file

        # ── Final summary ──────────────────────────────────────────
        filled = sum(1 for v in accumulated_json.values()
                     if v is not None and v != [] and v != "")
        total = len(accumulated_json)
        null_count = total - filled

        print(f"\n{'='*50}")
        print(f"📊 FINAL: {filled}/{total} fields filled ({round(filled/total*100,1)}%)")
        print(f"{'='*50}")

        # Emit API key usage stats
        key_status = self.llm_engine.key_manager.get_status()
        print(f"🔑 API Key Usage: {json.dumps(key_status, indent=2)}")

        summary = ExtractionSummary(
            total_fields_attempted=total,
            fields_extracted=filled,
            fields_null=null_count,
            overall_quality_score=round(filled / max(total, 1) * 100, 1)
        )

        global_meta = GlobalMeta(
            case_id=case_id,
            company_name=company_name,
            extraction_timestamp=datetime.now(timezone.utc),
            schema_version="3.0",
            pipeline_version="3.2.0",
            llm_model="meta-llama/llama-4-scout-17b-16e-instruct",
            llm_provider="groq",
            ocr_engine="pymupdf + easyocr_fallback",
            documents_processed=doc_metadata_map,
            extraction_summary=summary
        )

        try:
            return IntelliCreditJSON(
                meta=global_meta,
                extracted=ExtractedData(financial_data=accumulated_json)
            )
        except ValidationError as e:
            raise Exception(f"Schema validation failed: {e}")


if __name__ == "__main__":
    pipeline = IntelliCreditPipeline()
    print("Pipeline v3.2 (LLM + chunking + key rotation + EasyOCR fallback) initialized!")
