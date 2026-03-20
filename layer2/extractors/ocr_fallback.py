"""
EasyOCR-based fallback extractor.
Used when Groq API rate limit is hit — does regex extraction on OCR text
to fill as many remaining null fields as possible.
"""

import re
from typing import Dict, Any


class EasyOCRExtractor:
    """
    Regex-based extractor using EasyOCR text output.
    Only fills fields that are still null in the accumulated JSON.
    Not as accurate as LLM — but extracts deterministic fields reliably
    (IDs, dates, totals) so the pipeline can show useful data even on fallback.
    """

    def __init__(self):
        self._reader = None  # Lazy-load — heavy import

    def _load_reader(self):
        if self._reader is None:
            try:
                import easyocr
                self._reader = easyocr.Reader(['en'], gpu=False, verbose=False)
            except ImportError:
                raise ImportError("easyocr not installed. Run: pip install easyocr")

    def extract_text_from_pdf(self, filepath: str) -> str:
        """Extract text from PDF pages using EasyOCR."""
        import fitz
        import numpy as np

        self._load_reader()
        all_text = ""
        doc = fitz.open(filepath)
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
            if pix.n == 4:
                img = img[:, :, :3]
            results = self._reader.readtext(img, detail=0, paragraph=True)
            all_text += " ".join(results) + "\n"
        doc.close()
        return all_text

    def fill_remaining_fields(self, text: str, accumulated: dict) -> dict:
        """
        Only fills fields that are currently null/empty.
        Returns updated accumulated dict.
        """
        updated = dict(accumulated)

        # --- GST fields ---
        if updated.get("gstin") is None:
            m = re.search(r'\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1})\b', text)
            if m: updated["gstin"] = m.group(1)

        if updated.get("legal_name") is None:
            m = re.search(r'(?:Legal Name|Trade Name|Company Name)[:\s]+([A-Z][A-Za-z\s&.,()\-]+)', text)
            if m: updated["legal_name"] = m.group(1).strip()

        if updated.get("gst_filing_date") is None:
            m = re.search(r'(?:Date of Filing|Filing Date)[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})', text)
            if m: updated["gst_filing_date"] = self._normalize_date(m.group(1))

        if updated.get("total_taxable_value_domestic") is None:
            m = re.search(r'(?:Total Taxable Value|Taxable Turnover)[:\s₹]*([\d,]+\.?\d*)', text)
            if m: updated["total_taxable_value_domestic"] = self._parse_number(m.group(1))

        if updated.get("total_tax_collected") is None:
            m = re.search(r'(?:Total Tax|Total GST)[:\s₹]*([\d,]+\.?\d*)', text)
            if m: updated["total_tax_collected"] = self._parse_number(m.group(1))

        if updated.get("total_igst") is None:
            m = re.search(r'(?:IGST|Integrated Tax)[:\s₹]*([\d,]+\.?\d*)', text)
            if m: updated["total_igst"] = self._parse_number(m.group(1))

        if updated.get("total_cgst") is None:
            m = re.search(r'(?:CGST|Central Tax)[:\s₹]*([\d,]+\.?\d*)', text)
            if m: updated["total_cgst"] = self._parse_number(m.group(1))

        if updated.get("total_sgst") is None:
            m = re.search(r'(?:SGST|State Tax)[:\s₹]*([\d,]+\.?\d*)', text)
            if m: updated["total_sgst"] = self._parse_number(m.group(1))

        # --- ITR fields ---
        if updated.get("pan_number") is None:
            m = re.search(r'\b([A-Z]{5}[0-9]{4}[A-Z]{1})\b', text)
            if m: updated["pan_number"] = m.group(1)

        if updated.get("assessment_year") is None:
            m = re.search(r'Assessment Year[:\s]+(\d{4}-\d{2,4})', text, re.IGNORECASE)
            if m: updated["assessment_year"] = m.group(1)

        if updated.get("gross_receipts") is None:
            m = re.search(r'(?:Gross Receipts?|Gross Revenue|Total Revenue)[:\s₹]*([\d,]+\.?\d*)', text, re.IGNORECASE)
            if m: updated["gross_receipts"] = self._parse_number(m.group(1))

        if updated.get("net_profit_from_business") is None:
            m = re.search(r'(?:Net Profit|Profit from Business)[:\s₹]*([\d,]+\.?\d*)', text, re.IGNORECASE)
            if m: updated["net_profit_from_business"] = self._parse_number(m.group(1))

        if updated.get("taxable_income") is None:
            m = re.search(r'(?:Total Taxable Income|Net Taxable Income)[:\s₹]*([\d,]+\.?\d*)', text, re.IGNORECASE)
            if m: updated["taxable_income"] = self._parse_number(m.group(1))

        if updated.get("total_tax_payable") is None:
            m = re.search(r'(?:Tax Payable|Total Tax Due)[:\s₹]*([\d,]+\.?\d*)', text, re.IGNORECASE)
            if m: updated["total_tax_payable"] = self._parse_number(m.group(1))

        # --- Financial Statement fields ---
        if updated.get("revenue_from_operations") is None:
            m = re.search(r'Revenue from Operations[:\s₹]*([\d,]+\.?\d*)', text, re.IGNORECASE)
            if m: updated["revenue_from_operations"] = self._parse_number(m.group(1))

        if updated.get("profit_before_tax") is None:
            m = re.search(r'Profit Before Tax[:\s₹]*([\d,]+\.?\d*)', text, re.IGNORECASE)
            if m: updated["profit_before_tax"] = self._parse_number(m.group(1))

        if updated.get("profit_after_tax") is None:
            m = re.search(r'Profit After Tax[:\s₹]*([\d,]+\.?\d*)', text, re.IGNORECASE)
            if m: updated["profit_after_tax"] = self._parse_number(m.group(1))

        if updated.get("total_assets") is None:
            m = re.search(r'Total Assets[:\s₹]*([\d,]+\.?\d*)', text, re.IGNORECASE)
            if m: updated["total_assets"] = self._parse_number(m.group(1))

        if updated.get("total_liabilities") is None:
            m = re.search(r'Total Liabilities[:\s₹]*([\d,]+\.?\d*)', text, re.IGNORECASE)
            if m: updated["total_liabilities"] = self._parse_number(m.group(1))

        if updated.get("net_worth") is None:
            m = re.search(r"(?:Net Worth|Shareholders'? Equity)[:\s₹]*([\d,]+\.?\d*)", text, re.IGNORECASE)
            if m: updated["net_worth"] = self._parse_number(m.group(1))

        if updated.get("total_debt") is None:
            m = re.search(r'(?:Total Borrowings?|Total Debt)[:\s₹]*([\d,]+\.?\d*)', text, re.IGNORECASE)
            if m: updated["total_debt"] = self._parse_number(m.group(1))

        if updated.get("ebitda") is None:
            m = re.search(r'EBITDA[:\s₹]*([\d,]+\.?\d*)', text, re.IGNORECASE)
            if m: updated["ebitda"] = self._parse_number(m.group(1))

        # --- Bank Statement fields ---
        if updated.get("bank_name") is None:
            banks = ["State Bank of India", "HDFC Bank", "ICICI Bank", "Axis Bank",
                     "Punjab National Bank", "Bank of Baroda", "Canara Bank",
                     "Kotak Mahindra Bank", "IndusInd Bank", "Yes Bank", "IDFC"]
            for bank in banks:
                if bank.lower() in text.lower():
                    updated["bank_name"] = bank
                    break

        if updated.get("account_number") is None:
            m = re.search(r'(?:A/?c|Account)\s*(?:No|Number)?[.:\s]+(\d{9,18})', text, re.IGNORECASE)
            if m: updated["account_number"] = m.group(1)

        if updated.get("account_type") is None:
            for atype in ["Savings", "Current", "Overdraft", "Cash Credit"]:
                if atype.lower() in text.lower():
                    updated["account_type"] = atype
                    break

        if updated.get("opening_balance") is None:
            m = re.search(r'Opening Balance[:\s₹]*([\d,]+\.?\d*)', text, re.IGNORECASE)
            if m: updated["opening_balance"] = self._parse_number(m.group(1))

        if updated.get("closing_balance") is None:
            m = re.search(r'Closing Balance[:\s₹]*([\d,]+\.?\d*)', text, re.IGNORECASE)
            if m: updated["closing_balance"] = self._parse_number(m.group(1))

        if updated.get("total_credits") is None:
            m = re.search(r'Total Credits?[:\s₹]*([\d,]+\.?\d*)', text, re.IGNORECASE)
            if m: updated["total_credits"] = self._parse_number(m.group(1))

        if updated.get("total_debits") is None:
            m = re.search(r'Total Debits?[:\s₹]*([\d,]+\.?\d*)', text, re.IGNORECASE)
            if m: updated["total_debits"] = self._parse_number(m.group(1))

        # Company info
        if updated.get("company_name") is None:
            m = re.search(r'(?:Company Name|Entity Name)[:\s]+([A-Z][A-Za-z\s&.,\-]+(?:Ltd|Limited|LLP|Pvt|Inc)?)', text)
            if m: updated["company_name"] = m.group(1).strip()

        if updated.get("cin") is None:
            m = re.search(r'\b([LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})\b', text)
            if m: updated["cin"] = m.group(1)

        # --- Credit Rating fields ---
        if updated.get("latest_credit_rating") is None:
            for rating_pattern in [r'(CRISIL\s+[A-Z]{1,4}[+-]?)', r'(ICRA\s+[A-Z]{1,4}[+-]?)',
                                   r'(CARE\s+[A-Z]{1,4}[+-]?)', r'(\[?IND\]?\s+[A-Z]{1,4}[+-]?)']:
                m = re.search(rating_pattern, text, re.IGNORECASE)
                if m:
                    updated["latest_credit_rating"] = m.group(1).strip()
                    break

        if updated.get("rating_agency") is None:
            for agency in ["CRISIL", "ICRA", "CARE", "India Ratings", "Brickwork", "Acuité"]:
                if agency.lower() in text.lower():
                    updated["rating_agency"] = agency
                    break

        # --- ALM fields ---
        if updated.get("liquidity_gap_1m") is None:
            m = re.search(r'(?:1\s*month|0-30\s*days?|upto\s*1\s*month).*?gap[:\s₹]*([+-]?[\d,]+\.?\d*)', text, re.IGNORECASE)
            if m: updated["liquidity_gap_1m"] = self._parse_number(m.group(1))

        if updated.get("liquidity_gap_3m") is None:
            m = re.search(r'(?:3\s*month|1-3\s*months?).*?gap[:\s₹]*([+-]?[\d,]+\.?\d*)', text, re.IGNORECASE)
            if m: updated["liquidity_gap_3m"] = self._parse_number(m.group(1))

        # --- Shareholding Pattern fields ---
        if updated.get("promoter_holding_pct") is None:
            m = re.search(r'(?:Promoter|Promoters?)[\s\S]{0,50}?(\d{1,3}\.?\d{0,2})\s*%', text, re.IGNORECASE)
            if m: updated["promoter_holding_pct"] = self._parse_number(m.group(1))

        if updated.get("public_holding_pct") is None:
            m = re.search(r'(?:Public|Non-Promoter)[\s\S]{0,50}?(\d{1,3}\.?\d{0,2})\s*%', text, re.IGNORECASE)
            if m: updated["public_holding_pct"] = self._parse_number(m.group(1))

        if updated.get("pledged_shares_pct") is None:
            m = re.search(r'(?:Pledged|Encumbered)[\s\S]{0,50}?(\d{1,3}\.?\d{0,2})\s*%', text, re.IGNORECASE)
            if m: updated["pledged_shares_pct"] = self._parse_number(m.group(1))

        # --- Borrowing Profile fields ---
        if updated.get("total_outstanding_borrowings") is None:
            m = re.search(r'(?:Total Outstanding|Total Borrowing)[:\s₹]*([\\d,]+\\.?\\d*)', text, re.IGNORECASE)
            if m: updated["total_outstanding_borrowings"] = self._parse_number(m.group(1))

        if updated.get("debt_service_coverage_ratio") is None:
            m = re.search(r'(?:DSCR|Debt Service Coverage)[:\s]*(\d+\.?\d*)', text, re.IGNORECASE)
            if m: updated["debt_service_coverage_ratio"] = self._parse_number(m.group(1))

        if updated.get("interest_coverage_ratio") is None:
            m = re.search(r'(?:ICR|Interest Coverage)[:\s]*(\d+\.?\d*)', text, re.IGNORECASE)
            if m: updated["interest_coverage_ratio"] = self._parse_number(m.group(1))

        # --- Portfolio Performance fields ---
        if updated.get("gnpa_pct") is None:
            m = re.search(r'(?:GNPA|Gross NPA)[:\s]*(\d+\.?\d*)\s*%', text, re.IGNORECASE)
            if m: updated["gnpa_pct"] = self._parse_number(m.group(1))

        if updated.get("nnpa_pct") is None:
            m = re.search(r'(?:NNPA|Net NPA)[:\s]*(\d+\.?\d*)\s*%', text, re.IGNORECASE)
            if m: updated["nnpa_pct"] = self._parse_number(m.group(1))

        if updated.get("collection_efficiency_pct") is None:
            m = re.search(r'(?:Collection Efficiency)[:\s]*(\d+\.?\d*)\s*%', text, re.IGNORECASE)
            if m: updated["collection_efficiency_pct"] = self._parse_number(m.group(1))

        if updated.get("nim_pct") is None:
            m = re.search(r'(?:NIM|Net Interest Margin)[:\s]*(\d+\.?\d*)\s*%', text, re.IGNORECASE)
            if m: updated["nim_pct"] = self._parse_number(m.group(1))

        # --- Cashflow fields ---
        if updated.get("cashflow_from_operations") is None:
            m = re.search(r'(?:Cash ?flow from|CFO|Operating Activities)[:\s₹]*([+-]?[\d,]+\.?\d*)', text, re.IGNORECASE)
            if m: updated["cashflow_from_operations"] = self._parse_number(m.group(1))

        return updated

    @staticmethod
    def _parse_number(s: str) -> float:
        """Parse Indian-formatted numbers."""
        try:
            return float(s.replace(',', '').strip())
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _normalize_date(s: str) -> str:
        """Convert DD/MM/YYYY or DD-MM-YYYY to YYYY-MM-DD."""
        try:
            parts = re.split(r'[/-]', s)
            if len(parts) == 3:
                d, m, y = parts
                return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
        except Exception:
            pass
        return s
