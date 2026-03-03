from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List
from datetime import datetime


# --- Simple field wrapper (value + confidence) ---
class DataField(BaseModel):
    """Minimal wrapper: just the value and extraction confidence."""
    value: Any = None
    confidence: float = 0.0
    extraction_method: str = "llm"

    model_config = {"extra": "allow"}


# --- Document schemas: accept any fields the LLM extracts ---
class SRC_GST_Schema(BaseModel):
    model_config = {"extra": "allow"}

class SRC_ITR_Schema(BaseModel):
    model_config = {"extra": "allow"}

class SRC_BANK_Schema(BaseModel):
    model_config = {"extra": "allow"}

class SRC_FS_Schema(BaseModel):
    model_config = {"extra": "allow"}

class SRC_AR_Schema(BaseModel):
    model_config = {"extra": "allow"}


# --- Main document structure ---
class DocumentMetadata(BaseModel):
    filename: str
    file_hash: str
    pages: int
    ocr_used: bool
    extraction_confidence: float

class ExtractionSummary(BaseModel):
    total_fields_attempted: int = 0
    fields_extracted: int = 0
    fields_null: int = 0
    fields_low_confidence: int = 0
    human_review_queue: int = 0
    overall_quality_score: float = 0.0

class GlobalMeta(BaseModel):
    case_id: str
    company_name: str
    extraction_timestamp: datetime
    schema_version: str
    pipeline_version: str
    llm_model: str
    llm_provider: str
    ocr_engine: str
    documents_processed: Dict[str, DocumentMetadata]
    extraction_summary: ExtractionSummary

class ExtractedData(BaseModel):
    model_config = {"extra": "allow"}
    financial_data: Optional[Dict] = None

class IntelliCreditJSON(BaseModel):
    meta: GlobalMeta
    extracted: ExtractedData
