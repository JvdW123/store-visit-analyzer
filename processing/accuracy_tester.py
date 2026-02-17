"""
Accuracy Tester — Compare tool output against ground truth.

Aligns rows by composite key (Country + City + Retailer + Photo),
performs cell-by-cell comparison, calculates accuracy metrics,
and prepares difference batches for LLM root cause analysis.

Public API:
    compare_dataframes(tool_df, truth_df, columns_to_compare) → ComparisonResult
    load_excel_for_comparison(file_path) → pd.DataFrame
    prepare_llm_batch(differences, tool_df, max_differences) → list[dict]

See docs/TESTING.md for the ground truth comparison approach.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════

COLUMNS_TO_COMPARE = [
    "Product Type",
    "Brand",
    "Sub-brand",
    "Product Name",
    "Flavor",
    "Facings",
    "Price (Local Currency)",
    "Packaging Size (ml)",
    "Need State",
    "Juice Extraction Method",
    "Processing Method",
    "HPP Treatment",
    "Packaging Type",
    "Shelf Location",
    "Shelf Level",
    "Branded/Private Label",
    "Claims",
    "Stock Status",
]

NUMERIC_COLUMNS = ["Price (Local Currency)", "Packaging Size (ml)"]
NUMERIC_TOLERANCE = 0.01


# ═══════════════════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ComparisonKey:
    """Composite key for row alignment."""
    country: str
    city: str
    retailer: str
    photo: str
    
    @classmethod
    def from_row(cls, row: pd.Series) -> "ComparisonKey | None":
        """
        Extract composite key from DataFrame row.
        
        Returns None if any required field is missing or blank.
        
        Args:
            row: A pandas Series representing a DataFrame row.
        
        Returns:
            ComparisonKey instance or None if key cannot be constructed.
        """
        try:
            country = row.get("Country", "")
            city = row.get("City", "")
            retailer = row.get("Retailer", "")
            photo = row.get("Photo", "")
            
            # Convert to string and strip whitespace
            country = str(country).strip() if pd.notna(country) else ""
            city = str(city).strip() if pd.notna(city) else ""
            retailer = str(retailer).strip() if pd.notna(retailer) else ""
            photo = str(photo).strip() if pd.notna(photo) else ""
            
            # All fields must be non-empty
            if not all([country, city, retailer, photo]):
                return None
            
            return cls(
                country=country,
                city=city,
                retailer=retailer,
                photo=photo
            )
        except Exception as exc:
            logger.warning(f"Failed to extract ComparisonKey from row: {exc}")
            return None
    
    def to_string(self) -> str:
        """Return string representation for display."""
        return f"{self.country}|{self.city}|{self.retailer}|{self.photo}"
    
    def __hash__(self):
        """Make ComparisonKey hashable for use in sets/dicts."""
        return hash((self.country, self.city, self.retailer, self.photo))
    
    def __eq__(self, other):
        """Compare two ComparisonKeys for equality."""
        if not isinstance(other, ComparisonKey):
            return False
        return (
            self.country == other.country
            and self.city == other.city
            and self.retailer == other.retailer
            and self.photo == other.photo
        )


@dataclass
class CellDifference:
    """Single cell-level difference."""
    row_key: ComparisonKey
    column: str
    tool_value: Any
    truth_value: Any
    difference_type: str  # "one_blank", "both_filled", "numeric_mismatch"


@dataclass
class AccuracyMetrics:
    """Accuracy statistics at various levels."""
    overall_accuracy_pct: float
    total_cells_compared: int
    matching_cells: int
    different_cells: int
    both_blank_cells: int
    
    # Per-column breakdown
    accuracy_by_column: dict[str, float] = field(default_factory=dict)
    differences_by_column: dict[str, int] = field(default_factory=dict)
    
    # Per-file breakdown (if source file metadata available)
    accuracy_by_file: dict[str, float] = field(default_factory=dict)


@dataclass
class ComparisonResult:
    """Complete comparison output."""
    metrics: AccuracyMetrics
    differences: list[CellDifference]
    unmatched_tool_rows: list[ComparisonKey]
    unmatched_truth_rows: list[ComparisonKey]
    errors: list[str]


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def load_excel_for_comparison(
    file_path: Path | str,
    sheet_name: str = "SKU Data"
) -> pd.DataFrame:
    """
    Load Excel file for comparison.
    
    Handles:
    - Reading from "SKU Data" sheet or fallback to first sheet
    - Removing "Issue Description" column if present
    - Normalizing column names (strip whitespace)
    
    Args:
        file_path: Path to Excel file or file-like object.
        sheet_name: Name of sheet to read (default: "SKU Data").
    
    Returns:
        Clean DataFrame ready for comparison.
    
    Raises:
        Exception: If file cannot be read.
    """
    try:
        # Try to read from specified sheet
        df = pd.read_excel(file_path, sheet_name=sheet_name)
    except Exception:
        # Fallback to first sheet
        try:
            df = pd.read_excel(file_path)
            logger.info(f"Sheet '{sheet_name}' not found, using first sheet")
        except Exception as exc:
            logger.error(f"Failed to read Excel file: {exc}")
            raise
    
    # Remove Issue Description column if present
    if "Issue Description" in df.columns:
        df = df.drop(columns=["Issue Description"])
        logger.debug("Removed 'Issue Description' column")
    
    # Normalize column names (strip whitespace)
    df.columns = df.columns.str.strip()
    
    logger.info(f"Loaded {len(df)} rows with {len(df.columns)} columns")
    
    return df


def align_rows(
    tool_df: pd.DataFrame,
    truth_df: pd.DataFrame
) -> tuple[pd.DataFrame, list[ComparisonKey], list[ComparisonKey]]:
    """
    Align rows using composite key (Country + City + Retailer + Photo).
    
    Creates a merged DataFrame with '_tool' and '_truth' suffixed columns
    for all compared columns. Handles unmatched rows and duplicate keys.
    
    Args:
        tool_df: Tool output DataFrame.
        truth_df: Ground truth DataFrame.
    
    Returns:
        Tuple of:
        - Aligned DataFrame with suffixed columns
        - List of keys present in tool but not in truth
        - List of keys present in truth but not in tool
    """
    tool_keys: dict[ComparisonKey, int] = {}  # key → first row index
    truth_keys: dict[ComparisonKey, int] = {}  # key → first row index
    
    tool_rows_with_valid_keys: list[tuple[ComparisonKey, int]] = []
    truth_rows_with_valid_keys: list[tuple[ComparisonKey, int]] = []
    
    # Extract keys from tool output
    for idx, row in tool_df.iterrows():
        key = ComparisonKey.from_row(row)
        if key is not None:
            if key in tool_keys:
                logger.warning(
                    f"Duplicate key in tool output: {key.to_string()} "
                    f"(rows {tool_keys[key]} and {idx})"
                )
            else:
                tool_keys[key] = idx
                tool_rows_with_valid_keys.append((key, idx))
    
    # Extract keys from ground truth
    for idx, row in truth_df.iterrows():
        key = ComparisonKey.from_row(row)
        if key is not None:
            if key in truth_keys:
                logger.warning(
                    f"Duplicate key in ground truth: {key.to_string()} "
                    f"(rows {truth_keys[key]} and {idx})"
                )
            else:
                truth_keys[key] = idx
                truth_rows_with_valid_keys.append((key, idx))
    
    logger.info(
        f"Extracted {len(tool_keys)} unique keys from tool output, "
        f"{len(truth_keys)} from ground truth"
    )
    
    # Find unmatched rows
    tool_only_keys = set(tool_keys.keys()) - set(truth_keys.keys())
    truth_only_keys = set(truth_keys.keys()) - set(tool_keys.keys())
    
    unmatched_tool = list(tool_only_keys)
    unmatched_truth = list(truth_only_keys)
    
    if unmatched_tool:
        logger.warning(f"{len(unmatched_tool)} rows in tool output not in ground truth")
    if unmatched_truth:
        logger.warning(f"{len(unmatched_truth)} rows in ground truth not in tool output")
    
    # Build aligned DataFrame
    common_keys = set(tool_keys.keys()) & set(truth_keys.keys())
    
    aligned_rows = []
    for key in common_keys:
        tool_idx = tool_keys[key]
        truth_idx = truth_keys[key]
        
        aligned_row = {
            "_key_country": key.country,
            "_key_city": key.city,
            "_key_retailer": key.retailer,
            "_key_photo": key.photo,
        }
        
        # Add columns from tool output with '_tool' suffix
        for col in tool_df.columns:
            aligned_row[f"{col}_tool"] = tool_df.loc[tool_idx, col]
        
        # Add columns from ground truth with '_truth' suffix
        for col in truth_df.columns:
            aligned_row[f"{col}_truth"] = truth_df.loc[truth_idx, col]
        
        aligned_rows.append(aligned_row)
    
    aligned_df = pd.DataFrame(aligned_rows)
    
    logger.info(f"Aligned {len(aligned_df)} matching rows")
    
    return aligned_df, unmatched_tool, unmatched_truth


def compare_cell_values(
    tool_value: Any,
    truth_value: Any,
    column: str,
    numeric_tolerance: float = 0.01
) -> tuple[bool, str]:
    """
    Compare two cell values according to comparison rules.
    
    Rules:
    - Both blank → match (type: "both_blank")
    - One blank, one filled → mismatch (type: "one_blank")
    - Both filled, case-insensitive string match → match (type: "exact")
    - Numeric columns with tolerance → match if within tolerance (type: "numeric_within_tolerance")
    - Otherwise → mismatch (type: "mismatch")
    
    Args:
        tool_value: Value from tool output.
        truth_value: Value from ground truth.
        column: Column name (used to determine if numeric comparison needed).
        numeric_tolerance: Tolerance for numeric comparisons (default: 0.01).
    
    Returns:
        Tuple of (is_match, match_type).
    """
    # Check if both are blank
    tool_is_blank = pd.isna(tool_value) or str(tool_value).strip() == ""
    truth_is_blank = pd.isna(truth_value) or str(truth_value).strip() == ""
    
    if tool_is_blank and truth_is_blank:
        return True, "both_blank"
    
    if tool_is_blank or truth_is_blank:
        return False, "one_blank"
    
    # Both have values - normalize to strings and strip whitespace
    tool_str = str(tool_value).strip()
    truth_str = str(truth_value).strip()
    
    # For numeric columns, try numeric comparison first
    if column in NUMERIC_COLUMNS:
        try:
            tool_num = float(tool_str)
            truth_num = float(truth_str)
            
            if abs(tool_num - truth_num) <= numeric_tolerance:
                return True, "numeric_within_tolerance"
            else:
                return False, "numeric_mismatch"
        except (ValueError, TypeError):
            # Fall through to string comparison if conversion fails
            pass
    
    # Case-insensitive string comparison
    if tool_str.lower() == truth_str.lower():
        return True, "exact"
    
    return False, "mismatch"


def compare_dataframes(
    tool_df: pd.DataFrame,
    truth_df: pd.DataFrame,
    columns_to_compare: list[str]
) -> ComparisonResult:
    """
    Main comparison function.
    
    Steps:
    1. Align rows by composite key
    2. For each column in columns_to_compare:
       - Compare cell-by-cell using compare_cell_values()
       - Track matches, mismatches, both-blank
       - Record CellDifference objects for mismatches
    3. Calculate overall and per-column accuracy
    4. Return ComparisonResult with all metrics and differences
    
    Args:
        tool_df: Tool output DataFrame.
        truth_df: Ground truth DataFrame.
        columns_to_compare: List of column names to compare.
    
    Returns:
        ComparisonResult with metrics, differences, and errors.
    """
    errors: list[str] = []
    differences: list[CellDifference] = []
    
    # Step 1: Align rows
    try:
        aligned_df, unmatched_tool, unmatched_truth = align_rows(tool_df, truth_df)
    except Exception as exc:
        logger.error(f"Failed to align rows: {exc}")
        return ComparisonResult(
            metrics=AccuracyMetrics(
                overall_accuracy_pct=0.0,
                total_cells_compared=0,
                matching_cells=0,
                different_cells=0,
                both_blank_cells=0,
            ),
            differences=[],
            unmatched_tool_rows=[],
            unmatched_truth_rows=[],
            errors=[f"Row alignment failed: {exc}"]
        )
    
    if aligned_df.empty:
        logger.warning("No rows could be aligned between tool output and ground truth")
        return ComparisonResult(
            metrics=AccuracyMetrics(
                overall_accuracy_pct=0.0,
                total_cells_compared=0,
                matching_cells=0,
                different_cells=0,
                both_blank_cells=0,
            ),
            differences=[],
            unmatched_tool_rows=unmatched_tool,
            unmatched_truth_rows=unmatched_truth,
            errors=["No rows could be aligned"]
        )
    
    # Step 2: Compare cells column by column
    total_matches = 0
    total_differences = 0
    total_both_blank = 0
    
    accuracy_by_column: dict[str, float] = {}
    differences_by_column: dict[str, int] = {}
    
    for column in columns_to_compare:
        tool_col = f"{column}_tool"
        truth_col = f"{column}_truth"
        
        # Check if column exists in both dataframes
        if tool_col not in aligned_df.columns:
            logger.warning(f"Column '{column}' not found in tool output")
            errors.append(f"Column '{column}' missing in tool output")
            continue
        
        if truth_col not in aligned_df.columns:
            logger.warning(f"Column '{column}' not found in ground truth")
            errors.append(f"Column '{column}' missing in ground truth")
            continue
        
        col_matches = 0
        col_differences = 0
        col_both_blank = 0
        
        # Compare each row for this column
        for idx, row in aligned_df.iterrows():
            tool_value = row[tool_col]
            truth_value = row[truth_col]
            
            is_match, match_type = compare_cell_values(
                tool_value, truth_value, column, NUMERIC_TOLERANCE
            )
            
            if match_type == "both_blank":
                col_both_blank += 1
                col_matches += 1
            elif is_match:
                col_matches += 1
            else:
                col_differences += 1
                
                # Create CellDifference object
                key = ComparisonKey(
                    country=row["_key_country"],
                    city=row["_key_city"],
                    retailer=row["_key_retailer"],
                    photo=row["_key_photo"]
                )
                
                diff = CellDifference(
                    row_key=key,
                    column=column,
                    tool_value=tool_value,
                    truth_value=truth_value,
                    difference_type=match_type
                )
                differences.append(diff)
        
        # Calculate accuracy for this column
        total_col_cells = col_matches + col_differences
        if total_col_cells > 0:
            col_accuracy = (col_matches / total_col_cells) * 100
        else:
            col_accuracy = 0.0
        
        accuracy_by_column[column] = col_accuracy
        differences_by_column[column] = col_differences
        
        total_matches += col_matches
        total_differences += col_differences
        total_both_blank += col_both_blank
        
        logger.debug(
            f"Column '{column}': {col_matches} matches, {col_differences} differences "
            f"({col_accuracy:.1f}% accuracy)"
        )
    
    # Step 3: Calculate overall metrics
    total_cells = total_matches + total_differences
    if total_cells > 0:
        overall_accuracy = (total_matches / total_cells) * 100
    else:
        overall_accuracy = 0.0
    
    metrics = AccuracyMetrics(
        overall_accuracy_pct=overall_accuracy,
        total_cells_compared=total_cells,
        matching_cells=total_matches,
        different_cells=total_differences,
        both_blank_cells=total_both_blank,
        accuracy_by_column=accuracy_by_column,
        differences_by_column=differences_by_column,
    )
    
    logger.info(
        f"Comparison complete: {total_cells} cells compared, "
        f"{total_matches} matches ({overall_accuracy:.1f}%), "
        f"{total_differences} differences"
    )
    
    return ComparisonResult(
        metrics=metrics,
        differences=differences,
        unmatched_tool_rows=unmatched_tool,
        unmatched_truth_rows=unmatched_truth,
        errors=errors
    )


def prepare_llm_batch(
    differences: list[CellDifference],
    tool_df: pd.DataFrame,
    max_differences: int = 100
) -> list[dict]:
    """
    Prepare difference data for LLM root cause analysis.
    
    For each difference, includes full row context from tool output:
    - Country, City, Retailer, Photo (the key)
    - All compared columns (even if they match)
    - The specific column that differs
    - Tool value vs Truth value
    
    Limits to max_differences, sampling intelligently across different columns.
    
    Args:
        differences: List of CellDifference objects.
        tool_df: Tool output DataFrame for context.
        max_differences: Maximum differences to include (default: 100).
    
    Returns:
        List of dicts ready for LLM analysis.
    """
    if not differences:
        return []
    
    # Sample intelligently: prioritize diversity across columns
    sampled_diffs = _sample_differences_by_column(differences, max_differences)
    
    llm_batch = []
    
    for diff in sampled_diffs:
        # Find the row in tool_df that matches this key
        row_mask = (
            (tool_df["Country"] == diff.row_key.country) &
            (tool_df["City"] == diff.row_key.city) &
            (tool_df["Retailer"] == diff.row_key.retailer) &
            (tool_df["Photo"] == diff.row_key.photo)
        )
        
        matching_rows = tool_df[row_mask]
        
        if matching_rows.empty:
            logger.warning(f"Could not find row in tool_df for key: {diff.row_key.to_string()}")
            continue
        
        row = matching_rows.iloc[0]
        
        # Build row context with all relevant columns
        row_context = {}
        for col in COLUMNS_TO_COMPARE:
            if col in row:
                val = row[col]
                # Convert to string, handle NaN
                if pd.isna(val):
                    row_context[col] = ""
                else:
                    row_context[col] = str(val)
        
        # Add key fields
        row_context["Country"] = diff.row_key.country
        row_context["City"] = diff.row_key.city
        row_context["Retailer"] = diff.row_key.retailer
        row_context["Photo"] = diff.row_key.photo
        
        llm_item = {
            "row_key": diff.row_key.to_string(),
            "column": diff.column,
            "tool_value": str(diff.tool_value) if pd.notna(diff.tool_value) else "",
            "truth_value": str(diff.truth_value) if pd.notna(diff.truth_value) else "",
            "row_context": row_context
        }
        
        llm_batch.append(llm_item)
    
    logger.info(f"Prepared {len(llm_batch)} differences for LLM analysis")
    
    return llm_batch


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════

def _sample_differences_by_column(
    differences: list[CellDifference],
    max_count: int
) -> list[CellDifference]:
    """
    Sample differences intelligently to maximize column diversity.
    
    Strategy: Group by column, take roughly equal samples from each column
    to ensure all problematic columns are represented.
    
    Args:
        differences: Full list of differences.
        max_count: Maximum number to return.
    
    Returns:
        Sampled list of differences.
    """
    if len(differences) <= max_count:
        return differences
    
    # Group by column
    by_column: dict[str, list[CellDifference]] = {}
    for diff in differences:
        if diff.column not in by_column:
            by_column[diff.column] = []
        by_column[diff.column].append(diff)
    
    # Calculate how many to take from each column
    num_columns = len(by_column)
    per_column = max(1, max_count // num_columns)
    
    sampled = []
    for column, col_diffs in by_column.items():
        sampled.extend(col_diffs[:per_column])
    
    # If we still have room, add more from columns with most differences
    remaining = max_count - len(sampled)
    if remaining > 0:
        # Sort columns by difference count descending
        sorted_columns = sorted(
            by_column.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )
        
        for column, col_diffs in sorted_columns:
            already_included = sum(1 for d in sampled if d.column == column)
            available = col_diffs[already_included:]
            
            to_add = min(len(available), remaining)
            sampled.extend(available[:to_add])
            remaining -= to_add
            
            if remaining == 0:
                break
    
    return sampled[:max_count]
