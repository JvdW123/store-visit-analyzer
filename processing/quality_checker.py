"""
Quality checker — validates the final DataFrame and generates a quality report.

Runs three validation passes:
  1. Categorical validation: all values in constrained columns are in VALID_VALUES.
  2. Numeric validation: all numeric columns contain actual numeric types.
  3. Required fields: all required columns have no nulls.

Also computes null statistics per column and compiles all processing metadata
(normalization log, flagged items, exchange rates) into a single report dict.

Public API:
    check_quality(dataframe, ...) → QualityReport

See docs/ARCHITECTURE.md — quality_checker.py section for responsibilities.
"""

import logging
from dataclasses import dataclass, field

import pandas as pd

from config.schema import COLUMN_TYPES, MASTER_COLUMNS, REQUIRED_COLUMNS, VALID_VALUES

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class QualityReport:
    """Comprehensive quality report for the processed dataset."""

    total_rows: int = 0
    rows_per_file: dict[str, int] = field(default_factory=dict)
    null_counts: dict[str, int] = field(default_factory=dict)
    null_percentages: dict[str, float] = field(default_factory=dict)
    invalid_categoricals: list[dict] = field(default_factory=list)
    invalid_numerics: list[dict] = field(default_factory=list)
    missing_required: list[dict] = field(default_factory=list)
    normalization_log: list[dict] = field(default_factory=list)
    flagged_items: list[dict] = field(default_factory=list)
    exchange_rate_used: dict[str, float] = field(default_factory=dict)
    files_processed: list[str] = field(default_factory=list)
    is_clean: bool = True


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def check_quality(
    dataframe: pd.DataFrame,
    normalization_log: list[dict] | None = None,
    flagged_items: list[dict] | None = None,
    exchange_rate_used: dict[str, float] | None = None,
    source_filenames: list[str] | None = None,
    rows_per_file: dict[str, int] | None = None,
) -> QualityReport:
    """
    Validate the final DataFrame and build a comprehensive quality report.

    Checks:
      - All categorical column values are in their VALID_VALUES sets.
      - All numeric columns contain actual numeric types (not strings).
      - All REQUIRED_COLUMNS are fully populated (no nulls).

    Also computes null counts/percentages for every column.

    Args:
        dataframe: The final merged DataFrame to validate.
        normalization_log: Optional list of normalization changes from the
                          normalizer's changes_log.
        flagged_items: Optional list of items still flagged after LLM.
        exchange_rate_used: Optional dict of currency → rate used.
        source_filenames: Optional list of processed filenames.
        rows_per_file: Optional dict of filename → row count.

    Returns:
        QualityReport with all validation results and metadata.
    """
    report = QualityReport()
    report.total_rows = len(dataframe)
    report.normalization_log = normalization_log or []
    report.flagged_items = flagged_items or []
    report.exchange_rate_used = exchange_rate_used or {}
    report.files_processed = source_filenames or []
    report.rows_per_file = rows_per_file or {}

    # Compute null statistics
    report.null_counts, report.null_percentages = _compute_null_stats(dataframe)

    # Run validations
    report.invalid_categoricals = _validate_categoricals(dataframe)
    report.invalid_numerics = _validate_numerics(dataframe)
    report.missing_required = _check_required_fields(dataframe)

    # Determine overall cleanliness
    has_errors = (
        len(report.invalid_categoricals) > 0
        or len(report.invalid_numerics) > 0
        or len(report.missing_required) > 0
    )
    report.is_clean = not has_errors

    logger.info(
        f"Quality check complete: {report.total_rows} rows, "
        f"clean={report.is_clean}, "
        f"{len(report.invalid_categoricals)} invalid categoricals, "
        f"{len(report.invalid_numerics)} invalid numerics, "
        f"{len(report.missing_required)} missing required"
    )

    return report


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════

def _validate_categoricals(dataframe: pd.DataFrame) -> list[dict]:
    """
    Check all categorical columns with VALID_VALUES constraints.

    A non-null value that is not in the valid set is recorded as an error.
    Null/NaN values are acceptable (blank = we don't know).

    Args:
        dataframe: The DataFrame to validate.

    Returns:
        List of error dicts: {"row": int, "column": str, "value": str}
    """
    errors: list[dict] = []

    for column, valid_set in VALID_VALUES.items():
        if column not in dataframe.columns:
            continue

        for idx in dataframe.index:
            value = dataframe.at[idx, column]

            # NaN is OK (blank = we don't know)
            if pd.isna(value):
                continue

            value_str = str(value).strip()
            if value_str == "":
                continue

            if value_str not in valid_set:
                errors.append({
                    "row": idx,
                    "column": column,
                    "value": value_str,
                })

    return errors


def _validate_numerics(dataframe: pd.DataFrame) -> list[dict]:
    """
    Check all numeric columns contain actual numeric types.

    A non-null value whose type is not int or float (i.e. a string that
    was never converted) is recorded as an error.  Accepts Python int/float,
    numpy int/float, and pandas nullable integer types.

    Args:
        dataframe: The DataFrame to validate.

    Returns:
        List of error dicts: {"row": int, "column": str, "value": str}
    """
    import numpy as np

    errors: list[dict] = []

    numeric_columns = [
        col for col, dtype in COLUMN_TYPES.items()
        if dtype in ("integer", "float")
    ]

    for column in numeric_columns:
        if column not in dataframe.columns:
            continue

        for idx in dataframe.index:
            value = dataframe.at[idx, column]

            if pd.isna(value):
                continue

            # Accept Python numeric types, numpy numerics, and bool (which is
            # a subclass of int but should still pass as "numeric").
            if isinstance(value, (int, float, np.integer, np.floating)):
                continue

            errors.append({
                "row": idx,
                "column": column,
                "value": str(value),
            })

    return errors


def _check_required_fields(dataframe: pd.DataFrame) -> list[dict]:
    """
    Ensure all REQUIRED_COLUMNS have no null values.

    Args:
        dataframe: The DataFrame to validate.

    Returns:
        List of error dicts: {"row": int, "column": str}
    """
    errors: list[dict] = []

    for column in REQUIRED_COLUMNS:
        if column not in dataframe.columns:
            # If a required column is missing entirely, flag every row
            for idx in dataframe.index:
                errors.append({"row": idx, "column": column})
            continue

        for idx in dataframe.index:
            value = dataframe.at[idx, column]
            if pd.isna(value) or str(value).strip() == "":
                errors.append({"row": idx, "column": column})

    return errors


def _compute_null_stats(
    dataframe: pd.DataFrame,
) -> tuple[dict[str, int], dict[str, float]]:
    """
    Count nulls and compute null percentages for each column.

    Args:
        dataframe: The DataFrame to analyze.

    Returns:
        (null_counts, null_percentages) — both keyed by column name.
    """
    null_counts: dict[str, int] = {}
    null_percentages: dict[str, float] = {}

    total_rows = len(dataframe)

    # Only report on master columns that exist in the DataFrame
    columns_to_check = [c for c in MASTER_COLUMNS if c in dataframe.columns]

    for column in columns_to_check:
        null_count = int(dataframe[column].isna().sum())
        null_counts[column] = null_count

        if total_rows > 0:
            null_percentages[column] = round(
                (null_count / total_rows) * 100, 1
            )
        else:
            null_percentages[column] = 0.0

    return null_counts, null_percentages
