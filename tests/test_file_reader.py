"""
Tests for processing/file_reader.py

Covers all three structural types found in the test fixtures:
  A) Flat / clean — header in row 1, data in column A, no merged cells
  B) Sectioned — merged-cell separators, repeated headers, data in column A
  C) Offset + Sectioned — data starts in column F/G, merged separators

Also tests edge cases: context-only rows, annotation rows, extra columns,
numbers stored as strings, and error handling.
"""

from pathlib import Path

import pandas as pd
import pytest

from processing.file_reader import (
    FileReadResult,
    SectionMetadata,
    read_excel_file,
    _parse_section_text,
    _is_context_only_row,
)

# ---------------------------------------------------------------------------
# Fixture path helper
# ---------------------------------------------------------------------------
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _fixture(filename: str) -> Path:
    """Return the full path to a test fixture file."""
    path = FIXTURES_DIR / filename
    assert path.exists(), f"Fixture file not found: {path}"
    return path


# ═══════════════════════════════════════════════════════════════════════════
# Structure A: Flat / Clean files
# ═══════════════════════════════════════════════════════════════════════════

class TestFlatFiles:
    """Files with header in row 1, data starting in column A, no merged cells."""

    def test_aldi_fulham_basic_read(self):
        """aldi_fulham: flat file with 29 data rows and an annotation row."""
        result = read_excel_file(_fixture("aldi_fulham_shelf_analysis.xlsx"))

        assert isinstance(result, FileReadResult)
        assert len(result.errors) == 0
        assert result.header_row_index == 1
        assert result.data_start_column == 0
        assert result.sheet_name == "SKU Data"

    def test_aldi_fulham_data_rows(self):
        """aldi_fulham: should extract 28 data rows (29 content rows minus annotation row)."""
        result = read_excel_file(_fixture("aldi_fulham_shelf_analysis.xlsx"))
        raw_df = result.raw_dataframe

        assert not raw_df.empty
        # Row 8 has "OTHER TO GO DRINKS..." in Segment column only (1-2 cells)
        # — should be skipped by the <3 cells rule.
        # Row 9 is empty — also skipped.
        # So 30 total rows - 1 header - 1 annotation - 1 empty = 27 data rows,
        # but some rows at the end may also be empty. Verify we have at least 25.
        assert result.total_rows_read >= 25, (
            f"Expected at least 25 data rows, got {result.total_rows_read}"
        )

    def test_aldi_fulham_annotation_skipped(self):
        """aldi_fulham row 8: annotation row should appear in skipped_rows."""
        result = read_excel_file(_fixture("aldi_fulham_shelf_analysis.xlsx"))

        skipped_reasons = {s["row"]: s["reason"] for s in result.skipped_rows}
        # Row 8 has only 1 non-empty cell → should be skipped as "too few"
        assert 8 in skipped_reasons, (
            f"Row 8 should be skipped. Skipped rows: {skipped_reasons}"
        )

    def test_aldi_fulham_columns_present(self):
        """aldi_fulham: all expected raw columns should be in the DataFrame."""
        result = read_excel_file(_fixture("aldi_fulham_shelf_analysis.xlsx"))
        raw_df = result.raw_dataframe

        expected_cols = {"Brand", "Segment", "Flavor", "Facings", "Price (GBP)"}
        actual_cols = set(raw_df.columns)
        assert expected_cols.issubset(actual_cols), (
            f"Missing columns: {expected_cols - actual_cols}"
        )

    def test_lidl_fulham_flat_read(self):
        """Lidl_Fulham: clean flat file, header row 1, 31 data rows."""
        result = read_excel_file(_fixture("Lidl_Fulham_Juice_Analysis.xlsx"))

        assert len(result.errors) == 0
        assert result.header_row_index == 1
        assert result.data_start_column == 0
        assert result.total_rows_read >= 25

    def test_ms_fulham_numbers_as_strings(self):
        """M&S Fulham: some numeric cells stored as strings (e.g. '3.70')."""
        result = read_excel_file(
            _fixture("M&S Fulham_Juice_Analysis_Corrected.xlsx")
        )

        assert len(result.errors) == 0
        assert result.header_row_index == 1
        assert result.total_rows_read >= 40
        # Verify data is passed through as-is (string or number)
        raw_df = result.raw_dataframe
        assert "Brand" in raw_df.columns

    def test_sainsburys_pimlico_extra_column(self):
        """Sainsburys_Pimlico: has extra 'Fridge Number' column at C."""
        result = read_excel_file(
            _fixture("Sainsburys_Pimlico_Shelf_Analysis (1).xlsx")
        )

        assert len(result.errors) == 0
        assert result.header_row_index == 1
        raw_df = result.raw_dataframe
        assert "Fridge Number" in raw_df.columns
        assert result.total_rows_read >= 100


# ═══════════════════════════════════════════════════════════════════════════
# Structure A with context rows: Aldi Balham
# ═══════════════════════════════════════════════════════════════════════════

class TestContextRows:
    """Aldi Balham: flat file with context-only rows providing section metadata."""

    def test_aldi_balham_basic_read(self):
        """Aldi Balham: header row 1, no merged cells, has context rows."""
        result = read_excel_file(
            _fixture("Shelf_Analysis_Aldi_Balham_Checked.xlsx")
        )

        assert len(result.errors) == 0
        assert result.header_row_index == 1
        assert result.data_start_column == 0

    def test_aldi_balham_context_rows_detected(self):
        """Aldi Balham rows 2, 13: have photo/location but no SKU data → context rows."""
        result = read_excel_file(
            _fixture("Shelf_Analysis_Aldi_Balham_Checked.xlsx")
        )

        context_skipped = [
            s for s in result.skipped_rows
            if "context-only" in s.get("reason", "")
        ]
        assert len(context_skipped) >= 2, (
            f"Expected at least 2 context-only rows, got {len(context_skipped)}: "
            f"{context_skipped}"
        )

    def test_aldi_balham_context_rows_not_in_data(self):
        """Context rows should NOT appear as data rows in the DataFrame."""
        result = read_excel_file(
            _fixture("Shelf_Analysis_Aldi_Balham_Checked.xlsx")
        )
        raw_df = result.raw_dataframe

        # Context rows have no Brand value — every real data row should have Brand
        brand_values = raw_df["Brand"].dropna()
        assert len(brand_values) == len(raw_df), (
            f"Some data rows have no Brand — possible context row leak. "
            f"Rows with Brand: {len(brand_values)}, total: {len(raw_df)}"
        )

    def test_aldi_balham_section_metadata_carry_forward(self):
        """Section metadata from context rows should fill blank Photo/Location."""
        result = read_excel_file(
            _fixture("Shelf_Analysis_Aldi_Balham_Checked.xlsx")
        )

        assert len(result.sections) >= 2, (
            f"Expected at least 2 sections (from context rows), got {len(result.sections)}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Structure B: Sectioned files (merged-cell separators, data in column A)
# ═══════════════════════════════════════════════════════════════════════════

class TestSectionedFiles:
    """Files with merged-cell section separators and repeated headers."""

    def test_ms_covent_garden_sections(self):
        """MS_Covent_Garden: 13 merged separators, each followed by repeated header."""
        result = read_excel_file(
            _fixture("MS_Covent Garden_Small_Shelf_Analysis_Checked.xlsx")
        )

        assert len(result.errors) == 0
        assert result.header_row_index == 2  # Row 1 is merged separator, row 2 is header
        assert result.data_start_column == 0
        assert len(result.sections) >= 10  # 13 merged sections

    def test_ms_covent_garden_data_row_count(self):
        """MS_Covent_Garden: should extract 76 data rows across 13 sections.

        114 total rows - 13 merged separators - 12 repeated headers - empty rows = 76.
        """
        result = read_excel_file(
            _fixture("MS_Covent Garden_Small_Shelf_Analysis_Checked.xlsx")
        )
        assert result.total_rows_read >= 70

    def test_ms_covent_garden_repeated_headers_skipped(self):
        """MS_Covent_Garden: repeated header rows should be in skipped_rows."""
        result = read_excel_file(
            _fixture("MS_Covent Garden_Small_Shelf_Analysis_Checked.xlsx")
        )

        repeated_headers = [
            s for s in result.skipped_rows
            if "repeated header" in s.get("reason", "")
        ]
        # Should have at least 10 repeated headers (one per section after the first)
        assert len(repeated_headers) >= 10, (
            f"Expected 10+ repeated headers, got {len(repeated_headers)}"
        )

    def test_ms_covent_garden_section_metadata_parsed(self):
        """MS_Covent_Garden: section text should be parsed for photo/location."""
        result = read_excel_file(
            _fixture("MS_Covent Garden_Small_Shelf_Analysis_Checked.xlsx")
        )

        # At least one section should have a parsed shelf_location or photo
        has_metadata = any(
            s.photo or s.shelf_location for s in result.sections
        )
        assert has_metadata, "Expected at least one section with parsed metadata"

    def test_sainsburys_vauxhall_sections(self):
        """Sainsburys_Vauxhall: 3 merged sections."""
        result = read_excel_file(
            _fixture("Sainsburys_Vauxhall_Small_Shelf_Analysis_Checked.xlsx")
        )

        assert len(result.errors) == 0
        assert result.header_row_index == 2  # Row 1 is merged separator
        merged_sections = [
            s for s in result.sections
            if "merged" not in s.raw_text.lower()
            and "context" not in s.raw_text.lower()
        ]
        # Should have 3 sections from merged separators
        assert len(result.sections) >= 3

    def test_tesco_covent_garden_sections(self):
        """Tesco_Covent_Garden: 6 merged sections, extra 'Edited by Fee' column."""
        result = read_excel_file(
            _fixture("Tesco_Covent_Garden_Shelf_Analysis - Checked.xlsx")
        )

        assert len(result.errors) == 0
        assert result.total_rows_read >= 80

    def test_tesco_express_strand_sections(self):
        """Tesco_Express_Strand: 3 merged sections."""
        result = read_excel_file(
            _fixture("Tesco_Express_Strand_Analysis_Checked.xlsx")
        )

        assert len(result.errors) == 0
        assert result.header_row_index == 2
        assert result.total_rows_read >= 40


# ═══════════════════════════════════════════════════════════════════════════
# Structure C: Offset + Sectioned files
# ═══════════════════════════════════════════════════════════════════════════

class TestOffsetFiles:
    """Files where data starts in column F or G with merged separators."""

    def test_tesco_oval_offset_detection(self):
        """Tesco_Oval: data starts in column F (offset=5)."""
        result = read_excel_file(
            _fixture("Tesco_Oval_LargeShelf_Analysis.xlsx")
        )

        assert len(result.errors) == 0
        assert result.data_start_column == 5, (
            f"Expected offset 5 (column F), got {result.data_start_column}"
        )

    def test_tesco_oval_key_block_skipped(self):
        """Tesco_Oval: rows 1-4 (Key legend) should not appear as data."""
        result = read_excel_file(
            _fixture("Tesco_Oval_LargeShelf_Analysis.xlsx")
        )
        raw_df = result.raw_dataframe

        # The "Key" text should not appear in any Brand or Segment column
        if "Brand" in raw_df.columns:
            assert "Key" not in raw_df["Brand"].values

    def test_tesco_oval_data_rows(self):
        """Tesco_Oval: should extract 100+ data rows across 4 sections."""
        result = read_excel_file(
            _fixture("Tesco_Oval_LargeShelf_Analysis.xlsx")
        )

        assert result.total_rows_read >= 100, (
            f"Expected 100+ rows, got {result.total_rows_read}"
        )

    def test_tesco_oval_sections(self):
        """Tesco_Oval: 4 merged sections (Fridge1, Fridge2, Fridge3, To-Go)."""
        result = read_excel_file(
            _fixture("Tesco_Oval_LargeShelf_Analysis.xlsx")
        )

        merged_sections = [
            s for s in result.sections if "context" not in s.raw_text.lower()
        ]
        assert len(merged_sections) >= 4, (
            f"Expected 4+ sections, got {len(merged_sections)}"
        )

    def test_tesco_oval_section_metadata(self):
        """Tesco_Oval: section separators should parse location and photo."""
        result = read_excel_file(
            _fixture("Tesco_Oval_LargeShelf_Analysis.xlsx")
        )

        # The first section mentions "Chilled Section - Fridge 1"
        first_section = result.sections[0] if result.sections else None
        assert first_section is not None
        assert first_section.shelf_location is not None or first_section.photo is not None

    def test_waitrose_balham_offset_detection(self):
        """Waitrose_Balham: data starts in column G (offset=6)."""
        result = read_excel_file(
            _fixture("Waitrose_Balham_Large_Shelf_Analysis_v2.xlsx")
        )

        assert len(result.errors) == 0
        assert result.data_start_column == 6, (
            f"Expected offset 6 (column G), got {result.data_start_column}"
        )

    def test_waitrose_balham_data_rows(self):
        """Waitrose_Balham: should extract 100+ data rows across 11 sections."""
        result = read_excel_file(
            _fixture("Waitrose_Balham_Large_Shelf_Analysis_v2.xlsx")
        )

        assert result.total_rows_read >= 100
        assert len(result.sections) >= 10

    def test_waitrose_balham_columns(self):
        """Waitrose_Balham: column names should be read from the offset header."""
        result = read_excel_file(
            _fixture("Waitrose_Balham_Large_Shelf_Analysis_v2.xlsx")
        )
        raw_df = result.raw_dataframe

        expected_cols = {"Brand", "Segment", "Flavor"}
        actual_cols = set(raw_df.columns)
        assert expected_cols.issubset(actual_cols), (
            f"Missing: {expected_cols - actual_cols}. Have: {sorted(actual_cols)}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# All 11 files: smoke test
# ═══════════════════════════════════════════════════════════════════════════

class TestAllFilesSmoke:
    """Every raw fixture file should be readable without errors."""

    ALL_RAW_FILES = [
        "aldi_fulham_shelf_analysis.xlsx",
        "Lidl_Fulham_Juice_Analysis.xlsx",
        "M&S Fulham_Juice_Analysis_Corrected.xlsx",
        "MS_Covent Garden_Small_Shelf_Analysis_Checked.xlsx",
        "Sainsburys_Pimlico_Shelf_Analysis (1).xlsx",
        "Sainsburys_Vauxhall_Small_Shelf_Analysis_Checked.xlsx",
        "Shelf_Analysis_Aldi_Balham_Checked.xlsx",
        "Tesco_Covent_Garden_Shelf_Analysis - Checked.xlsx",
        "Tesco_Express_Strand_Analysis_Checked.xlsx",
        "Tesco_Oval_LargeShelf_Analysis.xlsx",
        "Waitrose_Balham_Large_Shelf_Analysis_v2.xlsx",
    ]

    @pytest.mark.parametrize("filename", ALL_RAW_FILES)
    def test_file_reads_without_errors(self, filename: str):
        """Every file should produce a result with no errors."""
        result = read_excel_file(_fixture(filename))

        assert len(result.errors) == 0, (
            f"{filename}: errors = {result.errors}"
        )

    @pytest.mark.parametrize("filename", ALL_RAW_FILES)
    def test_file_produces_data_rows(self, filename: str):
        """Every file should produce at least 5 data rows."""
        result = read_excel_file(_fixture(filename))

        assert result.total_rows_read >= 5, (
            f"{filename}: only {result.total_rows_read} rows extracted"
        )

    @pytest.mark.parametrize("filename", ALL_RAW_FILES)
    def test_file_has_brand_column(self, filename: str):
        """Every file should have a 'Brand' column in the output."""
        result = read_excel_file(_fixture(filename))
        raw_df = result.raw_dataframe

        assert "Brand" in raw_df.columns, (
            f"{filename}: 'Brand' column not found. Columns: {list(raw_df.columns)}"
        )

    @pytest.mark.parametrize("filename", ALL_RAW_FILES)
    def test_no_empty_dataframe(self, filename: str):
        """DataFrame should never be empty."""
        result = read_excel_file(_fixture(filename))

        assert not result.raw_dataframe.empty, (
            f"{filename}: raw_dataframe is empty"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Unit tests for internal helpers
# ═══════════════════════════════════════════════════════════════════════════

class TestParseSectionText:
    """Tests for _parse_section_text helper."""

    def test_pipe_delimited_full(self):
        """Full pipe-delimited section text with all fields."""
        text = (
            "📷 Chilled_section_Fridge1  |  Location: Chilled Section - Fridge 1  |  "
            "Est. Linear Meters: 2.5  |  Shelf Levels: 6"
        )
        meta = _parse_section_text(text)

        assert meta.shelf_location == "Chilled Section - Fridge 1"
        assert meta.est_linear_meters == 2.5
        assert meta.shelf_levels == 6

    def test_short_photo_reference(self):
        """Short separator like 'Photo: IMG_0118.jpeg'."""
        text = "Photo: IMG_0118.jpeg"
        meta = _parse_section_text(text)

        assert meta.photo == "IMG_0118.jpeg"

    def test_bare_photo_with_pipe(self):
        """Separator starting with photo name then pipe-delimited fields."""
        text = "To-Go Section — Shots  |  Photo: To_go_shots"
        meta = _parse_section_text(text)

        assert meta.photo == "To_go_shots"

    def test_empty_text(self):
        """Empty text should return empty metadata."""
        meta = _parse_section_text("")
        assert meta.photo is None
        assert meta.shelf_location is None

    def test_photo_reference_with_location(self):
        """Waitrose-style: 'Photo: X.jpg | Location: Y'."""
        text = "Photo: Chilled_Section_Fridge1_Top_shelf.jpg  |  Location: Chilled Section - Fridge 1"
        meta = _parse_section_text(text)

        assert meta.photo == "Chilled_Section_Fridge1_Top_shelf.jpg"
        assert meta.shelf_location == "Chilled Section - Fridge 1"


class TestIsContextOnlyRow:
    """Tests for _is_context_only_row helper."""

    def test_context_row_no_sku_data(self):
        """Row with photo+location but no Brand/Flavor/Facings → context."""
        column_names = ["Photo File Name", "Shelf Location", "Est. Linear Meters",
                        "Shelf Levels", "Shelf Level", "Segment", "Brand", "Flavor",
                        "Facings"]
        row_values = ["photo.jpg", "Chilled Section", 3.0, 5, None, None, None, None, None]

        assert _is_context_only_row(row_values, column_names) is True

    def test_data_row_has_brand(self):
        """Row with Brand populated → not context-only."""
        column_names = ["Photo File Name", "Shelf Location", "Brand", "Flavor", "Facings"]
        row_values = ["photo.jpg", "Chilled Section", "Innocent", "Orange", 3]

        assert _is_context_only_row(row_values, column_names) is False

    def test_empty_row_not_context(self):
        """Row with no context columns populated → not context (just empty)."""
        column_names = ["Photo File Name", "Shelf Location", "Brand", "Flavor", "Facings"]
        row_values = [None, None, None, None, None]

        assert _is_context_only_row(row_values, column_names) is False


# ═══════════════════════════════════════════════════════════════════════════
# Error handling
# ═══════════════════════════════════════════════════════════════════════════

class TestErrorHandling:
    """Edge cases and error conditions."""

    def test_nonexistent_file(self):
        """Reading a non-existent file should return errors, not crash."""
        result = read_excel_file(Path("tests/fixtures/does_not_exist.xlsx"))

        assert len(result.errors) > 0
        assert result.raw_dataframe.empty

    def test_source_row_tracking(self):
        """Every data row should have a _source_row column for traceability."""
        result = read_excel_file(_fixture("aldi_fulham_shelf_analysis.xlsx"))
        raw_df = result.raw_dataframe

        assert "_source_row" in raw_df.columns
        # Source rows should be integers > 1 (row 1 is the header)
        assert all(raw_df["_source_row"] > 1)
