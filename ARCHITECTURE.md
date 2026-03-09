# 🧠 Intelli-Credit System Architecture

## Overview

The Intelli-Credit platform is built using a **layered AI architecture** designed to process financial documents, extract insights, perform risk analysis, and generate a Credit Appraisal Memorandum (CAM).

The system follows an **8-layer pipeline**, ensuring modular processing and strong governance controls.

---

## High-Level Architecture

```

User Upload
↓
Document Ingestion
↓
Extraction & Validation
↓
Financial Cross-Triangulation
↓
Feature Engineering
↓
AI Risk Engine
↓
Human Decision Layer
↓
CAM Generation
↓
Governance Dashboard

```
## 🔄 System Architecture & Data Flow

Our system processes applications through a rigorous 8-Layer Pipeline. 
Below is a high-level mapping of how an application journeys from initial document upload through to final decisioning and governance logging.

```mermaid
flowchart TD
    %% Define Styles
    classDef default fill:#1e293b,stroke:#3b82f6,stroke-width:2px,color:#f8fafc;
    classDef userAction fill:#3b82f6,stroke:#1e40af,stroke-width:2px,color:#fff;
    classDef aiProcess fill:#8b5cf6,stroke:#5b21b6,stroke-width:2px,color:#fff;
    classDef db fill:#0f172a,stroke:#0f172a,stroke-width:2px,color:#94a3b8,stroke-dasharray: 5 5;
    classDef final fill:#10b981,stroke:#047857,stroke-width:2px,color:#fff;
    classDef hitl fill:#f59e0b,stroke:#b45309,stroke-width:2px,color:#fff;

    %% Data Ingestion
    Start([User Initiates Application]):::userAction
    L1["Layer 1: Data Ingestion & Classification\n(PDF, CSV, Excel, Images)"]:::default
    HITL_L1{"User Confirm Docs\n(HITL Checkpoint)"}:::hitl
    HITL_L2[Pipeline Halted\nApplication Rejected]:::default
    
    Start -->|Uploads File Batch| L1
    L1 --> HITL_L1
    HITL_L1 -->|Verified| L2
    HITL_L1 -->|Corrects Classification| L1

    %% Initial Extraction & Validation
    L2[Layer 2: Extraction & Fraud Validation\nGSTIN checks, Date matching]:::default
    L3[Layer 3: Cross-Triangulation\nReconcile Bank ↔ GST ↔ ITR]:::default
    
    L2 --> L3

    %% Feature Engine & Scoring
    L4["Layer 4: Feature Engine & NLP Analysis\n(Derive 120+ Ratios, LLM summarization)"]:::aiProcess
    HITL_L4{Officer Adjustments\nOverride Financials?}:::hitl
    
    L3 --> L4
    L4 --> HITL_L4
    
    HITL_L4 -->|Confirm Features| L5
    
    L5[Layer 5: Federated AI Risk Engine & SHAP\nGroq + Tavily gen Risk/5Cs]:::aiProcess
    HITL_L5{Hard Reject Flagged?}:::hitl
    
    L5 --> HITL_L5
    HITL_L5 -->|Policy Violated| L5_Halt([Pipeline Halted\nApplication Rejected]):::default
    HITL_L5 -->|Bypass/Clean| L6

    %% Final Decision & CAM
    L6["Layer 6: Credit Decision Override & Sign-off\n(Final Human Review)"]:::hitl
    L7["Layer 7: Automated CAM Generation\n(PDF Report Creation)"]:::aiProcess
    DB[(MySQL/SQLite Database)]:::db
    
    L6 --> L7
    L6 -.->|Updates Risk & Decision| DB
    L7 -.->|Generates Audit JSON/PDF| DB
    
    L7 --> Complete([Application Completed]):::final

    %% Governance
    Complete --> L8
    L8[Layer 8: Regulator Dashboard\nModel Drift, Performance, Live Metric Tracking]:::default
    L8 -.->|Reads Telemetry| DB
```



---

## Layer 1 — Document Ingestion & Classification

The system accepts multiple input formats including:

- PDF documents
- scanned images
- CSV files
- Excel spreadsheets

Documents are automatically classified based on type:

- bank statements
- GST returns
- financial statements
- legal records

Users verify document classification before processing continues.

---

## Layer 2 — Document Extraction & Validation

The extraction engine parses structured and unstructured financial data.

Processes include:

- OCR for scanned documents
- rule-based extraction
- schema validation
- GSTIN verification
- date validation

Extracted data is normalized into structured JSON schemas.

---

## Layer 3 — Cross-Triangulation

Financial data from different sources is cross-verified.

Examples include:

- GST turnover vs bank credits
- ITR revenue vs financial statements
- transaction patterns vs reported revenue

This helps detect:

- revenue inflation
- circular trading
- inconsistencies in financial reporting

---

## Layer 4 — Feature Engineering & NLP

This layer derives over **100 financial indicators** including:

- profitability ratios
- leverage ratios
- liquidity ratios
- revenue growth metrics

Natural Language Processing analyzes qualitative text such as:

- auditor notes
- management commentary
- regulatory disclosures

---

## Layer 5 — Federated AI Risk Engine

The AI engine evaluates borrower risk using:

- financial indicators
- external research signals
- qualitative insights

Outputs include:

- risk score
- probability of default
- five Cs of credit assessment

Explainability mechanisms highlight the factors influencing each score.

---

## Layer 6 — Human-in-the-Loop Decision Layer

Credit officers review AI recommendations.

Users may:

- approve AI decisions
- modify loan limits
- override recommendations

Overrides require justification and digital authorization.

---

## Layer 7 — CAM Generation

The system generates a **Credit Appraisal Memorandum (CAM)** containing:

- borrower details
- financial analysis
- AI insights
- credit decision summary

Reports can be exported as:

- PDF
- DOCX
- JSON

---

## Layer 8 — Governance & Monitoring

The governance layer tracks system performance and model behavior.

Key monitoring functions include:

- model performance metrics
- risk distribution monitoring
- decision history logging
- model drift detection

This ensures transparency, accountability, and long-term system reliability.

---

## Technology Stack

### Backend
- Python
- Flask
- Flask-SocketIO
- Groq API
- Tavily Web Search API

### Data Layer
- MySQL / SQLite
- JSON schemas
- structured financial datasets

### Frontend
- HTML / CSS / JavaScript
- Chart.js
- DataTables

---

## Design Principles

The Intelli-Credit architecture follows these core principles:

1. **Explainability** — AI decisions must be transparent.
2. **Human Oversight** — final credit decisions remain human-controlled.
3. **Modularity** — each processing stage operates independently.
4. **Scalability** — system can handle large document volumes.
5. **Governance** — audit trails and monitoring ensure responsible AI deployment.

---

## Conclusion

The Intelli-Credit architecture combines **document intelligence, explainable AI, financial analytics, and governance controls** to build a comprehensive credit decisioning system capable of modernizing corporate lending workflows.