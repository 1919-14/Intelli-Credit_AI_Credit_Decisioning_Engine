import pandas as pd
import fitz
import re
from typing import Dict, Any, List
from layer2.schemas.models import (
    DataPoint, StringPoint, FloatPoint, StatementPeriodPoint, StatementPeriod,
    MonthlyBalancePoint, MonthlyBalanceEntry, TransactionListPoint, TransactionEntry
)

class BankStatementExtractor:
    """
    Deterministic extraction for Bank Statements.
    Utilizes Pandas for CSV/Excel, and PyMuPDF Table finder for digital PDFs.
    """
    def __init__(self, filepath: str, ext: str):
        self.filepath = filepath
        self.ext = ext
        self.raw_df = None
        self.text_content = ""
        
    def _read_data(self):
        if self.ext in ['.csv', '.xlsx', '.xls']:
            try:
                self.raw_df = pd.read_csv(self.filepath) if self.ext == '.csv' else pd.read_excel(self.filepath)
            except Exception as e:
                # Malformed file
                self.raw_df = pd.DataFrame()
        elif self.ext == '.pdf':
            # Extract text for regex (Bank Name, Account No, Limit)
            doc = fitz.open(self.filepath)
            for page in doc:
                self.text_content += page.get_text()
                
            # For hackathon: We will extract the first valid table found
            tables = []
            for page in doc:
                page_tabs = page.find_tables()
                if page_tabs.tables:
                    tables.append(page_tabs[0].to_pandas())
            
            if tables:
                self.raw_df = pd.concat(tables, ignore_index=True)
            else:
                self.raw_df = pd.DataFrame()
            doc.close()

    def extract(self) -> Dict[str, Any]:
        """
        Extracts structured data mimicking sample.json SRC_BANK schema.
        Note: The actual transformation of DataFrames to the exact json struct 
        requires specific column mapping, we are using robust stubs here that hit the schema.
        """
        self._read_data()
        
        # 1. Regex Extractions (Account Info)
        bank_name = "Unknown"
        acc_no = "Unknown"
        acc_type = "Unknown"
        limit = None
        
        # Simple heuristics for demonstration
        if "state bank" in self.text_content.lower():
            bank_name = "State Bank of India"
        elif "hdfc" in self.text_content.lower():
            bank_name = "HDFC Bank"
            
        acc_match = re.search(r'(?:A/c No|Account No)[\s.:]+([\d\wX]+)', self.text_content)
        if acc_match:
            acc_no = acc_match.group(1)
            
        limit_match = re.search(r'(?:Sanctioned Limit|Limit)[\D]+([\d,]+)', self.text_content)
        if limit_match:
            try:
                limit = float(limit_match.group(1).replace(',', '')) / 100000.0 # Convert to Lakhs
            except:
                limit = None

        # Assemble basic Pydantic structs with metadata 
        bank_schema_dict = {
            "bank_name": {
                "value": bank_name if bank_name != "Unknown" else None,
                "confidence": 0.9 if bank_name != "Unknown" else 0.0,
                "extraction_method": "regex",
                "source_page": 1
            },
            "account_number_masked": {
                "value": acc_no if acc_no != "Unknown" else None,
                "confidence": 0.99 if acc_match else 0.0,
                "extraction_method": "regex",
                 "source_page": 1
            },
            "account_type": { "value": None, "confidence": 0.0, "extraction_method": "regex", "source_page": 1 },
            "statement_period": { 
                "value": {"from": "1970-01-01", "to": "1970-01-01"}, 
                "confidence": 0.0, 
                "extraction_method": "regex" 
            },
            "od_cc_limit_sanctioned_inr_lakhs": {
                 "value": limit,
                 "confidence": 0.9 if limit else 0.0,
                 "extraction_method": "regex",
                 "source_page": 1
            },
            # Stubs for pandas aggregations that would map df columns to these schemas
            "monthly_closing_balance": {
                "value": [], 
                "confidence": 0.0,
                "extraction_method": "pandas",
                "notes": "Pending DF column mapping logic"
            },
            "monthly_total_credits": { "value": [], "confidence": 0.0, "extraction_method": "pandas" },
            "monthly_total_debits": {"value": [], "confidence": 0.0, "extraction_method": "pandas" },
            "cheque_bounce_entries": {"value": [], "confidence": 0.0, "extraction_method": "pandas_filter"},
            "emi_loan_repayment_entries": {"value": [], "confidence": 0.0, "extraction_method": "pandas_filter"},
            "gst_payment_entries": {"value": [], "confidence": 0.0, "extraction_method": "pandas_filter"},
            "large_round_transfers": {"value": [], "confidence": 0.0, "extraction_method": "pandas_filter"},
            "salary_entries": {"value": [], "confidence": 0.0, "extraction_method": "pandas_filter"},
        }
        
        return bank_schema_dict
