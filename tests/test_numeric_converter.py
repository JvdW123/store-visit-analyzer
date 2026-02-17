"""
Tests for processing/numeric_converter.py

Covers: currency symbol stripping, confidence score scale normalization,
unknown-to-blank conversion, already-numeric passthrough, and error handling.
"""

import pandas as pd
import pytest

from processing.numeric_converter import (
    NumericConversionResult,
    convert_numerics,
    _convert_single_confidence_score,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_numeric_df(overrides: dict | None = None) -> pd.DataFrame:
    """Build a single-row DataFrame with numeric columns."""
    base = {
        "Brand": ["TestBrand"],
        "Shelf Levels": [None],
        "Facings": [None],
        "Price (Local Currency)": [None],
        "Packaging Size (ml)": [None],
        "Est. Linear Meters": [None],
        "Confidence Score": [None],
    }
    if overrides:
        for key, value in overrides.items():
            base[key] = [value] if not isinstance(value, list) else value
    return pd.DataFrame(base)


# ═══════════════════════════════════════════════════════════════════════════
# Currency symbol stripping
# ═══════════════════════════════════════════════════════════════════════════

class TestCurrencyStripping:
    def test_pound_sign(self):
        df = _make_numeric_df({"Price (Local Currency)": "£3.49"})
        result = convert_numerics(df)
        assert result.dataframe.at[0, "Price (Local Currency)"] == 3.49

    def test_euro_sign(self):
        df = _make_numeric_df({"Price (Local Currency)": "€2.99"})
        result = convert_numerics(df)
        assert result.dataframe.at[0, "Price (Local Currency)"] == 2.99

    def test_dollar_sign(self):
        df = _make_numeric_df({"Price (Local Currency)": "$4.50"})
        result = convert_numerics(df)
        assert result.dataframe.at[0, "Price (Local Currency)"] == 4.50

    def test_thousands_separator(self):
        df = _make_numeric_df({"Price (Local Currency)": "£1,250.00"})
        result = convert_numerics(df)
        assert result.dataframe.at[0, "Price (Local Currency)"] == 1250.00


# ═══════════════════════════════════════════════════════════════════════════
# Packaging Size — "ml" suffix stripping
# ═══════════════════════════════════════════════════════════════════════════

class TestPackagingSizeConversion:
    def test_ml_suffix(self):
        df = _make_numeric_df({"Packaging Size (ml)": "250ml"})
        result = convert_numerics(df)
        assert result.dataframe.at[0, "Packaging Size (ml)"] == 250

    def test_ml_with_space(self):
        df = _make_numeric_df({"Packaging Size (ml)": "330 ml"})
        result = convert_numerics(df)
        assert result.dataframe.at[0, "Packaging Size (ml)"] == 330

    def test_already_integer(self):
        df = _make_numeric_df({"Packaging Size (ml)": 500})
        result = convert_numerics(df)
        assert result.dataframe.at[0, "Packaging Size (ml)"] == 500


# ═══════════════════════════════════════════════════════════════════════════
# Integer columns
# ═══════════════════════════════════════════════════════════════════════════

class TestIntegerConversion:
    def test_shelf_levels_string(self):
        df = _make_numeric_df({"Shelf Levels": "  5  "})
        result = convert_numerics(df)
        assert result.dataframe.at[0, "Shelf Levels"] == 5

    def test_facings_string(self):
        df = _make_numeric_df({"Facings": "3"})
        result = convert_numerics(df)
        assert result.dataframe.at[0, "Facings"] == 3

    def test_facings_non_numeric_text(self):
        """Non-numeric text in Facings should be flagged as an error."""
        df = _make_numeric_df({"Facings": "Private Label"})
        result = convert_numerics(df)
        assert len(result.errors) >= 1
        assert result.errors[0]["column"] == "Facings"
        assert pd.isna(result.dataframe.at[0, "Facings"])


# ═══════════════════════════════════════════════════════════════════════════
# Float columns
# ═══════════════════════════════════════════════════════════════════════════

class TestFloatConversion:
    def test_linear_meters(self):
        df = _make_numeric_df({"Est. Linear Meters": "2.5"})
        result = convert_numerics(df)
        assert result.dataframe.at[0, "Est. Linear Meters"] == 2.5

    def test_price_rounding(self):
        df = _make_numeric_df({"Price (Local Currency)": "3.495"})
        result = convert_numerics(df)
        assert result.dataframe.at[0, "Price (Local Currency)"] == 3.50


# ═══════════════════════════════════════════════════════════════════════════
# Unknown / blank handling
# ═══════════════════════════════════════════════════════════════════════════

class TestUnknownHandling:
    def test_unknown_string_to_blank(self):
        df = _make_numeric_df({"Facings": "Unknown"})
        result = convert_numerics(df)
        assert pd.isna(result.dataframe.at[0, "Facings"])
        assert len(result.errors) == 0  # not an error, just blank

    def test_unkown_typo_to_blank(self):
        df = _make_numeric_df({"Shelf Levels": "Unkown"})
        result = convert_numerics(df)
        assert pd.isna(result.dataframe.at[0, "Shelf Levels"])
        assert len(result.errors) == 0

    def test_na_stays_na(self):
        df = _make_numeric_df({"Facings": None})
        result = convert_numerics(df)
        assert pd.isna(result.dataframe.at[0, "Facings"])

    def test_dash_to_blank(self):
        df = _make_numeric_df({"Shelf Levels": "-"})
        result = convert_numerics(df)
        assert pd.isna(result.dataframe.at[0, "Shelf Levels"])


# ═══════════════════════════════════════════════════════════════════════════
# Confidence Score special rules
# ═══════════════════════════════════════════════════════════════════════════

class TestConfidenceScoreNormalization:
    def test_percentage_string(self):
        """'85%' → 85"""
        df = _make_numeric_df({"Confidence Score": "85%"})
        result = convert_numerics(df)
        assert result.dataframe.at[0, "Confidence Score"] == 85

    def test_decimal_085_to_85(self):
        """0.85 → 85 (multiply by 100)"""
        df = _make_numeric_df({"Confidence Score": 0.85})
        result = convert_numerics(df)
        assert result.dataframe.at[0, "Confidence Score"] == 85

    def test_decimal_050_to_50(self):
        """0.5 → 50"""
        df = _make_numeric_df({"Confidence Score": 0.5})
        result = convert_numerics(df)
        assert result.dataframe.at[0, "Confidence Score"] == 50

    def test_one_point_zero_to_100(self):
        """1.0 → 100 (value > 0 and <= 1 → multiply by 100)"""
        df = _make_numeric_df({"Confidence Score": 1.0})
        result = convert_numerics(df)
        assert result.dataframe.at[0, "Confidence Score"] == 100

    def test_zero_stays_zero(self):
        """Exactly 0 → stays as 0"""
        df = _make_numeric_df({"Confidence Score": 0})
        result = convert_numerics(df)
        assert result.dataframe.at[0, "Confidence Score"] == 0

    def test_integer_42_stays_42(self):
        """42 → 42 (already on 0-100 scale)"""
        df = _make_numeric_df({"Confidence Score": 42})
        result = convert_numerics(df)
        assert result.dataframe.at[0, "Confidence Score"] == 42

    def test_exactly_100_stays_100(self):
        """100 → 100"""
        df = _make_numeric_df({"Confidence Score": 100})
        result = convert_numerics(df)
        assert result.dataframe.at[0, "Confidence Score"] == 100

    def test_above_100_flagged_as_error(self):
        """150 → error, set to blank"""
        df = _make_numeric_df({"Confidence Score": 150})
        result = convert_numerics(df)
        assert pd.isna(result.dataframe.at[0, "Confidence Score"])
        assert len(result.errors) >= 1

    def test_negative_flagged_as_error(self):
        """-5 → error, set to blank"""
        df = _make_numeric_df({"Confidence Score": -5})
        result = convert_numerics(df)
        assert pd.isna(result.dataframe.at[0, "Confidence Score"])
        assert len(result.errors) >= 1

    def test_blank_stays_blank(self):
        df = _make_numeric_df({"Confidence Score": None})
        result = convert_numerics(df)
        assert pd.isna(result.dataframe.at[0, "Confidence Score"])
        assert len(result.errors) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Unit tests for the internal Confidence Score converter
# ═══════════════════════════════════════════════════════════════════════════

class TestConfidenceScoreUnit:
    def test_string_percentage(self):
        val, err = _convert_single_confidence_score("90%")
        assert val == 90 and err is None

    def test_float_0_point_1(self):
        val, err = _convert_single_confidence_score(0.1)
        assert val == 10 and err is None

    def test_float_1_point_0(self):
        val, err = _convert_single_confidence_score(1.0)
        assert val == 100 and err is None

    def test_zero(self):
        val, err = _convert_single_confidence_score(0)
        assert val == 0 and err is None

    def test_unknown_string(self):
        val, err = _convert_single_confidence_score("Unknown")
        assert val is None and err is None

    def test_non_numeric(self):
        val, err = _convert_single_confidence_score("abc")
        assert val is None and err is not None


# ═══════════════════════════════════════════════════════════════════════════
# Already-numeric passthrough
# ═══════════════════════════════════════════════════════════════════════════

class TestAlreadyNumeric:
    def test_integer_passes_through(self):
        df = _make_numeric_df({"Facings": 4})
        result = convert_numerics(df)
        assert result.dataframe.at[0, "Facings"] == 4

    def test_float_passes_through(self):
        df = _make_numeric_df({"Price (Local Currency)": 3.99})
        result = convert_numerics(df)
        assert result.dataframe.at[0, "Price (Local Currency)"] == 3.99


# ═══════════════════════════════════════════════════════════════════════════
# Original DataFrame not mutated
# ═══════════════════════════════════════════════════════════════════════════

class TestImmutability:
    def test_original_not_mutated(self):
        df = _make_numeric_df({"Price (Local Currency)": "£9.99"})
        original_val = df.at[0, "Price (Local Currency)"]
        _ = convert_numerics(df)
        assert df.at[0, "Price (Local Currency)"] == original_val
