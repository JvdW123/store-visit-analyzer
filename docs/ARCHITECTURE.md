# Technical Architecture
# File structure, module responsibilities, tech stack, and processing pipeline

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Language | Python 3.11+ | Core processing |
| UI | Streamlit | Web interface |
| Excel I/O | openpyxl | Read/write .xlsx with formatting |
| Data Processing | pandas | DataFrame operations |
| String Matching | thefuzz | Fuzzy matching for column names, typos |
| LLM API | anthropic SDK | Claude Sonnet for ambiguous items |
| HTTP | requests | Exchange rate API fetch |

---

## Project Structure

```
store-visit-analyzer/
├── .cursorrules                    # AI agent coding conventions
├── app.py                          # Streamlit entry point & UI layout
├── requirements.txt                # Python dependencies
├── README.md                       # Project overview & setup instructions
│
├── docs/                           # Documentation (read by AI agent as needed)
│   ├── PRD.md                      # Objectives, scope, user stories, UI flow
│   ├── SCHEMA.md                   # Master column definitions, types, valid values
│   ├── RULES.md                    # Normalization rules, deterministic vs LLM logic
│   ├── ARCHITECTURE.md             # This file
│   ├── FILENAME_CONFIG.md          # Known retailers, cities, parsing config
│   └── TESTING.md                  # Testing strategy & ground truth approach
│
├── config/                         # Configuration (imported by processing modules)
│   ├── schema.py                   # Master column order, types, required fields
│   ├── column_mapping.py           # Raw → Master column name mappings
│   ├── normalization_rules.py      # Lookup tables (Python dicts) from RULES.md
│   └── filename_config.py          # Known retailers, cities, format keywords
│
├── processing/                     # Core processing pipeline
│   ├── file_reader.py              # Excel reading, structure detection, image skip
│   ├── filename_parser.py          # Filename → Retailer / City / Format
│   ├── column_mapper.py            # Raw columns → Master schema mapping
│   ├── normalizer.py               # Deterministic normalization (lookup tables)
│   ├── llm_cleaner.py              # LLM API call for ambiguous items
│   ├── numeric_converter.py        # Text → number conversions
│   ├── price_calculator.py         # Price per liter + currency conversion
│   ├── merger.py                   # Combine files + incremental append + dedup
│   └── quality_checker.py          # Validation + quality report generation
│
├── utils/                          # Shared utilities
│   ├── fuzzy_match.py              # Fuzzy string matching helpers
│   └── excel_formatter.py          # Output Excel formatting (headers, colors, filters)
│
├── pages/                          # Streamlit multi-page (if needed)
│   └── (reserved for future Tool B)
│
└── tests/                          # Testing
    ├── test_file_reader.py         # Tests for file_reader.py
    ├── test_filename_parser.py     # Tests for filename_parser.py
    ├── test_column_mapper.py       # Tests for column_mapper.py
    ├── test_normalizer.py          # Tests for normalizer.py
    ├── test_numeric_converter.py   # Tests for numeric_converter.py
    ├── test_integration.py         # End-to-end pipeline test
    ├── compare_ground_truth.py     # Automated comparison against ground truth
    └── fixtures/                   # Test data files
        ├── (raw Excel test files)
        └── ground_truth_master.xlsx  # Expected correct output (created later)
```

---

## Module Responsibilities

### `app.py` — Streamlit UI
- Renders the UI layout (settings, upload, metadata table, progress, preview, download)
- Calls processing modules — contains NO business logic itself
- Handles user interactions (confirm metadata, replace/skip dialog)

### `config/schema.py`
- Defines `MASTER_COLUMNS`: ordered list of column names
- Defines `COLUMN_TYPES`: dict mapping column name → expected Python type
- Defines `REQUIRED_COLUMNS`: list of columns that must be populated
- Defines `VALID_VALUES`: dict mapping column name → set of valid values

### `config/column_mapping.py`
- Defines `EXACT_MATCHES`: dict of raw name → master name (case-insensitive)
- Defines `KNOWN_RENAMES`: dict of raw name → master name for semantic renames (e.g. "Segment" → "Product Type")

### `config/normalization_rules.py`
- Defines one dict per categorical column: `PRODUCT_TYPE_MAP`, `NEED_STATE_MAP`, etc.
- Each maps raw value (lowercase) → normalized value
- Values not in the dict → flagged for LLM

### `config/filename_config.py`
- Defines `KNOWN_RETAILERS`, `KNOWN_CITIES`, `FORMAT_KEYWORDS`
- Defines `FILENAME_SUFFIXES_TO_STRIP`: common suffixes to remove before parsing

### `processing/file_reader.py`
- **Input:** file path to .xlsx
- **Output:** raw DataFrame + metadata dict (header_row, section_info, etc.)
- Detects structure: finds header row, data start column
- Handles merged-cell section separators: extracts metadata, skips separator rows
- Skips embedded images
- Carries forward section metadata to data rows within each section

### `processing/filename_parser.py`
- **Input:** filename string
- **Output:** dict with `retailer`, `city`, `store_format`, `confidence`
- Strips known suffixes, searches for known retailers (longest match first)
- Fuzzy matches against known cities
- Extracts format keywords
- Returns confidence score; low confidence → flagged for user review

### `processing/column_mapper.py`
- **Input:** list of raw column names
- **Output:** dict mapping raw name → master name (or "unmapped")
- Tries exact match → known renames → fuzzy match → flags for LLM

### `processing/normalizer.py`
- **Input:** DataFrame with raw values
- **Output:** DataFrame with normalized values + list of flagged cells
- Applies lookup tables from config/normalization_rules.py
- Strips whitespace, lowercases for matching, returns proper-cased value
- Any value not in lookup → added to flagged list

### `processing/llm_cleaner.py`
- **Input:** list of flagged items (row_index, column, original_value, context)
- **Output:** list of resolved items (row_index, column, normalized_value, reasoning)
- Builds prompt from template + flagged items
- Calls Claude Sonnet API
- Validates response: all returned values must be in valid sets
- If no API key → returns empty list (graceful degradation)

### `processing/numeric_converter.py`
- **Input:** DataFrame
- **Output:** DataFrame with numeric columns converted + list of conversion errors
- Strips currency symbols, %, whitespace
- Handles Confidence Score scale normalization (0-1 vs 0-100)
- Logs conversion failures

### `processing/price_calculator.py`
- **Input:** DataFrame + exchange_rate
- **Output:** DataFrame with Currency, Price (EUR), Price per Liter (EUR) calculated
- Derives Currency from Country
- Calculates EUR prices
- Recalculates Price per Liter (never trusts raw values)

### `processing/merger.py`
- **Input:** list of cleaned DataFrames + optional existing master DataFrame
- **Output:** combined DataFrame + list of overlapping stores (for user dialog)
- Concatenates all new DataFrames
- If existing master: detects overlaps on Retailer + City + Store Format
- Returns overlap info for UI to display replace/skip dialog
- Applies user's replace/skip decisions

### `processing/quality_checker.py`
- **Input:** final DataFrame + processing logs
- **Output:** quality report dict (summary stats, normalization log, flagged items)
- Counts nulls per column
- Validates all categorical values are in valid sets
- Validates all numeric columns are numeric
- Compiles normalization audit trail

### `utils/fuzzy_match.py`
- Wraps thefuzz library
- `best_match(value, candidates, threshold=80)` → best match or None
- Used by column_mapper, normalizer, and filename_parser

### `utils/excel_formatter.py`
- Applies formatting to output Excel: headers, filters, column widths, number formats
- Highlights flagged cells in yellow
- Creates the three output sheets (SKU Data, Quality Report, Source Files)

---

## Data Flow

```
Raw Excel Files
       │
       ▼
  file_reader.py ──→ Raw DataFrame + section metadata
       │
       ▼
  filename_parser.py ──→ Retailer, City, Format (added as columns)
       │
       ▼
  column_mapper.py ──→ Columns renamed to master schema
       │
       ▼
  normalizer.py ──→ Known values normalized + flagged items list
       │
       ▼
  numeric_converter.py ──→ Text → numbers + conversion error list
       │
       ▼
  price_calculator.py ──→ Currency + EUR prices + Price/Liter
       │
       ▼
  llm_cleaner.py ──→ Flagged items resolved (if API key provided)
       │
       ▼
  merger.py ──→ All files combined (+ dedup against existing master)
       │
       ▼
  quality_checker.py ──→ Validation + quality report
       │
       ▼
  excel_formatter.py ──→ Formatted .xlsx output
```

---

## Key Design Constraints

1. **Modules are independent:** Each processing module takes a DataFrame in and returns a DataFrame out. They can be tested in isolation.
2. **Config-driven:** All rules, mappings, and lookups live in config/. Processing code imports from config — never hardcodes values.
3. **LLM is optional:** Every module works without llm_cleaner.py. The pipeline just skips the LLM step and flags items instead.
4. **One API call per file:** All flagged items for a file are batched into a single Sonnet call.
5. **No database:** Files in, files out. State is in the Excel files.
