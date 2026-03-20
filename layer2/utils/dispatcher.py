import fitz # PyMuPDF
import os
import hashlib
from typing import Dict, Any, Tuple

class DocumentDispatcher:
    """
    Handles initial ingestion, normalization, and routing of N uploads.
    """
    SUPPORTED_EXTENSIONS = {'.pdf', '.csv', '.xlsx'}
    
    # Heuristics to map physical files to the sample.json SRC keys
    KEYWORD_MAPPING = {
        "SRC_GST": ["gstr", "gst", "gstr-3b", "gstr-1", "gstr3b", "gstr1"],
        "SRC_ITR": ["itr", "income tax", "computation", "acknowledgement"],
        "SRC_BANK": ["statement", "sbi", "hdfc", "icici", "axis", "kotak", "bank"],
        "SRC_FS": ["financials", "balance sheet", "p&l", "profit and loss", "audit report"],
        "SRC_AR": ["annual report", "directors report", "cashflow", "cash flow"],
        "SRC_BMM": ["board minutes", "resolution", "bmm"],
        "SRC_RAT": ["rating", "crisil", "icra", "care", "india ratings"],
        "SRC_SHP": ["shareholding", "shp", "promoter holding", "share pattern"],
        "SRC_ALM": ["alm", "asset liability", "alco", "maturity profile", "liquidity gap"],
        "SRC_BRP": ["borrowing profile", "debt schedule", "credit facilities", "lender list", "borrowing"],
        "SRC_PRT": ["portfolio", "par report", "collection efficiency", "pool performance", "gnpa", "nnpa"],
        "SRC_ESG": ["sustainability", "esg", "climate", "carbon", "greenhouse", "emissions", "environment"],
        "SRC_ANR": ["annual return", "mgt-7", "mgt7", "aoc-4", "aoc4", "form 20b", "mca return"],
    }

    @staticmethod
    def get_file_hash(filepath: str) -> str:
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return "sha256:" + sha256_hash.hexdigest()[:6] # Shortened for JSON brevity

    @classmethod
    def analyze_pdf(cls, filepath: str) -> Tuple[int, bool, str]:
        """
        Returns (num_pages, is_scanned, first_page_text)
        Determines if a PDF is scanned based on text/area ratio.
        """
        doc = fitz.open(filepath)
        num_pages = len(doc)
        
        if num_pages == 0:
            return 0, False, ""
            
        first_page = doc[0]
        text = first_page.get_text()
        
        # Heuristic: If we pull less than 50 chars from the first page of a document,
        # it's highly likely to be a scanned image encapsulated in PDF.
        is_scanned = len(text.strip()) < 50
            
        doc.close()
        return num_pages, is_scanned, text.lower()

    @classmethod
    def classify_document(cls, filename: str, first_page_text: str = "") -> str:
        """
        Attempts to map a file to its SRC_* key in sample.json using filename and content.
        """
        search_corpus = (filename + " " + first_page_text).lower()
        
        for doc_key, keywords in cls.KEYWORD_MAPPING.items():
            if any(kw in search_corpus for kw in keywords):
                return doc_key
                
        return "SRC_UNKNOWN" # Requires human-in-the-loop mapping

    @classmethod
    def ingest(cls, filepath: str) -> Dict[str, Any]:
        """
        Main entry point. Normalizes the input file and determines routing.
        """
        filename = os.path.basename(filepath)
        ext = os.path.splitext(filename)[1].lower()
        
        if ext not in cls.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file format: {ext}")
            
        file_hash = cls.get_file_hash(filepath)
        
        meta = {
            "filename": filename,
            "filepath": filepath,
            "file_hash": file_hash,
            "extension": ext,
            "ocr_required": False,
            "pages": 1, 
        }

        first_page_text = ""
        
        if ext == '.pdf':
            pages, is_scanned, first_page_text = cls.analyze_pdf(filepath)
            meta["pages"] = pages
            meta["ocr_required"] = is_scanned # Flag this vector for EasyOCR / Groq Vision
            
        meta["target_key"] = cls.classify_document(filename, first_page_text)
        
        return meta
