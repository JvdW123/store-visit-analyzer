"""
Tests for processing/filename_parser.py

Covers:
  - All 11 fixture filenames with expected Retailer/City/Format
  - Edge cases: Tesco Express vs Tesco, M&S variants, two-word cities
  - Suffix stripping: _checked, _corrected, _v2, (1), " - "
  - Format extraction: "Large" from "LargeShelf", substring matching
  - Unknown filenames: low confidence, None fields
  - Internal helper unit tests
"""

import pytest

from processing.filename_parser import (
    FilenameParseResult,
    parse_filename,
    _clean_filename,
    _match_retailer,
    _match_city,
    _match_format,
    _compute_confidence,
)


# ═══════════════════════════════════════════════════════════════════════════
# All 11 fixture filenames — parametrized
# ═══════════════════════════════════════════════════════════════════════════

ALL_FIXTURE_FILENAMES = [
    # (filename, expected_retailer, expected_city, expected_format)
    ("aldi_fulham_shelf_analysis.xlsx", "Aldi", "Fulham", None),
    ("Lidl_Fulham_Juice_Analysis.xlsx", "Lidl", "Fulham", None),
    ("M&S Fulham_Juice_Analysis_Corrected.xlsx", "M&S", "Fulham", None),
    ("MS_Covent Garden_Small_Shelf_Analysis_Checked.xlsx", "M&S", "Covent Garden", "Small"),
    ("Sainsburys_Pimlico_Shelf_Analysis (1).xlsx", "Sainsbury's", "Pimlico", None),
    ("Sainsburys_Vauxhall_Small_Shelf_Analysis_Checked.xlsx", "Sainsbury's", "Vauxhall", "Small"),
    ("Shelf_Analysis_Aldi_Balham_Checked.xlsx", "Aldi", "Balham", None),
    ("Tesco_Covent_Garden_Shelf_Analysis - Checked.xlsx", "Tesco", "Covent Garden", None),
    ("Tesco_Express_Strand_Analysis_Checked.xlsx", "Tesco Express", "Strand", None),
    ("Tesco_Oval_LargeShelf_Analysis.xlsx", "Tesco", "Oval", "Large"),
    ("Waitrose_Balham_Large_Shelf_Analysis_v2.xlsx", "Waitrose", "Balham", "Large"),
]


class TestAllFixtureFilenames:
    """Every fixture filename should parse to the correct metadata."""

    @pytest.mark.parametrize(
        "filename,expected_retailer,expected_city,expected_format",
        ALL_FIXTURE_FILENAMES,
        ids=[f[0].split(".")[0] for f in ALL_FIXTURE_FILENAMES],
    )
    def test_retailer(self, filename, expected_retailer, expected_city, expected_format):
        result = parse_filename(filename)
        assert result.retailer == expected_retailer, (
            f"'{filename}': expected retailer '{expected_retailer}', "
            f"got '{result.retailer}'"
        )

    @pytest.mark.parametrize(
        "filename,expected_retailer,expected_city,expected_format",
        ALL_FIXTURE_FILENAMES,
        ids=[f[0].split(".")[0] for f in ALL_FIXTURE_FILENAMES],
    )
    def test_city(self, filename, expected_retailer, expected_city, expected_format):
        result = parse_filename(filename)
        assert result.city == expected_city, (
            f"'{filename}': expected city '{expected_city}', "
            f"got '{result.city}'"
        )

    @pytest.mark.parametrize(
        "filename,expected_retailer,expected_city,expected_format",
        ALL_FIXTURE_FILENAMES,
        ids=[f[0].split(".")[0] for f in ALL_FIXTURE_FILENAMES],
    )
    def test_format(self, filename, expected_retailer, expected_city, expected_format):
        result = parse_filename(filename)
        assert result.store_format == expected_format, (
            f"'{filename}': expected format '{expected_format}', "
            f"got '{result.store_format}'"
        )

    @pytest.mark.parametrize(
        "filename,expected_retailer,expected_city,expected_format",
        ALL_FIXTURE_FILENAMES,
        ids=[f[0].split(".")[0] for f in ALL_FIXTURE_FILENAMES],
    )
    def test_confidence_high(self, filename, expected_retailer, expected_city, expected_format):
        """All known fixture filenames should have confidence >= 85."""
        result = parse_filename(filename)
        assert result.confidence >= 85, (
            f"'{filename}': confidence {result.confidence}% is below 85%"
        )

    @pytest.mark.parametrize(
        "filename,expected_retailer,expected_city,expected_format",
        ALL_FIXTURE_FILENAMES,
        ids=[f[0].split(".")[0] for f in ALL_FIXTURE_FILENAMES],
    )
    def test_raw_filename_preserved(self, filename, expected_retailer, expected_city, expected_format):
        """The raw_filename field should always contain the original input."""
        result = parse_filename(filename)
        assert result.raw_filename == filename


# ═══════════════════════════════════════════════════════════════════════════
# Edge cases: Retailer matching
# ═══════════════════════════════════════════════════════════════════════════

class TestRetailerEdgeCases:
    """Test that retailer matching handles tricky patterns correctly."""

    def test_tesco_express_not_just_tesco(self):
        """'Tesco Express' must match as a single retailer, not just 'Tesco'."""
        result = parse_filename("Tesco_Express_Strand_Analysis_Checked.xlsx")
        assert result.retailer == "Tesco Express"

    def test_tesco_alone(self):
        """Plain 'Tesco' should match 'Tesco', not 'Tesco Express'."""
        result = parse_filename("Tesco_Oval_LargeShelf_Analysis.xlsx")
        assert result.retailer == "Tesco"

    def test_ms_with_ampersand(self):
        """'M&S' with ampersand and space should resolve to 'M&S'."""
        result = parse_filename("M&S Fulham_Juice_Analysis_Corrected.xlsx")
        assert result.retailer == "M&S"

    def test_ms_without_ampersand(self):
        """'MS_' (no ampersand) should resolve to 'M&S'."""
        result = parse_filename("MS_Covent Garden_Small_Shelf_Analysis_Checked.xlsx")
        assert result.retailer == "M&S"

    def test_sainsburys_without_apostrophe(self):
        """'Sainsburys' without apostrophe should resolve to "Sainsbury's"."""
        result = parse_filename("Sainsburys_Pimlico_Shelf_Analysis (1).xlsx")
        assert result.retailer == "Sainsbury's"


# ═══════════════════════════════════════════════════════════════════════════
# Edge cases: City matching
# ═══════════════════════════════════════════════════════════════════════════

class TestCityEdgeCases:
    """Test that city matching handles tricky patterns correctly."""

    def test_covent_garden_two_words(self):
        """'Covent Garden' should be matched as a single two-word city."""
        result = parse_filename("Tesco_Covent_Garden_Shelf_Analysis - Checked.xlsx")
        assert result.city == "Covent Garden"

    def test_covent_garden_with_retailer_prefix(self):
        """'MS_Covent Garden' — city with space in original, underscore elsewhere."""
        result = parse_filename("MS_Covent Garden_Small_Shelf_Analysis_Checked.xlsx")
        assert result.city == "Covent Garden"

    def test_oval_short_city(self):
        """'Oval' is a very short city name — should still match exactly."""
        result = parse_filename("Tesco_Oval_LargeShelf_Analysis.xlsx")
        assert result.city == "Oval"

    def test_retailer_in_middle_of_filename(self):
        """'Shelf_Analysis_Aldi_Balham' — retailer is in the middle, not at start."""
        result = parse_filename("Shelf_Analysis_Aldi_Balham_Checked.xlsx")
        assert result.city == "Balham"


# ═══════════════════════════════════════════════════════════════════════════
# Edge cases: Format matching
# ═══════════════════════════════════════════════════════════════════════════

class TestFormatEdgeCases:
    """Test that format keyword extraction handles edge cases."""

    def test_large_from_largeshelf(self):
        """'LargeShelf' → should extract 'Large' via substring match."""
        result = parse_filename("Tesco_Oval_LargeShelf_Analysis.xlsx")
        assert result.store_format == "Large"

    def test_small_standalone(self):
        """'Small' as a standalone token should be extracted."""
        result = parse_filename("MS_Covent Garden_Small_Shelf_Analysis_Checked.xlsx")
        assert result.store_format == "Small"

    def test_express_is_not_format(self):
        """'Express' in 'Tesco Express' should NOT be treated as a format."""
        result = parse_filename("Tesco_Express_Strand_Analysis_Checked.xlsx")
        assert result.store_format is None

    def test_no_format_in_flat_file(self):
        """Files without format keywords should return None."""
        result = parse_filename("aldi_fulham_shelf_analysis.xlsx")
        assert result.store_format is None


# ═══════════════════════════════════════════════════════════════════════════
# Unit tests: _clean_filename helper
# ═══════════════════════════════════════════════════════════════════════════

class TestCleanFilename:
    """Test the filename cleaning/normalization helper."""

    def test_strips_xlsx_extension(self):
        result = _clean_filename("aldi_fulham_shelf_analysis.xlsx")
        assert ".xlsx" not in result

    def test_strips_xls_extension(self):
        result = _clean_filename("aldi_fulham.xls")
        assert ".xls" not in result

    def test_strips_copy_indicator(self):
        """Trailing ' (1)' should be removed."""
        result = _clean_filename("Sainsburys_Pimlico_Shelf_Analysis (1).xlsx")
        assert "(1)" not in result

    def test_strips_copy_indicator_v2(self):
        """Trailing ' (2)' should also be removed."""
        result = _clean_filename("SomeFile (2).xlsx")
        assert "(2)" not in result

    def test_normalizes_dash_separator(self):
        """' - ' should become a space, not stay as dash."""
        result = _clean_filename("Tesco_Covent_Garden_Shelf_Analysis - Checked.xlsx")
        assert " - " not in result

    def test_strips_known_suffixes(self):
        result = _clean_filename("aldi_fulham_shelf_analysis.xlsx")
        assert "shelf" not in result
        assert "analysis" not in result

    def test_strips_checked_suffix(self):
        result = _clean_filename("Shelf_Analysis_Aldi_Balham_Checked.xlsx")
        assert "checked" not in result

    def test_strips_corrected_suffix(self):
        result = _clean_filename("M&S Fulham_Juice_Analysis_Corrected.xlsx")
        assert "corrected" not in result

    def test_strips_v2_suffix(self):
        result = _clean_filename("Waitrose_Balham_Large_Shelf_Analysis_v2.xlsx")
        assert "_v2" not in result

    def test_replaces_underscores_with_spaces(self):
        result = _clean_filename("aldi_fulham_shelf_analysis.xlsx")
        assert "_" not in result

    def test_result_is_lowercase(self):
        result = _clean_filename("Lidl_Fulham_Juice_Analysis.xlsx")
        assert result == result.lower()

    def test_no_double_spaces(self):
        result = _clean_filename("MS_Covent Garden_Small_Shelf_Analysis_Checked.xlsx")
        assert "  " not in result


# ═══════════════════════════════════════════════════════════════════════════
# Unit tests: _match_retailer helper
# ═══════════════════════════════════════════════════════════════════════════

class TestMatchRetailer:
    """Test the retailer matching helper directly."""

    def test_exact_match_aldi(self):
        canonical, remaining, score = _match_retailer("aldi fulham")
        assert canonical == "Aldi"
        assert score == 100

    def test_exact_match_tesco_express(self):
        """Longest match: 'tesco express' should win over 'tesco'."""
        canonical, remaining, score = _match_retailer("tesco express strand")
        assert canonical == "Tesco Express"
        assert "strand" in remaining
        assert score == 100

    def test_ms_with_ampersand(self):
        canonical, remaining, score = _match_retailer("m&s fulham")
        assert canonical == "M&S"
        assert score == 100

    def test_ms_without_ampersand(self):
        canonical, remaining, score = _match_retailer("ms covent garden small")
        assert canonical == "M&S"
        assert score == 100

    def test_retailer_removed_from_remaining(self):
        """The matched retailer should be stripped from the remaining string."""
        canonical, remaining, score = _match_retailer("lidl fulham")
        assert "lidl" not in remaining
        assert "fulham" in remaining

    def test_unknown_retailer_returns_none(self):
        canonical, remaining, score = _match_retailer("unknown store london")
        assert canonical is None
        assert score == 0


# ═══════════════════════════════════════════════════════════════════════════
# Unit tests: _match_city helper
# ═══════════════════════════════════════════════════════════════════════════

class TestMatchCity:
    """Test the city matching helper directly."""

    def test_exact_match_fulham(self):
        canonical, score = _match_city("fulham")
        assert canonical == "Fulham"
        assert score == 100

    def test_exact_match_covent_garden(self):
        canonical, score = _match_city("covent garden small")
        assert canonical == "Covent Garden"
        assert score == 100

    def test_exact_match_oval(self):
        canonical, score = _match_city("oval largeshelf")
        assert canonical == "Oval"
        assert score == 100

    def test_unknown_city(self):
        canonical, score = _match_city("randomtown largeshelf")
        assert canonical is None
        assert score == 0


# ═══════════════════════════════════════════════════════════════════════════
# Unit tests: _match_format helper
# ═══════════════════════════════════════════════════════════════════════════

class TestMatchFormat:
    """Test the format keyword matching helper."""

    def test_small(self):
        assert _match_format("covent garden small") == "Small"

    def test_large(self):
        assert _match_format("balham large") == "Large"

    def test_large_substring_in_largeshelf(self):
        """'large' should be found inside 'largeshelf' via substring match."""
        assert _match_format("oval largeshelf") == "Large"

    def test_no_format(self):
        assert _match_format("fulham") is None

    def test_medium(self):
        assert _match_format("some store medium") == "Medium"


# ═══════════════════════════════════════════════════════════════════════════
# Unit tests: _compute_confidence helper
# ═══════════════════════════════════════════════════════════════════════════

class TestComputeConfidence:
    """Test the confidence scoring logic."""

    def test_both_exact(self):
        assert _compute_confidence(100, 100) == 100

    def test_exact_retailer_fuzzy_city(self):
        assert _compute_confidence(100, 85) == 90

    def test_fuzzy_retailer_exact_city(self):
        assert _compute_confidence(85, 100) == 85

    def test_both_fuzzy(self):
        assert _compute_confidence(85, 90) == 85

    def test_missing_retailer(self):
        assert _compute_confidence(0, 100) == 50

    def test_missing_city(self):
        assert _compute_confidence(100, 0) == 50

    def test_both_missing(self):
        assert _compute_confidence(0, 0) == 50


# ═══════════════════════════════════════════════════════════════════════════
# Unknown / fabricated filenames
# ═══════════════════════════════════════════════════════════════════════════

class TestUnknownFilenames:
    """Fabricated filenames with no known retailer or city."""

    def test_completely_unknown(self):
        result = parse_filename("random_data_file.xlsx")
        assert result.retailer is None
        assert result.city is None
        assert result.confidence <= 50

    def test_only_retailer_known(self):
        """A filename with a known retailer but unknown city."""
        result = parse_filename("Aldi_UnknownTown_Analysis.xlsx")
        assert result.retailer == "Aldi"
        assert result.city is None
        assert result.confidence == 50

    def test_return_type(self):
        result = parse_filename("anything.xlsx")
        assert isinstance(result, FilenameParseResult)
        assert isinstance(result.confidence, int)
        assert isinstance(result.raw_filename, str)

    def test_full_path_extracts_filename(self):
        """Passing a full path should still work — only the filename is parsed."""
        result = parse_filename("C:/Users/data/uploads/aldi_fulham_shelf_analysis.xlsx")
        assert result.retailer == "Aldi"
        assert result.city == "Fulham"
