"""
Tests for processing/normalizer.py

Covers: lookup-table normalization for all categorical columns, cross-column
HPP → Processing Method rule, LLM-only column flagging, blank/NaN handling,
and the changes log.
"""

import pandas as pd
import pytest

from processing.normalizer import (
    FlaggedItem,
    NormalizationResult,
    normalize,
)


# ---------------------------------------------------------------------------
# Helper to build a minimal DataFrame for testing
# ---------------------------------------------------------------------------

def _make_df(overrides: dict | None = None, rows: int = 1) -> pd.DataFrame:
    """Build a single-row DataFrame with sensible defaults, optionally overridden."""
    base = {
        "Brand": ["TestBrand"] * rows,
        "Product Name": [None] * rows,
        "Flavor": ["Orange"] * rows,
        "Product Type": [None] * rows,
        "Need State": [None] * rows,
        "Branded/Private Label": [None] * rows,
        "Processing Method": [None] * rows,
        "HPP Treatment": [None] * rows,
        "Packaging Type": [None] * rows,
        "Shelf Level": [None] * rows,
        "Stock Status": [None] * rows,
        "Shelf Location": [None] * rows,
        "Juice Extraction Method": [None] * rows,
        "Claims": [None] * rows,
        "Notes": [None] * rows,
    }
    if overrides:
        for key, value in overrides.items():
            if isinstance(value, list):
                base[key] = value
            else:
                base[key] = [value] * rows
    return pd.DataFrame(base)


# ═══════════════════════════════════════════════════════════════════════════
# Product Type normalization
# ═══════════════════════════════════════════════════════════════════════════

class TestProductTypeNormalization:
    def test_known_value_normalizes(self):
        df = _make_df({"Product Type": "pure juices"})
        result = normalize(df)
        assert result.dataframe.at[0, "Product Type"] == "Pure Juices"

    def test_case_insensitive(self):
        df = _make_df({"Product Type": "SMOOTHIES"})
        result = normalize(df)
        assert result.dataframe.at[0, "Product Type"] == "Smoothies"

    def test_whitespace_stripped(self):
        df = _make_df({"Product Type": "  Shots  "})
        result = normalize(df)
        assert result.dataframe.at[0, "Product Type"] == "Shots"

    def test_unknown_value_flagged(self):
        df = _make_df({"Product Type": "Health Juice"})
        result = normalize(df)
        assert len(result.flagged_items) >= 1
        flagged_cols = [f.column for f in result.flagged_items]
        assert "Product Type" in flagged_cols
        # Check that reason is populated
        product_flagged = [f for f in result.flagged_items if f.column == "Product Type"]
        assert len(product_flagged) > 0
        assert product_flagged[0].reason == "'Health Juice' not in allowed values for Product Type"

    def test_blank_not_flagged(self):
        df = _make_df({"Product Type": None})
        result = normalize(df)
        product_flagged = [f for f in result.flagged_items if f.column == "Product Type"]
        assert len(product_flagged) == 0

    def test_empty_string_not_flagged(self):
        df = _make_df({"Product Type": "   "})
        result = normalize(df)
        product_flagged = [f for f in result.flagged_items if f.column == "Product Type"]
        assert len(product_flagged) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Need State
# ═══════════════════════════════════════════════════════════════════════════

class TestNeedStateNormalization:
    def test_indulgent_maps_to_indulgence(self):
        df = _make_df({"Need State": "Indulgent"})
        result = normalize(df)
        assert result.dataframe.at[0, "Need State"] == "Indulgence"

    def test_functional(self):
        df = _make_df({"Need State": "functional"})
        result = normalize(df)
        assert result.dataframe.at[0, "Need State"] == "Functional"


# ═══════════════════════════════════════════════════════════════════════════
# Branded / Private Label
# ═══════════════════════════════════════════════════════════════════════════

class TestBrandedPrivateLabelNormalization:
    def test_branded(self):
        df = _make_df({"Branded/Private Label": "branded"})
        result = normalize(df)
        assert result.dataframe.at[0, "Branded/Private Label"] == "Branded"

    def test_typo_pirvate_lable(self):
        df = _make_df({"Branded/Private Label": "Pirvate lable"})
        result = normalize(df)
        assert result.dataframe.at[0, "Branded/Private Label"] == "Private Label"


# ═══════════════════════════════════════════════════════════════════════════
# Processing Method
# ═══════════════════════════════════════════════════════════════════════════

class TestProcessingMethodNormalization:
    def test_pasteurised_british_spelling(self):
        df = _make_df({"Processing Method": "pasteurised"})
        result = normalize(df)
        assert result.dataframe.at[0, "Processing Method"] == "Pasteurized"

    def test_flash_pasteurised(self):
        df = _make_df({"Processing Method": "Flash pasteurised"})
        result = normalize(df)
        assert result.dataframe.at[0, "Processing Method"] == "Pasteurized"

    def test_cold_pressed_hyphenated_maps_to_blank(self):
        """Cold-pressed maps to blank — it informs Juice Extraction Method instead."""
        df = _make_df({"Processing Method": "Cold-pressed"})
        result = normalize(df)
        assert pd.isna(result.dataframe.at[0, "Processing Method"])

    def test_freshly_squeezed_maps_to_blank(self):
        """Freshly Squeezed maps to blank — it informs Juice Extraction Method."""
        df = _make_df({"Processing Method": "Freshly Squeezed"})
        result = normalize(df)
        assert pd.isna(result.dataframe.at[0, "Processing Method"])

    def test_unpasteurised_maps_to_blank(self):
        """Unpasteurised maps to blank — removed as Processing Method value."""
        df = _make_df({"Processing Method": "Unpasteurised"})
        result = normalize(df)
        assert pd.isna(result.dataframe.at[0, "Processing Method"])

    def test_unknown_maps_to_blank(self):
        df = _make_df({"Processing Method": "Unknown"})
        result = normalize(df)
        assert pd.isna(result.dataframe.at[0, "Processing Method"])

    def test_unkown_typo_maps_to_blank(self):
        """'Unkown' (common typo) should map to blank, not be flagged."""
        df = _make_df({"Processing Method": "Unkown"})
        result = normalize(df)
        assert pd.isna(result.dataframe.at[0, "Processing Method"])
        proc_flagged = [f for f in result.flagged_items if f.column == "Processing Method"]
        assert len(proc_flagged) == 0


# ═══════════════════════════════════════════════════════════════════════════
# HPP Treatment
# ═══════════════════════════════════════════════════════════════════════════

class TestHPPTreatmentNormalization:
    def test_yes(self):
        df = _make_df({"HPP Treatment": "yes"})
        result = normalize(df)
        assert result.dataframe.at[0, "HPP Treatment"] == "Yes"

    def test_pasteurized_maps_to_no(self):
        df = _make_df({"HPP Treatment": "Pasteurized"})
        result = normalize(df)
        assert result.dataframe.at[0, "HPP Treatment"] == "No"

    def test_cold_pressed_assumed_maps_to_blank(self):
        df = _make_df({"HPP Treatment": "Cold pressed ? Assumed"})
        result = normalize(df)
        assert pd.isna(result.dataframe.at[0, "HPP Treatment"])


# ═══════════════════════════════════════════════════════════════════════════
# Shelf Level
# ═══════════════════════════════════════════════════════════════════════════

class TestShelfLevelNormalization:
    def test_number_to_ordinal(self):
        df = _make_df({"Shelf Level": "1"})
        result = normalize(df)
        assert result.dataframe.at[0, "Shelf Level"] == "1st"

    def test_top_to_1st(self):
        df = _make_df({"Shelf Level": "Top"})
        result = normalize(df)
        assert result.dataframe.at[0, "Shelf Level"] == "1st"

    def test_bottom_to_5th(self):
        df = _make_df({"Shelf Level": "bottom"})
        result = normalize(df)
        assert result.dataframe.at[0, "Shelf Level"] == "5th"

    def test_unknown_maps_to_blank(self):
        df = _make_df({"Shelf Level": "Unkown"})
        result = normalize(df)
        assert pd.isna(result.dataframe.at[0, "Shelf Level"])


# ═══════════════════════════════════════════════════════════════════════════
# Shelf Location — deterministic only for exact matches
# ═══════════════════════════════════════════════════════════════════════════

class TestShelfLocationNormalization:
    def test_exact_match(self):
        df = _make_df({"Shelf Location": "Chilled Section"})
        result = normalize(df)
        assert result.dataframe.at[0, "Shelf Location"] == "Chilled Section"

    def test_non_exact_match_flagged(self):
        df = _make_df({"Shelf Location": "Front of store chiller"})
        result = normalize(df)
        loc_flagged = [f for f in result.flagged_items if f.column == "Shelf Location"]
        assert len(loc_flagged) == 1
        assert loc_flagged[0].original_value == "Front of store chiller"
        assert loc_flagged[0].reason == "'Front of store chiller' not in allowed values for Shelf Location"


# ═══════════════════════════════════════════════════════════════════════════
# Cross-column rule: HPP Treatment → Processing Method
# ═══════════════════════════════════════════════════════════════════════════

class TestCrossColumnRule:
    def test_hpp_yes_blank_processing_sets_hpp(self):
        df = _make_df({
            "HPP Treatment": "Yes",
            "Processing Method": None,
        })
        result = normalize(df)
        assert result.dataframe.at[0, "Processing Method"] == "HPP"

    def test_hpp_yes_existing_processing_not_overwritten(self):
        """When HPP Treatment is Yes but Processing Method already has a valid
        value (Pasteurized), the cross-column rule should not overwrite it."""
        df = _make_df({
            "HPP Treatment": "Yes",
            "Processing Method": "Pasteurized",
        })
        result = normalize(df)
        assert result.dataframe.at[0, "Processing Method"] == "Pasteurized"

    def test_hpp_yes_cold_pressed_raw_becomes_hpp(self):
        """Raw 'Cold Pressed' maps to blank, then HPP Treatment=Yes fills it."""
        df = _make_df({
            "HPP Treatment": "Yes",
            "Processing Method": "Cold Pressed",
        })
        result = normalize(df)
        # "Cold Pressed" → blank in normalization, then cross-column rule sets "HPP"
        assert result.dataframe.at[0, "Processing Method"] == "HPP"

    def test_hpp_no_blank_processing_stays_blank(self):
        df = _make_df({
            "HPP Treatment": "No",
            "Processing Method": None,
        })
        result = normalize(df)
        assert pd.isna(result.dataframe.at[0, "Processing Method"])


# ═══════════════════════════════════════════════════════════════════════════
# Juice Extraction Method — deterministic inference
# ═══════════════════════════════════════════════════════════════════════════

class TestJuiceExtractionMethodInference:
    def test_hpp_treatment_yes_infers_cold_pressed(self):
        """Rule 1: HPP Treatment == 'Yes' → Cold Pressed."""
        df = _make_df({"HPP Treatment": "Yes"})
        result = normalize(df)
        assert result.dataframe.at[0, "Juice Extraction Method"] == "Cold Pressed"

    def test_processing_method_hpp_infers_cold_pressed(self):
        """Rule 2: Processing Method == 'HPP' → Cold Pressed."""
        df = _make_df({"Processing Method": "HPP"})
        result = normalize(df)
        assert result.dataframe.at[0, "Juice Extraction Method"] == "Cold Pressed"

    def test_claims_from_concentrate(self):
        """Rule 4: Claims contain 'from concentrate' → From Concentrate."""
        df = _make_df({"Claims": "Made from concentrate, 100% juice"})
        result = normalize(df)
        assert result.dataframe.at[0, "Juice Extraction Method"] == "From Concentrate"

    def test_claims_cold_pressed(self):
        """Rule 5: Claims contain 'cold pressed' → Cold Pressed."""
        df = _make_df({"Claims": "Cold pressed, organic"})
        result = normalize(df)
        assert result.dataframe.at[0, "Juice Extraction Method"] == "Cold Pressed"

    def test_claims_cold_pressed_hyphenated(self):
        """Rule 5: Claims contain 'cold-pressed' → Cold Pressed."""
        df = _make_df({"Claims": "cold-pressed juice"})
        result = normalize(df)
        assert result.dataframe.at[0, "Juice Extraction Method"] == "Cold Pressed"

    def test_notes_squeezed(self):
        """Rule 6: Notes contain 'squeezed' → Squeezed."""
        df = _make_df({"Notes": "freshly squeezed daily"})
        result = normalize(df)
        assert result.dataframe.at[0, "Juice Extraction Method"] == "Squeezed"

    def test_no_match_blank_flagged_for_llm(self):
        """Rule 7: No deterministic match → flagged for LLM."""
        df = _make_df({
            "Juice Extraction Method": None,
            "HPP Treatment": "No",
            "Processing Method": "Pasteurized",
            "Claims": "100% organic",
        })
        result = normalize(df)
        jem_flagged = [
            f for f in result.flagged_items if f.column == "Juice Extraction Method"
        ]
        assert len(jem_flagged) == 1
        assert jem_flagged[0].reason == "Could not determine Juice Extraction Method from available data"

    def test_valid_value_not_overwritten(self):
        """A value already in VALID_VALUES should not be changed."""
        df = _make_df({"Juice Extraction Method": "Squeezed"})
        result = normalize(df)
        assert result.dataframe.at[0, "Juice Extraction Method"] == "Squeezed"
        jem_flagged = [
            f for f in result.flagged_items if f.column == "Juice Extraction Method"
        ]
        assert len(jem_flagged) == 0

    def test_non_valid_value_flagged(self):
        """A non-blank, non-valid value should be flagged."""
        df = _make_df({"Juice Extraction Method": "hand squeezed"})
        result = normalize(df)
        jem_flagged = [
            f for f in result.flagged_items if f.column == "Juice Extraction Method"
        ]
        assert len(jem_flagged) == 1
        assert jem_flagged[0].reason == "'hand squeezed' not in allowed values for Juice Extraction Method"

    def test_rule_priority_hpp_over_claims(self):
        """Rule 1 (HPP Treatment=Yes) takes priority over Rule 4 (from concentrate in Claims)."""
        df = _make_df({
            "HPP Treatment": "Yes",
            "Claims": "from concentrate",
        })
        result = normalize(df)
        assert result.dataframe.at[0, "Juice Extraction Method"] == "Cold Pressed"

    def test_inference_logged_in_changes(self):
        """Deterministic inference should appear in the changes log."""
        df = _make_df({"HPP Treatment": "Yes"})
        result = normalize(df)
        jem_changes = [c for c in result.changes_log if c["column"] == "Juice Extraction Method"]
        assert len(jem_changes) >= 1
        assert jem_changes[0]["normalized"] == "Cold Pressed"
        assert "deterministic" in jem_changes[0]["method"]


# ═══════════════════════════════════════════════════════════════════════════
# Flavor flagging — Product Name present but no Flavor
# ═══════════════════════════════════════════════════════════════════════════

class TestFlavorFlagging:
    def test_product_name_no_flavor_flagged(self):
        """Row with Product Name but no Flavor should be flagged."""
        df = _make_df({
            "Product Name": "Innocent Smoothie Orange & Mango 750ml",
            "Flavor": None,
        })
        result = normalize(df)
        flavor_flagged = [f for f in result.flagged_items if f.column == "Flavor"]
        assert len(flavor_flagged) == 1
        assert flavor_flagged[0].reason == "Flavor is empty — extract from Product Name 'Innocent Smoothie Orange & Mango 750ml'"

    def test_product_name_with_flavor_not_flagged(self):
        """Row with both Product Name and Flavor should not be flagged."""
        df = _make_df({
            "Product Name": "Innocent Smoothie Orange & Mango 750ml",
            "Flavor": "Orange & Mango",
        })
        result = normalize(df)
        flavor_flagged = [f for f in result.flagged_items if f.column == "Flavor"]
        assert len(flavor_flagged) == 0

    def test_no_product_name_not_flagged(self):
        """Row with no Product Name should not be flagged for Flavor."""
        df = _make_df({
            "Product Name": None,
            "Flavor": None,
        })
        result = normalize(df)
        flavor_flagged = [f for f in result.flagged_items if f.column == "Flavor"]
        assert len(flavor_flagged) == 0

    def test_flavor_context_includes_product_name(self):
        """Flagged Flavor item should include Product Name in context."""
        df = _make_df({
            "Product Name": "Tropicana Pure Premium Orange",
            "Flavor": None,
        })
        result = normalize(df)
        flavor_flagged = [f for f in result.flagged_items if f.column == "Flavor"]
        assert len(flavor_flagged) == 1
        assert flavor_flagged[0].context.get("Product Name") == "Tropicana Pure Premium Orange"
        assert flavor_flagged[0].reason == "Flavor is empty — extract from Product Name 'Tropicana Pure Premium Orange'"


# ═══════════════════════════════════════════════════════════════════════════
# Changes log
# ═══════════════════════════════════════════════════════════════════════════

class TestChangesLog:
    def test_change_logged_for_normalization(self):
        df = _make_df({"Product Type": "pure juices"})
        result = normalize(df)
        assert len(result.changes_log) >= 1
        log_entry = result.changes_log[0]
        assert log_entry["original"] == "pure juices"
        assert log_entry["normalized"] == "Pure Juices"
        assert log_entry["method"] == "deterministic"

    def test_no_change_logged_for_already_correct(self):
        df = _make_df({"Product Type": "Pure Juices"})
        result = normalize(df)
        product_changes = [c for c in result.changes_log if c["column"] == "Product Type"]
        assert len(product_changes) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Context in flagged items
# ═══════════════════════════════════════════════════════════════════════════

class TestFlaggedItemContext:
    def test_context_includes_brand_and_claims(self):
        df = _make_df({
            "Product Type": "Weird Category",
            "Brand": "Tropicana",
            "Claims": "100% organic",
        })
        result = normalize(df)
        flagged = [f for f in result.flagged_items if f.column == "Product Type"]
        assert len(flagged) == 1
        assert flagged[0].context.get("Brand") == "Tropicana"
        assert flagged[0].context.get("Claims") == "100% organic"

    def test_context_excludes_blank_values(self):
        df = _make_df({
            "Product Type": "Weird Category",
            "Brand": "Tropicana",
            "Claims": None,
        })
        result = normalize(df)
        flagged = [f for f in result.flagged_items if f.column == "Product Type"]
        assert "Claims" not in flagged[0].context


# ═══════════════════════════════════════════════════════════════════════════
# DataFrame column preservation
# ═══════════════════════════════════════════════════════════════════════════

class TestDataFramePreservation:
    def test_column_order_preserved(self):
        df = _make_df({"Product Type": "Shots"})
        original_columns = list(df.columns)
        result = normalize(df)
        assert list(result.dataframe.columns) == original_columns

    def test_original_dataframe_not_mutated(self):
        df = _make_df({"Product Type": "pure juices"})
        original_value = df.at[0, "Product Type"]
        _ = normalize(df)
        assert df.at[0, "Product Type"] == original_value
