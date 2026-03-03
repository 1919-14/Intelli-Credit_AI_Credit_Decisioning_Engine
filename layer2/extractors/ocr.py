import os
import fitz # PyMuPDF
import easyocr
import io
from PIL import Image
from typing import Dict, Any, List

class OCRFallback:
    """
    Handles scanned documents or handles HTTP 429/1K TPM limit fallbacks from Groq.
    """
    def __init__(self, use_gpu: bool = True):
        # Initialize EasyOCR reader (Downloads models on first run)
        self.reader = easyocr.Reader(['en', 'hi'], gpu=use_gpu) 
        
    def pdf_to_images(self, filepath: str) -> List[Image.Image]:
        """
        Converts a PDF file to a list of PIL Images (one per page) using PyMuPDF.
        """
        images = []
        doc = fitz.open(filepath)
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2)) # 2x zoom for better OCR
            img_bytes = pix.tobytes("png")
            images.append(Image.open(io.BytesIO(img_bytes)))
            
        doc.close()
        return images
        
    def extract_text(self, filepath: str) -> Dict[str, Any]:
        """
        Takes a scanned PDF and returns the OCR'd text along with a confidence metric.
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")
            
        images = self.pdf_to_images(filepath)
        full_text_blocks = []
        confidences = []
        
        for idx, img in enumerate(images):
            # EasyOCR expects a numpy array or file path. PIL Image -> bytes
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()
            
            # paragraph=True groups words into paragraphs for better LLM context
            results = self.reader.readtext(img_byte_arr, paragraph=True)
            
            page_text = ""
            for res in results:
                # res is ([bounding box], text, confidence) if paragraph=False
                # if paragraph=True, res is (bbox, text)
                # We'll use paragraph=False internally to get confidence, but group it ourselves
                pass
                
        # EasyOCR implementation detail: paragraph=True drops confidence scores.
        # We need confidence scores for sample.json.
        
        for idx, img in enumerate(images):
             img_byte_arr = io.BytesIO()
             img.save(img_byte_arr, format='PNG')
             img_bytes = img_byte_arr.getvalue()
             
             raw_results = self.reader.readtext(img_bytes)
             
             page_text = ""
             for bbox, text, conf in raw_results:
                 page_text += text + " "
                 confidences.append(conf)
                 
             full_text_blocks.append({"page": idx + 1, "text": page_text.strip()})
             
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        return {
            "blocks": full_text_blocks,
            "ocr_confidence_score": round(avg_confidence, 4),
            "pages_processed": len(images)
        }
