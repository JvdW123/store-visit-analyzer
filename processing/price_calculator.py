"""
Price calculator — derives Currency, Price (EUR), and Price per Liter (EUR).

Currency is derived from Country.  Price (EUR) is the local price multiplied
by an exchange rate.  Price per Liter is always recalculated from Price (EUR)
and Packaging Size — raw file values are never trusted.

Public API:
    calculate_prices(dataframe, exchange_rates, country) → PriceCalculationResult

See docs/RULES.md — Currency & Exchange Rate section for the specification.
"""

import logging
from dataclasses import dataclass, field

import pandas as pd

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════

COUNTRY_CURRENCY_MAP: dict[str, str] = {
    "United Kingdom": "GBP",
    "France": "EUR",
    "Germany": "EUR",
    "Netherlands": "EUR",
}

DEFAULT_EXCHANGE_RATES: dict[str, float] = {
    "GBP": 1.18,   # Fallback GBP → EUR rate if no API / override
    "EUR": 1.0,
}


# ═══════════════════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class PriceCalculationResult:
    """Output of the calculate_prices() function."""

    dataframe: pd.DataFrame = field(default_factory=pd.DataFrame)
    exchange_rate_used: dict[str, float] = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def calculate_prices(
    dataframe: pd.DataFrame,
    exchange_rates: dict[str, float] | None = None,
    country: str = "United Kingdom",
) -> PriceCalculationResult:
    """
    Derive Currency, Price (EUR), and Price per Liter (EUR).

    Steps:
      1. Set Currency based on Country.
      2. Calculate Price (EUR) = Price (Local) x exchange_rate.
      3. Recalculate Price per Liter (EUR) = Price (EUR) / (Packaging Size / 1000).

    Args:
        dataframe: DataFrame with numeric columns already converted.
        exchange_rates: Optional override for currency → EUR rates.
                        Falls back to DEFAULT_EXCHANGE_RATES.
        country: Country string for currency derivation.

    Returns:
        PriceCalculationResult with updated DataFrame, rates used, and errors.
    """
    result_df = dataframe.copy()
    rates = exchange_rates if exchange_rates is not None else DEFAULT_EXCHANGE_RATES.copy()
    errors: list[dict] = []

    # Step 1: Derive Currency from Country
    currency = _derive_currency(country)
    result_df["Currency"] = currency

    # Ensure the exchange rate for this currency exists
    if currency not in rates:
        logger.warning(
            f"No exchange rate for '{currency}' — defaulting to 1.0"
        )
        rates[currency] = 1.0

    # Step 2: Calculate Price (EUR)
    if "Price (Local Currency)" in result_df.columns:
        for idx in result_df.index:
            local_price = result_df.at[idx, "Price (Local Currency)"]
            eur_price = _calculate_eur_price(local_price, currency, rates)
            result_df.at[idx, "Price (EUR)"] = eur_price
    else:
        result_df["Price (EUR)"] = None

    # Step 3: Recalculate Price per Liter (EUR)
    has_packaging = "Packaging Size (ml)" in result_df.columns
    has_eur_price = "Price (EUR)" in result_df.columns

    if has_eur_price and has_packaging:
        for idx in result_df.index:
            price_eur = result_df.at[idx, "Price (EUR)"]
            packaging_ml = result_df.at[idx, "Packaging Size (ml)"]

            price_per_liter, error = _calculate_price_per_liter(
                price_eur, packaging_ml
            )
            result_df.at[idx, "Price per Liter (EUR)"] = price_per_liter

            if error is not None:
                errors.append({
                    "row": idx,
                    "column": "Price per Liter (EUR)",
                    "error": error,
                })
    else:
        result_df["Price per Liter (EUR)"] = None

    # Construct Store Name if both Retailer and City are present
    if "Retailer" in result_df.columns and "City" in result_df.columns:
        result_df["Store Name"] = result_df.apply(
            lambda row: _build_store_name(row.get("Retailer"), row.get("City")),
            axis=1,
        )

    # Set Country column
    result_df["Country"] = country

    logger.info(
        f"Price calculation complete: currency={currency}, "
        f"rate={rates.get(currency)}, {len(errors)} errors"
    )

    return PriceCalculationResult(
        dataframe=result_df,
        exchange_rate_used=rates,
        errors=errors,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════

def _derive_currency(country: str) -> str:
    """
    Map a country name to its currency code.

    Args:
        country: Country string (e.g. "United Kingdom").

    Returns:
        Currency code (e.g. "GBP"). Defaults to "EUR" if unknown.
    """
    currency = COUNTRY_CURRENCY_MAP.get(country)

    if currency is None:
        logger.warning(
            f"Unknown country '{country}' — defaulting currency to EUR"
        )
        return "EUR"

    return currency


def _calculate_eur_price(
    local_price: float | None,
    currency: str,
    rates: dict[str, float],
) -> float | None:
    """
    Convert a local-currency price to EUR.

    Args:
        local_price: Price in local currency, or None.
        currency: Currency code (e.g. "GBP").
        rates: Dict of currency → EUR conversion rate.

    Returns:
        Price in EUR rounded to 2 decimal places, or None if input is missing.
    """
    if pd.isna(local_price):
        return None

    rate = rates.get(currency, 1.0)
    return round(float(local_price) * rate, 2)


def _calculate_price_per_liter(
    price_eur: float | None,
    packaging_ml: int | None,
) -> tuple[float | None, str | None]:
    """
    Calculate Price per Liter (EUR) from Price (EUR) and Packaging Size (ml).

    Formula: Price (EUR) / (Packaging Size (ml) / 1000)

    Args:
        price_eur: Price in EUR, or None.
        packaging_ml: Packaging size in milliliters, or None.

    Returns:
        (price_per_liter, error_message) — error is None on success.
    """
    if pd.isna(price_eur) or pd.isna(packaging_ml):
        return None, None

    packaging_ml_val = int(packaging_ml)

    if packaging_ml_val == 0:
        return None, "Packaging Size is 0 — cannot calculate Price per Liter"

    price_per_liter = float(price_eur) / (packaging_ml_val / 1000)
    return round(price_per_liter, 2), None


def _build_store_name(retailer: str | None, city: str | None) -> str | None:
    """
    Construct Store Name as '{Retailer} {City}'.

    Returns None if either component is missing.
    """
    if pd.isna(retailer) or pd.isna(city):
        return None

    retailer_str = str(retailer).strip()
    city_str = str(city).strip()

    if not retailer_str or not city_str:
        return None

    return f"{retailer_str} {city_str}"
