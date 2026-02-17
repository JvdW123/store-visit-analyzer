"""
LLM cleaner — resolves ambiguous data items using Claude Sonnet.

All flagged items from the normalizer are batched into a single API call
per file.  The LLM returns structured JSON with normalized values, which
are validated against VALID_VALUES before being applied to the DataFrame.

If no API key is provided, the LLM step is skipped entirely and flagged
items remain unresolved (highlighted in yellow in the output Excel).

Public API:
    clean_with_llm(dataframe, flagged_items, api_key) → LLMCleaningResult

See docs/RULES.md — LLM Call Specification for the prompt template.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field

import pandas as pd

from config.schema import VALID_VALUES
from processing.normalizer import FlaggedItem

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════

_MODEL_ID = "claude-sonnet-4-20250514"

# Maximum flagged items per API call.  Beyond this, batch into multiple calls.
_MAX_ITEMS_PER_BATCH = 200

_PROMPT_TEMPLATE = """You are a data cleaning assistant for supermarket shelf analysis data.

TASK: Resolve the following ambiguous data items. For each item, return the
normalized value from the allowed values list, or "" (blank) if you cannot
determine it with reasonable confidence. IMPORTANT: Never return "Unknown" —
if you are unsure, return blank.

MASTER SCHEMA VALID VALUES:
- Product Type: "Pure Juices", "Smoothies", "Shots", "Other"
- Need State: "Indulgence", "Functional"
- Branded/Private Label: "Branded", "Private Label"
- Processing Method: "Pasteurized", "HPP"
- HPP Treatment: "Yes", "No"
- Packaging Type: "PET Bottle", "Tetra Pak", "Can", "Carton", "Glass Bottle"
- Juice Extraction Method: "Squeezed", "Cold Pressed", "From Concentrate"
- Stock Status: "In Stock", "Out of Stock"
- Shelf Level: "1st", "2nd", "3rd", "4th", "5th", "6th"
- Shelf Location: "Chilled Section", "To-Go Section", "To-Go Section — Shots", "Meal Deal Section"
- Flavor: free text (extract from Product Name)

COLUMN-SPECIFIC INSTRUCTIONS:
- Processing Method: determine if the product is "Pasteurized" or "HPP" based
  on Claims, Notes, and Brand. If you cannot determine, return blank.
- Juice Extraction Method: consider the full row context — Brand, Product Name,
  Claims, Notes, Processing Method, HPP Treatment. Valid values: "Cold Pressed",
  "Squeezed", "From Concentrate".
- Flavor: extract the flavor or fruit combination from the Product Name. Focus
  on the fruit/ingredient descriptors. For example: "Innocent Smoothie Orange &
  Mango 750ml" → "Orange & Mango", "Tropicana Pure Premium Orange With Bits" →
  "Orange", "Naked Green Machine 750ml" → "Green Machine". If no clear flavor,
  return blank.

ITEMS TO RESOLVE:
{flagged_items_json}

Return a JSON array where each element has:
- "row_index": the row index from the input
- "column": the column name
- "original_value": the original value
- "normalized_value": your decision (valid value or "" for blank)
- "reasoning": brief explanation (1 sentence)"""


# ═══════════════════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class LLMCleaningResult:
    """Output of the clean_with_llm() function."""

    dataframe: pd.DataFrame = field(default_factory=pd.DataFrame)
    resolved_items: list[dict] = field(default_factory=list)
    rejected_items: list[dict] = field(default_factory=list)
    skipped: bool = False
    api_cost_estimate: float = 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def clean_with_llm(
    dataframe: pd.DataFrame,
    flagged_items: list[FlaggedItem],
    api_key: str | None = None,
) -> LLMCleaningResult:
    """
    Resolve flagged items using Claude Sonnet.

    Batches all flagged items into one API call (or multiple if > 200 items).
    Parses the JSON response, validates returned values against VALID_VALUES,
    and applies valid decisions to the DataFrame.

    Args:
        dataframe: The partially-cleaned DataFrame.
        flagged_items: List of FlaggedItems from the normalizer.
        api_key: Anthropic API key. If None, LLM step is skipped.

    Returns:
        LLMCleaningResult with updated DataFrame and resolution details.
    """
    result_df = dataframe.copy()

    # No API key → skip entirely
    if not api_key:
        logger.info("No API key provided — skipping LLM cleaning step")
        return LLMCleaningResult(dataframe=result_df, skipped=True)

    # No flagged items → nothing to do
    if not flagged_items:
        logger.info("No flagged items to resolve — skipping LLM call")
        return LLMCleaningResult(dataframe=result_df, skipped=False)

    # Batch items if there are too many
    batches = _create_batches(flagged_items, _MAX_ITEMS_PER_BATCH)

    all_resolved: list[dict] = []
    all_rejected: list[dict] = []
    total_cost: float = 0.0

    for batch_idx, batch in enumerate(batches):
        logger.info(
            f"Processing LLM batch {batch_idx + 1}/{len(batches)} "
            f"({len(batch)} items)"
        )

        prompt = _build_prompt(batch)

        try:
            response_text, cost = _call_sonnet_api(prompt, api_key)
        except Exception as exc:
            logger.error(f"LLM API call failed: {exc}")
            # Try once more after a short delay
            try:
                time.sleep(2)
                response_text, cost = _call_sonnet_api(prompt, api_key)
            except Exception as retry_exc:
                logger.error(f"LLM API retry also failed: {retry_exc}")
                continue

        total_cost += cost

        llm_decisions = _parse_llm_response(response_text)
        if llm_decisions is None:
            logger.error("Failed to parse LLM response — skipping batch")
            continue

        resolved, rejected = _validate_and_apply(result_df, llm_decisions)
        all_resolved.extend(resolved)
        all_rejected.extend(rejected)

    logger.info(
        f"LLM cleaning complete: {len(all_resolved)} resolved, "
        f"{len(all_rejected)} rejected, estimated cost: ${total_cost:.4f}"
    )

    return LLMCleaningResult(
        dataframe=result_df,
        resolved_items=all_resolved,
        rejected_items=all_rejected,
        skipped=False,
        api_cost_estimate=total_cost,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════

def _build_prompt(flagged_items: list[FlaggedItem]) -> str:
    """
    Assemble the LLM prompt from the template and flagged items.

    Each flagged item is serialized as a JSON object with full row context
    (Brand, Flavor, Claims, Processing Method, HPP Treatment, Notes) so the
    LLM can make informed decisions.

    Args:
        flagged_items: List of FlaggedItems to include.

    Returns:
        Complete prompt string ready for the API call.
    """
    items_for_json: list[dict] = []

    for item in flagged_items:
        entry = {
            "row_index": item.row_index,
            "column": item.column,
            "original_value": item.original_value,
            "context": item.context,
        }
        items_for_json.append(entry)

    flagged_json = json.dumps(items_for_json, indent=2, ensure_ascii=False)
    return _PROMPT_TEMPLATE.format(flagged_items_json=flagged_json)


def _call_sonnet_api(prompt: str, api_key: str) -> tuple[str, float]:
    """
    Call the Claude Sonnet API with the given prompt.

    Uses the anthropic Python SDK.  Returns the response text and an
    estimated cost based on token usage.

    Args:
        prompt: The complete prompt string.
        api_key: Anthropic API key.

    Returns:
        (response_text, estimated_cost_usd)

    Raises:
        Exception: On API errors (network, auth, rate limit, etc.).
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model=_MODEL_ID,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = message.content[0].text

    # Estimate cost from token usage (Sonnet pricing: ~$3/M input, ~$15/M output)
    input_tokens = message.usage.input_tokens
    output_tokens = message.usage.output_tokens
    estimated_cost = (input_tokens * 3.0 / 1_000_000) + (output_tokens * 15.0 / 1_000_000)

    logger.info(
        f"Sonnet API call: {input_tokens} input tokens, "
        f"{output_tokens} output tokens, est. cost ${estimated_cost:.4f}"
    )

    return response_text, estimated_cost


def _parse_llm_response(response_text: str) -> list[dict] | None:
    """
    Parse the JSON array from the LLM's response text.

    Handles cases where the LLM wraps the JSON in markdown code fences
    (```json ... ```) or includes other text before/after the array.

    Args:
        response_text: Raw text from the LLM response.

    Returns:
        List of decision dicts, or None if parsing fails.
    """
    if not response_text:
        return None

    # Try to extract JSON from markdown code fences
    fenced_match = re.search(
        r"```(?:json)?\s*\n?(.*?)```",
        response_text,
        re.DOTALL,
    )
    json_text = fenced_match.group(1).strip() if fenced_match else response_text.strip()

    # Try to find the JSON array boundaries
    start_idx = json_text.find("[")
    end_idx = json_text.rfind("]")

    if start_idx == -1 or end_idx == -1:
        logger.error("No JSON array found in LLM response")
        return None

    json_text = json_text[start_idx : end_idx + 1]

    # Fix common JSON issues: trailing commas before ] or }
    json_text = re.sub(r",\s*([}\]])", r"\1", json_text)

    try:
        decisions = json.loads(json_text)
    except json.JSONDecodeError as exc:
        logger.error(f"Failed to parse LLM JSON response: {exc}")
        return None

    if not isinstance(decisions, list):
        logger.error("LLM response is not a JSON array")
        return None

    return decisions


def _validate_and_apply(
    dataframe: pd.DataFrame,
    llm_decisions: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Validate each LLM decision against VALID_VALUES and apply valid ones.

    A decision is valid if:
      - The normalized_value is "" (blank) — always accepted.
      - The normalized_value is in VALID_VALUES for that column.
      - The row_index exists in the DataFrame.
      - The column exists in the DataFrame.

    Invalid decisions are rejected and logged.

    Args:
        dataframe: DataFrame to modify IN PLACE with valid decisions.
        llm_decisions: List of decision dicts from the LLM.

    Returns:
        (resolved_items, rejected_items) — both are lists of dicts.
    """
    resolved: list[dict] = []
    rejected: list[dict] = []

    for decision in llm_decisions:
        row_index = decision.get("row_index")
        column = decision.get("column")
        normalized_value = decision.get("normalized_value", "")
        reasoning = decision.get("reasoning", "")

        # Validate row index
        if row_index is None or row_index not in dataframe.index:
            logger.warning(
                f"LLM returned invalid row_index {row_index} — skipping"
            )
            rejected.append({**decision, "rejection_reason": "invalid row_index"})
            continue

        # Validate column exists
        if column is None or column not in dataframe.columns:
            logger.warning(
                f"LLM returned invalid column '{column}' — skipping"
            )
            rejected.append({**decision, "rejection_reason": "invalid column"})
            continue

        # Blank is always accepted
        if normalized_value == "":
            dataframe.at[row_index, column] = None
            resolved.append(decision)
            logger.debug(
                f"Applied LLM decision: [{column}] row {row_index} → blank "
                f"(reason: {reasoning})"
            )
            continue

        # Validate against VALID_VALUES
        valid_set = VALID_VALUES.get(column)
        if valid_set is not None and normalized_value not in valid_set:
            logger.warning(
                f"LLM returned invalid value '{normalized_value}' for "
                f"column '{column}' (not in valid set) — rejecting"
            )
            rejected.append({
                **decision,
                "rejection_reason": f"'{normalized_value}' not in valid values",
            })
            continue

        # Apply the valid decision
        dataframe.at[row_index, column] = normalized_value
        resolved.append(decision)
        logger.debug(
            f"Applied LLM decision: [{column}] row {row_index} "
            f"→ '{normalized_value}' (reason: {reasoning})"
        )

    return resolved, rejected


def _create_batches(
    items: list[FlaggedItem],
    max_per_batch: int,
) -> list[list[FlaggedItem]]:
    """
    Split flagged items into batches of at most *max_per_batch* each.

    Args:
        items: Full list of flagged items.
        max_per_batch: Maximum items per batch.

    Returns:
        List of batches (each batch is a list of FlaggedItems).
    """
    if len(items) <= max_per_batch:
        return [items]

    batches: list[list[FlaggedItem]] = []
    for start in range(0, len(items), max_per_batch):
        batches.append(items[start : start + max_per_batch])

    return batches
