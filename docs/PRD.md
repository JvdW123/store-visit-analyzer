# Product Requirements Document (PRD)
# Store Visit Analyzer — Tool A: Data Consolidation & Cleaning

**Version:** 2.1 | **Date:** 17 February 2026 | **Status:** Approved

---

## 1. Overview

### 1.1 What is this tool?
A Streamlit web application that consolidates any number of raw shelf analysis Excel files from supermarket store visits into a single clean master dataset. Uses a hybrid approach: deterministic code handles ~80-90% of cleaning, Claude Sonnet API handles the remaining ~10-20% requiring semantic judgment.

### 1.2 Why does it exist?
Fruity Line conducts store visits across retailers to analyze chilled juice and smoothie shelf positioning, assortment, pricing, and competitive dynamics. Each visit produces an Excel file, but these files have inconsistent structures, naming conventions, and data quality. Manual consolidation is time-consuming and error-prone.

### 1.3 Design Principles
- **Any file, any mess:** Handle Excel files that are messy in unpredictable ways — not just the files used during development.
- **Deterministic first, LLM second:** Code handles everything with clear rules. LLM only touches what requires semantic judgment.
- **Graceful degradation:** Without an API key, the tool still produces ~80-90% clean output with ambiguous cells flagged for manual review.
- **Country-agnostic from day one:** UK (GBP) first, but the data model supports any country and currency.
- **Blank means we don't know:** If data is unavailable or ambiguous, the cell is blank. "Unknown" is never used as a value.

---

## 2. User Stories

| # | As a... | I want to... | So that... |
|---|---------|-------------|-----------|
| 1 | Analyst | Upload any number of raw store visit Excel files and get one clean master file | I don't have to manually copy-paste and normalize data across files |
| 2 | Analyst | Upload new store visit files and append them to an existing master | I can incrementally build my dataset without reprocessing everything |
| 3 | Analyst | See a data quality report showing what was cleaned and what needs review | I trust the output and can manually fix remaining issues |
| 4 | Analyst | Set the exchange rate for currency conversion | Price comparisons across countries are accurate |
| 5 | Colleague | Run the tool without technical knowledge | The UI is self-explanatory and doesn't require coding skills |
| 6 | Analyst | Use the tool even without an API key | I still get a mostly-clean output with flagged items |

---

## 3. Scope

### 3.1 In scope (v1)
- Upload & parse any number of raw Excel files (.xlsx)
- Filename parsing → Retailer, City, Store Format
- Structure detection → header rows, data columns, merged sections, embedded images (skipped)
- Column mapping → raw column names to master schema
- Data normalization → deterministic rules + LLM for unknowns
- Inference → Juice Extraction Method, Processing Method, HPP Treatment
- Typo correction
- Currency handling → local currency preserved, EUR conversion via configurable exchange rate
- Numeric conversion → text-stored numbers to proper types
- Price per Liter recalculation
- Incremental append → new files to existing master, with replace/skip dialog on store overlap
- Data quality report
- Download consolidated master as .xlsx
- Streamlit UI with drag-and-drop, progress indicators, data preview

### 3.2 Out of scope (v1)
- Analysis workbook generation (future Tool B)
- PowerPoint deck generation (future Tool B)
- Multi-country data (UK only for v1, but schema supports expansion)
- Cloud deployment, authentication, database backend

---

## 4. UI Flow

```
┌─────────────────────────────────────────────────────┐
│  STORE VISIT ANALYZER — Data Consolidation Tool     │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ⚙️ Settings                                        │
│  ├── API Key: [________________] (optional)         │
│  ├── Exchange Rate GBP→EUR: [1.17] (auto-fetched)   │
│  │   ℹ️ Rate fetched from ECB. Edit to override.     │
│  └── Country: [United Kingdom ▼]                    │
│                                                     │
│  📁 Upload Files                                    │
│  ├── Raw Excel files: [drag & drop area]            │
│  └── Existing master (optional): [drag & drop]      │
│                                                     │
│  ── After upload ──                                 │
│                                                     │
│  📋 Step 1: File Metadata (editable table)          │
│  │  File               | Retailer    | City    | Format  │
│  │  aldi_fulham...xlsx  | Aldi        | Fulham  |         │
│  │  ...                 | ...         | ...     | ...     │
│  └── [Confirm & Process ▶]                          │
│                                                     │
│  ── After processing ──                             │
│                                                     │
│  📊 Step 2: Processing Summary                      │
│  ├── Files processed: 11                            │
│  ├── Total SKUs: 906                                │
│  ├── Cleaned deterministically: 812 (89.6%)         │
│  ├── Cleaned by LLM: 78 (8.6%)                     │
│  ├── Flagged for review: 16 (1.8%)                  │
│  └── [View Details ▼]                               │
│                                                     │
│  📋 Step 3: Data Preview (scrollable table)         │
│  └── [Highlight flagged cells in yellow]            │
│                                                     │
│  💾 Download                                        │
│  └── [Download Master Excel ⬇]                      │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### User Flow Detail

```
1. USER OPENS APP → Settings sidebar: API key, exchange rate, country

2. USER UPLOADS FILES → Drag & drop raw Excel files + optional existing master

3. FILENAME PARSING & CONFIRMATION
   ├── Auto-parsed Retailer, City, Format displayed in editable table
   ├── User reviews and corrects if needed
   └── Confirms to proceed

4. PROCESSING (automated, with progress bar)
   ├── Step 1: Deterministic processing per file
   ├── Step 2: LLM processing (if API key provided)
   ├── Step 3: Final validation
   │   ├── Combine all files
   │   ├── If appending to master: check for store overlaps
   │   │   └── For each overlap: ask user "Replace or Skip?"
   │   └── Generate quality report
   └── Display processing summary

5. REVIEW & DOWNLOAD → Data preview with flags → Download master Excel
```

---

## 5. Resolved Design Decisions

| # | Decision |
|---|---------|
| 1 | All UK stores = GBP regardless of how raw files label price columns |
| 2 | Shelf Location normalization is LLM-driven (high variability makes deterministic rules brittle) |
| 3 | Deduplication at store visit level: Retailer + City + Store Format. On overlap, user chooses replace or skip |
| 4 | Product Name left blank if not in source data |
| 5 | Merged section metadata overrides per-row values when per-row is blank |
| 6 | Exchange rate auto-fetched from API, pre-filled in UI, user can override. Fallback to hardcoded default |
| 7 | All unknown/ambiguous values = blank. "Unknown" never used as a value |

---

## 6. Development Phases

| Phase | What | Test |
|-------|------|------|
| 1 | Core file reading & structure detection | Extract raw data from all test files |
| 2 | Filename parsing & column mapping | Correctly parse all test filenames and map columns |
| 3 | Deterministic normalization & numeric conversion | Known values normalize correctly, numbers convert, prices recalculate |
| 4 | LLM integration | Edge cases resolved, Juice Extraction Method inferred |
| 5 | Merge, dedup & quality report | Combining works, append deduplicates, report is accurate |
| 6 | Streamlit UI | End-to-end: upload → process → preview → download |
| 7 | Output formatting & polish | Client-ready Excel output |

Each phase is tested against ground truth data (see `tests/` directory and TESTING.md).
