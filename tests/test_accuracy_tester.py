"""
Unit tests for accuracy_tester.py

Tests all comparison functions including:
- ComparisonKey extraction and validation
- Cell value comparison logic
- Row alignment
- DataFrame comparison
- LLM batch preparation
"""

import pandas as pd
import pytest

from processing.accuracy_tester import (
    ComparisonKey,
    CellDifference,
    AccuracyMetrics,
    ComparisonResult,
    load_excel_for_comparison,
    align_rows,
    compare_cell_values,
    compare_dataframes,
    prepare_llm_batch,
    COLUMNS_TO_COMPARE,
    NUMERIC_TOLERANCE,
)


# ═══════════════════════════════════════════════════════════════════════════
# ComparisonKey tests
# ═══════════════════════════════════════════════════════════════════════════

def test_comparison_key_from_row_valid():
    """Test ComparisonKey.from_row() with valid row."""
    row = pd.Series({
        "Country": "United Kingdom",
        "City": "London",
        "Retailer": "Tesco",
        "Photo": "photo123.jpg"
    })
    
    key = ComparisonKey.from_row(row)
    
    assert key is not None
    assert key.country == "United Kingdom"
    assert key.city == "London"
    assert key.retailer == "Tesco"
    assert key.photo == "photo123.jpg"


def test_comparison_key_from_row_with_whitespace():
    """Test ComparisonKey.from_row() strips whitespace."""
    row = pd.Series({
        "Country": "  United Kingdom  ",
        "City": " London ",
        "Retailer": "Tesco  ",
        "Photo": "  photo123.jpg"
    })
    
    key = ComparisonKey.from_row(row)
    
    assert key is not None
    assert key.country == "United Kingdom"
    assert key.city == "London"
    assert key.retailer == "Tesco"
    assert key.photo == "photo123.jpg"


def test_comparison_key_from_row_missing_country():
    """Test ComparisonKey.from_row() with missing Country."""
    row = pd.Series({
        "Country": None,
        "City": "London",
        "Retailer": "Tesco",
        "Photo": "photo123.jpg"
    })
    
    key = ComparisonKey.from_row(row)
    assert key is None


def test_comparison_key_from_row_missing_city():
    """Test ComparisonKey.from_row() with missing City."""
    row = pd.Series({
        "Country": "United Kingdom",
        "City": "",
        "Retailer": "Tesco",
        "Photo": "photo123.jpg"
    })
    
    key = ComparisonKey.from_row(row)
    assert key is None


def test_comparison_key_from_row_missing_retailer():
    """Test ComparisonKey.from_row() with missing Retailer."""
    row = pd.Series({
        "Country": "United Kingdom",
        "City": "London",
        "Retailer": None,
        "Photo": "photo123.jpg"
    })
    
    key = ComparisonKey.from_row(row)
    assert key is None


def test_comparison_key_from_row_missing_photo():
    """Test ComparisonKey.from_row() with missing Photo."""
    row = pd.Series({
        "Country": "United Kingdom",
        "City": "London",
        "Retailer": "Tesco",
        "Photo": ""
    })
    
    key = ComparisonKey.from_row(row)
    assert key is None


def test_comparison_key_to_string():
    """Test ComparisonKey.to_string() format."""
    key = ComparisonKey(
        country="UK",
        city="London",
        retailer="Tesco",
        photo="photo.jpg"
    )
    
    assert key.to_string() == "UK|London|Tesco|photo.jpg"


def test_comparison_key_equality():
    """Test ComparisonKey equality comparison."""
    key1 = ComparisonKey(
        country="UK",
        city="London",
        retailer="Tesco",
        photo="photo.jpg"
    )
    key2 = ComparisonKey(
        country="UK",
        city="London",
        retailer="Tesco",
        photo="photo.jpg"
    )
    key3 = ComparisonKey(
        country="UK",
        city="Manchester",
        retailer="Tesco",
        photo="photo.jpg"
    )
    
    assert key1 == key2
    assert key1 != key3


def test_comparison_key_hashable():
    """Test ComparisonKey can be used in sets/dicts."""
    key1 = ComparisonKey("UK", "London", "Tesco", "photo.jpg")
    key2 = ComparisonKey("UK", "London", "Tesco", "photo.jpg")
    key3 = ComparisonKey("UK", "Manchester", "Tesco", "photo.jpg")
    
    key_set = {key1, key2, key3}
    assert len(key_set) == 2  # key1 and key2 are equal


# ═══════════════════════════════════════════════════════════════════════════
# compare_cell_values tests
# ═══════════════════════════════════════════════════════════════════════════

def test_compare_cell_values_both_blank():
    """Test compare_cell_values() when both values are blank."""
    is_match, match_type = compare_cell_values(None, None, "Brand")
    assert is_match is True
    assert match_type == "both_blank"
    
    is_match, match_type = compare_cell_values("", "", "Brand")
    assert is_match is True
    assert match_type == "both_blank"
    
    is_match, match_type = compare_cell_values(pd.NA, None, "Brand")
    assert is_match is True
    assert match_type == "both_blank"


def test_compare_cell_values_one_blank():
    """Test compare_cell_values() when one value is blank."""
    is_match, match_type = compare_cell_values("Innocent", None, "Brand")
    assert is_match is False
    assert match_type == "one_blank"
    
    is_match, match_type = compare_cell_values(None, "Innocent", "Brand")
    assert is_match is False
    assert match_type == "one_blank"
    
    is_match, match_type = compare_cell_values("Smoothies", "", "Product Type")
    assert is_match is False
    assert match_type == "one_blank"


def test_compare_cell_values_exact_match():
    """Test compare_cell_values() for exact string matches."""
    is_match, match_type = compare_cell_values("Smoothies", "Smoothies", "Product Type")
    assert is_match is True
    assert match_type == "exact"
    
    # Case-insensitive
    is_match, match_type = compare_cell_values("Smoothies", "smoothies", "Product Type")
    assert is_match is True
    assert match_type == "exact"
    
    # Whitespace stripped
    is_match, match_type = compare_cell_values(" Smoothies ", "Smoothies", "Product Type")
    assert is_match is True
    assert match_type == "exact"


def test_compare_cell_values_string_mismatch():
    """Test compare_cell_values() for string mismatches."""
    is_match, match_type = compare_cell_values("Smoothies", "Shots", "Product Type")
    assert is_match is False
    assert match_type == "mismatch"


def test_compare_cell_values_numeric_within_tolerance():
    """Test numeric comparison with 0.01 tolerance."""
    # Exactly equal
    is_match, match_type = compare_cell_values(2.99, 2.99, "Price (Local Currency)")
    assert is_match is True
    assert match_type == "numeric_within_tolerance"
    
    # Within tolerance
    is_match, match_type = compare_cell_values(2.99, 2.989, "Price (Local Currency)")
    assert is_match is True
    assert match_type == "numeric_within_tolerance"
    
    is_match, match_type = compare_cell_values(2.99, 3.00, "Price (Local Currency)")
    assert is_match is True
    assert match_type == "numeric_within_tolerance"


def test_compare_cell_values_numeric_outside_tolerance():
    """Test numeric comparison outside tolerance."""
    is_match, match_type = compare_cell_values(2.99, 3.01, "Price (Local Currency)")
    assert is_match is False
    assert match_type == "numeric_mismatch"
    
    is_match, match_type = compare_cell_values(250, 750, "Packaging Size (ml)")
    assert is_match is False
    assert match_type == "numeric_mismatch"


def test_compare_cell_values_numeric_as_strings():
    """Test numeric comparison when values are strings."""
    is_match, match_type = compare_cell_values("2.99", "2.989", "Price (Local Currency)")
    assert is_match is True
    assert match_type == "numeric_within_tolerance"
    
    is_match, match_type = compare_cell_values("250", "250", "Packaging Size (ml)")
    assert is_match is True
    assert match_type == "numeric_within_tolerance"


def test_compare_cell_values_type_coercion():
    """Test that string '5' matches int 5."""
    # For numeric columns
    is_match, match_type = compare_cell_values("5", 5, "Facings")
    assert is_match is True
    
    # For non-numeric columns
    is_match, match_type = compare_cell_values("5", 5, "Brand")
    assert is_match is True
    assert match_type == "exact"


# ═══════════════════════════════════════════════════════════════════════════
# align_rows tests
# ═══════════════════════════════════════════════════════════════════════════

def test_align_rows_perfect_match():
    """Test align_rows() when all rows match between tool and truth."""
    tool_df = pd.DataFrame({
        "Country": ["UK", "UK"],
        "City": ["London", "Manchester"],
        "Retailer": ["Tesco", "Tesco"],
        "Photo": ["p1.jpg", "p2.jpg"],
        "Brand": ["Innocent", "Tropicana"]
    })
    
    truth_df = pd.DataFrame({
        "Country": ["UK", "UK"],
        "City": ["London", "Manchester"],
        "Retailer": ["Tesco", "Tesco"],
        "Photo": ["p1.jpg", "p2.jpg"],
        "Brand": ["Innocent", "Tropicana"]
    })
    
    aligned_df, unmatched_tool, unmatched_truth = align_rows(tool_df, truth_df)
    
    assert len(aligned_df) == 2
    assert len(unmatched_tool) == 0
    assert len(unmatched_truth) == 0
    
    # Check that columns are suffixed
    assert "Brand_tool" in aligned_df.columns
    assert "Brand_truth" in aligned_df.columns


def test_align_rows_with_unmatched():
    """Test align_rows() with rows present in only one file."""
    tool_df = pd.DataFrame({
        "Country": ["UK", "UK", "UK"],
        "City": ["London", "Manchester", "Birmingham"],
        "Retailer": ["Tesco", "Tesco", "Tesco"],
        "Photo": ["p1.jpg", "p2.jpg", "p3.jpg"],
        "Brand": ["Innocent", "Tropicana", "Naked"]
    })
    
    truth_df = pd.DataFrame({
        "Country": ["UK", "UK"],
        "City": ["London", "Leeds"],
        "Retailer": ["Tesco", "Tesco"],
        "Photo": ["p1.jpg", "p4.jpg"],
        "Brand": ["Innocent", "PJ"]
    })
    
    aligned_df, unmatched_tool, unmatched_truth = align_rows(tool_df, truth_df)
    
    # Only London/Tesco/p1.jpg matches
    assert len(aligned_df) == 1
    
    # 2 rows in tool not in truth (Manchester, Birmingham)
    assert len(unmatched_tool) == 2
    
    # 1 row in truth not in tool (Leeds)
    assert len(unmatched_truth) == 1


def test_align_rows_duplicate_keys():
    """Test align_rows() when duplicate composite keys exist."""
    # This should log a warning but still work (using first occurrence)
    tool_df = pd.DataFrame({
        "Country": ["UK", "UK"],
        "City": ["London", "London"],
        "Retailer": ["Tesco", "Tesco"],
        "Photo": ["p1.jpg", "p1.jpg"],  # Duplicate
        "Brand": ["Innocent", "Tropicana"]
    })
    
    truth_df = pd.DataFrame({
        "Country": ["UK"],
        "City": ["London"],
        "Retailer": ["Tesco"],
        "Photo": ["p1.jpg"],
        "Brand": ["Innocent"]
    })
    
    aligned_df, unmatched_tool, unmatched_truth = align_rows(tool_df, truth_df)
    
    # Should only align one row (first occurrence)
    assert len(aligned_df) == 1
    assert aligned_df.iloc[0]["Brand_tool"] == "Innocent"  # First occurrence


def test_align_rows_missing_key_fields():
    """Test align_rows() with rows that have missing key fields."""
    tool_df = pd.DataFrame({
        "Country": ["UK", "UK", None],
        "City": ["London", "Manchester", "Leeds"],
        "Retailer": ["Tesco", "Tesco", "Tesco"],
        "Photo": ["p1.jpg", "p2.jpg", "p3.jpg"],
        "Brand": ["Innocent", "Tropicana", "Naked"]
    })
    
    truth_df = pd.DataFrame({
        "Country": ["UK", "UK"],
        "City": ["London", "Manchester"],
        "Retailer": ["Tesco", "Tesco"],
        "Photo": ["p1.jpg", "p2.jpg"],
        "Brand": ["Innocent", "Tropicana"]
    })
    
    aligned_df, unmatched_tool, unmatched_truth = align_rows(tool_df, truth_df)
    
    # Only 2 rows can be aligned (3rd row in tool has missing Country)
    assert len(aligned_df) == 2
    assert len(unmatched_tool) == 0  # The row with None Country is excluded entirely
    assert len(unmatched_truth) == 0


# ═══════════════════════════════════════════════════════════════════════════
# compare_dataframes tests
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_tool_output():
    """Create a mock tool output DataFrame."""
    return pd.DataFrame({
        "Country": ["UK", "UK", "UK"],
        "City": ["London", "London", "Manchester"],
        "Retailer": ["Tesco", "Tesco", "Tesco"],
        "Photo": ["p1.jpg", "p2.jpg", "p3.jpg"],
        "Product Type": ["Smoothies", "Pure Juices", "Shots"],
        "Brand": ["Innocent", "Tropicana", "Boost"],
        "Price (Local Currency)": [2.99, 3.50, 1.99],
        "Packaging Size (ml)": [750, 1000, 60],
    })


@pytest.fixture
def mock_ground_truth():
    """Create a mock ground truth DataFrame."""
    return pd.DataFrame({
        "Country": ["UK", "UK", "UK"],
        "City": ["London", "London", "Manchester"],
        "Retailer": ["Tesco", "Tesco", "Tesco"],
        "Photo": ["p1.jpg", "p2.jpg", "p3.jpg"],
        "Product Type": ["Smoothies", "Pure Juices", "Smoothies"],  # p3 differs
        "Brand": ["Innocent", "Tropicana", "Boost"],
        "Price (Local Currency)": [2.99, 3.60, 1.99],  # p2 differs beyond tolerance (0.10)
        "Packaging Size (ml)": [750, 1000, 60],
    })


def test_compare_dataframes_full_pipeline(mock_tool_output, mock_ground_truth):
    """End-to-end test: load two DataFrames, compare, get metrics."""
    columns = ["Product Type", "Brand", "Price (Local Currency)", "Packaging Size (ml)"]
    
    result = compare_dataframes(mock_tool_output, mock_ground_truth, columns)
    
    assert isinstance(result, ComparisonResult)
    assert result.metrics.total_cells_compared == 12  # 3 rows × 4 columns
    
    # Should have 2 differences: p2 Price, p3 Product Type
    assert result.metrics.different_cells == 2
    assert result.metrics.matching_cells == 10
    
    # Check differences
    assert len(result.differences) == 2
    
    # Check per-column accuracy
    assert "Product Type" in result.metrics.accuracy_by_column
    assert "Brand" in result.metrics.accuracy_by_column
    
    # Brand should be 100% accurate
    assert result.metrics.accuracy_by_column["Brand"] == 100.0
    
    # Product Type should be 66.7% (2/3 correct)
    assert 66.0 <= result.metrics.accuracy_by_column["Product Type"] <= 67.0


def test_compare_dataframes_with_missing_columns():
    """Test compare_dataframes() when a column is missing in one file."""
    tool_df = pd.DataFrame({
        "Country": ["UK"],
        "City": ["London"],
        "Retailer": ["Tesco"],
        "Photo": ["p1.jpg"],
        "Product Type": ["Smoothies"],
        "Brand": ["Innocent"]
    })
    
    truth_df = pd.DataFrame({
        "Country": ["UK"],
        "City": ["London"],
        "Retailer": ["Tesco"],
        "Photo": ["p1.jpg"],
        "Product Type": ["Smoothies"]
        # Brand column missing
    })
    
    columns = ["Product Type", "Brand"]
    
    result = compare_dataframes(tool_df, truth_df, columns)
    
    # Should log error about missing Brand column in truth
    assert any("Brand" in error for error in result.errors)
    
    # Should still compare Product Type
    assert "Product Type" in result.metrics.accuracy_by_column


def test_compare_dataframes_no_matching_rows():
    """Test compare_dataframes() when no rows can be aligned."""
    tool_df = pd.DataFrame({
        "Country": ["UK"],
        "City": ["London"],
        "Retailer": ["Tesco"],
        "Photo": ["p1.jpg"],
        "Brand": ["Innocent"]
    })
    
    truth_df = pd.DataFrame({
        "Country": ["UK"],
        "City": ["Manchester"],
        "Retailer": ["Tesco"],
        "Photo": ["p2.jpg"],
        "Brand": ["Tropicana"]
    })
    
    result = compare_dataframes(tool_df, truth_df, ["Brand"])
    
    assert result.metrics.total_cells_compared == 0
    assert len(result.differences) == 0
    assert len(result.unmatched_tool_rows) == 1
    assert len(result.unmatched_truth_rows) == 1


# ═══════════════════════════════════════════════════════════════════════════
# prepare_llm_batch tests
# ═══════════════════════════════════════════════════════════════════════════

def test_prepare_llm_batch(mock_tool_output):
    """Test prepare_llm_batch() formats differences correctly."""
    key1 = ComparisonKey("UK", "London", "Tesco", "p1.jpg")
    key2 = ComparisonKey("UK", "London", "Tesco", "p2.jpg")
    
    differences = [
        CellDifference(key1, "Product Type", "Smoothies", "Shots", "mismatch"),
        CellDifference(key2, "Brand", "Innocent", "Tropicana", "mismatch"),
    ]
    
    batch = prepare_llm_batch(differences, mock_tool_output, max_differences=100)
    
    assert len(batch) == 2
    
    # Check first item
    assert batch[0]["row_key"] == "UK|London|Tesco|p1.jpg"
    assert batch[0]["column"] == "Product Type"
    assert batch[0]["tool_value"] == "Smoothies"
    assert batch[0]["truth_value"] == "Shots"
    assert "row_context" in batch[0]
    assert batch[0]["row_context"]["Brand"] == "Innocent"


def test_prepare_llm_batch_empty():
    """Test prepare_llm_batch() with no differences."""
    tool_df = pd.DataFrame({
        "Country": ["UK"],
        "City": ["London"],
        "Retailer": ["Tesco"],
        "Photo": ["p1.jpg"],
        "Brand": ["Innocent"]
    })
    
    batch = prepare_llm_batch([], tool_df, max_differences=100)
    
    assert len(batch) == 0


def test_prepare_llm_batch_max_differences(mock_tool_output):
    """Test prepare_llm_batch() limits to max_differences."""
    key = ComparisonKey("UK", "London", "Tesco", "p1.jpg")
    
    # Create 150 differences
    differences = [
        CellDifference(key, "Brand", f"Brand{i}", f"Truth{i}", "mismatch")
        for i in range(150)
    ]
    
    batch = prepare_llm_batch(differences, mock_tool_output, max_differences=50)
    
    assert len(batch) <= 50


def test_prepare_llm_batch_column_diversity():
    """Test prepare_llm_batch() samples across different columns."""
    tool_df = pd.DataFrame({
        "Country": ["UK"] * 10,
        "City": ["London"] * 10,
        "Retailer": ["Tesco"] * 10,
        "Photo": [f"p{i}.jpg" for i in range(10)],
        "Product Type": ["Smoothies"] * 10,
        "Brand": ["Innocent"] * 10,
    })
    
    # Create differences in two columns
    differences = []
    for i in range(5):
        key = ComparisonKey("UK", "London", "Tesco", f"p{i}.jpg")
        differences.append(CellDifference(key, "Product Type", "A", "B", "mismatch"))
    
    for i in range(5, 10):
        key = ComparisonKey("UK", "London", "Tesco", f"p{i}.jpg")
        differences.append(CellDifference(key, "Brand", "C", "D", "mismatch"))
    
    batch = prepare_llm_batch(differences, tool_df, max_differences=6)
    
    # Should sample from both columns (3 from each)
    product_type_count = sum(1 for item in batch if item["column"] == "Product Type")
    brand_count = sum(1 for item in batch if item["column"] == "Brand")
    
    assert product_type_count >= 2
    assert brand_count >= 2


# ═══════════════════════════════════════════════════════════════════════════
# Edge case tests
# ═══════════════════════════════════════════════════════════════════════════

def test_nan_vs_none_vs_empty_string_equivalence():
    """Test that NaN, None, and empty string are all treated as blank."""
    test_cases = [
        (None, None),
        (None, ""),
        ("", None),
        (pd.NA, None),
        (None, pd.NA),
        ("", ""),
    ]
    
    for val1, val2 in test_cases:
        is_match, match_type = compare_cell_values(val1, val2, "Brand")
        assert is_match is True
        assert match_type == "both_blank"


def test_whitespace_normalization():
    """Test that leading/trailing spaces are ignored."""
    is_match, _ = compare_cell_values("  Smoothies  ", "Smoothies", "Product Type")
    assert is_match is True
    
    is_match, _ = compare_cell_values("Smoothies", "  Smoothies", "Product Type")
    assert is_match is True


def test_special_characters_in_composite_key():
    """Test keys with quotes, pipes, etc."""
    row = pd.Series({
        "Country": "United Kingdom",
        "City": "King's Lynn",  # Apostrophe
        "Retailer": "M&S",  # Ampersand
        "Photo": "photo|123.jpg"  # Pipe character
    })
    
    key = ComparisonKey.from_row(row)
    
    assert key is not None
    assert key.city == "King's Lynn"
    assert key.retailer == "M&S"
    assert key.photo == "photo|123.jpg"
    assert "|" in key.to_string()  # Pipe is part of format


def test_excel_date_conversion_handling():
    """Test handling of values that Excel might convert to dates."""
    # Excel might convert "1/4" to a date
    # Our comparison should handle this gracefully
    is_match, match_type = compare_cell_values("1/4", "1/4", "Claims")
    assert is_match is True


def test_compare_with_mixed_types():
    """Test comparison when types are mixed (int vs float vs string)."""
    # String "5" vs int 5 (for numeric columns, converts and compares numerically)
    is_match, _ = compare_cell_values("5", 5, "Packaging Size (ml)")
    assert is_match is True
    
    # Float 5.0 vs int 5 (for numeric columns)
    is_match, _ = compare_cell_values(5.0, 5, "Packaging Size (ml)")
    assert is_match is True
    
    # String "5.0" vs int 5 (for numeric columns)
    is_match, _ = compare_cell_values("5.0", 5, "Packaging Size (ml)")
    assert is_match is True
    
    # For non-numeric columns, string comparison
    is_match, _ = compare_cell_values("5", "5", "Brand")
    assert is_match is True
