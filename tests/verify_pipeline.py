import os
import json
import fitz # type: ignore
from dotenv import load_dotenv
from layer2.layer2_processor import IntelliCreditPipeline

load_dotenv()

def create_dummy_pdf(filename: str, text: str):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(fitz.Point(50, 50), text)
    doc.save(filename)
    doc.close()

def main():
    print("Generating dummy test files for all SRC keys...")
    
    # 1. SRC_BANK (Structured)
    bank_text = '''
    State Bank of India Statement
    Account No. XXXX XXXX 4521
    Sanctioned Limit: Rs. 4,00,00,000
    '''
    create_dummy_pdf("sbi_statement_12m.pdf", bank_text)
    
    # 2. SRC_FS (Unstructured Financials)
    fs_text = '''
    M/s Shah & Associates Notes to Accounts
    For the Financial Year FY24
    Net Profit after tax stood at Rs 87.32 Lakhs.
    Total Assets are 1243.7 Lakhs.
    '''
    create_dummy_pdf("financials_FY24.pdf", fs_text)

    # 3. SRC_GST (Structured Tax)
    gst_text = '''
    Form GSTR-3B
    GSTIN: 24AABCR1234F1Z5
    Registration Status: Active
    '''
    create_dummy_pdf("gstr3b_FY24.pdf", gst_text)
    
    # 4. SRC_ITR (Semi-Structured Tax)
    itr_text = '''
    ITR-6 Form
    PAN: AABCR1234F
    Assessment Year AY2024-25
    '''
    create_dummy_pdf("itr6_FY24.pdf", itr_text)
    
    # 5. SRC_BMM, SRC_RAT, SRC_SHP, SRC_AR
    create_dummy_pdf("board_minutes_2024.pdf", "Board Resolution passed on 14th July.")
    create_dummy_pdf("crisil_rating_2024.pdf", "CRISIL Rating: BBB-")
    create_dummy_pdf("shareholding_Q3.pdf", "Promoter Holding: 65%")
    create_dummy_pdf("annual_report_FY24.pdf", "Annual Report FY24")
    
    print("Files generated. Initializing Intelli-Credit Pipeline...")
    pipeline = IntelliCreditPipeline()
    
    print("Running extraction...")
    
    target_files = [
        "sbi_statement_12m.pdf", 
        "financials_FY24.pdf",
        "gstr3b_FY24.pdf",
        "itr6_FY24.pdf",
        "board_minutes_2024.pdf",
        "crisil_rating_2024.pdf",
        "shareholding_Q3.pdf",
        "annual_report_FY24.pdf"
    ]
    
    try:
        result = pipeline.process_files(target_files)
        
        output_json = result.model_dump_json(indent=2)
        print(f"EXTRACTION SUCCESSFUL! Generated {len(output_json.splitlines())} lines of JSON.")
        
        with open("layer2_test_output.json", "w", encoding="utf-8") as f:
            f.write(output_json)
            
        print("Saved full output to layer2_test_output.json")
        
    except Exception as e:
        print(f"Pipeline Failed: {e}")
        
    finally:
        for f in target_files:
            if os.path.exists(f):
                os.remove(f)

if __name__ == "__main__":
    main()
