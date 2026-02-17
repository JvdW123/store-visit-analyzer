"""
Tests for processing/llm_cleaner.py

Covers: prompt building, response parsing, VALID_VALUES validation,
no-API-key skip, empty flagged list, and mocked API calls.
"""

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from processing.llm_cleaner import (
    LLMCleaningResult,
    clean_with_llm,
    _build_prompt,
    _parse_llm_response,
    _validate_and_apply,
    _create_batches,
)
from processing.normalizer import FlaggedItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_flagged_item(
    row_index: int = 0,
    column: str = "Product Type",
    original_value: str = "Health Juice",
    reason: str = "Test reason",
    context: dict | None = None,
) -> FlaggedItem:
    return FlaggedItem(
        row_index=row_index,
        column=column,
        original_value=original_value,
        reason=reason,
        context=context or {"Brand": "Tropicana", "Claims": "100% organic"},
    )


def _make_df_for_llm() -> pd.DataFrame:
    return pd.DataFrame({
        "Product Type": ["Health Juice", "Weird Drink"],
        "Shelf Location": ["Front chiller", "Back aisle"],
        "Brand": ["Tropicana", "Innocent"],
        "Flavor": ["Orange", "Berry"],
        "Claims": ["100% organic", "No added sugar"],
        "Notes": [None, None],
    })


# ═══════════════════════════════════════════════════════════════════════════
# No API key → skip
# ═══════════════════════════════════════════════════════════════════════════

class TestNoApiKey:
    def test_skipped_when_no_key(self):
        df = _make_df_for_llm()
        flagged = [_make_flagged_item()]
        result = clean_with_llm(df, flagged, api_key=None)
        assert result.skipped is True
        assert len(result.resolved_items) == 0

    def test_dataframe_unchanged_when_skipped(self):
        df = _make_df_for_llm()
        original_value = df.at[0, "Product Type"]
        flagged = [_make_flagged_item()]
        result = clean_with_llm(df, flagged, api_key=None)
        assert result.dataframe.at[0, "Product Type"] == original_value


# ═══════════════════════════════════════════════════════════════════════════
# Empty flagged items → no API call
# ═══════════════════════════════════════════════════════════════════════════

class TestEmptyFlagged:
    def test_no_call_when_empty(self):
        df = _make_df_for_llm()
        result = clean_with_llm(df, [], api_key="sk-test")
        assert result.skipped is False
        assert len(result.resolved_items) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Prompt building
# ═══════════════════════════════════════════════════════════════════════════

class TestBuildPrompt:
    def test_prompt_contains_flagged_items(self):
        flagged = [_make_flagged_item()]
        prompt = _build_prompt(flagged)
        assert "Health Juice" in prompt
        assert "Product Type" in prompt

    def test_prompt_contains_context(self):
        flagged = [_make_flagged_item(
            context={"Brand": "Tropicana", "Claims": "100% organic"}
        )]
        prompt = _build_prompt(flagged)
        assert "Tropicana" in prompt
        assert "100% organic" in prompt

    def test_prompt_contains_valid_values(self):
        flagged = [_make_flagged_item()]
        prompt = _build_prompt(flagged)
        assert "Pure Juices" in prompt
        assert "Smoothies" in prompt
        assert "Chilled Section" in prompt
        # Processing Method now only has Pasteurized and HPP
        assert '"Pasteurized", "HPP"' in prompt
        # Flavor extraction instructions
        assert "Flavor" in prompt
        assert "extract the flavor" in prompt.lower()

    def test_prompt_has_json_structure(self):
        flagged = [_make_flagged_item()]
        prompt = _build_prompt(flagged)
        assert "row_index" in prompt
        assert "column" in prompt
        assert "original_value" in prompt


# ═══════════════════════════════════════════════════════════════════════════
# Response parsing
# ═══════════════════════════════════════════════════════════════════════════

class TestParseResponse:
    def test_clean_json(self):
        response = json.dumps([{
            "row_index": 0,
            "column": "Product Type",
            "original_value": "Health Juice",
            "normalized_value": "Other",
            "reasoning": "Not a standard juice type.",
        }])
        result = _parse_llm_response(response)
        assert result is not None
        assert len(result) == 1
        assert result[0]["normalized_value"] == "Other"

    def test_markdown_fenced_json(self):
        response = '```json\n[{"row_index": 0, "column": "Product Type", "original_value": "x", "normalized_value": "Other", "reasoning": "test"}]\n```'
        result = _parse_llm_response(response)
        assert result is not None
        assert len(result) == 1

    def test_trailing_comma_handled(self):
        response = '[{"row_index": 0, "column": "Product Type", "original_value": "x", "normalized_value": "Other", "reasoning": "test",}]'
        result = _parse_llm_response(response)
        assert result is not None
        assert len(result) == 1

    def test_no_json_returns_none(self):
        result = _parse_llm_response("Sorry, I cannot help with that.")
        assert result is None

    def test_empty_string_returns_none(self):
        result = _parse_llm_response("")
        assert result is None

    def test_text_around_json_array(self):
        response = 'Here are my results:\n[{"row_index": 0, "column": "Product Type", "original_value": "x", "normalized_value": "Other", "reasoning": "test"}]\nHope that helps!'
        result = _parse_llm_response(response)
        assert result is not None
        assert len(result) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Validation and apply
# ═══════════════════════════════════════════════════════════════════════════

class TestValidateAndApply:
    def test_valid_value_applied(self):
        df = _make_df_for_llm()
        decisions = [{
            "row_index": 0,
            "column": "Product Type",
            "original_value": "Health Juice",
            "normalized_value": "Other",
            "reasoning": "Doesn't fit standard categories.",
        }]
        resolved, rejected = _validate_and_apply(df, decisions)
        assert len(resolved) == 1
        assert len(rejected) == 0
        assert df.at[0, "Product Type"] == "Other"

    def test_blank_value_accepted(self):
        df = _make_df_for_llm()
        decisions = [{
            "row_index": 0,
            "column": "Product Type",
            "original_value": "Health Juice",
            "normalized_value": "",
            "reasoning": "Cannot determine.",
        }]
        resolved, rejected = _validate_and_apply(df, decisions)
        assert len(resolved) == 1
        assert pd.isna(df.at[0, "Product Type"])

    def test_invalid_value_rejected(self):
        df = _make_df_for_llm()
        decisions = [{
            "row_index": 0,
            "column": "Product Type",
            "original_value": "Health Juice",
            "normalized_value": "Juice Box",  # not in valid values
            "reasoning": "My guess.",
        }]
        resolved, rejected = _validate_and_apply(df, decisions)
        assert len(resolved) == 0
        assert len(rejected) == 1
        # Original value should remain unchanged
        assert df.at[0, "Product Type"] == "Health Juice"

    def test_invalid_row_index_rejected(self):
        df = _make_df_for_llm()
        decisions = [{
            "row_index": 999,
            "column": "Product Type",
            "original_value": "x",
            "normalized_value": "Other",
            "reasoning": "test",
        }]
        resolved, rejected = _validate_and_apply(df, decisions)
        assert len(rejected) == 1

    def test_invalid_column_rejected(self):
        df = _make_df_for_llm()
        decisions = [{
            "row_index": 0,
            "column": "Nonexistent Column",
            "original_value": "x",
            "normalized_value": "Other",
            "reasoning": "test",
        }]
        resolved, rejected = _validate_and_apply(df, decisions)
        assert len(rejected) == 1

    def test_column_without_valid_values_accepts_any(self):
        """Columns not in VALID_VALUES (like free-text) accept any non-empty value."""
        df = _make_df_for_llm()
        decisions = [{
            "row_index": 0,
            "column": "Brand",  # free text, not in VALID_VALUES
            "original_value": "Tropicana",
            "normalized_value": "Tropicana Fresh",
            "reasoning": "Full brand name.",
        }]
        resolved, rejected = _validate_and_apply(df, decisions)
        assert len(resolved) == 1
        assert df.at[0, "Brand"] == "Tropicana Fresh"


# ═══════════════════════════════════════════════════════════════════════════
# Batching
# ═══════════════════════════════════════════════════════════════════════════

class TestBatching:
    def test_single_batch_when_under_limit(self):
        items = [_make_flagged_item(row_index=i) for i in range(10)]
        batches = _create_batches(items, 200)
        assert len(batches) == 1
        assert len(batches[0]) == 10

    def test_multiple_batches_when_over_limit(self):
        items = [_make_flagged_item(row_index=i) for i in range(5)]
        batches = _create_batches(items, 2)
        assert len(batches) == 3  # 2, 2, 1
        assert len(batches[0]) == 2
        assert len(batches[2]) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Integration with mocked API
# ═══════════════════════════════════════════════════════════════════════════

class TestMockedAPICall:
    @patch("processing.llm_cleaner._call_sonnet_api")
    def test_valid_response_applied(self, mock_api):
        mock_response = json.dumps([{
            "row_index": 0,
            "column": "Product Type",
            "original_value": "Health Juice",
            "normalized_value": "Other",
            "reasoning": "Not a standard category.",
        }])
        mock_api.return_value = (mock_response, 0.005, 100, 50)

        df = _make_df_for_llm()
        flagged = [_make_flagged_item(row_index=0)]

        result = clean_with_llm(df, flagged, api_key="sk-test")

        assert result.skipped is False
        assert len(result.resolved_items) == 1
        assert result.dataframe.at[0, "Product Type"] == "Other"

    @patch("processing.llm_cleaner._call_sonnet_api")
    def test_partial_invalid_response(self, mock_api):
        mock_response = json.dumps([
            {
                "row_index": 0,
                "column": "Product Type",
                "original_value": "Health Juice",
                "normalized_value": "Other",
                "reasoning": "ok",
            },
            {
                "row_index": 1,
                "column": "Shelf Location",
                "original_value": "Front chiller",
                "normalized_value": "The Fridge",  # invalid
                "reasoning": "guess",
            },
        ])
        mock_api.return_value = (mock_response, 0.005, 100, 50)

        df = _make_df_for_llm()
        flagged = [
            _make_flagged_item(row_index=0),
            _make_flagged_item(row_index=1, column="Shelf Location",
                               original_value="Front chiller"),
        ]

        result = clean_with_llm(df, flagged, api_key="sk-test")

        assert len(result.resolved_items) == 1
        assert len(result.rejected_items) == 1
        assert result.dataframe.at[0, "Product Type"] == "Other"
        # Row 1 Shelf Location unchanged because "The Fridge" was rejected
        assert result.dataframe.at[1, "Shelf Location"] == "Back aisle"
