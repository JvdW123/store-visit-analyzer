"""
Deterministic normalizer — applies lookup-table rules to categorical columns.

For each categorical column with a known normalization table, values are
matched (case-insensitive, whitespace-stripped) and replaced with the
canonical form.  Values that cannot be matched are flagged for LLM review.

Special rules:
  - If HPP Treatment == "Yes" and Processing Method is blank → set Processing
    Method to "HPP" (cross-column rule from RULES.md).
  - Shelf Location: only exact-match values are normalized; everything else
    is flagged for LLM.
  - Juice Extraction Method: deterministic inference rules applied first
    (HPP Treatment, Processing Method, Claims/Notes keywords), with LLM
    fallback for rows that cannot be resolved.
  - Flavor: rows with Product Name but no Flavor are flagged for LLM
    extraction.

Public API:
    normalize(dataframe) → NormalizationResult

See docs/RULES.md for the full lookup tables and decision matrix.
"""

import logging
from dataclasses import dataclass, field

import pandas as pd

from config.normalization_rules import (
    COLUMN_TO_RULE_MAP,
    LLM_ONLY_COLUMNS,
)
from config.schema import VALID_VALUES

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class FlaggedItem:
    """A single cell value that could not be resolved deterministically."""

    row_index: int
    column: str
    original_value: str
    context: dict[str, str] = field(default_factory=dict)


@dataclass
class NormalizationResult:
    """Output of the normalize() function."""

    dataframe: pd.DataFrame = field(default_factory=pd.DataFrame)
    flagged_items: list[FlaggedItem] = field(default_factory=list)
    changes_log: list[dict] = field(default_factory=list)


# Context columns included with every flagged item so the LLM has enough
# information to make semantic judgments (e.g., infer Juice Extraction Method
# from Processing Method + Claims + Notes).
_CONTEXT_COLUMNS: list[str] = [
    "Brand",
    "Product Name",
    "Flavor",
    "Product Type",
    "Processing Method",
    "HPP Treatment",
    "Claims",
    "Notes",
    "Shelf Location",
]


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def normalize(dataframe: pd.DataFrame) -> NormalizationResult:
    """
    Apply all deterministic lookup tables to categorical columns.

    For each column listed in COLUMN_TO_RULE_MAP, normalizes known values
    and flags unknown values for LLM review.  Then applies cross-column
    rules (HPP → Processing Method).  Finally, flags Juice Extraction
    Method values for LLM inference.

    Args:
        dataframe: DataFrame with columns already mapped to master schema
                   names (output of column_mapper).

    Returns:
        NormalizationResult with cleaned DataFrame, flagged items list,
        and a log of every change made.
    """
    result_df = dataframe.copy()
    all_flagged: list[FlaggedItem] = []
    all_changes: list[dict] = []

    # Step 1: Normalize each categorical column via its lookup table
    for column_name, lookup_table in COLUMN_TO_RULE_MAP.items():
        if column_name not in result_df.columns:
            continue

        column_flagged, column_changes = _normalize_column(
            result_df, column_name, lookup_table
        )
        all_flagged.extend(column_flagged)
        all_changes.extend(column_changes)

    # Step 2: Cross-column rule — HPP Treatment + Processing Method
    cross_changes = _apply_cross_column_rules(result_df)
    all_changes.extend(cross_changes)

    # Step 3: Flag LLM-only columns (currently empty after Juice Extraction
    # Method moved to deterministic-first inference)
    for column_name in LLM_ONLY_COLUMNS:
        if column_name not in result_df.columns:
            continue
        llm_flagged = _flag_llm_only_column(result_df, column_name)
        all_flagged.extend(llm_flagged)

    # Step 4: Infer Juice Extraction Method deterministically, flag remainder
    jem_flagged, jem_changes = _infer_juice_extraction_method(result_df)
    all_flagged.extend(jem_flagged)
    all_changes.extend(jem_changes)

    # Step 5: Flag rows with Product Name but no Flavor for LLM extraction
    flavor_flagged = _flag_missing_flavor(result_df)
    all_flagged.extend(flavor_flagged)

    logger.info(
        f"Normalization complete: {len(all_changes)} values changed, "
        f"{len(all_flagged)} items flagged for review"
    )

    return NormalizationResult(
        dataframe=result_df,
        flagged_items=all_flagged,
        changes_log=all_changes,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════

def _normalize_column(
    dataframe: pd.DataFrame,
    column: str,
    lookup: dict[str, str],
) -> tuple[list[FlaggedItem], list[dict]]:
    """
    Normalize one column using its lookup table.

    For each cell:
      - blank/NaN → leave as NaN (not flagged)
      - found in lookup → replace with canonical value (or NaN if mapped to "")
      - not found → flag for LLM review

    Args:
        dataframe: DataFrame to modify IN PLACE for this column.
        column: Master column name.
        lookup: lowercase-keyed normalization dict.

    Returns:
        (flagged_items, changes_log) for this column.
    """
    flagged: list[FlaggedItem] = []
    changes: list[dict] = []

    for idx in dataframe.index:
        raw_value = dataframe.at[idx, column]

        # Blank / NaN → leave as-is, not flagged
        if pd.isna(raw_value) or str(raw_value).strip() == "":
            continue

        original_str = str(raw_value).strip()
        lookup_key = original_str.lower()

        if lookup_key in lookup:
            normalized = lookup[lookup_key]

            # Empty string in lookup means "convert to blank"
            if normalized == "":
                dataframe.at[idx, column] = None
                changes.append({
                    "row": idx,
                    "column": column,
                    "original": original_str,
                    "normalized": "(blank)",
                    "method": "deterministic",
                })
            else:
                # Always write the canonical value (also strips whitespace
                # from the original cell, e.g. "  Shots  " → "Shots")
                raw_cell_str = str(raw_value)
                dataframe.at[idx, column] = normalized
                if raw_cell_str != normalized:
                    changes.append({
                        "row": idx,
                        "column": column,
                        "original": original_str,
                        "normalized": normalized,
                        "method": "deterministic",
                    })

        else:
            # Value not in lookup → flag for LLM review
            context = _build_context(dataframe, idx)
            flagged.append(FlaggedItem(
                row_index=idx,
                column=column,
                original_value=original_str,
                context=context,
            ))
            logger.debug(
                f"Flagged [{column}] row {idx}: '{original_str}' — not in lookup"
            )

    return flagged, changes


def _apply_cross_column_rules(dataframe: pd.DataFrame) -> list[dict]:
    """
    Apply cross-column interaction rules after individual normalization.

    Rule: If HPP Treatment == "Yes" AND Processing Method is blank,
    set Processing Method to "HPP".

    Args:
        dataframe: DataFrame to modify IN PLACE.

    Returns:
        List of change log entries.
    """
    changes: list[dict] = []

    if "HPP Treatment" not in dataframe.columns:
        return changes
    if "Processing Method" not in dataframe.columns:
        return changes

    for idx in dataframe.index:
        hpp_value = dataframe.at[idx, "HPP Treatment"]
        proc_value = dataframe.at[idx, "Processing Method"]

        hpp_is_yes = (
            not pd.isna(hpp_value)
            and str(hpp_value).strip() == "Yes"
        )
        proc_is_blank = (
            pd.isna(proc_value)
            or str(proc_value).strip() == ""
        )

        if hpp_is_yes and proc_is_blank:
            dataframe.at[idx, "Processing Method"] = "HPP"
            changes.append({
                "row": idx,
                "column": "Processing Method",
                "original": "(blank)",
                "normalized": "HPP",
                "method": "cross-column rule (HPP Treatment = Yes)",
            })

    if changes:
        logger.info(
            f"Cross-column rule applied: set Processing Method to 'HPP' "
            f"for {len(changes)} rows"
        )

    return changes


def _flag_llm_only_column(
    dataframe: pd.DataFrame,
    column: str,
) -> list[FlaggedItem]:
    """
    Flag all non-blank values in an LLM-only column.

    These columns have no deterministic normalization rules — every value
    must be resolved by the LLM.

    Args:
        dataframe: The DataFrame (not modified).
        column: The LLM-only column name.

    Returns:
        List of FlaggedItems for non-blank values.
    """
    flagged: list[FlaggedItem] = []

    for idx in dataframe.index:
        raw_value = dataframe.at[idx, column]

        if pd.isna(raw_value) or str(raw_value).strip() == "":
            continue

        original_str = str(raw_value).strip()

        # Check if the value is already in the valid set
        valid_set = VALID_VALUES.get(column, set())
        if original_str in valid_set:
            continue

        context = _build_context(dataframe, idx)
        flagged.append(FlaggedItem(
            row_index=idx,
            column=column,
            original_value=original_str,
            context=context,
        ))

    if flagged:
        logger.info(
            f"Flagged {len(flagged)} values in LLM-only column '{column}'"
        )

    return flagged


def _infer_juice_extraction_method(
    dataframe: pd.DataFrame,
) -> tuple[list[FlaggedItem], list[dict]]:
    """
    Apply deterministic rules to infer Juice Extraction Method, then flag
    remaining blank rows for LLM.

    Rules (applied in order, first match wins per row):
      1. HPP Treatment == "Yes"                       → "Cold Pressed"
      2. Processing Method == "HPP"                   → "Cold Pressed"
      3. Processing Method == "Freshly Squeezed"      → "Squeezed"
      4. Claims/Notes contain "from concentrate"      → "From Concentrate"
      5. Claims/Notes contain "cold pressed"/"cold-pressed" → "Cold Pressed"
      6. Claims/Notes contain "squeezed"/"freshly squeezed" → "Squeezed"
      7. None matched AND value is blank              → flag for LLM

    Args:
        dataframe: DataFrame to modify IN PLACE.

    Returns:
        (flagged_items, changes_log) for this step.
    """
    col = "Juice Extraction Method"
    flagged: list[FlaggedItem] = []
    changes: list[dict] = []

    if col not in dataframe.columns:
        return flagged, changes

    has_hpp = "HPP Treatment" in dataframe.columns
    has_proc = "Processing Method" in dataframe.columns
    has_claims = "Claims" in dataframe.columns
    has_notes = "Notes" in dataframe.columns

    valid_set = VALID_VALUES.get(col, set())

    for idx in dataframe.index:
        current_value = dataframe.at[idx, col]

        # If a valid value is already set, skip
        if not pd.isna(current_value) and str(current_value).strip() != "":
            if str(current_value).strip() in valid_set:
                continue
            # Non-blank, non-valid value — flag it
            context = _build_context(dataframe, idx)
            flagged.append(FlaggedItem(
                row_index=idx,
                column=col,
                original_value=str(current_value).strip(),
                context=context,
            ))
            continue

        # Gather row data for rules
        hpp_val = ""
        if has_hpp:
            v = dataframe.at[idx, "HPP Treatment"]
            hpp_val = str(v).strip() if not pd.isna(v) else ""

        proc_val = ""
        if has_proc:
            v = dataframe.at[idx, "Processing Method"]
            proc_val = str(v).strip() if not pd.isna(v) else ""

        claims_val = ""
        if has_claims:
            v = dataframe.at[idx, "Claims"]
            claims_val = str(v).strip().lower() if not pd.isna(v) else ""

        notes_val = ""
        if has_notes:
            v = dataframe.at[idx, "Notes"]
            notes_val = str(v).strip().lower() if not pd.isna(v) else ""

        text_combined = claims_val + " " + notes_val

        inferred: str | None = None
        rule_desc = ""

        # Rule 1: HPP Treatment == "Yes"
        if hpp_val == "Yes":
            inferred = "Cold Pressed"
            rule_desc = "HPP Treatment = Yes"
        # Rule 2: Processing Method == "HPP"
        elif proc_val == "HPP":
            inferred = "Cold Pressed"
            rule_desc = "Processing Method = HPP"
        # Rule 3: Processing Method == "Freshly Squeezed"
        elif proc_val == "Freshly Squeezed":
            inferred = "Squeezed"
            rule_desc = "Processing Method = Freshly Squeezed"
        # Rule 4: Claims/Notes contain "from concentrate"
        elif "from concentrate" in text_combined:
            inferred = "From Concentrate"
            rule_desc = "Claims/Notes contain 'from concentrate'"
        # Rule 5: Claims/Notes contain "cold pressed" or "cold-pressed"
        elif "cold pressed" in text_combined or "cold-pressed" in text_combined:
            inferred = "Cold Pressed"
            rule_desc = "Claims/Notes contain 'cold pressed'"
        # Rule 6: Claims/Notes contain "squeezed" or "freshly squeezed"
        elif "squeezed" in text_combined:
            inferred = "Squeezed"
            rule_desc = "Claims/Notes contain 'squeezed'"

        if inferred is not None:
            dataframe.at[idx, col] = inferred
            changes.append({
                "row": idx,
                "column": col,
                "original": "(blank)",
                "normalized": inferred,
                "method": f"deterministic rule ({rule_desc})",
            })
        else:
            # Rule 7: flag for LLM
            context = _build_context(dataframe, idx)
            flagged.append(FlaggedItem(
                row_index=idx,
                column=col,
                original_value="",
                context=context,
            ))

    if changes:
        logger.info(
            f"Juice Extraction Method inferred deterministically for "
            f"{len(changes)} rows"
        )
    if flagged:
        logger.info(
            f"Juice Extraction Method flagged for LLM: {len(flagged)} rows"
        )

    return flagged, changes


def _flag_missing_flavor(
    dataframe: pd.DataFrame,
) -> list[FlaggedItem]:
    """
    Flag rows that have a Product Name but no Flavor for LLM extraction.

    The LLM will extract the flavor/fruit from the product name text.

    Args:
        dataframe: The DataFrame (not modified).

    Returns:
        List of FlaggedItems for rows needing Flavor extraction.
    """
    flagged: list[FlaggedItem] = []

    if "Product Name" not in dataframe.columns:
        return flagged

    has_flavor = "Flavor" in dataframe.columns

    for idx in dataframe.index:
        product_name = dataframe.at[idx, "Product Name"]

        # Skip if no Product Name
        if pd.isna(product_name) or str(product_name).strip() == "":
            continue

        # Skip if Flavor is already populated
        if has_flavor:
            flavor = dataframe.at[idx, "Flavor"]
            if not pd.isna(flavor) and str(flavor).strip() != "":
                continue

        context = _build_context(dataframe, idx)
        flagged.append(FlaggedItem(
            row_index=idx,
            column="Flavor",
            original_value="",
            context=context,
        ))

    if flagged:
        logger.info(
            f"Flagged {len(flagged)} rows for LLM Flavor extraction "
            f"(have Product Name but no Flavor)"
        )

    return flagged


def _build_context(dataframe: pd.DataFrame, row_index: int) -> dict[str, str]:
    """
    Extract context columns for a flagged item's row.

    Provides the LLM with surrounding data (Brand, Flavor, Claims, etc.)
    so it can make informed decisions about ambiguous values.

    Args:
        dataframe: The full DataFrame.
        row_index: Index of the row to extract context from.

    Returns:
        Dict of column_name → value (as string) for available context columns.
    """
    context: dict[str, str] = {}

    for col in _CONTEXT_COLUMNS:
        if col not in dataframe.columns:
            continue
        value = dataframe.at[row_index, col]
        if pd.isna(value) or str(value).strip() == "":
            continue
        context[col] = str(value).strip()

    return context
