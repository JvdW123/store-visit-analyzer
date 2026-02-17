# Phase 1 Implementation Summary
# Analysis Engine + Storyline Config

## Overview

Phase 1 of Tool B is complete. The analysis engine transforms master data from Tool A into structured DataFrames ready for charting and PowerPoint generation.

## Files Created

### 1. `config/storyline.py` (456 lines)
**Purpose:** Single source of truth for the entire 10-slide deck structure.

**Key Components:**
- `STORYLINE`: List of 10 slide configurations (declarative)
- `BRAND_COLORS`: Fruity Line visual identity colors
- `CHART_COLORS`: Consistent color schemes for charts, heatmaps, and retailers
- `get_slide_config()`: Retrieve config for a specific slide
- `get_retailer_slides()`: Get all retailer deep dive slides (4-10)
- `validate_storyline()`: Validate configuration completeness

**Design Decisions:**
- Analysis functions referenced as strings, resolved at runtime
- Hardcoded 7 retailers for deep dives (Aldi, Lidl, M&S, Sainsbury's, Tesco, Tesco Express, Waitrose)
- Separation of concerns: config defines WHAT, calculations define HOW

### 2. `analysis/calculations.py` (630 lines)
**Purpose:** Pure calculation functions that transform master DataFrames into slide-ready data.

**Functions:**
- `share_by_category()`: Calculate percentage share within groups (used by Slide 1)
- `brand_retailer_heatmap()`: Generate brand × retailer heatmap with metrics (Slide 2)
- `retailer_sizing()`: Calculate SKU counts and category shares (Slide 3)
- `retailer_deep_dive()`: Generate 4 charts for a single retailer (Slides 4-10)
- `market_fingerprint()`: Generate 5 category breakdowns (Slide 1)

**Helper Functions:**
- `_validate_required_columns()`: Raise error if columns missing
- `_safe_percentage()`: Handle division by zero gracefully

**Edge Cases Handled:**
- Missing columns → raise ValueError with clear message
- Empty DataFrames → return empty with correct schema
- NaN values → excluded from calculations
- Division by zero → return 0.0
- Retailer/brand not in data → return empty DataFrame
- Fewer items than requested → return all available

### 3. `analysis/slide_data.py` (167 lines)
**Purpose:** Orchestrator that connects storyline config to calculation functions.

**Functions:**
- `generate_all_slide_data()`: Generate data for all 10 slides
- `generate_slide_data()`: Generate data for a single slide
- `_call_analysis_function()`: Dynamically call functions by name

**Features:**
- Validates storyline configuration before processing
- Isolates failures: if one slide fails, others continue
- Comprehensive logging at INFO and WARNING levels
- Returns dict mapping slide_number → slide data

### 4. `tests/test_calculations.py` (690 lines)
**Purpose:** Comprehensive tests for all calculation functions.

**Test Coverage:**
- 23 tests covering all functions and edge cases
- Fixture-based approach with known expected outputs
- Tests for: normal operation, edge cases, empty data, missing values, division by zero

**Fixtures:**
- `sample_master_df`: 15 rows with 3 retailers, 5 brands, diverse categories
- `empty_df`: Empty DataFrame with correct schema

**Test Results:**
- ✅ All 23 tests pass
- ✅ All 457 tests in the full suite pass (no regressions)

## Design Principles Applied

1. **Config-driven**: All slide definitions in `storyline.py`, not hardcoded in logic
2. **Pure functions**: Calculations have no side effects, only data transformations
3. **Defensive programming**: Handle all edge cases gracefully, never crash
4. **Separation of concerns**: Config → Orchestrator → Calculations → (Future: Rendering)
5. **Testable**: Small, isolated functions with clear inputs/outputs
6. **Readable**: Docstrings, type hints, descriptive names, inline comments

## Key Decisions Confirmed

1. ✅ **Hardcode retailers in config for v1** (7 retailers for deep dives)
2. ✅ **Show 0% for missing categories** (include all categories in output)
3. ✅ **Aggregate across formats for deep dives** (no format filtering)
4. ✅ **Full precision in DataFrames** (round in PowerPoint generator, not here)

## Data Flow

```
Master Excel (from Tool A)
       ↓
  Load SKU Data sheet
       ↓
  generate_all_slide_data(master_df)
       ↓
  For each slide in STORYLINE:
    - Get slide config
    - Call analysis function by name
    - Pass df + params
       ↓
  Return dict[slide_number → slide_data]
       ↓
  (Phase 2: Render to PowerPoint)
```

## Example Outputs

### Slide 1: Market Fingerprint
Returns dict with 5 DataFrames:
```python
{
    "product_type": DataFrame([Retailer, Product Type, Count, Percentage]),
    "pl_vs_branded": DataFrame([Retailer, Branded/Private Label, Count, Percentage]),
    "extraction": DataFrame([Retailer, Juice Extraction Method, Count, Percentage]),
    "hpp": DataFrame([Retailer, HPP Treatment, Count, Percentage]),
    "need_state": DataFrame([Retailer, Need State, Count, Percentage])
}
```

### Slide 2: Brand Landscape
Returns single DataFrame:
```python
DataFrame([
    Brand, Total Market Share,
    Aldi, Lidl, M&S, Sainsbury's, Tesco, Tesco Express, Waitrose,
    % Cold Pressed, % Functional
])
```

### Slide 3: Retailer Sizing
Returns tuple of 2 DataFrames:
```python
(
    table_data: DataFrame([Retailer, Store Format, Avg SKU Count, Avg Facings]),
    chart_data: DataFrame([Retailer, % PL, % HPP, % Cold Pressed])
)
```

### Slides 4-10: Retailer Deep Dives
Returns dict with 4 DataFrames per retailer:
```python
{
    "product_type": DataFrame([Product Type, Facings]),
    "pl_vs_branded": DataFrame([Branded/Private Label, Percentage]),
    "extraction": DataFrame([Juice Extraction Method, Percentage]),
    "need_state": DataFrame([Need State, Percentage])
}
```

## Next Steps (Phase 2)

1. **PowerPoint Generation**
   - Install `python-pptx` library
   - Create slide templates with Fruity Line branding
   - Implement chart rendering (matplotlib or plotly → images)
   - Generate .pptx file from slide data

2. **Analysis Workbook**
   - Export all slide data to Excel for deeper analysis
   - One sheet per slide with raw data
   - Summary sheet with key metrics

3. **Streamlit Integration**
   - Create `pages/2_Analysis.py` for Tool B UI
   - File uploader for master Excel
   - Preview of slide data
   - Download buttons for PowerPoint and analysis workbook

4. **Testing**
   - Integration tests with real master Excel files
   - Visual regression tests for PowerPoint output
   - Performance tests with large datasets

## Performance Notes

- All calculations are vectorized using pandas (fast)
- No loops over rows (except for retailer iteration in chart_data)
- Memory-efficient: processes data in-place where possible
- Test suite runs in < 2 seconds for 23 tests

## Dependencies

All dependencies already in `requirements.txt`:
- pandas >= 2.1.0 ✅
- pytest >= 7.4.0 ✅

New dependencies for Phase 2:
- python-pptx (for PowerPoint generation)
- matplotlib or plotly (for chart rendering)

## Validation

✅ All 23 new tests pass  
✅ All 457 total tests pass (no regressions)  
✅ Code follows project conventions (.cursorrules)  
✅ Comprehensive docstrings and type hints  
✅ Edge cases handled gracefully  
✅ Logging implemented throughout  

Phase 1 is **complete and ready for Phase 2**.
