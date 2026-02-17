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

| # | Processing Step | Approach | Model | Rationale |
|---|----------------|----------|-------|-----------|
| 1 | Excel reading & image skipping | **Code only** | — | Mechanical: openpyxl handles this |
| 2 | Structure detection (header rows, merged cells) | **Code only** | — | Pattern-based: scan for header-like rows, detect merged ranges |
| 3 | Section metadata extraction | **Code only** | — | Parse merged cell text by splitting on "\|" delimiter |
| 4 | Filename → Retailer/City/Format | **Code only** (fuzzy match) | — | Finite set of known values. User confirms in UI anyway |
| 5 | Column name mapping | **Code first**, LLM fallback | Sonnet | 95% match deterministically. Sonnet only for truly novel column names |
| 6 | Known categorical normalization | **Code only** (lookup tables) | — | Explicit rules, fast, no errors |
| 7 | Unknown categorical values | **LLM** | Sonnet | Semantic judgment: "Health juice" → "Other" |
| 8 | Shelf Location normalization | **LLM** (except exact matches) | Sonnet | High variability, unpredictable phrasing |
| 9 | Juice Extraction Method inference | **Code first**, LLM fallback | Sonnet | Deterministic rules from HPP/Processing/Claims/Notes; Sonnet for remainder |
| 10 | Processing Method edge cases | **LLM** | Sonnet | Contradictions need judgment |
| 11 | HPP Treatment edge cases | **LLM** | Sonnet | Conflicting signals between columns |
| 12 | Typo correction | **Code first** (fuzzy match), LLM confirmation | Sonnet | Levenshtein catches typos, Sonnet confirms |
| 13 | Numeric conversion | **Code only** | — | Regex + type casting |
| 14 | Price per Liter recalculation | **Code only** | — | Pure math |
| 15 | Currency conversion | **Code only** | — | Multiplication by exchange rate |
| 16 | Confidence Score normalization | **Code only** | — | Rule-based scale detection |
| 17 | Deduplication | **Code only** | — | Composite key matching |
| 18 | Quality report generation | **Code only** | — | Counting and validation |

**LLM model:** Claude Sonnet (claude-sonnet-4-20250514) — hardcoded, no user choice in UI.
**LLM calls:** Steps 5 (fallback), 7, 8, 9, 10, 11, 12 (confirmation) are ALL batched into one single API call per file.
**No API key?** Steps 5-12 are skipped. Ambiguous items flagged in yellow for manual review. Tool still produces ~80-90% clean output.

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
**Valid values:** "Pasteurized", "HPP"

| Raw Value | Normalized |
|-----------|-----------|
| "Pasteurized", "pasteurised", "Pasteurised", "Flash pasteurised" | "Pasteurized" |
| "Cold-pressed", "Cold pressed", "Pressed" | blank (informs Juice Extraction Method instead) |
| "unpasteurised", "Unpasteurised", "Not pasteurised" | blank (removed as Processing Method value) |
| "Freshly Squeezed", "freshly squeezed" | blank (informs Juice Extraction Method instead) |
| "HPP", "HPP Treated", "HPP Treatment" | "HPP" |
| "Unknown", "unknown" | blank |
| null / blank | blank |

**Additional rule:** If HPP Treatment = "Yes" AND Processing Method is blank → set Processing Method = "HPP"
**LLM fallback:** For remaining blank Processing Method values, the LLM reads Claims + Notes + Brand to determine "Pasteurized" or "HPP". If the LLM cannot determine → leave blank.

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
- "Chilled Drinks Section" → "Chilled Section"
- "To-Go Section" → "To-Go Section"
- "To-Go Section — Shots" → "To-Go Section — Shots"
- "Meal Deal Section" → "Meal Deal Section"

All other non-blank values → send to LLM for classification.

### Juice Extraction Method — Deterministic Inference Rules
**Valid values:** "Cold Pressed", "Squeezed", "From Concentrate"

Deterministic rules are applied in order; first match wins per row:

| # | Rule | Result |
|---|------|--------|
| 1 | HPP Treatment == "Yes" | "Cold Pressed" |
| 2 | Processing Method == "HPP" | "Cold Pressed" |
| 3 | Processing Method == "Freshly Squeezed" | "Squeezed" |
| 4 | Claims or Notes contain "not from concentrate" (case-insensitive) | "Squeezed" |
| 5 | Claims or Notes contain "from concentrate" but NOT "not from concentrate" (case-insensitive) | "From Concentrate" |
| 6 | Claims or Notes contain "cold pressed" or "cold-pressed" (case-insensitive) | "Cold Pressed" |
| 7 | Claims or Notes contain "squeezed" or "freshly squeezed" (case-insensitive) | "Squeezed" |
| 8 | None of the above match | Flag for LLM |

**LLM prompt context for Juice Extraction Method:** Brand, Sub-brand, Product Name, Claims, Notes, Processing Method, HPP Treatment. The Sub-brand may contain processing terminology (e.g. "Freshly Squeezed", "Cold Pressed").

### Flavor — LLM Extraction from Product Name
The raw Excel column "Flavor" actually contains Product Name data (the text on the label/logo). After column mapping remaps raw "Flavor" → "Product Name", the Flavor column is populated by LLM inference.

For every row with a Product Name but no Flavor, the LLM is asked to extract ALL flavor/fruit/ingredient components from the product name. Examples:
- "Innocent Smoothie Orange & Mango 750ml" → Flavor: "Orange & Mango"
- "Tropicana Pure Premium Orange With Bits" → Flavor: "Orange"
- "Orange Juice 1L" → Flavor: "Orange"
- "Naked Green Machine 750ml" → Flavor: "Green Machine"
- "Apple, Mango & Passion Fruit Smoothie" → Flavor: "Apple, Mango & Passion Fruit"
- "Strawberry Banana Smoothie" → Flavor: "Strawberry & Banana"
- "Ginger & Turmeric Shot" → Flavor: "Ginger & Turmeric"
- "Blueberry & Lion's Mane Kombucha" → Flavor: "Blueberry" (Lion's Mane is a functional ingredient, not a flavor)
- "Probiotic Mango Juice" → Flavor: "Mango" (Probiotics are a health additive, not a flavor)
- "Spicy Ginger & Lemon" → Flavor: "Ginger & Lemon" (strip taste modifiers like "spicy")

**Flavor vs. functional ingredient rule:** Include fruits, vegetables, herbs, spices, and culinary ingredients that contribute to taste (Orange, Ginger, Turmeric, Matcha, Mint, etc.). Exclude functional/supplement ingredients that don't describe a taste (Probiotics, Lion's Mane, Collagen, Protein, Vitamins, Ashwagandha, CBD, Spirulina).

**Conjunction standardization:** Always use " & " as separator. After LLM extraction, a post-normalization step:
1. Checks `FLAVOR_MAP` for exact-match replacements (e.g. "Strawberry Banana" → "Strawberry & Banana")
2. Normalizes "/" separators to " & " (e.g. "Ginger/Turmeric" → "Ginger & Turmeric")

If no clear flavor can be determined, Flavor is left blank.

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
- Processing Method: "Pasteurized", "HPP"
- HPP Treatment: "Yes", "No"
- Packaging Type: "PET Bottle", "Tetra Pak", "Can", "Carton", "Glass Bottle"
- Juice Extraction Method: "Squeezed", "Cold Pressed", "From Concentrate"
- Stock Status: "In Stock", "Out of Stock"
- Shelf Level: "1st", "2nd", "3rd", "4th", "5th", "6th"
- Shelf Location: "Chilled Section", "To-Go Section", "To-Go Section — Shots", "Meal Deal Section"
- Flavor: free text (extract from Product Name)

COLUMN-SPECIFIC INSTRUCTIONS:
- Processing Method: determine if the product is "Pasteurized" or "HPP" based
  on Claims, Notes, and Brand. If you cannot determine, return blank.
- Juice Extraction Method: consider the full row context — Brand, Sub-brand,
  Product Name, Claims, Notes, Processing Method, HPP Treatment. The Sub-brand
  may contain processing terminology. Claims mentioning "not from concentrate"
  indicate "Squeezed" (NOT "From Concentrate").
- Flavor: Extract ALL flavor components from Product Name, joined with " & ".
  Include taste ingredients (fruits, herbs, spices). Exclude functional/supplement
  ingredients that don't describe taste (Probiotics, Lion's Mane, Collagen, etc.).
  Strip taste modifiers ("Spicy Ginger" → "Ginger") but keep varietal modifiers
  ("Blood Orange" → "Blood Orange"). See full instructions in code.

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

---

## Excel Output Format

The tool generates a formatted Excel workbook with three sheets:

### Sheet 1: SKU Data
- All master columns in the defined schema order
- Yellow highlighting on cells that require review
- **Issue Description column** (added as the LAST column when flagged cells exist):
  - Consolidates all issues for each row
  - Format: "ColumnName: reason | ColumnName2: reason2"
  - Example: "Product Type: 'Health Juice' not in allowed values for Product Type | Flavor: Flavor is empty — extract from Product Name 'Tropicana Orange 750ml'"
  - Only appears when there are flagged cells in the dataset
- Auto-filter enabled on header row
- Frozen header row for easy scrolling
- Number formats applied (currency, integers, decimals)

### Sheet 2: Data Quality Report
- Summary statistics (total rows, files processed, clean status)
- Null counts by column
- Normalization log (sample of changes made)
- Exchange rates used
- Remaining flagged items list

### Sheet 3: Source Files
- Audit trail of all processed files
- Columns: Filename, Retailer, City, Store Format, Row Count, Date Processed

---

## Re-upload Corrected Master Workflow

After downloading the Excel file with flagged cells:

1. **Review flagged cells**: Yellow-highlighted cells indicate data that needs correction
2. **Check Issue Description column**: See consolidated reasons for all issues in each row
3. **Fix the data**: Edit the yellow-highlighted cells directly in Excel
4. **Re-upload**: Use the "Re-upload Corrected Master" section in the app
   - Upload the corrected Excel file
   - The tool will:
     - Read from the "SKU Data" sheet
     - Automatically drop the Issue Description column
     - Update the session with the corrected data
     - Display success message with row count

**Note:** The in-app data editor has been replaced with this download-fix-reupload workflow to provide better visibility of issues and allow for more complex corrections in Excel.
