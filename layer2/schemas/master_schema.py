# Master extraction schema — the EXACT JSON structure the LLM fills in.
# Each document adds its data to this template progressively.
# The LLM is also instructed to add any extra fields it discovers.

MASTER_SCHEMA = {
    # ─── GST Data (from GSTR-1 / GSTR-3B) ───
    "gstin": None,
    "legal_name": None,
    "trade_name": None,
    "gst_filing_status": None,
    "gst_filing_period": None,
    "gst_filing_date": None,
    "total_taxable_value_domestic": None,
    "total_taxable_value_exports": None,
    "total_igst": None,
    "total_cgst": None,
    "total_sgst": None,
    "total_tax_collected": None,
    "num_b2b_invoices": None,
    "num_amendments": None,
    "itc_available_total": None,
    "itc_claimed_total": None,
    "b2b_invoices": [],
    "export_invoices": [],

    # ─── ITR Data (from ITR-3 / ITR-6) ───
    "pan_number": None,
    "assessee_name": None,
    "assessment_year": None,
    "financial_year": None,
    "itr_filing_date": None,
    "nature_of_business": None,
    "gross_receipts": None,
    "total_expenses": None,
    "net_profit_from_business": None,
    "other_income": None,
    "gross_total_income": None,
    "total_deductions_vi_a": None,
    "taxable_income": None,
    "total_tax_payable": None,
    "tax_paid_advance_tds": None,
    "depreciation": None,
    "interest_paid": None,
    "house_property_loss": None,
    "section_80c_deduction": None,
    "section_80d_deduction": None,
    "donations_80g": None,

    # ─── Financial Statements / Annual Report Data ───
    "company_name": None,
    "cin": None,
    "fs_financial_year": None,
    "industry": None,
    "revenue_from_operations": None,
    "fs_other_income": None,
    "total_revenue": None,
    "fs_total_expenses": None,
    "ebitda": None,
    "fs_depreciation": None,
    "profit_before_tax": None,
    "tax_expense": None,
    "profit_after_tax": None,
    "total_assets": None,
    "total_liabilities": None,
    "net_worth": None,
    "total_debt": None,
    "current_assets": None,
    "current_liabilities": None,
    "cash_and_equivalents": None,
    "trade_receivables": None,
    "trade_payables": None,
    "inventory": None,
    "share_capital": None,
    "reserves_and_surplus": None,
    "director_remuneration": None,
    "loans_from_directors": None,
    "num_employees": None,
    "auditor_name": None,
    "audit_opinion": None,
    "dividend_declared": None,
    "related_party_transactions_total": None,

    # ─── Cashflow Statement Data ───
    "cashflow_from_operations": None,
    "cashflow_from_investing": None,
    "cashflow_from_financing": None,
    "net_cashflow": None,

    # ─── Bank Statement Data ───
    "bank_name": None,
    "bank_branch": None,
    "account_number": None,
    "account_type": None,
    "statement_from_date": None,
    "statement_to_date": None,
    "opening_balance": None,
    "closing_balance": None,
    "total_credits": None,
    "total_debits": None,
    "num_credit_transactions": None,
    "num_debit_transactions": None,
    "avg_monthly_balance": None,
    "min_balance": None,
    "max_balance": None,
    "od_cc_limit": None,
    "num_cheque_bounces": None,
    "num_emi_payments": None,
    "total_emi_amount": None,
    "num_gst_payments": None,
    "total_gst_paid": None,
    "salary_credits_total": None,
    "large_cash_deposits": [],
    "large_cash_withdrawals": [],

    # ─── ALM (Asset-Liability Management) Data ───
    "alm_period": None,
    "alm_short_term_assets": None,
    "alm_medium_term_assets": None,
    "alm_long_term_assets": None,
    "alm_short_term_liabilities": None,
    "alm_medium_term_liabilities": None,
    "alm_long_term_liabilities": None,
    "liquidity_gap_1m": None,
    "liquidity_gap_3m": None,
    "liquidity_gap_6m": None,
    "liquidity_gap_1y": None,
    "cumulative_liquidity_gap": None,
    "alco_minutes_date": None,
    "interest_rate_sensitivity": None,
    "alm_maturity_buckets": [],

    # ─── Shareholding Pattern Data ───
    "promoter_holding_pct": None,
    "public_holding_pct": None,
    "institutional_holding_pct": None,
    "foreign_holding_pct": None,
    "total_shares_outstanding": None,
    "pledged_shares_pct": None,
    "top_shareholders": [],
    "shareholding_period": None,

    # ─── Borrowing Profile Data ───
    "total_outstanding_borrowings": None,
    "secured_borrowings": None,
    "unsecured_borrowings": None,
    "short_term_borrowings": None,
    "long_term_borrowings": None,
    "avg_cost_of_funds": None,
    "debt_service_coverage_ratio": None,
    "interest_coverage_ratio": None,
    "latest_credit_rating": None,
    "rating_agency": None,
    "existing_lenders": [],
    "credit_facilities": [],
    "total_sanctioned_limits": None,
    "total_utilized_limits": None,

    # ─── Portfolio Cuts / Performance Data ───
    "portfolio_aum": None,
    "gnpa_pct": None,
    "nnpa_pct": None,
    "par_30_pct": None,
    "par_60_pct": None,
    "par_90_pct": None,
    "yield_on_portfolio": None,
    "cost_of_funds_portfolio": None,
    "nim_pct": None,
    "collection_efficiency_pct": None,
    "disbursement_current_fy": None,
    "portfolio_vintage_months": None,
    "write_off_pct": None,
    "recovery_rate_pct": None,
    "portfolio_concentration_top10_pct": None,

    # ─── ESG Risk & Sustainability Data (from Climate/Sustainability Reports) ───
    "carbon_footprint_mt": None,              # Metric tonnes CO2 equivalent
    "scope1_emissions": None,                 # Direct emissions
    "scope2_emissions": None,                 # Indirect (energy) emissions
    "scope3_emissions": None,                 # Value chain emissions
    "esg_transition_risk": None,              # Low / Medium / High / Critical
    "esg_physical_risk": None,                # Low / Medium / High
    "sustainability_rating": None,            # e.g. "AA", "BBB", rating body name
    "sustainability_rating_agency": None,     # e.g. "MSCI", "Sustainalytics"
    "green_financing_eligible": None,         # True / False
    "renewable_energy_pct": None,             # % of energy from renewables
    "water_usage_intensity": None,            # Litres per unit of revenue
    "waste_recycled_pct": None,               # % waste recycled
    "social_compliance_score": None,          # Labour, community metrics
    "governance_board_independence_pct": None, # % independent directors (ESG)
    "esg_report_period": None,                # e.g. "FY2024-25"
    "esg_key_risks": [],                      # Array of risk descriptions

    # ─── Annual Return / Statutory Compliance Data (MCA MGT-7 / AOC-4) ───
    "annual_return_filed": None,              # True / False
    "annual_return_filing_date": None,        # Date of filing
    "annual_return_year": None,               # e.g. "2024-25"
    "registered_office_address": None,        # As per MCA
    "active_directors_list": [],              # Array of director names
    "total_directors_count": None,
    "independent_directors_count": None,
    "declared_indebtedness": None,            # Total indebtedness as per Annual Return
    "declared_paid_up_capital": None,
    "declared_reserves": None,
    "mca_company_status": None,               # Active / Under Liquidation etc.
    "charges_registered": None,               # Number of charges on MCA
    "statutory_compliance_flags": [],         # Array of compliance issues found
}
