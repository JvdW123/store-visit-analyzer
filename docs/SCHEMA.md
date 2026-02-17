# Master File Schema
# Defines the exact column structure, data types, and valid values for the output

---

## Column Definitions (in order)

| # | Column Name | Data Type | Required | Source | Valid Values / Notes |
|---|------------|-----------|----------|--------|---------------------|
| 1 | Country | Text | Yes | Derived from country setting | "United Kingdom", "France", "Germany", etc. |
| 2 | City | Text | Yes | Derived from filename | Free text, standardized capitalization |
| 3 | Retailer | Text | Yes | Derived from filename | From known retailers list (see FILENAME_CONFIG.md) |
| 4 | Store Format | Text | No | Derived from filename | "Small", "Medium", "Large", or blank |
| 5 | Store Name | Text | Yes | Constructed | "{Retailer} {City}" |
| 6 | Photo | Text | No | Raw column or merged section header | Photo filename reference |
| 7 | Shelf Location | Text | No | Direct match, LLM-normalized | "Chilled Section", "To-Go Section", "To-Go Section — Shots", "Meal Deal Section" |
| 8 | Shelf Levels | Integer | No | Direct match | Total shelf levels. Must be numeric. |
| 9 | Shelf Level | Text | No | Direct match | "1st", "2nd", "3rd", "4th", "5th", "6th" |
| 10 | Product Type | Text | No | Raw: "Segment" | "Pure Juices", "Smoothies", "Shots", "Other" |
| 11 | Branded/Private Label | Text | No | Raw: "Branded / Private Label" | "Branded", "Private Label" |
| 12 | Brand | Text | No | Direct match | Free text, as-is from source |
| 13 | Sub-brand | Text | No | Direct match | Free text, as-is from source |
| 14 | Product Name | Text | No | Raw: "Flavor" | Free text, as-is from source (raw "Flavor" column contains product name data) |
| 15 | Flavor | Text | No | LLM-inferred from Product Name | Free text, flavor/fruit extracted from Product Name by LLM |
| 16 | Facings | Integer | No | Direct match | Must be numeric |
| 17 | Price (Local Currency) | Float | No | Raw: "Price (GBP/EUR/Pounds)" | 2 decimal places |
| 18 | Currency | Text | Yes | Derived from Country | "GBP", "EUR" |
| 19 | Price (EUR) | Float | No | Calculated | Local price × exchange rate. 2 decimal places. |
| 20 | Packaging Size (ml) | Integer | No | Direct match | Must be numeric |
| 21 | Price per Liter (EUR) | Float | No | Calculated | Price (EUR) / (Packaging Size / 1000). 2 decimal places. |
| 22 | Need State | Text | No | Raw: "Sub-segment" | "Indulgence", "Functional" |
| 23 | Juice Extraction Method | Text | No | LLM-inferred | "Squeezed", "Cold Pressed", "From Concentrate" |
| 24 | Processing Method | Text | No | Direct + LLM | "Pasteurized", "HPP" |
| 25 | HPP Treatment | Text | No | Direct + LLM | "Yes", "No" |
| 26 | Packaging Type | Text | No | Direct match | "PET Bottle", "Tetra Pak", "Can", "Carton", "Glass Bottle" |
| 27 | Claims | Text | No | Direct match | Free text, as-is from source |
| 28 | Bonus/Promotions | Text | No | Raw: "Bonus" | Free text, as-is from source |
| 29 | Stock Status | Text | No | Direct match | "In Stock", "Out of Stock" |
| 30 | Est. Linear Meters | Float | No | Direct match or section headers | 1 decimal place |
| 31 | Fridge Number | Text | No | Only in some files | As-is where present |
| 32 | Confidence Score | Integer | No | Direct match | 0-100 scale |
| 33 | Notes | Text | No | Direct match | Free text, as-is from source |

---

## Column Mapping (Raw → Master)

| Master Column | Known Raw Column Names | Mapping Method |
|--------------|----------------------|----------------|
| Photo | "Photo File Name", "Photo" | Exact match |
| Shelf Location | "Shelf Location" | Exact match |
| Shelf Levels | "Shelf Levels" | Exact match |
| Shelf Level | "Shelf Level" | Exact match |
| Product Type | "Segment" | Known rename |
| Branded/Private Label | "Branded / Private Label" | Known rename |
| Brand | "Brand" | Exact match |
| Sub-brand | "Sub-brand" | Exact match |
| Product Name | "Flavor" | Known rename (raw "Flavor" contains product name data) |
| Facings | "Facings" | Exact match |
| Price (Local Currency) | "Price (GBP)", "Price (EUR)", "Price (Pounds)" | Fuzzy match on "Price" |
| Packaging Size (ml) | "Packaging Size (ml)" | Exact match |
| Need State | "Sub-segment" | Known rename |
| Processing Method | "Processing Method" | Exact match |
| HPP Treatment | "HPP Treatment" | Exact match |
| Packaging Type | "Packaging Type" | Exact match |
| Claims | "Claims" | Exact match |
| Bonus/Promotions | "Bonus" | Known rename |
| Stock Status | "Stock Status" | Exact match |
| Est. Linear Meters | "Est. Linear Meters" | Exact match |
| Fridge Number | "Fridge Number" | Exact match |
| Confidence Score | "Confidence Score" | Exact match |
| Notes | "Notes" | Exact match |

For unmatched column names: fuzzy string matching → LLM fallback → flag for user review.

---

## Derived & Calculated Columns

| Column | Formula | Notes |
|--------|---------|-------|
| Country | From app settings | "United Kingdom" for v1 |
| City | From filename parser | See FILENAME_CONFIG.md |
| Retailer | From filename parser | See FILENAME_CONFIG.md |
| Store Format | From filename parser | "Small", "Large", or blank |
| Store Name | `f"{Retailer} {City}"` | Constructed |
| Currency | From Country mapping | UK → "GBP", France/Germany → "EUR" |
| Price (EUR) | `Price_Local × exchange_rate` | 1.0 if already EUR |
| Price per Liter (EUR) | `Price_EUR / (Packaging_Size_ml / 1000)` | Blank if either input is missing |
| Juice Extraction Method | Deterministic rules first (HPP Treatment, Processing Method, Claims/Notes), LLM fallback | See RULES.md |
| Flavor | LLM-inferred from Product Name | Extracted flavor/fruit from product name text |

---

## Output Excel Format

### Sheet 1: "SKU Data"
- All rows in column order above
- Header row with auto-filter enabled
- Column widths auto-fitted
- Number formats: 2dp for prices, integers for counts
- Flagged cells highlighted in yellow

### Sheet 2: "Data Quality Report"
- Summary: rows per file, total SKUs, null counts per column
- Normalization log: original → cleaned value, method (deterministic/LLM)
- Remaining flagged items for manual review
- Exchange rate used

### Sheet 3: "Source Files"
- Table: Filename | Retailer | City | Format | Rows | Date Processed
- Audit trail for which files were included

---

## Global Rule: Blank = We Don't Know

If data is unavailable, could not be determined, or is ambiguous → cell is **blank** (empty/NaN).

The string "Unknown" is **never** used as a value. This ensures:
- Blank cells excluded from counts (COUNTA, pivot tables)
- No accidental inclusion of "Unknown" in category totals
- Clean distinction: has value (we know) vs. empty (we don't)
