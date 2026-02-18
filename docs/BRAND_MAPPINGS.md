# Brand Mappings Documentation

## Overview

Brand-based inference rules provide the **highest priority** method for determining Juice Extraction Method and Processing Method. These rules are based on known brand practices and apply before all other deterministic rules.

## Current Coverage

- **UK Market**: 17 brands mapped (as of Feb 2026)
- **Other Markets**: To be added in future updates

## How It Works

### 1. Fuzzy Matching

The system uses fuzzy string matching to handle:
- **Spelling variations**: "Tropicanna" → "Tropicana"
- **Case differences**: "INNOCENT" → "Innocent"
- **Extra whitespace**: "  Tropicana  " → "Tropicana"

**Similarity Threshold**: 85% (configurable in `config/brand_mappings.py`)

### 2. Priority

Brand rules have **HIGHEST PRIORITY** and override all other indicators, including:
- HPP Treatment values
- Processing Method values
- Claims and Notes text

This design choice reflects the reality that brands have consistent processing methods across their product lines.

### 3. Conflict Detection

When explicit indicators contradict brand mapping, the system:
1. **Applies the brand value** (brand wins)
2. **Flags the conflict** for manual review
3. **Highlights the row** with yellow background in Excel output

**Example Conflicts**:
- Brand: "Tropicana" (says "Squeezed") + Claims: "from concentrate" → Conflict
- Brand: "Innocent" (says "Pasteurized") + HPP Treatment: "Yes" → Conflict

### 4. Dual Field Setting

Brand rules set **both** fields simultaneously:
- **Juice Extraction Method**: "Cold Pressed", "Squeezed", or "From Concentrate"
- **Processing Method**: "HPP" or "Pasteurized"

This ensures consistency between related fields.

## UK Brand Mappings

### Cold-Pressed + HPP Brands

| Brand | Juice Extraction Method | Processing Method | Category |
|-------|------------------------|-------------------|----------|
| MOJU | Cold Pressed | HPP | Shots |
| The Turmeric Co. | Cold Pressed | HPP | Shots |
| Mockingbird | Cold Pressed | HPP | Smoothies / Juices / Shots |
| Plenish | Cold Pressed | HPP | Juices / Shots |

### Squeezed + Pasteurized Brands

| Brand | Juice Extraction Method | Processing Method | Category |
|-------|------------------------|-------------------|----------|
| Innocent | Squeezed | Pasteurized | Smoothies / Juices |
| Tropicana | Squeezed | Pasteurized | Juices |
| Copella | Squeezed | Pasteurized | Juices |
| Cawston Press | Squeezed | Pasteurized | Juices / Sparkling drinks |
| James White | Squeezed | Pasteurized | Juices / Shots |

### From Concentrate + Pasteurized Brands

| Brand | Juice Extraction Method | Processing Method | Category |
|-------|------------------------|-------------------|----------|
| Naked | From Concentrate | Pasteurized | Smoothies / Juices |
| Juice Burst | From Concentrate | Pasteurized | Juices |
| Happy Monkey | From Concentrate | Pasteurized | Smoothies (kids) |
| Ocean Spray | From Concentrate | Pasteurized | Juices / Juice drinks |
| Welch's | From Concentrate | Pasteurized | Juices |
| Don Simon | From Concentrate | Pasteurized | Juices |
| Pommegreat | From Concentrate | Pasteurized | Juices |
| POM (POM Wonderful) | From Concentrate | Pasteurized | Juices |

## Adding New Brands

### For UK Market

1. Open `config/brand_mappings.py`
2. Add entry to `UK_BRAND_MAPPINGS` dictionary:

```python
"Brand Name": {
    "juice_extraction_method": "Squeezed",  # or "Cold Pressed", "From Concentrate"
    "processing_method": "Pasteurized"       # or "HPP"
}
```

3. Update this documentation file with the new brand
4. Run tests to ensure no conflicts: `pytest tests/test_normalizer.py::TestBrandBasedInference`

### For New Markets

1. Create new mapping dictionary in `config/brand_mappings.py`:

```python
US_BRAND_MAPPINGS = {
    "Brand Name": {
        "juice_extraction_method": "...",
        "processing_method": "..."
    },
    # ... more brands
}
```

2. Update `match_brand()` function to support new country code
3. Add documentation section for new market in this file
4. Add tests for new market brands

## Maintenance

### When to Update

- **Brand changes processing method**: Update mapping immediately
- **New brand enters market**: Add to mappings if significant market share
- **Brand exits market**: Keep in mappings (historical data may still reference it)

### Validation

After updating brand mappings, run:

```bash
# Test brand matching
pytest tests/test_normalizer.py::TestBrandBasedInference -v

# Test conflict detection
pytest tests/test_normalizer.py::TestBrandConflictDetection -v

# Run full test suite
pytest tests/test_normalizer.py -v
```

## Technical Details

### File Locations

- **Mappings**: `config/brand_mappings.py`
- **Conflict Detection**: `processing/conflict_detector.py`
- **Integration**: `processing/normalizer.py` (function `_infer_juice_extraction_method`)

### Configuration

```python
# config/brand_mappings.py
DEFAULT_COUNTRY = "UK"
BRAND_MATCHING_THRESHOLD = 85  # Minimum similarity score (0-100)
```

### Fuzzy Matching Algorithm

Uses `rapidfuzz` library with `token_sort_ratio` scoring:
- Handles word order variations
- Case-insensitive
- Tokenizes and sorts words before comparison
- Returns best match above threshold

## Examples

### Successful Match

```python
Input: "Tropicana"
Match: "Tropicana" (100% similarity)
Result: 
  - Juice Extraction Method = "Squeezed"
  - Processing Method = "Pasteurized"
  - No conflicts
```

### Fuzzy Match with Typo

```python
Input: "Tropicanna"
Match: "Tropicana" (92% similarity, above 85% threshold)
Result: 
  - Juice Extraction Method = "Squeezed"
  - Processing Method = "Pasteurized"
  - No conflicts
```

### Conflict Detected

```python
Input: 
  - Brand = "Tropicana"
  - Claims = "from concentrate"
Match: "Tropicana" (100% similarity)
Result:
  - Juice Extraction Method = "Squeezed" (brand wins)
  - Processing Method = "Pasteurized"
  - CONFLICT FLAGGED: Brand says "Squeezed" but Claims indicate "From Concentrate"
  - Row highlighted yellow for manual review
```

### No Match

```python
Input: "Unknown Brand XYZ"
Match: None (best match below 85% threshold)
Result:
  - Falls through to next rule (explicit indicators)
  - No brand-based values applied
```

## Future Enhancements

- [ ] Add US market brand mappings
- [ ] Add EU market brand mappings (France, Germany, Spain)
- [ ] Implement brand confidence scoring
- [ ] Add brand aliases (e.g., "POM" and "POM Wonderful" as same brand)
- [ ] Track brand mapping changes over time
- [ ] Add brand category validation (ensure brand matches product type)

## Questions?

For questions about brand mappings or to request additions, contact the data team or create an issue in the project repository.
