"""
Merger — combines multiple cleaned DataFrames into one consolidated dataset.

Supports two modes:
  1. Fresh merge: concatenate all new DataFrames.
  2. Incremental append: detect store-level overlaps against an existing
     master DataFrame, return overlap info for the UI to ask the user
     replace/skip, and apply the user's decisions.

Public API:
    merge_dataframes(dataframes, source_filenames, existing_master)
        → MergeResult
    apply_overlap_decisions(merged, existing_master, decisions)
        → pd.DataFrame

See docs/ARCHITECTURE.md — merger.py section for responsibilities.
"""

import logging
from dataclasses import dataclass, field

import pandas as pd

from config.schema import MASTER_COLUMNS

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class StoreOverlap:
    """Describes one store that exists in both new and existing data."""

    retailer: str
    city: str
    store_format: str | None
    existing_row_count: int
    new_row_count: int


@dataclass
class MergeResult:
    """Output of the merge_dataframes() function."""

    dataframe: pd.DataFrame = field(default_factory=pd.DataFrame)
    overlaps: list[StoreOverlap] = field(default_factory=list)
    total_rows: int = 0
    source_file_counts: dict[str, int] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def merge_dataframes(
    dataframes: list[pd.DataFrame],
    source_filenames: list[str],
    existing_master: pd.DataFrame | None = None,
) -> MergeResult:
    """
    Combine multiple cleaned DataFrames into one consolidated dataset.

    Steps:
      1. Filter out empty DataFrames.
      2. Normalize all to MASTER_COLUMNS ordering (add missing columns as NaN).
      3. Concatenate all new DataFrames.
      4. If existing_master is provided, detect store-level overlaps.

    Args:
        dataframes: List of cleaned DataFrames (one per file).
        source_filenames: Corresponding filenames for each DataFrame.
        existing_master: Optional existing master DataFrame for overlap detection.

    Returns:
        MergeResult with combined DataFrame, overlap info, and stats.
    """
    # Track row counts per source file
    file_counts: dict[str, int] = {}

    # Step 1: Filter out empty DataFrames and record file counts
    valid_pairs: list[tuple[pd.DataFrame, str]] = []
    for df, filename in zip(dataframes, source_filenames):
        if df is None or df.empty:
            logger.info(f"Skipping empty DataFrame from '{filename}'")
            continue
        file_counts[filename] = len(df)
        valid_pairs.append((df, filename))

    if not valid_pairs:
        logger.info("No valid DataFrames to merge")
        return MergeResult(source_file_counts=file_counts)

    # Step 2: Normalize columns — ensure all DataFrames have the same columns
    normalized_dfs: list[pd.DataFrame] = []
    for df, filename in valid_pairs:
        normalized = _normalize_columns(df)
        # Tag with source filename for traceability
        normalized["_source_file"] = filename
        normalized_dfs.append(normalized)

    # Step 3: Concatenate
    combined = pd.concat(normalized_dfs, ignore_index=True)

    # Step 4: Detect overlaps if existing master is provided
    overlaps: list[StoreOverlap] = []
    if existing_master is not None and not existing_master.empty:
        overlaps = _detect_overlaps(combined, existing_master)

    total_rows = len(combined)

    logger.info(
        f"Merge complete: {total_rows} total rows from {len(valid_pairs)} files, "
        f"{len(overlaps)} store overlaps"
    )

    return MergeResult(
        dataframe=combined,
        overlaps=overlaps,
        total_rows=total_rows,
        source_file_counts=file_counts,
    )


def apply_overlap_decisions(
    merged: pd.DataFrame,
    existing_master: pd.DataFrame,
    decisions: dict[str, str],
) -> pd.DataFrame:
    """
    Apply user's replace/skip decisions for overlapping stores.

    Args:
        merged: The newly merged DataFrame (from merge_dataframes).
        existing_master: The existing master DataFrame.
        decisions: Dict of store_key → "replace" or "skip".
                   store_key format: "Retailer|City|StoreFormat"

    Returns:
        Final combined DataFrame after applying decisions.
    """
    if not decisions:
        # No decisions → just concatenate
        result = pd.concat([existing_master, merged], ignore_index=True)
        return result

    # Separate new data into overlap vs non-overlap rows
    new_overlap_rows: list[pd.DataFrame] = []
    new_non_overlap_rows: list[pd.DataFrame] = []

    overlap_keys = set(decisions.keys())

    for idx in merged.index:
        store_key = _build_store_key(merged.loc[idx])
        if store_key in overlap_keys:
            new_overlap_rows.append(merged.loc[[idx]])
        else:
            new_non_overlap_rows.append(merged.loc[[idx]])

    # Process existing master: remove rows for "replace" stores
    existing_to_keep: list[pd.DataFrame] = []
    for idx in existing_master.index:
        store_key = _build_store_key(existing_master.loc[idx])
        if store_key in decisions and decisions[store_key] == "replace":
            continue  # Drop existing rows for replaced stores
        existing_to_keep.append(existing_master.loc[[idx]])

    # Build result
    parts: list[pd.DataFrame] = []

    # Always include existing rows to keep
    if existing_to_keep:
        parts.append(pd.concat(existing_to_keep, ignore_index=True))

    # Always include non-overlapping new rows
    if new_non_overlap_rows:
        parts.append(pd.concat(new_non_overlap_rows, ignore_index=True))

    # Include new overlap rows for "replace" decisions
    for df_chunk in new_overlap_rows:
        store_key = _build_store_key(df_chunk.iloc[0])
        if decisions.get(store_key) == "replace":
            parts.append(df_chunk)
        # "skip" → don't include new overlap rows

    if not parts:
        return pd.DataFrame(columns=merged.columns)

    return pd.concat(parts, ignore_index=True)


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════

def _normalize_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure the DataFrame has all MASTER_COLUMNS in the correct order.

    Missing columns are added as NaN.  Extra columns (like _source_row)
    are preserved at the end.

    Args:
        dataframe: Input DataFrame.

    Returns:
        DataFrame with MASTER_COLUMNS first, then any extra columns.
    """
    df = dataframe.copy()

    # Add any missing master columns
    for col in MASTER_COLUMNS:
        if col not in df.columns:
            df[col] = None

    # Reorder: master columns first, then extras
    extra_cols = [c for c in df.columns if c not in MASTER_COLUMNS]
    ordered_cols = MASTER_COLUMNS + extra_cols
    return df[ordered_cols]


def _build_store_key(row: pd.Series) -> str:
    """
    Create a composite key for store-level overlap detection.

    Key format: "Retailer|City|StoreFormat"
    Blank Store Format is represented as empty string.

    Args:
        row: A single row (as pd.Series).

    Returns:
        Composite key string.
    """
    retailer_val = row.get("Retailer", "")
    retailer = str(retailer_val).strip() if pd.notna(retailer_val) else ""
    
    city_val = row.get("City", "")
    city = str(city_val).strip() if pd.notna(city_val) else ""
    
    store_format_val = row.get("Store Format", "")
    store_format = str(store_format_val).strip() if pd.notna(store_format_val) else ""
    
    return f"{retailer}|{city}|{store_format}"


def _detect_overlaps(
    new_df: pd.DataFrame,
    existing_df: pd.DataFrame,
) -> list[StoreOverlap]:
    """
    Find stores that appear in both the new data and the existing master.

    A "store" is identified by its composite key: Retailer + City + Store Format.

    Args:
        new_df: The newly merged DataFrame.
        existing_df: The existing master DataFrame.

    Returns:
        List of StoreOverlap objects describing each overlap.
    """
    # Build store → row count for new data
    new_store_counts: dict[str, int] = {}
    new_store_meta: dict[str, dict] = {}
    for idx in new_df.index:
        key = _build_store_key(new_df.loc[idx])
        new_store_counts[key] = new_store_counts.get(key, 0) + 1
        if key not in new_store_meta:
            new_store_meta[key] = {
                "retailer": str(new_df.at[idx, "Retailer"]) if pd.notna(new_df.at[idx, "Retailer"]) else "",
                "city": str(new_df.at[idx, "City"]) if pd.notna(new_df.at[idx, "City"]) else "",
                "store_format": str(new_df.at[idx, "Store Format"]) if pd.notna(new_df.at[idx, "Store Format"]) else None,
            }

    # Build store → row count for existing data
    existing_store_counts: dict[str, int] = {}
    for idx in existing_df.index:
        key = _build_store_key(existing_df.loc[idx])
        existing_store_counts[key] = existing_store_counts.get(key, 0) + 1

    # Find overlaps
    overlaps: list[StoreOverlap] = []
    for key in new_store_counts:
        if key in existing_store_counts:
            meta = new_store_meta[key]
            fmt = meta["store_format"]
            overlaps.append(StoreOverlap(
                retailer=meta["retailer"],
                city=meta["city"],
                store_format=fmt if fmt else None,
                existing_row_count=existing_store_counts[key],
                new_row_count=new_store_counts[key],
            ))

    if overlaps:
        logger.info(f"Detected {len(overlaps)} store overlaps with existing master")

    return overlaps
