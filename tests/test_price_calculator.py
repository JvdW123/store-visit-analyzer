"""
Tests for processing/price_calculator.py

Covers: currency derivation, EUR conversion, price-per-liter calculation,
missing/zero packaging size, store name construction, and error handling.
"""

import pandas as pd
import pytest

from processing.price_calculator import (
    PriceCalculationResult,
    calculate_prices,
    _derive_currency,
    _calculate_eur_price,
    _calculate_price_per_liter,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_price_df(overrides: dict | None = None) -> pd.DataFrame:
    """Build a single-row DataFrame with price-relevant columns."""
    base = {
        "Retailer": ["Tesco"],
        "City": ["London"],
        "Price (Local Currency)": [None],
        "Packaging Size (ml)": [None],
    }
    if overrides:
        for key, value in overrides.items():
            base[key] = [value] if not isinstance(value, list) else value
    return pd.DataFrame(base)


# ═══════════════════════════════════════════════════════════════════════════
# Currency derivation
# ═══════════════════════════════════════════════════════════════════════════

class TestCurrencyDerivation:
    def test_uk_to_gbp(self):
        assert _derive_currency("United Kingdom") == "GBP"

    def test_france_to_eur(self):
        assert _derive_currency("France") == "EUR"

    def test_germany_to_eur(self):
        assert _derive_currency("Germany") == "EUR"

    def test_netherlands_to_eur(self):
        assert _derive_currency("Netherlands") == "EUR"

    def test_unknown_country_defaults_to_eur(self):
        assert _derive_currency("Atlantis") == "EUR"


# ═══════════════════════════════════════════════════════════════════════════
# EUR price conversion
# ═══════════════════════════════════════════════════════════════════════════

class TestEURConversion:
    def test_gbp_to_eur(self):
        df = _make_price_df({"Price (Local Currency)": 3.00})
        result = calculate_prices(
            df,
            exchange_rates={"GBP": 1.18, "EUR": 1.0},
            country="United Kingdom",
        )
        assert result.dataframe.at[0, "Price (EUR)"] == 3.54  # 3.00 * 1.18

    def test_eur_stays_same(self):
        df = _make_price_df({"Price (Local Currency)": 2.50})
        result = calculate_prices(
            df,
            exchange_rates={"EUR": 1.0},
            country="France",
        )
        assert result.dataframe.at[0, "Price (EUR)"] == 2.50

    def test_missing_price_gives_none(self):
        df = _make_price_df({"Price (Local Currency)": None})
        result = calculate_prices(df, country="United Kingdom")
        assert pd.isna(result.dataframe.at[0, "Price (EUR)"])

    def test_currency_column_set(self):
        df = _make_price_df()
        result = calculate_prices(df, country="United Kingdom")
        assert result.dataframe.at[0, "Currency"] == "GBP"

    def test_exchange_rate_logged(self):
        rates = {"GBP": 1.20, "EUR": 1.0}
        df = _make_price_df({"Price (Local Currency)": 1.00})
        result = calculate_prices(df, exchange_rates=rates, country="United Kingdom")
        assert result.exchange_rate_used["GBP"] == 1.20


# ═══════════════════════════════════════════════════════════════════════════
# Price per Liter
# ═══════════════════════════════════════════════════════════════════════════

class TestPricePerLiter:
    def test_correct_calculation(self):
        """3.54 EUR / (250ml / 1000) = 14.16 EUR/L"""
        df = _make_price_df({
            "Price (Local Currency)": 3.00,
            "Packaging Size (ml)": 250,
        })
        result = calculate_prices(
            df,
            exchange_rates={"GBP": 1.18, "EUR": 1.0},
            country="United Kingdom",
        )
        assert result.dataframe.at[0, "Price per Liter (EUR)"] == 14.16

    def test_missing_packaging_gives_none(self):
        df = _make_price_df({
            "Price (Local Currency)": 3.00,
            "Packaging Size (ml)": None,
        })
        result = calculate_prices(df, country="United Kingdom")
        assert pd.isna(result.dataframe.at[0, "Price per Liter (EUR)"])

    def test_missing_price_gives_none(self):
        df = _make_price_df({
            "Price (Local Currency)": None,
            "Packaging Size (ml)": 500,
        })
        result = calculate_prices(df, country="United Kingdom")
        assert pd.isna(result.dataframe.at[0, "Price per Liter (EUR)"])

    def test_zero_packaging_gives_none_and_error(self):
        df = _make_price_df({
            "Price (Local Currency)": 3.00,
            "Packaging Size (ml)": 0,
        })
        result = calculate_prices(df, country="United Kingdom")
        assert pd.isna(result.dataframe.at[0, "Price per Liter (EUR)"])
        assert len(result.errors) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# Store Name construction
# ═══════════════════════════════════════════════════════════════════════════

class TestStoreName:
    def test_store_name_constructed(self):
        df = _make_price_df()
        result = calculate_prices(df, country="United Kingdom")
        assert result.dataframe.at[0, "Store Name"] == "Tesco London"

    def test_missing_retailer_gives_none(self):
        df = _make_price_df({"Retailer": None})
        result = calculate_prices(df, country="United Kingdom")
        assert pd.isna(result.dataframe.at[0, "Store Name"])


# ═══════════════════════════════════════════════════════════════════════════
# Immutability
# ═══════════════════════════════════════════════════════════════════════════

class TestImmutability:
    def test_original_not_mutated(self):
        df = _make_price_df({"Price (Local Currency)": 5.00})
        original_val = df.at[0, "Price (Local Currency)"]
        _ = calculate_prices(df, country="United Kingdom")
        assert df.at[0, "Price (Local Currency)"] == original_val
