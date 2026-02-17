"""
Numeric converter — converts text-stored numbers to proper Python types.

Handles currency symbols, percentage signs, "ml" suffixes, and the
Confidence Score's variable scale (0-1 vs 0-100 vs percentage string).

Public API:
    convert_numerics(dataframe) → NumericConversionResult

See docs/RULES.md — Numeric Conversion Rules for the full specification.
"""

import logging
import re
from dataclasses import dataclass, field

import pandas as pd

from config.schema import COLUMN_TYPES

logger = logging.getLogger(__name__)

# Columns that need numeric conversion, grouped by target type.
_INTEGER_COLUMNS: list[str] = [
    col for col, dtype in COLUMN_TYPES.items() if dtype == "integer"
]
_FLOAT_COLUMNS: list[str] = [
    col for col, dtype in COLUMN_TYPES.items() if dtype == "float"
]

# Regex to strip common currency symbols and thousands separators
_CURRENCY_PATTERN = re.compile(r"[£€$]")
_THOUSANDS_SEP_PATTERN = re.compile(r"(?<=\d),(?=\d{3})")

# Words that mean "unknown" — convert to blank, not an error
_UNKNOWN_STRINGS: set[str] = {"unknown", "unkown", "n/a", "na", "-", "—"}


# ═══════════════════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class NumericConversionResult:
    """Output of the convert_numerics() function."""

    dataframe: pd.DataFrame = field(default_factory=pd.DataFrame)
    errors: list[dict] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def convert_numerics(dataframe: pd.DataFrame) -> NumericConversionResult:
    """
    Convert all numeric columns from text to proper Python types.

    Processes integer and float columns defined in COLUMN_TYPES.
    Confidence Score gets special handling for scale normalization.

    Args:
        dataframe: DataFrame with master-schema column names.

    Returns:
        NumericConversionResult with converted DataFrame and list of
        conversion errors (row, column, original value, error message).
    """
    result_df = dataframe.copy()
    all_errors: list[dict] = []

    # Process each numeric column
    for column in _INTEGER_COLUMNS + _FLOAT_COLUMNS:
        if column not in result_df.columns:
            continue

        target_type = COLUMN_TYPES[column]

        # Confidence Score has special conversion logic
        if column == "Confidence Score":
            errors = _convert_confidence_score_column(result_df, column)
        else:
            errors = _convert_column(result_df, column, target_type)

        all_errors.extend(errors)

    logger.info(
        f"Numeric conversion complete: {len(all_errors)} conversion errors"
    )

    return NumericConversionResult(dataframe=result_df, errors=all_errors)


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════

def _convert_column(
    dataframe: pd.DataFrame,
    column: str,
    target_type: str,
) -> list[dict]:
    """
    Convert a single column to its target numeric type.

    Args:
        dataframe: DataFrame to modify IN PLACE for this column.
        column: Column name to convert.
        target_type: "integer" or "float".

    Returns:
        List of error dicts for values that could not be converted.
    """
    errors: list[dict] = []

    for idx in dataframe.index:
        raw_value = dataframe.at[idx, column]

        # Already NaN → leave as-is
        if pd.isna(raw_value):
            continue

        # Already the correct numeric type
        if target_type == "integer" and isinstance(raw_value, (int,)):
            continue
        if target_type == "float" and isinstance(raw_value, (int, float)):
            continue

        converted, error = _safe_convert(raw_value, target_type, column)

        if error is not None:
            errors.append({
                "row": idx,
                "column": column,
                "original": str(raw_value),
                "error": error,
            })
            dataframe.at[idx, column] = None
        else:
            dataframe.at[idx, column] = converted

    return errors


def _safe_convert(
    value: object,
    target_type: str,
    column: str,
) -> tuple[int | float | None, str | None]:
    """
    Try to convert a single value to the target numeric type.

    Strips currency symbols, "ml", "%", whitespace, thousands separators.
    Values that are "unknown" variants are converted to None (blank).

    Args:
        value: The raw cell value.
        target_type: "integer" or "float".
        column: Column name (for logging context).

    Returns:
        (converted_value, error_message) — error_message is None on success.
    """
    raw_str = str(value).strip()

    # Check for "unknown" variants → blank
    if raw_str.lower() in _UNKNOWN_STRINGS:
        return None, None

    # Empty after stripping
    if raw_str == "":
        return None, None

    cleaned = _clean_numeric_string(raw_str, column)

    if cleaned == "":
        return None, f"Value '{raw_str}' is empty after cleaning"

    try:
        float_val = float(cleaned)
    except ValueError:
        return None, f"Cannot convert '{raw_str}' to number"

    if target_type == "integer":
        return int(round(float_val)), None
    else:
        # Round floats based on column precision conventions
        if "price" in column.lower() or "per liter" in column.lower():
            return round(float_val, 2), None
        elif "linear" in column.lower():
            return round(float_val, 1), None
        return float_val, None


def _clean_numeric_string(raw_str: str, column: str) -> str:
    """
    Strip non-numeric noise from a string before conversion.

    Removes: currency symbols (£€$), "ml", "%", thousands-separator commas,
    and leading/trailing whitespace.

    Args:
        raw_str: The raw string value.
        column: Column name (for context-specific stripping).

    Returns:
        Cleaned string ready for float() conversion.
    """
    cleaned = raw_str

    # Strip currency symbols
    cleaned = _CURRENCY_PATTERN.sub("", cleaned)

    # Strip "ml" suffix (for Packaging Size)
    cleaned = re.sub(r"\s*ml\b", "", cleaned, flags=re.IGNORECASE)

    # Strip percentage sign
    cleaned = cleaned.replace("%", "")

    # Remove thousands-separator commas (e.g. "1,250" → "1250")
    cleaned = _THOUSANDS_SEP_PATTERN.sub("", cleaned)

    # Final whitespace strip
    cleaned = cleaned.strip()

    return cleaned


def _convert_confidence_score_column(
    dataframe: pd.DataFrame,
    column: str,
) -> list[dict]:
    """
    Convert and normalize the Confidence Score column.

    Special rules (from RULES.md):
      1. String contains "%" → strip "%", convert to float
      2. Value > 0 and <= 1 → multiply by 100  (e.g. 0.85 → 85, 1.0 → 100)
      3. Value == 0 → keep as 0
      4. Value between 1 and 100 (exclusive of 0, inclusive of 100) → round to int
      5. Value > 100 or < 0 → flag as error, set to blank
      6. null / blank → blank

    Args:
        dataframe: DataFrame to modify IN PLACE.
        column: "Confidence Score".

    Returns:
        List of error dicts for out-of-range values.
    """
    errors: list[dict] = []

    for idx in dataframe.index:
        raw_value = dataframe.at[idx, column]

        if pd.isna(raw_value):
            continue

        converted, error = _convert_single_confidence_score(raw_value)

        if error is not None:
            errors.append({
                "row": idx,
                "column": column,
                "original": str(raw_value),
                "error": error,
            })
            dataframe.at[idx, column] = None
        else:
            dataframe.at[idx, column] = converted

    return errors


def _convert_single_confidence_score(value: object) -> tuple[int | None, str | None]:
    """
    Normalize a single Confidence Score value.

    Args:
        value: Raw cell value (could be str, int, float).

    Returns:
        (normalized_int, error_message) — error is None on success, value is
        None for blank/unknown inputs.
    """
    raw_str = str(value).strip()

    # Unknown variants → blank
    if raw_str.lower() in _UNKNOWN_STRINGS:
        return None, None

    if raw_str == "":
        return None, None

    # Strip percentage sign if present
    had_percent = "%" in raw_str
    cleaned = raw_str.replace("%", "").strip()

    try:
        float_val = float(cleaned)
    except ValueError:
        return None, f"Cannot convert Confidence Score '{raw_str}' to number"

    # Range validation and scale normalization
    if float_val < 0:
        return None, f"Confidence Score '{raw_str}' is negative (out of range)"

    if float_val > 100:
        return None, f"Confidence Score '{raw_str}' exceeds 100 (out of range)"

    # Exactly 0 → keep as 0
    if float_val == 0:
        return 0, None

    # Value > 0 and <= 1 → interpret as 0-1 scale, multiply by 100
    if float_val <= 1:
        return int(round(float_val * 100)), None

    # Value > 1 and <= 100 → already on 0-100 scale
    return int(round(float_val)), None
