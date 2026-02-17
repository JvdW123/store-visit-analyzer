"""
Tests for analysis calculation functions.

Uses small, hand-crafted fixture data with known expected outputs.
Tests all calculation functions and edge cases.
"""

import pytest
import pandas as pd
import numpy as np

from analysis.calculations import (
    share_by_category,
    brand_retailer_heatmap,
    retailer_sizing,
    retailer_deep_dive,
    market_fingerprint,
    _safe_percentage,
    _validate_required_columns,
)


@pytest.fixture
def sample_master_df() -> pd.DataFrame:
    """
    Small fixture DataFrame with known values for testing.
    
    Contains:
    - 3 retailers (Aldi, Lidl, Tesco)
    - 2 brands (Innocent, Tropicana)
    - Mix of Product Types, PL vs Branded, extraction methods, etc.
    - Total: 15 rows
    """
    data = [
        # Aldi - 5 rows
        {
            "Country": "United Kingdom",
            "City": "London",
            "Retailer": "Aldi",
            "Store Format": "Discount",
            "Store Name": "Aldi London",
            "Brand": "Innocent",
            "Product Name": "Orange Juice",
            "Product Type": "Pure Juices",
            "Branded/Private Label": "Branded",
            "Juice Extraction Method": "Cold Pressed",
            "HPP Treatment": "Yes",
            "Need State": "Indulgence",
            "Facings": 10,
        },
        {
            "Country": "United Kingdom",
            "City": "London",
            "Retailer": "Aldi",
            "Store Format": "Discount",
            "Store Name": "Aldi London",
            "Brand": "Tropicana",
            "Product Name": "Apple Juice",
            "Product Type": "Pure Juices",
            "Branded/Private Label": "Branded",
            "Juice Extraction Method": "Squeezed",
            "HPP Treatment": "No",
            "Need State": "Functional",
            "Facings": 8,
        },
        {
            "Country": "United Kingdom",
            "City": "London",
            "Retailer": "Aldi",
            "Store Format": "Discount",
            "Store Name": "Aldi London",
            "Brand": "Aldi",
            "Product Name": "Smoothie Mix",
            "Product Type": "Smoothies",
            "Branded/Private Label": "Private Label",
            "Juice Extraction Method": "Cold Pressed",
            "HPP Treatment": "Yes",
            "Need State": "Functional",
            "Facings": 12,
        },
        {
            "Country": "United Kingdom",
            "City": "Manchester",
            "Retailer": "Aldi",
            "Store Format": "Discount",
            "Store Name": "Aldi Manchester",
            "Brand": "Innocent",
            "Product Name": "Berry Smoothie",
            "Product Type": "Smoothies",
            "Branded/Private Label": "Branded",
            "Juice Extraction Method": "Cold Pressed",
            "HPP Treatment": "Yes",
            "Need State": "Indulgence",
            "Facings": 6,
        },
        {
            "Country": "United Kingdom",
            "City": "Manchester",
            "Retailer": "Aldi",
            "Store Format": "Discount",
            "Store Name": "Aldi Manchester",
            "Brand": "Tropicana",
            "Product Name": "Ginger Shot",
            "Product Type": "Shots",
            "Branded/Private Label": "Branded",
            "Juice Extraction Method": "Squeezed",
            "HPP Treatment": "No",
            "Need State": "Functional",
            "Facings": 4,
        },
        # Lidl - 5 rows
        {
            "Country": "United Kingdom",
            "City": "London",
            "Retailer": "Lidl",
            "Store Format": "Discount",
            "Store Name": "Lidl London",
            "Brand": "Innocent",
            "Product Name": "Orange Juice",
            "Product Type": "Pure Juices",
            "Branded/Private Label": "Branded",
            "Juice Extraction Method": "Cold Pressed",
            "HPP Treatment": "Yes",
            "Need State": "Indulgence",
            "Facings": 15,
        },
        {
            "Country": "United Kingdom",
            "City": "London",
            "Retailer": "Lidl",
            "Store Format": "Discount",
            "Store Name": "Lidl London",
            "Brand": "Lidl",
            "Product Name": "Apple Juice",
            "Product Type": "Pure Juices",
            "Branded/Private Label": "Private Label",
            "Juice Extraction Method": "From Concentrate",
            "HPP Treatment": "No",
            "Need State": "Indulgence",
            "Facings": 20,
        },
        {
            "Country": "United Kingdom",
            "City": "London",
            "Retailer": "Lidl",
            "Store Format": "Discount",
            "Store Name": "Lidl London",
            "Brand": "Tropicana",
            "Product Name": "Smoothie",
            "Product Type": "Smoothies",
            "Branded/Private Label": "Branded",
            "Juice Extraction Method": "Squeezed",
            "HPP Treatment": "No",
            "Need State": "Functional",
            "Facings": 5,
        },
        {
            "Country": "United Kingdom",
            "City": "Birmingham",
            "Retailer": "Lidl",
            "Store Format": "Discount",
            "Store Name": "Lidl Birmingham",
            "Brand": "Innocent",
            "Product Name": "Berry Smoothie",
            "Product Type": "Smoothies",
            "Branded/Private Label": "Branded",
            "Juice Extraction Method": "Cold Pressed",
            "HPP Treatment": "Yes",
            "Need State": "Indulgence",
            "Facings": 8,
        },
        {
            "Country": "United Kingdom",
            "City": "Birmingham",
            "Retailer": "Lidl",
            "Store Format": "Discount",
            "Store Name": "Lidl Birmingham",
            "Brand": "Lidl",
            "Product Name": "Ginger Shot",
            "Product Type": "Shots",
            "Branded/Private Label": "Private Label",
            "Juice Extraction Method": "From Concentrate",
            "HPP Treatment": "No",
            "Need State": "Functional",
            "Facings": 2,
        },
        # Tesco - 5 rows
        {
            "Country": "United Kingdom",
            "City": "London",
            "Retailer": "Tesco",
            "Store Format": "Supermarket",
            "Store Name": "Tesco London",
            "Brand": "Innocent",
            "Product Name": "Orange Juice",
            "Product Type": "Pure Juices",
            "Branded/Private Label": "Branded",
            "Juice Extraction Method": "Cold Pressed",
            "HPP Treatment": "Yes",
            "Need State": "Indulgence",
            "Facings": 18,
        },
        {
            "Country": "United Kingdom",
            "City": "London",
            "Retailer": "Tesco",
            "Store Format": "Supermarket",
            "Store Name": "Tesco London",
            "Brand": "Tropicana",
            "Product Name": "Apple Juice",
            "Product Type": "Pure Juices",
            "Branded/Private Label": "Branded",
            "Juice Extraction Method": "Squeezed",
            "HPP Treatment": "No",
            "Need State": "Functional",
            "Facings": 12,
        },
        {
            "Country": "United Kingdom",
            "City": "London",
            "Retailer": "Tesco",
            "Store Format": "Supermarket",
            "Store Name": "Tesco London",
            "Brand": "Tesco",
            "Product Name": "Smoothie Mix",
            "Product Type": "Smoothies",
            "Branded/Private Label": "Private Label",
            "Juice Extraction Method": "Squeezed",
            "HPP Treatment": "No",
            "Need State": "Functional",
            "Facings": 10,
        },
        {
            "Country": "United Kingdom",
            "City": "Manchester",
            "Retailer": "Tesco",
            "Store Format": "Supermarket",
            "Store Name": "Tesco Manchester",
            "Brand": "Innocent",
            "Product Name": "Berry Smoothie",
            "Product Type": "Smoothies",
            "Branded/Private Label": "Branded",
            "Juice Extraction Method": "Cold Pressed",
            "HPP Treatment": "Yes",
            "Need State": "Indulgence",
            "Facings": 7,
        },
        {
            "Country": "United Kingdom",
            "City": "Manchester",
            "Retailer": "Tesco",
            "Store Format": "Supermarket",
            "Store Name": "Tesco Manchester",
            "Brand": "Tropicana",
            "Product Name": None,  # Missing Product Name
            "Product Type": None,  # Missing Product Type
            "Branded/Private Label": "Branded",
            "Juice Extraction Method": "Squeezed",
            "HPP Treatment": "No",
            "Need State": "Functional",
            "Facings": 3,
        },
    ]
    
    return pd.DataFrame(data)


@pytest.fixture
def empty_df() -> pd.DataFrame:
    """Empty DataFrame with correct schema."""
    columns = [
        "Country", "City", "Retailer", "Store Format", "Store Name",
        "Brand", "Product Name", "Product Type", "Branded/Private Label",
        "Juice Extraction Method", "HPP Treatment", "Need State", "Facings"
    ]
    return pd.DataFrame(columns=columns)


# Test helper functions
def test_safe_percentage_normal():
    """Test normal percentage calculation."""
    assert _safe_percentage(50, 100) == 50.0
    assert _safe_percentage(1, 3) == pytest.approx(33.333333, rel=0.0001)


def test_safe_percentage_division_by_zero():
    """Test division by zero returns 0.0."""
    assert _safe_percentage(10, 0) == 0.0
    assert _safe_percentage(0, 0) == 0.0


def test_safe_percentage_nan():
    """Test NaN denominator returns 0.0."""
    assert _safe_percentage(10, np.nan) == 0.0


def test_validate_required_columns_success(sample_master_df):
    """Test validation passes when all columns present."""
    _validate_required_columns(sample_master_df, ["Retailer", "Facings"])
    # Should not raise


def test_validate_required_columns_failure(sample_master_df):
    """Test validation raises ValueError when columns missing."""
    with pytest.raises(ValueError, match="Missing required columns"):
        _validate_required_columns(sample_master_df, ["Retailer", "NonExistentColumn"])


# Test share_by_category
def test_share_by_category_basic(sample_master_df):
    """Test basic percentage calculation by retailer × product type."""
    result = share_by_category(
        sample_master_df,
        groupby="Retailer",
        category_col="Product Type"
    )
    
    # Check structure
    assert list(result.columns) == ["Retailer", "Product Type", "Count", "Percentage"]
    assert len(result) > 0
    
    # Aldi has: Pure Juices (18), Smoothies (18), Shots (4) = 40 total
    # Pure Juices = 18/40 = 45%
    aldi_pure = result[
        (result["Retailer"] == "Aldi") & 
        (result["Product Type"] == "Pure Juices")
    ]
    assert len(aldi_pure) == 1
    assert aldi_pure["Count"].iloc[0] == 18
    assert aldi_pure["Percentage"].iloc[0] == pytest.approx(45.0, rel=0.01)


def test_share_by_category_missing_values(sample_master_df):
    """Test that NaN category values are excluded."""
    result = share_by_category(
        sample_master_df,
        groupby="Retailer",
        category_col="Product Type"
    )
    
    # Should not have any rows with NaN Product Type
    assert result["Product Type"].isna().sum() == 0


def test_share_by_category_empty_df(empty_df):
    """Test that empty input returns empty output with correct schema."""
    result = share_by_category(
        empty_df,
        groupby="Retailer",
        category_col="Product Type"
    )
    
    assert list(result.columns) == ["Retailer", "Product Type", "Count", "Percentage"]
    assert len(result) == 0


def test_share_by_category_single_category(sample_master_df):
    """Test when filtering results in single category."""
    # Filter to only Aldi Shots
    aldi_shots = sample_master_df[
        (sample_master_df["Retailer"] == "Aldi") & 
        (sample_master_df["Product Type"] == "Shots")
    ]
    
    result = share_by_category(
        aldi_shots,
        groupby="Retailer",
        category_col="Product Type"
    )
    
    # Should have 1 row with 100%
    assert len(result) == 1
    assert result["Percentage"].iloc[0] == 100.0


# Test brand_retailer_heatmap
def test_brand_retailer_heatmap_basic(sample_master_df):
    """Test heatmap generation with top N brands."""
    result = brand_retailer_heatmap(sample_master_df, top_n=3)
    
    # Check structure
    expected_cols = [
        "Brand", "Total Market Share",
        "Aldi", "Lidl", "M&S", "Sainsbury's", "Tesco", "Tesco Express", "Waitrose",
        "% Cold Pressed", "% Functional"
    ]
    assert list(result.columns) == expected_cols
    
    # Should have 3 brands (Innocent, Tropicana, and one PL brand)
    assert len(result) == 3
    
    # Innocent has highest facings (10+6+15+8+18+7 = 64)
    assert result.iloc[0]["Brand"] == "Innocent"
    
    # Total market share should sum to less than 100 (we only have top 3)
    total_share = result["Total Market Share"].sum()
    assert 0 < total_share <= 100


def test_brand_retailer_heatmap_fewer_than_top_n(sample_master_df):
    """Test when fewer brands exist than top_n requested."""
    result = brand_retailer_heatmap(sample_master_df, top_n=100)
    
    # Should return all available brands (Innocent, Tropicana, Aldi, Lidl, Tesco)
    # Plus the aggregated "Private Label" row
    assert len(result) == 6
    
    # Verify Private Label row is present
    assert "Private Label" in result["Brand"].values


def test_brand_retailer_heatmap_brand_not_at_retailer(sample_master_df):
    """Test that missing brand × retailer combinations return 0.0."""
    result = brand_retailer_heatmap(sample_master_df, top_n=5)
    
    # Check that all retailer columns exist and have numeric values
    retailers = ["Aldi", "Lidl", "M&S", "Sainsbury's", "Tesco", "Tesco Express", "Waitrose"]
    for retailer in retailers:
        assert retailer in result.columns
        assert result[retailer].dtype in [np.float64, np.int64]


def test_brand_retailer_heatmap_empty_df(empty_df):
    """Test empty input."""
    result = brand_retailer_heatmap(empty_df, top_n=15)
    
    expected_cols = [
        "Brand", "Total Market Share",
        "Aldi", "Lidl", "M&S", "Sainsbury's", "Tesco", "Tesco Express", "Waitrose",
        "% Cold Pressed", "% Functional"
    ]
    assert list(result.columns) == expected_cols
    assert len(result) == 0


# Test retailer_sizing
def test_retailer_sizing_basic(sample_master_df):
    """Test table and chart data generation."""
    table_data, chart_data = retailer_sizing(sample_master_df)
    
    # Check table structure
    assert list(table_data.columns) == [
        "Retailer", "Store Format", "Avg SKU Count", "Avg Facings"
    ]
    assert len(table_data) > 0
    
    # Check chart structure
    assert list(chart_data.columns) == ["Retailer", "% PL", "% HPP", "% Cold Pressed"]
    assert len(chart_data) == 3  # Aldi, Lidl, Tesco
    
    # Aldi has 2 stores (London, Manchester)
    aldi_table = table_data[table_data["Retailer"] == "Aldi"]
    assert len(aldi_table) == 1  # One format (Discount)


def test_retailer_sizing_single_store(sample_master_df):
    """Test when retailer has only one store."""
    # Filter to only Tesco London
    tesco_london = sample_master_df[sample_master_df["Store Name"] == "Tesco London"]
    
    table_data, chart_data = retailer_sizing(tesco_london)
    
    # Should have 1 row in table (avg = that store's values)
    assert len(table_data) == 1
    assert len(chart_data) == 1


def test_retailer_sizing_missing_format(sample_master_df):
    """Test when Store Format is blank."""
    # Remove Store Format column
    df_no_format = sample_master_df.drop(columns=["Store Format"])
    
    table_data, chart_data = retailer_sizing(df_no_format)
    
    # Should have "Unknown" as format
    assert "Unknown" in table_data["Store Format"].values


# Test retailer_deep_dive
def test_retailer_deep_dive_basic(sample_master_df):
    """Test all four charts for a single retailer."""
    result = retailer_deep_dive(sample_master_df, "Aldi")
    
    # Check structure
    assert set(result.keys()) == {"product_type", "pl_vs_branded", "extraction", "need_state"}
    
    # Check product_type (absolute facings)
    pt_df = result["product_type"]
    assert list(pt_df.columns) == ["Product Type", "Facings"]
    assert len(pt_df) == 3  # Pure Juices, Smoothies, Shots
    
    # Check pl_vs_branded (percentage)
    pl_df = result["pl_vs_branded"]
    assert list(pl_df.columns) == ["Branded/Private Label", "Percentage"]
    assert len(pl_df) == 2  # Branded, Private Label
    
    # Percentages should sum to 100 (or close due to rounding)
    assert pl_df["Percentage"].sum() == pytest.approx(100.0, rel=0.01)


def test_retailer_deep_dive_retailer_not_found(sample_master_df):
    """Test when retailer doesn't exist in data."""
    result = retailer_deep_dive(sample_master_df, "Waitrose")
    
    # Should return empty DataFrames with correct schema
    assert len(result["product_type"]) == 0
    assert len(result["pl_vs_branded"]) == 0
    assert len(result["extraction"]) == 0
    assert len(result["need_state"]) == 0


def test_retailer_deep_dive_missing_categories(sample_master_df):
    """Test when some categories are missing for the retailer."""
    # Filter to only rows with Product Type
    df_filtered = sample_master_df[sample_master_df["Product Type"].notna()]
    
    result = retailer_deep_dive(df_filtered, "Aldi")
    
    # Should still have all four keys
    assert set(result.keys()) == {"product_type", "pl_vs_branded", "extraction", "need_state"}


# Test market_fingerprint
def test_market_fingerprint_basic(sample_master_df):
    """Test all five category breakdowns."""
    result = market_fingerprint(sample_master_df)
    
    # Check structure
    assert set(result.keys()) == {
        "product_type", "pl_vs_branded", "extraction", "hpp", "need_state"
    }
    
    # Check each DataFrame has correct structure
    pt_df = result["product_type"]
    assert list(pt_df.columns) == ["Retailer", "Product Type", "Count", "Percentage"]
    assert len(pt_df) > 0
    
    # Check that all retailers are present
    retailers = pt_df["Retailer"].unique()
    assert "Aldi" in retailers
    assert "Lidl" in retailers
    assert "Tesco" in retailers


def test_market_fingerprint_empty_df(empty_df):
    """Test empty input."""
    result = market_fingerprint(empty_df)
    
    # Should have all five keys
    assert set(result.keys()) == {
        "product_type", "pl_vs_branded", "extraction", "hpp", "need_state"
    }
    
    # Each should be empty with correct schema
    for key, df in result.items():
        assert len(df) == 0
        assert len(df.columns) == 4  # [Retailer, category, Count, Percentage]


def test_market_fingerprint_percentages_sum_to_100(sample_master_df):
    """Test that percentages within each retailer sum to ~100%."""
    result = market_fingerprint(sample_master_df)
    
    # Check Product Type percentages for Aldi
    pt_df = result["product_type"]
    aldi_pcts = pt_df[pt_df["Retailer"] == "Aldi"]["Percentage"].sum()
    assert aldi_pcts == pytest.approx(100.0, rel=0.01)
    
    # Check PL vs Branded percentages for Lidl
    pl_df = result["pl_vs_branded"]
    lidl_pcts = pl_df[pl_df["Retailer"] == "Lidl"]["Percentage"].sum()
    assert lidl_pcts == pytest.approx(100.0, rel=0.01)


# Integration test: realistic workflow
def test_full_workflow(sample_master_df):
    """Test a realistic workflow: generate all slide data types."""
    # Slide 1: Market Fingerprint
    mf_data = market_fingerprint(sample_master_df)
    assert len(mf_data) == 5
    
    # Slide 2: Brand Landscape
    bl_data = brand_retailer_heatmap(sample_master_df, top_n=15)
    assert len(bl_data) > 0
    
    # Slide 3: Retailer Sizing
    table, chart = retailer_sizing(sample_master_df)
    assert len(table) > 0
    assert len(chart) > 0
    
    # Slide 4: Retailer Deep Dive
    dd_data = retailer_deep_dive(sample_master_df, "Aldi")
    assert len(dd_data) == 4
    
    # All data generated successfully
    assert True
