"""
Tests for processing/merger.py

Covers: fresh merge, overlap detection, replace/skip decisions,
empty input handling, and column normalization.
"""

import pandas as pd
import pytest

from processing.merger import (
    MergeResult,
    StoreOverlap,
    merge_dataframes,
    apply_overlap_decisions,
    _build_store_key,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store_df(
    retailer: str = "Tesco",
    city: str = "London",
    store_format: str | None = "Large",
    rows: int = 3,
) -> pd.DataFrame:
    """Build a DataFrame for a single store with multiple SKU rows."""
    return pd.DataFrame({
        "Retailer": [retailer] * rows,
        "City": [city] * rows,
        "Store Format": [store_format] * rows,
        "Brand": [f"Brand_{i}" for i in range(rows)],
        "Product Type": ["Pure Juices"] * rows,
    })


# ═══════════════════════════════════════════════════════════════════════════
# Fresh merge (no existing master)
# ═══════════════════════════════════════════════════════════════════════════

class TestFreshMerge:
    def test_two_files_concatenated(self):
        df1 = _make_store_df("Tesco", "London", rows=3)
        df2 = _make_store_df("Sainsburys", "Manchester", rows=2)
        result = merge_dataframes(
            [df1, df2],
            ["file1.xlsx", "file2.xlsx"],
        )
        assert result.total_rows == 5
        assert result.source_file_counts["file1.xlsx"] == 3
        assert result.source_file_counts["file2.xlsx"] == 2

    def test_overlaps_empty_when_no_master(self):
        df1 = _make_store_df()
        result = merge_dataframes([df1], ["file1.xlsx"])
        assert len(result.overlaps) == 0

    def test_columns_normalized_to_master_schema(self):
        df1 = pd.DataFrame({
            "Brand": ["X"],
            "Retailer": ["Tesco"],
            "City": ["London"],
        })
        result = merge_dataframes([df1], ["file1.xlsx"])
        # Country, Currency, and all other master columns should exist
        assert "Country" in result.dataframe.columns
        assert "Currency" in result.dataframe.columns
        assert "Price (EUR)" in result.dataframe.columns


# ═══════════════════════════════════════════════════════════════════════════
# Overlap detection
# ═══════════════════════════════════════════════════════════════════════════

class TestOverlapDetection:
    def test_overlap_detected(self):
        existing = _make_store_df("Tesco", "London", "Large", rows=5)
        new_data = _make_store_df("Tesco", "London", "Large", rows=3)
        result = merge_dataframes(
            [new_data],
            ["new_file.xlsx"],
            existing_master=existing,
        )
        assert len(result.overlaps) == 1
        overlap = result.overlaps[0]
        assert overlap.retailer == "Tesco"
        assert overlap.city == "London"
        assert overlap.existing_row_count == 5
        assert overlap.new_row_count == 3

    def test_no_overlap_different_stores(self):
        existing = _make_store_df("Tesco", "London", rows=5)
        new_data = _make_store_df("Sainsburys", "Manchester", rows=3)
        result = merge_dataframes(
            [new_data],
            ["new_file.xlsx"],
            existing_master=existing,
        )
        assert len(result.overlaps) == 0

    def test_blank_format_matches_blank_format(self):
        """Stores with blank format should still be detected as overlapping."""
        existing = _make_store_df("Tesco", "London", None, rows=3)
        new_data = _make_store_df("Tesco", "London", None, rows=2)
        result = merge_dataframes(
            [new_data],
            ["new_file.xlsx"],
            existing_master=existing,
        )
        assert len(result.overlaps) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Replace / Skip decisions
# ═══════════════════════════════════════════════════════════════════════════

class TestOverlapDecisions:
    def test_replace_removes_old_keeps_new(self):
        existing = _make_store_df("Tesco", "London", "Large", rows=5)
        new_data = _make_store_df("Tesco", "London", "Large", rows=3)

        decisions = {"Tesco|London|Large": "replace"}
        result = apply_overlap_decisions(new_data, existing, decisions)

        # Should have only the 3 new rows
        tesco_rows = result[
            (result["Retailer"] == "Tesco") & (result["City"] == "London")
        ]
        assert len(tesco_rows) == 3

    def test_skip_keeps_old_drops_new(self):
        existing = _make_store_df("Tesco", "London", "Large", rows=5)
        new_data = _make_store_df("Tesco", "London", "Large", rows=3)

        decisions = {"Tesco|London|Large": "skip"}
        result = apply_overlap_decisions(new_data, existing, decisions)

        # Should have only the 5 existing rows
        tesco_rows = result[
            (result["Retailer"] == "Tesco") & (result["City"] == "London")
        ]
        assert len(tesco_rows) == 5


# ═══════════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_empty_dataframe_filtered_out(self):
        df1 = _make_store_df(rows=3)
        df2 = pd.DataFrame()  # empty
        result = merge_dataframes([df1, df2], ["f1.xlsx", "f2.xlsx"])
        assert result.total_rows == 3

    def test_none_dataframe_filtered_out(self):
        df1 = _make_store_df(rows=2)
        result = merge_dataframes([df1, None], ["f1.xlsx", "f2.xlsx"])
        assert result.total_rows == 2

    def test_all_empty_gives_empty_result(self):
        result = merge_dataframes([pd.DataFrame()], ["empty.xlsx"])
        assert result.total_rows == 0
        assert result.dataframe.empty


# ═══════════════════════════════════════════════════════════════════════════
# Store key building
# ═══════════════════════════════════════════════════════════════════════════

class TestStoreKey:
    def test_normal_key(self):
        row = pd.Series({"Retailer": "Tesco", "City": "London", "Store Format": "Large"})
        assert _build_store_key(row) == "Tesco|London|Large"

    def test_blank_format(self):
        row = pd.Series({"Retailer": "Tesco", "City": "London", "Store Format": None})
        assert _build_store_key(row) == "Tesco|London|"

    def test_missing_retailer(self):
        row = pd.Series({"City": "London", "Store Format": "Large"})
        assert _build_store_key(row) == "|London|Large"
