# Testing Strategy
# How to verify the tool produces correct, reliable output

---

## Core Principle: Ground Truth Comparison

The tool's output is compared against a **ground truth master file** — a manually verified correct output produced by Claude Opus 4.6 processing the same input files. This is the quality benchmark.

---

## Testing Layers

### Layer 1: Unit Tests (per module)
Each processing module has its own test file. Tests run instantly, no API key needed.

| Module | Test File | What's Tested |
|--------|-----------|--------------|
| file_reader.py | test_file_reader.py | Structure detection, merged cell handling, image skipping, data extraction |
| filename_parser.py | test_filename_parser.py | Retailer/City/Format extraction from various filename patterns |
| column_mapper.py | test_column_mapper.py | Exact matches, known renames, fuzzy matches, unmapped handling |
| normalizer.py | test_normalizer.py | Every lookup table entry, edge cases, flagging of unknown values |
| numeric_converter.py | test_numeric_converter.py | Text→number conversion, %, scale detection, error flagging |

**How to run:** `python -m pytest tests/ -v`

### Layer 2: Integration Test (full pipeline)
Runs the complete pipeline on test fixture files and validates the output.

| Test File | What's Tested |
|-----------|--------------|
| test_integration.py | End-to-end: raw files → clean master. Checks row counts, column presence, data types, no "Unknown" values |

### Layer 3: Ground Truth Comparison (accuracy benchmark)
Compares tool output cell-by-cell against ground truth.

| Test File | What's Tested |
|-----------|--------------|
| compare_ground_truth.py | Cell-by-cell diff between tool output and ground truth. Generates accuracy report. |

---

## Ground Truth File

**Location:** `tests/fixtures/ground_truth_master.xlsx`

**How to create it:**
1. Upload all 11 raw Excel files to Claude Opus 4.6
2. Prompt it to consolidate and clean per the SCHEMA.md and RULES.md specifications
3. Manually review the output for accuracy
4. Save as ground_truth_master.xlsx

**When to update it:**
- When new normalization rules are added
- When new test files are added
- When a bug is found in the ground truth itself

---

## Ground Truth Comparison Script

`tests/compare_ground_truth.py` produces this output:

```
=== Ground Truth Comparison Report ===

Files compared:
  Tool output: output_master.xlsx (906 rows)
  Ground truth: ground_truth_master.xlsx (906 rows)

Row count match: ✅ (906 = 906)
Column count match: ✅ (33 = 33)

Cell-by-cell accuracy:
  Total cells: 29,898
  Matching: 28,653 (95.8%)
  Different: 1,245 (4.2%)
  Both blank: 8,421 (not counted)

Differences by column:
  Shelf Location: 42 differences (LLM variation)
  Processing Method: 18 differences
  Juice Extraction Method: 31 differences
  ...

Sample differences:
  Row 45 | Processing Method | Tool: "Pasteurized" | Truth: "HPP" | Source: Tesco_Oval
  Row 112 | Shelf Location | Tool: "Chilled Section" | Truth: "To-Go Section" | Source: M&S_CG
  ...
```

**Accuracy targets:**
| Phase | Expected Accuracy | Notes |
|-------|------------------|-------|
| Phase 1-3 (deterministic only) | ~85-90% | Flagged items not yet resolved |
| Phase 4 (with LLM) | ~95-98% | Most items resolved |
| Phase 5-7 (final) | ~97-99% | Edge cases addressed |

---

## Test Fixtures

Store raw test Excel files in `tests/fixtures/`. These are copies of the original 11 files used during development. They serve as regression tests — if a code change breaks parsing of any file, the tests catch it.

---

## Testing Workflow

After each development phase:

```
1. Run unit tests:          python -m pytest tests/ -v
2. Run integration test:    python -m pytest tests/test_integration.py -v
3. Run ground truth check:  python tests/compare_ground_truth.py
4. Review the accuracy report
5. Investigate any new differences
6. Fix or document (if difference is an improvement over ground truth)
```

---

## What to Test for Each Phase

### Phase 1: File Reading
- [ ] All 11 test files produce a DataFrame with data rows
- [ ] Merged cells are detected and skipped (not in data rows)
- [ ] Section metadata (photo, location, linear meters) is extracted
- [ ] Embedded images don't cause errors
- [ ] Empty rows are excluded
- [ ] Files with offset columns (F, G) are handled

### Phase 2: Filename Parsing & Column Mapping
- [ ] All 11 filenames produce correct Retailer, City, Format
- [ ] "M_S" and "MS" both map to "M&S"
- [ ] "Tesco Express" is not parsed as "Tesco" + city "Express"
- [ ] All column name variations are mapped correctly
- [ ] "Segment" maps to "Product Type", "Sub-segment" to "Need State"

### Phase 3: Normalization & Numeric Conversion
- [ ] Every value in the lookup tables normalizes correctly
- [ ] Case-insensitive matching works
- [ ] Whitespace-stripped matching works
- [ ] Unknown values are flagged (not silently dropped or defaulted)
- [ ] Confidence Score: 0.8 → 80, "80%" → 80, 85 → 85
- [ ] Price per Liter is recalculated correctly
- [ ] Currency conversion applies correctly

### Phase 4: LLM Integration
- [ ] Flagged items are batched correctly into one API call
- [ ] LLM response is validated (only valid values accepted)
- [ ] Invalid LLM responses are caught and left blank
- [ ] Tool works without API key (graceful degradation)
- [ ] Juice Extraction Method is inferred for rows with relevant Claims

### Phase 5: Merge & Dedup
- [ ] Multiple files combine into one DataFrame
- [ ] Existing master + new files: overlapping stores detected
- [ ] Replace/skip decision is applied correctly
- [ ] No duplicate rows in final output

### Phase 6-7: UI & Output
- [ ] Streamlit app loads without errors
- [ ] File upload works (single and multiple files)
- [ ] Metadata table is editable
- [ ] Progress bar updates during processing
- [ ] Output Excel has 3 sheets with correct formatting
- [ ] Flagged cells are highlighted in yellow
