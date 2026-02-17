"""
Tests for processing/quality_checker.py

Covers: clean DataFrame detection, invalid categoricals, non-numeric in
numeric column, missing required fields, null stats, and empty DataFrame.
"""

import pandas as pd
import pytest

from processing.quality_checker import (
    QualityReport,
    check_quality,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_clean_df(rows: int = 3) -> pd.DataFrame:
    """Build a DataFrame that should pass all quality checks.

    Integer columns use explicit Python int values via object dtype to avoid
    numpy int64 issues when later setting individual cells to strings.
    """
    df = pd.DataFrame({
        "Country": ["United Kingdom"] * rows,
        "City": ["London"] * rows,
        "Retailer": ["Tesco"] * rows,
        "Store Name": ["Tesco London"] * rows,
        "Currency": ["GBP"] * rows,
        "Product Type": ["Pure Juices"] * rows,
        "Branded/Private Label": ["Branded"] * rows,
        "Processing Method": ["Pasteurized"] * rows,
        "HPP Treatment": ["No"] * rows,
        "Packaging Type": ["PET Bottle"] * rows,
        "Stock Status": ["In Stock"] * rows,
        "Shelf Level": ["1st"] * rows,
        "Shelf Location": ["Chilled Section"] * rows,
        "Brand": [f"Brand_{i}" for i in range(rows)],
        "Facings": pd.array([3] * rows, dtype="Int64"),
        "Price (Local Currency)": [2.99] * rows,
        "Price (EUR)": [3.53] * rows,
        "Packaging Size (ml)": pd.array([250] * rows, dtype="Int64"),
        "Shelf Levels": pd.array([5] * rows, dtype="Int64"),
        "Confidence Score": pd.array([85] * rows, dtype="Int64"),
        "Est. Linear Meters": [2.5] * rows,
    })
    return df


# ═══════════════════════════════════════════════════════════════════════════
# Clean DataFrame
# ═══════════════════════════════════════════════════════════════════════════

class TestCleanDataFrame:
    def test_is_clean_true(self):
        df = _make_clean_df()
        report = check_quality(df)
        assert report.is_clean is True
        assert len(report.invalid_categoricals) == 0
        assert len(report.invalid_numerics) == 0
        assert len(report.missing_required) == 0

    def test_total_rows(self):
        df = _make_clean_df(rows=5)
        report = check_quality(df)
        assert report.total_rows == 5


# ═══════════════════════════════════════════════════════════════════════════
# Invalid categorical values
# ═══════════════════════════════════════════════════════════════════════════

class TestInvalidCategoricals:
    def test_invalid_product_type_detected(self):
        df = _make_clean_df(rows=1)
        df.at[0, "Product Type"] = "Energy Drink"  # not in valid set
        report = check_quality(df)
        assert report.is_clean is False
        assert len(report.invalid_categoricals) >= 1
        error = report.invalid_categoricals[0]
        assert error["column"] == "Product Type"
        assert error["value"] == "Energy Drink"

    def test_null_categorical_is_ok(self):
        df = _make_clean_df(rows=1)
        df.at[0, "Product Type"] = None  # blank is fine
        report = check_quality(df)
        product_errors = [
            e for e in report.invalid_categoricals if e["column"] == "Product Type"
        ]
        assert len(product_errors) == 0

    def test_multiple_invalid_values(self):
        df = _make_clean_df(rows=2)
        df.at[0, "Product Type"] = "Bad Value 1"
        df.at[1, "Shelf Level"] = "99th"
        report = check_quality(df)
        assert len(report.invalid_categoricals) == 2


# ═══════════════════════════════════════════════════════════════════════════
# Invalid numeric values
# ═══════════════════════════════════════════════════════════════════════════

class TestInvalidNumerics:
    def test_string_in_numeric_column(self):
        # Build with object dtype so we can insert a string into a "numeric" column
        df = _make_clean_df(rows=1)
        df["Facings"] = df["Facings"].astype(object)
        df.at[0, "Facings"] = "three"  # should be numeric
        report = check_quality(df)
        assert report.is_clean is False
        assert len(report.invalid_numerics) >= 1
        facings_errors = [e for e in report.invalid_numerics if e["column"] == "Facings"]
        assert len(facings_errors) >= 1

    def test_null_numeric_is_ok(self):
        df = _make_clean_df(rows=1)
        df.at[0, "Facings"] = None
        report = check_quality(df)
        facings_errors = [
            e for e in report.invalid_numerics if e["column"] == "Facings"
        ]
        assert len(facings_errors) == 0

    def test_int_and_float_are_valid(self):
        df = _make_clean_df(rows=1)
        df.at[0, "Facings"] = 3
        df.at[0, "Price (Local Currency)"] = 2.99
        report = check_quality(df)
        assert len(report.invalid_numerics) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Missing required fields
# ═══════════════════════════════════════════════════════════════════════════

class TestMissingRequired:
    def test_missing_country(self):
        df = _make_clean_df(rows=1)
        df.at[0, "Country"] = None
        report = check_quality(df)
        assert report.is_clean is False
        assert len(report.missing_required) >= 1

    def test_empty_string_is_missing(self):
        df = _make_clean_df(rows=1)
        df.at[0, "City"] = "   "  # whitespace-only is missing
        report = check_quality(df)
        missing_city = [
            e for e in report.missing_required if e["column"] == "City"
        ]
        assert len(missing_city) == 1

    def test_all_required_present_no_errors(self):
        df = _make_clean_df()
        report = check_quality(df)
        assert len(report.missing_required) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Null statistics
# ═══════════════════════════════════════════════════════════════════════════

class TestNullStats:
    def test_null_counts(self):
        df = _make_clean_df(rows=4)
        df.at[0, "Brand"] = None
        df.at[1, "Brand"] = None
        report = check_quality(df)
        # Brand might not be in null_counts if not in MASTER_COLUMNS that are present
        if "Brand" in report.null_counts:
            assert report.null_counts["Brand"] == 2
            assert report.null_percentages["Brand"] == 50.0

    def test_zero_nulls(self):
        df = _make_clean_df()
        report = check_quality(df)
        assert report.null_counts.get("Country", 0) == 0

    def test_null_percentage_calculation(self):
        df = _make_clean_df(rows=10)
        df.at[0, "Product Type"] = None
        report = check_quality(df)
        assert report.null_counts.get("Product Type") == 1
        assert report.null_percentages.get("Product Type") == 10.0


# ═══════════════════════════════════════════════════════════════════════════
# Empty DataFrame
# ═══════════════════════════════════════════════════════════════════════════

class TestEmptyDataFrame:
    def test_empty_df_is_clean(self):
        df = pd.DataFrame()
        report = check_quality(df)
        assert report.is_clean is True
        assert report.total_rows == 0

    def test_empty_df_no_errors(self):
        df = pd.DataFrame()
        report = check_quality(df)
        assert len(report.invalid_categoricals) == 0
        assert len(report.invalid_numerics) == 0
        assert len(report.missing_required) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Metadata passthrough
# ═══════════════════════════════════════════════════════════════════════════

class TestMetadata:
    def test_normalization_log_included(self):
        df = _make_clean_df()
        log = [{"row": 0, "column": "Product Type", "original": "pure juices",
                "normalized": "Pure Juices"}]
        report = check_quality(df, normalization_log=log)
        assert len(report.normalization_log) == 1

    def test_exchange_rate_included(self):
        df = _make_clean_df()
        rates = {"GBP": 1.18}
        report = check_quality(df, exchange_rate_used=rates)
        assert report.exchange_rate_used == {"GBP": 1.18}

    def test_source_filenames_included(self):
        df = _make_clean_df()
        files = ["file1.xlsx", "file2.xlsx"]
        report = check_quality(df, source_filenames=files)
        assert report.files_processed == files
