# Normalization Rules & Processing Logic
# Defines all deterministic cleanup rules and the LLM integration approach

---

## Processing Pipeline Overview

```
STEP 1 — DETERMINISTIC (no LLM, instant)
├── Read Excel, skip images, find header rows
├── Detect merged section separators, extract section metadata
├── Extract all data rows into raw DataFrame
├── Parse filename → Retailer, City, Format
├── Map columns to master schema (exact + fuzzy match)
├── Apply known normalization lookup tables (below)
├── Convert text → numbers for numeric columns
├── Recalculate Price per Liter, apply currency conversion
├── Flag values that could NOT be resolved deterministically
└── Output: partially clean DataFrame + flagged items list

STEP 2 — LLM (Claude Sonnet, one API call per file)
├── Send ONLY flagged/ambiguous items:
│   ├── Filename metadata (if fuzzy match confidence was low)
│   ├── Column names that couldn't be auto-mapped
│   ├── Categorical values not in known lookup tables
│   ├── Shelf Location values (always LLM-normalized)
│   ├── Rows needing Juice Extraction Method inference
│   ├── Rows with ambiguous Processing Method or HPP
│   └── Suspected typos (fuzzy match score below threshold)
├── Sonnet returns structured JSON
├── Validate response (values must be in valid sets)
└── Apply validated decisions to DataFrame

STEP 3 — DETERMINISTIC (no LLM, instant)
├── Final validation pass
├── Generate data quality report
├── Format and export to Excel
└── Output: clean master .xlsx + quality report
```

---

## Decision Matrix: Deterministic vs. LLM

| Processing Step | Approach | Rationale |
|----------------|----------|-----------|
| Excel reading & image skipping | **Deterministic** | Mechanical: openpyxl handles this |
| Structure detection (header rows, merged cells) | **Deterministic** | Pattern-based: scan for header-like rows, detect merged ranges |
| Section metadata extraction | **Deterministic** | Parse merged cell text by splitting on "\|" delimiter |
| Filename → Retailer/City/Format | **Deterministic** (known-value lookup + fuzzy match) | Retailers are a finite set. LLM fallback only if confidence < threshold |
| Column name mapping | **Deterministic** (exact + fuzzy match), LLM fallback | Most names are recognizable. Only novel names need LLM |
| Known categorical normalization | **Deterministic** (lookup tables below) | Explicit rules, fast and reliable |
| Unknown categorical values | **LLM** | Requires semantic understanding |
| Shelf Location normalization | **LLM** (except exact matches to valid categories) | High variability, unpredictable phrasing |
| Juice Extraction Method inference | **LLM** | Must read across Processing Method + Claims + Notes |
| Processing Method for unknowns | **LLM** | Edge cases need judgment |
| HPP Treatment for contradictions | **LLM** | Conflicting signals need resolution |
| Typo detection & correction | **Deterministic** (fuzzy match, threshold), LLM for confirmation | Levenshtein distance catches most typos |
| Numeric conversion | **Deterministic** | Regex + type casting |
| Price per Liter recalculation | **Deterministic** | Pure math |
| Currency conversion | **Deterministic** | Multiplication by exchange rate |
| Confidence Score normalization | **Deterministic** | Rule-based scale detection |
| Deduplication | **Deterministic** | Composite key matching |
| Quality report | **Deterministic** | Counting and validation |

---

## Deterministic Normalization Lookup Tables

Any value NOT found in these tables is flagged for the LLM.
All matching is case-insensitive. Leading/trailing whitespace is stripped before matching.

### Product Type (raw column: "Segment")
| Raw Value | Normalized |
|-----------|-----------|
| "Pure Juices", "Pure juices", "pure juices" | "Pure Juices" |
| "Smoothies", "smoothies", "smoothies " | "Smoothies" |
| "Shots", "shots" | "Shots" |
| "Other", "OTHER" | "Other" |
| null / blank | blank |

### Need State (raw column: "Sub-segment")
| Raw Value | Normalized |
|-----------|-----------|
| "Indulgence", "Indulgent", "indulgence" | "Indulgence" |
| "Functional", "functional" | "Functional" |
| null / blank | blank |

### Branded/Private Label
| Raw Value | Normalized |
|-----------|-----------|
| "Branded", "branded" | "Branded" |
| "Private Label", "private label", "Pirvate lable" | "Private Label" |
| null / blank | blank |

### Processing Method
| Raw Value | Normalized |
|-----------|-----------|
| "Pasteurized", "pasteurised", "Pasteurised", "Flash pasteurised" | "Pasteurized" |
| "Cold-pressed", "Cold pressed", "Pressed" | "Cold Pressed" |
| "unpasteurised", "Unpasteurised", "Not pasteurised" | "Unpasteurized" |
| "Freshly Squeezed", "freshly squeezed" | "Freshly Squeezed" |
| "HPP", "HPP Treated", "HPP Treatment" | "HPP" |
| "Unknown", "unknown" | blank |
| null / blank | blank |

**Additional rule:** If HPP Treatment = "Yes" AND Processing Method is blank → set Processing Method = "HPP"

### HPP Treatment
| Raw Value | Normalized |
|-----------|-----------|
| "Yes", "yes", "HPP Treatment", "HPP Treated" | "Yes" |
| "No", "no" | "No" |
| "Pasteurized", "Pasteurised" | "No" |
| "Unknown", "Unkown", "unsure", "unknown" | blank |
| "Cold pressed ? Assumed" | blank |
| null / blank | blank |

### Packaging Type
| Raw Value | Normalized |
|-----------|-----------|
| "PET bottle", "PET Bottle", "pet bottle" | "PET Bottle" |
| "Tetra Pak", "Tetrapak", "tetra pak" | "Tetra Pak" |
| "Can", "can" | "Can" |
| "Carton", "Carton (Multi-pack)" | "Carton" |
| "Glass Bottle", "Glass bottle" | "Glass Bottle" |
| null / blank | blank |

### Shelf Level
| Raw Value | Normalized |
|-----------|-----------|
| "1st", "1st (Top)", "1", "Top", "top" | "1st" |
| "2nd", "2" | "2nd" |
| "3rd", "3" | "3rd" |
| "4th", "4" | "4th" |
| "5th", "5th (Bottom)", "5", "Bottom", "bottom" | "5th" |
| "6th", "6" | "6th" |
| "Unkown", "Unknown", "unknown" | blank |
| null / blank | blank |

### Stock Status
| Raw Value | Normalized |
|-----------|-----------|
| "In Stock", "in stock" | "In Stock" |
| "Out of Stock", "out of stock" | "Out of Stock" |
| null / blank | blank (do NOT assume "In Stock") |

### Shelf Location
**LLM-normalized.** Only exact matches to valid categories are handled deterministically:
- "Chilled Section" → "Chilled Section"
- "To-Go Section" → "To-Go Section"
- "To-Go Section — Shots" → "To-Go Section — Shots"
- "Meal Deal Section" → "Meal Deal Section"

All other non-blank values → send to LLM for classification.

---

## Numeric Conversion Rules

| Column | Target Type | Conversion Logic |
|--------|-------------|-----------------|
| Shelf Levels | Integer | Strip whitespace, convert. If fails → flag |
| Facings | Integer | Strip whitespace, convert. If non-numeric text (e.g. "Private Label") → flag as data error |
| Price (Local Currency) | Float (2dp) | Strip currency symbols (£, €), whitespace. Convert. |
| Packaging Size (ml) | Integer | Strip "ml", whitespace. Convert. |
| Est. Linear Meters | Float (1dp) | Strip whitespace. Convert. |
| Confidence Score | Integer | See special rules below |

### Confidence Score Normalization
1. If string contains "%" → strip "%", convert to float
2. If value is between 0 and 1 (exclusive) → multiply by 100
3. If value is between 1 and 100 → round to integer
4. If value > 100 or value < 0 → flag as data error, leave blank
5. null / blank → blank

### Price per Liter Calculation
Always recalculate — never trust raw values:
```
Price per Liter (EUR) = Price (EUR) / (Packaging Size (ml) / 1000)
```
If either Price or Packaging Size is missing → leave blank.

---

## Currency & Exchange Rate

- **Currency** derived from Country: UK → "GBP", France/Germany/NL → "EUR"
- **UK stores always GBP** regardless of raw file column labels
- **Price (EUR)** = Price (Local) × exchange rate (1.0 if already EUR)
- **Exchange rate** auto-fetched from API, user-overridable, logged in quality report

---

## LLM Call Specification

**Model:** Claude Sonnet (claude-sonnet-4-20250514)
**Calls per file:** 1 (all ambiguous items batched)
**Estimated cost per file:** ~$0.005-0.01

**Prompt template:**
```
You are a data cleaning assistant for supermarket shelf analysis data.

TASK: Resolve the following ambiguous data items. For each item, return the
normalized value from the allowed values list, or "" (blank) if you cannot
determine it with reasonable confidence. IMPORTANT: Never return "Unknown" —
if you are unsure, return blank.

MASTER SCHEMA VALID VALUES:
- Product Type: "Pure Juices", "Smoothies", "Shots", "Other"
- Need State: "Indulgence", "Functional"
- Branded/Private Label: "Branded", "Private Label"
- Processing Method: "Pasteurized", "HPP", "Unpasteurized", "Cold Pressed", "Freshly Squeezed"
- HPP Treatment: "Yes", "No"
- Packaging Type: "PET Bottle", "Tetra Pak", "Can", "Carton", "Glass Bottle"
- Juice Extraction Method: "Squeezed", "Cold Pressed", "From Concentrate"
- Stock Status: "In Stock", "Out of Stock"
- Shelf Level: "1st", "2nd", "3rd", "4th", "5th", "6th"
- Shelf Location: "Chilled Section", "To-Go Section", "To-Go Section — Shots", "Meal Deal Section"

ITEMS TO RESOLVE:
{flagged_items_json}

Return a JSON array where each element has:
- "row_index": the row index from the input
- "column": the column name
- "original_value": the original value
- "normalized_value": your decision (valid value or "" for blank)
- "reasoning": brief explanation (1 sentence)
```

**Fallback if no API key:** Skip LLM step. Output file has ambiguous cells highlighted in yellow with a "Needs Review" flag.
