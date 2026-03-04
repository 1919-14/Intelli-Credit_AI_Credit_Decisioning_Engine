import os
import json
import copy
from datetime import datetime, timezone
import fitz
from pydantic import ValidationError
from typing import Dict, Any, List

from layer2.utils.dispatcher import DocumentDispatcher
from layer2.extractors.unstructured import GroqExtractor, GroqRateLimitError
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
}


class IntelliCreditPipeline:
    def __init__(self):
        self.dispatcher = DocumentDispatcher()
        self.llm_engine = GroqExtractor()
        self._ocr_engine = None  # Lazy-load: only created if rate limit hit

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

    def process_files(
        self,
        filepaths: List[str],
        case_id: str = "IC-2025-001",
        company_name: str = "Unknown"
    ) -> IntelliCreditJSON:
        """
        Accumulative pipeline:
        - Start with empty master schema
        - For each document:
            → Try LLM (full text + current JSON)
            → If rate limited → fall back to EasyOCR regex on remaining null fields only
        - Final JSON has data from ALL documents
        """
        doc_metadata_map: Dict[str, DocumentMetadata] = {}
        accumulated_json = copy.deepcopy(MASTER_SCHEMA)
        rate_limited = False   # flip to True once limit hits — stay on OCR for rest

        for fp in filepaths:
            meta = self.dispatcher.ingest(fp)
            target_key = meta["target_key"]
            doc_label = DOC_TYPE_LABELS.get(target_key, "Financial Document")
            print(f"\n📄 [{meta['filename']}] → {target_key} ({doc_label})")

            doc_metadata_map[target_key] = DocumentMetadata(
                filename=meta["filename"],
                file_hash=meta["file_hash"],
                pages=meta["pages"],
                ocr_used=False,
                extraction_confidence=0.0
            )

            full_text = self._extract_full_text(fp)
            print(f"  📝 {len(full_text)} chars extracted ({meta['pages']} pages)")

            if not rate_limited:
                # ── Primary: LLM extraction ────────────────────────────
                try:
                    accumulated_json = self.llm_engine.extract_and_fill(
                        full_text=full_text,
                        current_json=accumulated_json,
                        doc_type_hint=doc_label
                    )
                    doc_metadata_map[target_key].extraction_confidence = 0.90

                except GroqRateLimitError as e:
                    print(f"  ⚠️  Groq rate limit hit: {e}")
                    print(f"  🔄 Switching to EasyOCR fallback for remaining documents...")
                    rate_limited = True
                    # Fall through to OCR block below

                except Exception as e:
                    print(f"  ❌ LLM error: {e}")
                    print(f"  🔄 Falling back to EasyOCR for this document...")
                    rate_limited = True
                    # Fall through to OCR block below

            if rate_limited:
                # ── Fallback: EasyOCR regex on remaining null fields ──
                ocr = self._get_ocr_engine()
                try:
                    # Try to get better OCR text if PyMuPDF text is sparse
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

        # ── Final summary ──────────────────────────────────────────
        filled = sum(1 for v in accumulated_json.values()
                     if v is not None and v != [] and v != "")
        total = len(accumulated_json)
        null_count = total - filled

        print(f"\n{'='*50}")
        print(f"📊 FINAL: {filled}/{total} fields filled ({round(filled/total*100,1)}%)")
        print(f"{'='*50}")

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
            pipeline_version="3.1.0",
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
    print("Pipeline v3.1 (LLM + EasyOCR fallback) initialized!")
