import pandas as pd
import fitz
import re
from datetime import datetime
from typing import Dict, Any, List


class BankStatementExtractor:
    """
    Deterministic extraction for Bank Statements.
    Utilizes Pandas for CSV/Excel, and PyMuPDF Table finder for digital PDFs.
    Falls back to LLM extraction for financial aggregations.
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
                self.raw_df = pd.DataFrame()
        elif self.ext == '.pdf':
            doc = fitz.open(self.filepath)
            for page in doc:
                self.text_content += page.get_text()
                
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

    def _extract_account_type(self) -> str:
        """Extract account type from text."""
        text_lower = self.text_content.lower()
        if re.search(r'\b(savings?\s*(a/?c|account))', text_lower):
            return "Savings"
        elif re.search(r'\b(current\s*(a/?c|account))', text_lower):
            return "Current"
        elif re.search(r'\b(od|over\s*draft)', text_lower):
            return "OD"
        elif re.search(r'\b(cc|cash\s*credit)', text_lower):
            return "CC"
        # Fallback: look for keywords
        for kw, val in [("savings", "Savings"), ("current", "Current")]:
            if kw in text_lower:
                return val
        return None

    def _extract_statement_period(self) -> dict:
        """Extract statement period dates from text."""
        # Try various date range patterns
        patterns = [
            r'(?:statement\s*period|period)[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\s*(?:to|[-–])\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
            r'(?:from)[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\s*(?:to)\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
            r'(\d{1,2}[-/]\w{3}[-/]\d{2,4})\s*(?:to|[-–])\s*(\d{1,2}[-/]\w{3}[-/]\d{2,4})',
        ]
        for pat in patterns:
            match = re.search(pat, self.text_content, re.IGNORECASE)
            if match:
                from_str, to_str = match.group(1), match.group(2)
                try:
                    for fmt in ('%d-%m-%Y', '%d/%m/%Y', '%d-%b-%Y', '%d/%b/%Y', '%d-%m-%y', '%d/%m/%y'):
                        try:
                            from_dt = datetime.strptime(from_str, fmt).strftime('%Y-%m-%d')
                            to_dt = datetime.strptime(to_str, fmt).strftime('%Y-%m-%d')
                            return {"from": from_dt, "to": to_dt}
                        except ValueError:
                            continue
                except:
                    pass
        return None

    def _mask_account_number(self, acc_no: str) -> str:
        """Mask account number, keeping last 4 digits visible."""
        if not acc_no or acc_no == "Unknown":
            return None
        clean = re.sub(r'[^0-9X]', '', acc_no)
        if len(clean) >= 4:
            return 'X' * (len(clean) - 4) + clean[-4:]
        return clean

    def extract(self) -> Dict[str, Any]:
        """Extracts structured data for SRC_BANK schema."""
        self._read_data()
        
        # 1. Regex Extractions (Account Info)
        bank_name = None
        acc_no = None
        acc_type = self._extract_account_type()
        limit = None
        
        # Bank name detection
        bank_patterns = [
            (r'state\s*bank\s*of\s*india|sbi', "State Bank of India"),
            (r'hdfc\s*bank', "HDFC Bank"),
            (r'icici\s*bank', "ICICI Bank"),
            (r'axis\s*bank', "Axis Bank"),
            (r'kotak\s*mahindra', "Kotak Mahindra Bank"),
            (r'bank\s*of\s*baroda|bob', "Bank of Baroda"),
            (r'punjab\s*national\s*bank|pnb', "Punjab National Bank"),
            (r'canara\s*bank', "Canara Bank"),
            (r'union\s*bank', "Union Bank of India"),
            (r'indian\s*bank', "Indian Bank"),
            (r'yes\s*bank', "Yes Bank"),
            (r'indusind\s*bank', "IndusInd Bank"),
        ]
        for pattern, name in bank_patterns:
            if re.search(pattern, self.text_content, re.IGNORECASE):
                bank_name = name
                break
            
        acc_match = re.search(r'(?:A/c\s*No|Account\s*No|Account\s*Number|Acct\.?\s*No)[\s.:]+([0-9X]+)', self.text_content, re.IGNORECASE)
        if acc_match:
            acc_no = acc_match.group(1)
            
        limit_match = re.search(r'(?:Sanctioned\s*Limit|OD\s*Limit|CC\s*Limit|Limit)[^\d]*?([\d,]+)', self.text_content, re.IGNORECASE)
        if limit_match:
            try:
                limit = float(limit_match.group(1).replace(',', '')) / 100000.0
            except:
                limit = None

        # Statement period
        period = self._extract_statement_period()

        # Assemble schema
        bank_schema_dict = {
            "bank_name": {
                "value": bank_name,
                "confidence": 0.90 if bank_name else 0.0,
                "extraction_method": "regex",
                "source_page": 1
            },
            "account_number_masked": {
                "value": self._mask_account_number(acc_no) if acc_no else None,
                "confidence": 0.95 if acc_no else 0.0,
                "extraction_method": "regex",
                "source_page": 1
            },
            "account_type": {
                "value": acc_type,
                "confidence": 0.85 if acc_type else 0.0,
                "extraction_method": "regex",
                "source_page": 1
            },
            "statement_period": { 
                "value": period if period else {"from": "1970-01-01", "to": "1970-01-01"}, 
                "confidence": 0.90 if period else 0.0, 
                "extraction_method": "regex" 
            },
            "od_cc_limit_sanctioned_inr_lakhs": {
                 "value": limit,
                 "confidence": 0.90 if limit else 0.0,
                 "extraction_method": "regex",
                 "source_page": 1
            },
            # Financial aggregation fields — empty stubs, will be filled by LLM fallback if text is available
            "monthly_closing_balance": {"value": [], "confidence": 0.0, "extraction_method": "pandas"},
            "monthly_total_credits": {"value": [], "confidence": 0.0, "extraction_method": "pandas"},
            "monthly_total_debits": {"value": [], "confidence": 0.0, "extraction_method": "pandas"},
            "cheque_bounce_entries": {"value": [], "confidence": 0.0, "extraction_method": "pandas_filter"},
            "emi_loan_repayment_entries": {"value": [], "confidence": 0.0, "extraction_method": "pandas_filter"},
            "gst_payment_entries": {"value": [], "confidence": 0.0, "extraction_method": "pandas_filter"},
            "large_round_transfers": {"value": [], "confidence": 0.0, "extraction_method": "pandas_filter"},
            "salary_entries": {"value": [], "confidence": 0.0, "extraction_method": "pandas_filter"},
        }

        # LLM fallback for financial aggregations if raw text has transaction-like content
        if self.text_content and len(self.text_content) > 200:
            try:
                from layer2.extractors.unstructured import GroqExtractor
                llm = GroqExtractor()
                # Only extract the financial fields that are still empty
                fin_schema = {
                    "monthly_closing_balance": [],
                    "monthly_total_credits": [],
                    "monthly_total_debits": [],
                    "cheque_bounce_entries": [],
                    "emi_loan_repayment_entries": [],
                    "gst_payment_entries": [],
                    "large_round_transfers": [],
                    "salary_entries": [],
                }
                llm_result = llm.extract_json_schema(self.text_content, fin_schema, src_type="SRC_BANK")
                # Merge LLM results into our schema (only overwrite empty stubs)
                for key, val in llm_result.items():
                    if key in bank_schema_dict and isinstance(val, dict):
                        if val.get("value") and val["value"] != []:
                            bank_schema_dict[key] = val
            except Exception as e:
                print(f"Bank LLM fallback failed: {e}")
        
        return bank_schema_dict

