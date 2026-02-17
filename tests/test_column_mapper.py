"""
Tests for processing/column_mapper.py

Covers:
  - Exact match mapping (Brand, Flavor, etc.)
  - Known rename mapping (Segment → Product Type, etc.)
  - Fuzzy match fallback for misspelled column names
  - Unmapped columns flagged correctly
  - Internal columns (_unnamed_*, _source_row) silently skipped
  - Confidence scores: 100 for exact/rename, <100 for fuzzy
  - Real column sets from the 11 fixture files
"""

import pytest

from processing.column_mapper import (
    ColumnMappingResult,
    map_columns,
)


# ═══════════════════════════════════════════════════════════════════════════
# Exact match tests
# ═══════════════════════════════════════════════════════════════════════════

class TestExactMatches:
    """Columns that match master names exactly (case-insensitive)."""

    def test_brand_maps_directly(self):
        result = map_columns(["Brand"])
        assert result.mapping["Brand"] == "Brand"
        assert result.confidence["Brand"] == 100

    def test_case_insensitive(self):
        """'BRAND' and 'brand' should both map to 'Brand'."""
        result = map_columns(["brand", "FLAVOR"])
        assert result.mapping["brand"] == "Brand"
        assert result.mapping["FLAVOR"] == "Product Name"

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace should be ignored."""
        result = map_columns(["  Brand  ", " Flavor "])
        assert result.mapping["  Brand  "] == "Brand"
        assert result.mapping[" Flavor "] == "Product Name"

    def test_photo_file_name_variant(self):
        """'Photo File Name' should map to 'Photo'."""
        result = map_columns(["Photo File Name"])
        assert result.mapping["Photo File Name"] == "Photo"

    def test_common_exact_columns(self):
        """A batch of common exact-match columns."""
        columns = [
            "Brand", "Shelf Location", "Shelf Levels", "Shelf Level",
            "Facings", "Processing Method", "HPP Treatment",
            "Packaging Type", "Claims", "Stock Status", "Notes",
            "Confidence Score", "Fridge Number", "Est. Linear Meters",
        ]
        result = map_columns(columns)
        assert len(result.unmapped) == 0
        for col in columns:
            assert result.mapping[col] is not None
            assert result.confidence[col] == 100


# ═══════════════════════════════════════════════════════════════════════════
# Known rename tests
# ═══════════════════════════════════════════════════════════════════════════

class TestKnownRenames:
    """Columns that are semantically renamed (raw term → master term)."""

    def test_segment_to_product_type(self):
        result = map_columns(["Segment"])
        assert result.mapping["Segment"] == "Product Type"
        assert result.confidence["Segment"] == 100

    def test_sub_segment_to_need_state(self):
        result = map_columns(["Sub-segment"])
        assert result.mapping["Sub-segment"] == "Need State"
        assert result.confidence["Sub-segment"] == 100

    def test_branded_private_label(self):
        result = map_columns(["Branded / Private Label"])
        assert result.mapping["Branded / Private Label"] == "Branded/Private Label"

    def test_bonus_to_bonus_promotions(self):
        result = map_columns(["Bonus"])
        assert result.mapping["Bonus"] == "Bonus/Promotions"

    def test_price_gbp(self):
        result = map_columns(["Price (GBP)"])
        assert result.mapping["Price (GBP)"] == "Price (Local Currency)"

    def test_price_eur(self):
        result = map_columns(["Price (EUR)"])
        assert result.mapping["Price (EUR)"] == "Price (Local Currency)"

    def test_price_pounds(self):
        result = map_columns(["Price (Pounds)"])
        assert result.mapping["Price (Pounds)"] == "Price (Local Currency)"

    def test_price_per_liter_gbp(self):
        result = map_columns(["Price per Liter (GBP)"])
        assert result.mapping["Price per Liter (GBP)"] == "Price per Liter (EUR)"

    def test_all_renames_confidence_100(self):
        """All known renames should have confidence 100."""
        columns = ["Segment", "Sub-segment", "Bonus", "Price (GBP)"]
        result = map_columns(columns)
        for col in columns:
            assert result.confidence[col] == 100


# ═══════════════════════════════════════════════════════════════════════════
# Fuzzy match tests
# ═══════════════════════════════════════════════════════════════════════════

class TestFuzzyMatch:
    """Columns that require fuzzy matching to resolve."""

    def test_misspelled_processing_method(self):
        """'Procesing Method' (missing 's') should fuzzy-match."""
        result = map_columns(["Procesing Method"])
        assert result.mapping["Procesing Method"] == "Processing Method"
        assert result.confidence["Procesing Method"] < 100
        assert result.confidence["Procesing Method"] >= 80

    def test_misspelled_packaging_type(self):
        """'Packging Type' should fuzzy-match to 'Packaging Type'."""
        result = map_columns(["Packging Type"])
        assert result.mapping["Packging Type"] == "Packaging Type"
        assert result.confidence["Packging Type"] >= 80

    def test_fuzzy_confidence_below_100(self):
        """Fuzzy matches should always have confidence < 100."""
        result = map_columns(["Procesing Method"])
        assert result.confidence["Procesing Method"] < 100


# ═══════════════════════════════════════════════════════════════════════════
# Unmapped columns
# ═══════════════════════════════════════════════════════════════════════════

class TestUnmappedColumns:
    """Columns that cannot be mapped to any master column."""

    def test_random_column_unmapped(self):
        result = map_columns(["Random Column XYZ"])
        assert result.mapping["Random Column XYZ"] is None
        assert "Random Column XYZ" in result.unmapped
        assert result.confidence["Random Column XYZ"] == 0

    def test_edited_by_fee_unmapped(self):
        """'Edited by Fee' (a real extra column in Tesco files) should be unmapped."""
        result = map_columns(["Edited by Fee"])
        assert result.mapping["Edited by Fee"] is None
        assert "Edited by Fee" in result.unmapped

    def test_mixed_mapped_and_unmapped(self):
        """A mix of known and unknown columns."""
        result = map_columns(["Brand", "Unknown Col", "Segment"])
        assert result.mapping["Brand"] == "Brand"
        assert result.mapping["Segment"] == "Product Type"
        assert result.mapping["Unknown Col"] is None
        assert result.unmapped == ["Unknown Col"]


# ═══════════════════════════════════════════════════════════════════════════
# Internal columns (skipped)
# ═══════════════════════════════════════════════════════════════════════════

class TestInternalColumnsSkipped:
    """Internal columns prefixed with '_' should be silently skipped."""

    def test_source_row_skipped(self):
        result = map_columns(["Brand", "_source_row"])
        assert "_source_row" not in result.mapping
        assert "_source_row" not in result.unmapped

    def test_unnamed_columns_skipped(self):
        result = map_columns(["_unnamed_0", "_unnamed_1", "Brand"])
        assert "_unnamed_0" not in result.mapping
        assert "_unnamed_1" not in result.mapping
        assert "Brand" in result.mapping

    def test_only_internal_columns(self):
        """If all columns are internal, result should be empty."""
        result = map_columns(["_source_row", "_unnamed_0"])
        assert len(result.mapping) == 0
        assert len(result.unmapped) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Result type tests
# ═══════════════════════════════════════════════════════════════════════════

class TestResultType:
    """Verify the ColumnMappingResult data structure."""

    def test_return_type(self):
        result = map_columns(["Brand"])
        assert isinstance(result, ColumnMappingResult)
        assert isinstance(result.mapping, dict)
        assert isinstance(result.unmapped, list)
        assert isinstance(result.confidence, dict)

    def test_empty_input(self):
        result = map_columns([])
        assert result.mapping == {}
        assert result.unmapped == []
        assert result.confidence == {}


# ═══════════════════════════════════════════════════════════════════════════
# Realistic column sets from fixture files
# ═══════════════════════════════════════════════════════════════════════════

class TestRealisticColumnSets:
    """Test with column names similar to what the fixture files produce."""

    def test_typical_flat_file_columns(self):
        """Column set from a typical flat file (Aldi/Lidl style)."""
        raw_columns = [
            "Photo File Name", "Shelf Location", "Shelf Levels",
            "Shelf Level", "Segment", "Branded / Private Label",
            "Brand", "Sub-brand", "Flavor", "Facings", "Price (GBP)",
            "Packaging Size (ml)", "Sub-segment", "Processing Method",
            "HPP Treatment", "Packaging Type", "Claims", "Bonus",
            "Stock Status", "Confidence Score", "Notes",
        ]
        result = map_columns(raw_columns)

        # Every column should be mapped
        assert len(result.unmapped) == 0, (
            f"Unmapped columns: {result.unmapped}"
        )

        # Spot-check key renames
        assert result.mapping["Segment"] == "Product Type"
        assert result.mapping["Sub-segment"] == "Need State"
        assert result.mapping["Branded / Private Label"] == "Branded/Private Label"
        assert result.mapping["Bonus"] == "Bonus/Promotions"
        assert result.mapping["Price (GBP)"] == "Price (Local Currency)"
        assert result.mapping["Photo File Name"] == "Photo"

    def test_file_with_fridge_number(self):
        """Column set from Sainsburys_Pimlico which has Fridge Number."""
        raw_columns = [
            "Photo File Name", "Fridge Number", "Shelf Location",
            "Shelf Levels", "Shelf Level", "Segment",
            "Branded / Private Label", "Brand", "Sub-brand", "Flavor",
            "Facings", "Price (GBP)", "Packaging Size (ml)",
            "Sub-segment", "Processing Method", "HPP Treatment",
            "Packaging Type", "Claims", "Bonus", "Stock Status",
            "Confidence Score", "Notes",
        ]
        result = map_columns(raw_columns)
        assert len(result.unmapped) == 0
        assert result.mapping["Fridge Number"] == "Fridge Number"

    def test_file_with_est_linear_meters(self):
        """Column set from a sectioned file with Est. Linear Meters."""
        raw_columns = [
            "Photo File Name", "Shelf Location", "Est. Linear Meters",
            "Shelf Levels", "Shelf Level", "Segment", "Brand",
            "Sub-brand", "Flavor", "Facings", "Price (GBP)",
            "Packaging Size (ml)", "Processing Method", "HPP Treatment",
            "Packaging Type", "Claims", "Bonus", "Stock Status",
            "Confidence Score", "Notes",
        ]
        result = map_columns(raw_columns)
        assert len(result.unmapped) == 0
        assert result.mapping["Est. Linear Meters"] == "Est. Linear Meters"
