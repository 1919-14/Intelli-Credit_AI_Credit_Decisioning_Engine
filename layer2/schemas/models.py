from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Union, Any, Dict
from datetime import date, datetime

# --- METADATA WRAPPERS (ZERO HALLUCINATION AUDIT TRAIL) ---
class ExtractionMeta(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score from OCR or LLM")
    source_page: Optional[int] = Field(None, description="The page number where the data was found")
    raw_snippet: Optional[str] = Field(None, description="The exact raw text used for extraction")
    extraction_method: str = Field(description="E.g., regex, pandas, llm, groq_vision")
    notes: Optional[str] = Field(None, description="Any internal flags or extraction notes")

# Generic wrapper for single values
class DataPoint(ExtractionMeta):
    value: Any # Will be overridden by subclasses

class StringPoint(DataPoint):
    value: Optional[str]

class FloatPoint(DataPoint):
    value: Optional[float]

class IntPoint(DataPoint):
    value: Optional[int]

class DatePoint(DataPoint):
    value: Optional[date]

class BoolPoint(DataPoint):
    value: Optional[bool]


# --- SRC_GST Sub-Schemas ---
class OutwardTurnoverEntry(BaseModel):
    month: str
    taxable_value_inr_lakhs: float

class OutwardTurnoverPoint(DataPoint):
    value: List[OutwardTurnoverEntry]

class ITCAvailableEntry(BaseModel):
    month: str
    itc_available_inr_lakhs: float
    
class ITCAvailablePoint(DataPoint):
    value: List[ITCAvailableEntry]

class ITCClaimedEntry(BaseModel):
    month: str
    itc_claimed_inr_lakhs: float

class ITCClaimedPoint(DataPoint):
    value: List[ITCClaimedEntry]

class GSTFilingEntry(BaseModel):
    month: str
    due_date: date
    filed_date: date
    on_time: bool

class GSTFilingPoint(DataPoint):
    value: List[GSTFilingEntry]

class SRC_GST_Schema(BaseModel):
    gstin: StringPoint
    gstin_registration_status: StringPoint
    gstr1_monthly_outward_turnover: OutwardTurnoverPoint
    gstr2a_monthly_itc_available: ITCAvailablePoint
    gstr3b_monthly_itc_claimed: ITCClaimedPoint
    gst_filing_dates: GSTFilingPoint


# --- SRC_ITR Sub-Schemas ---
class StringListPoint(DataPoint):
    value: List[str]

class PATEntry(BaseModel):
    financial_year: str
    pat_inr_lakhs: float

class PATPoint(DataPoint):
    value: List[PATEntry]

class RevenueEntry(BaseModel):
    financial_year: str
    revenue_inr_lakhs: float

class RevenuePoint(DataPoint):
    value: List[RevenueEntry]

class AssetsEntry(BaseModel):
    financial_year: str
    total_assets_inr_lakhs: float

class AssetsPoint(DataPoint):
    value: List[AssetsEntry]

class LiabilitiesEntry(BaseModel):
    financial_year: str
    total_liabilities_inr_lakhs: float

class LiabilitiesPoint(DataPoint):
    value: List[LiabilitiesEntry]

class TaxPaidEntry(BaseModel):
    financial_year: str
    tax_paid_inr_lakhs: float
    
class TaxPaidPoint(DataPoint):
    value: List[TaxPaidEntry]

class RemunerationEntry(BaseModel):
    financial_year: str
    remuneration_inr_lakhs: float

class RemunerationPoint(DataPoint):
    value: List[RemunerationEntry]

class SRC_ITR_Schema(BaseModel):
    pan_number: StringPoint
    assessment_years_covered: StringListPoint
    net_profit_after_tax: PATPoint
    gross_revenue: RevenuePoint
    total_assets: AssetsPoint
    total_liabilities: LiabilitiesPoint
    tax_paid: TaxPaidPoint
    director_remuneration: RemunerationPoint
    loans_from_directors: DataPoint # List of Dict or empty list


# --- SRC_BANK Sub-Schemas ---
class StatementPeriod(BaseModel):
    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")

class StatementPeriodPoint(DataPoint):
    value: StatementPeriod

class MonthlyBalanceEntry(BaseModel):
    month: str
    closing_balance_inr_lakhs: float

class MonthlyBalancePoint(DataPoint):
    value: List[MonthlyBalanceEntry]

class MonthlyCreditEntry(BaseModel):
    month: str
    total_credits_inr_lakhs: float

class MonthlyCreditPoint(DataPoint):
    value: List[MonthlyCreditEntry]
    
class MonthlyDebitEntry(BaseModel):
    month: str
    total_debits_inr_lakhs: float

class MonthlyDebitPoint(DataPoint):
    value: List[MonthlyDebitEntry]

class TransactionEntry(BaseModel):
    date: Optional[Union[date, str]] = None
    month: Optional[str] = None
    narration: str
    amount_inr_lakhs: float
    type: str = Field(description="'DR' or 'CR'")
    reason: Optional[str] = None
    lender_name: Optional[str] = None

class TransactionListPoint(DataPoint):
    value: List[TransactionEntry]

class SRC_BANK_Schema(BaseModel):
    bank_name: StringPoint
    account_number_masked: StringPoint
    account_type: StringPoint
    statement_period: StatementPeriodPoint
    od_cc_limit_sanctioned_inr_lakhs: FloatPoint
    monthly_closing_balance: MonthlyBalancePoint
    monthly_total_credits: MonthlyCreditPoint
    monthly_total_debits: MonthlyDebitPoint
    cheque_bounce_entries: TransactionListPoint
    emi_loan_repayment_entries: TransactionListPoint
    gst_payment_entries: TransactionListPoint
    large_round_transfers: TransactionListPoint
    salary_entries: TransactionListPoint

# --- MAIN DOCUMENT SCHEMA ---

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
    model_config = {"extra": "allow"} # Pass-through schema pending for FS, RAT, BMM, etc.
    SRC_GST: Optional[SRC_GST_Schema] = None
    SRC_ITR: Optional[SRC_ITR_Schema] = None
    SRC_BANK: Optional[SRC_BANK_Schema] = None
    # We can add SRC_FS, SRC_AR etc later as we expand the pipeline.

class IntelliCreditJSON(BaseModel):
    meta: GlobalMeta
    extracted: ExtractedData
