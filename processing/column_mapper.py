"""
Column mapper — renames raw Excel column names to the master schema.

Uses a three-step cascade:
  1. Exact match against known column names (case-insensitive)
  2. Known semantic renames (e.g. "Segment" → "Product Type")
  3. Fuzzy match against master column names (thefuzz, threshold 80)

Columns that cannot be mapped are flagged for LLM review in a later phase.
Internal columns (prefixed with "_") are silently skipped.

Public API:
    map_columns(raw_columns) → ColumnMappingResult

See docs/SCHEMA.md — Column Mapping table for the source of truth.
"""

import logging
from dataclasses import dataclass, field

from config.column_mapping import EXACT_MATCHES, KNOWN_RENAMES
from config.schema import MASTER_COLUMNS
from utils.fuzzy_match import best_match

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Data class
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ColumnMappingResult:
    """Result of mapping raw column names to the master schema."""

    mapping: dict[str, str | None] = field(default_factory=dict)
    """raw_name → master_name, or None if unmapped."""

    unmapped: list[str] = field(default_factory=list)
    """Raw column names that could not be mapped to any master column."""

    confidence: dict[str, int] = field(default_factory=dict)
    """raw_name → match confidence (100 = exact/known rename, 80-99 = fuzzy)."""


# Build a fuzzy-match candidates dict: lowercase master name → proper master name.
# Used by the fuzzy matching step.
_MASTER_CANDIDATES: dict[str, str] = {
    col.lower(): col for col in MASTER_COLUMNS
}


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def map_columns(raw_columns: list[str]) -> ColumnMappingResult:
    """
    Map raw Excel column names to master schema column names.

    Uses a three-step cascade for each column:
      1. Exact match (case-insensitive) against EXACT_MATCHES
      2. Known rename (case-insensitive) against KNOWN_RENAMES
      3. Fuzzy match against MASTER_COLUMNS (threshold=80)

    Internal columns (starting with "_") are silently skipped and do not
    appear in the result.

    Args:
        raw_columns: List of column name strings from the raw DataFrame.

    Returns:
        ColumnMappingResult with mapping dict, unmapped list, and confidence
        scores for each mapped column.
    """
    result = ColumnMappingResult()

    for raw_name in raw_columns:
        # Skip internal/placeholder columns
        if raw_name.startswith("_"):
            continue

        master_name, score = _map_single_column(raw_name)

        result.mapping[raw_name] = master_name
        result.confidence[raw_name] = score

        if master_name is None:
            result.unmapped.append(raw_name)
            logger.info(f"Unmapped column: '{raw_name}' — flagged for review")
        else:
            logger.debug(
                f"Mapped '{raw_name}' → '{master_name}' (confidence={score})"
            )

    logger.info(
        f"Column mapping complete: {len(result.mapping)} columns processed, "
        f"{len(result.unmapped)} unmapped"
    )

    return result


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════

def _map_single_column(raw_name: str) -> tuple[str | None, int]:
    """
    Map a single raw column name through the three-step cascade.

    Args:
        raw_name: The raw column name from the Excel file.

    Returns:
        (master_name, confidence_score) — master_name is None if no match.
    """
    normalized = raw_name.strip().lower()

    # Step 1: Exact match
    if normalized in EXACT_MATCHES:
        return EXACT_MATCHES[normalized], 100

    # Step 2: Known rename
    if normalized in KNOWN_RENAMES:
        return KNOWN_RENAMES[normalized], 100

    # Step 3: Fuzzy match against master column names
    master_name, score = best_match(normalized, _MASTER_CANDIDATES, threshold=80)
    if master_name is not None:
        return master_name, score

    return None, 0
