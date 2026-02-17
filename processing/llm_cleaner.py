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

from config.normalization_rules import FLAVOR_MAP
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
- Juice Extraction Method: consider the full row context — Brand, Sub-brand,
  Product Name, Claims, Notes, Processing Method, HPP Treatment. The Sub-brand
  may contain processing terminology (e.g. "Freshly Squeezed", "Cold Pressed").
  Claims mentioning "not from concentrate" indicate "Squeezed" (NOT "From
  Concentrate"). Valid values: "Cold Pressed", "Squeezed", "From Concentrate".
- Flavor: Extract ALL flavor/fruit/ingredient components from the Product Name.
  Include every flavor-relevant ingredient mentioned, joined with " & ".
  Always use " & " as the separator (not "/", "and", or comma-only).

  INCLUDE as flavors: fruits, vegetables, herbs, spices, and culinary
  ingredients that contribute to taste (e.g. Orange, Mango, Ginger,
  Turmeric, Mint, Beetroot, Carrot, Lemon, Lime, Matcha).

  EXCLUDE from flavors: functional/supplement ingredients that do NOT
  describe a taste (e.g. Probiotics, Lion's Mane, Collagen, Protein,
  Vitamins, Ashwagandha, CBD, Spirulina). These are health additives,
  not flavors — omit them from the Flavor field entirely.

  EDGE CASE — Ginger, Turmeric, Matcha: these ARE flavors because they
  have a distinct taste. Include them. The test is: "does this ingredient
  define what the drink tastes like?" If yes, it is a flavor.

  Strip taste-modifier adjectives that don't identify a distinct variety:
  "Spicy Ginger" → "Ginger", "Sweet Mango" → "Mango".
  BUT keep varietal/type modifiers: "Blood Orange" → "Blood Orange",
  "Pink Grapefruit" → "Pink Grapefruit".

  If the product name itself IS a flavor description (e.g. Berry Energise,
  Green Machine), use it as the Flavor.
  Only return blank if there is truly no flavor information at all.

  Examples:
    Smooth Orange 900ml → Orange
    Orange Juice 1L → Orange
    Berry Energise → Berry Energise
    Tropical Blast 1.35L → Tropical Blast
    7x Ginger Shots → Ginger
    Naked Green Machine 750ml → Green Machine
    Tropicana Pure Premium Orange With Bits → Orange
    Apple, Mango & Passion Fruit Smoothie → Apple, Mango & Passion Fruit
    Strawberry Banana Smoothie → Strawberry & Banana
    Ginger & Turmeric Shot → Ginger & Turmeric
    Blueberry & Lion's Mane Kombucha → Blueberry
    Probiotic Mango Juice → Mango
    Spicy Ginger & Lemon → Ginger & Lemon

- Product Name cleanup: If the Product Name contains volume/size info (e.g. 900 ml, 
  1.35L, 750ml), multipack counts (e.g. 7x), or pack size numbers, note this in 
  your reasoning. These should be in the Packaging Size column, not in the Product Name.

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
    input_tokens: int = 0
    output_tokens: int = 0


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
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    for batch_idx, batch in enumerate(batches):
        logger.info(
            f"Processing LLM batch {batch_idx + 1}/{len(batches)} "
            f"({len(batch)} items)"
        )

        prompt = _build_prompt(batch)

        try:
            response_text, cost, input_tokens, output_tokens = _call_sonnet_api(prompt, api_key)
        except Exception as exc:
            logger.error(f"LLM API call failed: {exc}")
            # Try once more after a short delay
            try:
                time.sleep(2)
                response_text, cost, input_tokens, output_tokens = _call_sonnet_api(prompt, api_key)
            except Exception as retry_exc:
                logger.error(f"LLM API retry also failed: {retry_exc}")
                continue

        total_cost += cost
        total_input_tokens += input_tokens
        total_output_tokens += output_tokens

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
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
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


def _call_sonnet_api(prompt: str, api_key: str) -> tuple[str, float, int, int]:
    """
    Call the Claude Sonnet API with the given prompt.

    Uses the anthropic Python SDK.  Returns the response text, estimated cost,
    and token usage counts.

    Args:
        prompt: The complete prompt string.
        api_key: Anthropic API key.

    Returns:
        (response_text, estimated_cost_usd, input_tokens, output_tokens)

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

    return response_text, estimated_cost, input_tokens, output_tokens


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

        # Post-process Flavor values through FLAVOR_MAP / separator normalizer
        if column == "Flavor":
            original_llm_value = normalized_value
            normalized_value = _normalize_flavor(normalized_value)
            if normalized_value != original_llm_value:
                logger.debug(
                    f"Flavor post-normalization: '{original_llm_value}' "
                    f"→ '{normalized_value}'"
                )
                decision = {**decision, "normalized_value": normalized_value}

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


def _normalize_flavor(value: str) -> str:
    """
    Post-extraction normalization for Flavor values.

    1. Check FLAVOR_MAP for an exact (case-insensitive) replacement.
    2. If not found, apply general separator normalization:
       replace "/" with " & " (handling optional surrounding spaces).

    Args:
        value: The raw Flavor string from the LLM.

    Returns:
        Normalized Flavor string.
    """
    if not value or not value.strip():
        return value

    stripped = value.strip()
    lookup_key = stripped.lower()

    # Exact match in FLAVOR_MAP
    if lookup_key in FLAVOR_MAP:
        return FLAVOR_MAP[lookup_key]

    # General separator normalization: " / " or "/" → " & "
    normalized = re.sub(r"\s*/\s*", " & ", stripped)

    return normalized


# ═══════════════════════════════════════════════════════════════════════════
# Root Cause Analysis for Accuracy Testing
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class DifferenceAnalysis:
    """LLM analysis of a single difference."""
    row_key_str: str  # "UK|London|Tesco|photo123.jpg"
    column: str
    tool_value: str
    truth_value: str
    root_cause_category: str  # (a) through (g)
    explanation: str  # 1-2 sentence explanation
    fix_recommendation: str | None  # Actionable fix or None


@dataclass
class RootCauseAnalysisResult:
    """Output of root cause analysis."""
    analyses: list[DifferenceAnalysis] = field(default_factory=list)
    root_cause_summary: dict[str, int] = field(default_factory=dict)  # Category → count
    api_cost_estimate: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None


_ROOT_CAUSE_PROMPT_TEMPLATE = """You are analyzing differences between a data processing tool's output and ground truth data.

TOOL PROCESSING PIPELINE:
1. Excel reading → column mapping → normalization (lookup tables) → numeric conversion → price calculation → LLM cleaning

ROOT CAUSE CATEGORIES:
(a) file_reader_error: Tool misread raw Excel data (merged cells, image interference, structure detection)
(b) column_mapping_error: Raw column name mapped to wrong master column
(c) normalization_rule_error: Value not in lookup table, or lookup table has wrong mapping
(d) llm_inference_error: LLM made incorrect decision (wrong category, wrong extraction)
(e) numeric_conversion_error: Text-to-number conversion failed or produced wrong result
(f) price_calculation_error: Price per liter calculation or currency conversion wrong
(g) ground_truth_error: Ground truth is actually incorrect; tool is right

DIFFERENCES TO ANALYZE:
{differences_json}

For each difference, return:
- row_key: the composite key
- column: column name
- tool_value: what the tool produced
- truth_value: what ground truth has
- root_cause_category: one of (a) through (g) above
- explanation: 1-2 sentence explanation of why this happened
- fix_recommendation: specific action to fix (e.g., "Add 'Flash Pasteurised' → 'Pasteurized' to PROCESSING_METHOD_MAP in config/normalization_rules.py") or null if ground truth is wrong

Return a JSON array of analysis objects."""


def analyze_differences_for_root_cause(
    differences_batch: list[dict],
    api_key: str | None = None,
) -> RootCauseAnalysisResult:
    """
    Analyze differences using Claude Sonnet to determine root causes.
    
    Args:
        differences_batch: List of dicts with keys:
            - row_key (Country|City|Retailer|Photo)
            - column
            - tool_value
            - truth_value
            - row_context (full row data from tool output)
        api_key: Anthropic API key
    
    Returns:
        RootCauseAnalysisResult with categorized root causes and fix recommendations
    """
    # No API key → skip entirely
    if not api_key:
        logger.info("No API key provided — skipping root cause analysis")
        return RootCauseAnalysisResult(error="No API key provided")
    
    # No differences → nothing to do
    if not differences_batch:
        logger.info("No differences to analyze")
        return RootCauseAnalysisResult()
    
    # Build prompt
    prompt = _ROOT_CAUSE_PROMPT_TEMPLATE.format(
        differences_json=json.dumps(differences_batch, indent=2, ensure_ascii=False)
    )
    
    # Call API
    try:
        response_text, cost, input_tokens, output_tokens = _call_sonnet_api(prompt, api_key)
    except Exception as exc:
        logger.error(f"Root cause analysis API call failed: {exc}")
        return RootCauseAnalysisResult(error=f"API call failed: {exc}")
    
    # Parse response
    analyses_json = _parse_llm_response(response_text)
    if analyses_json is None:
        logger.error("Failed to parse root cause analysis response")
        return RootCauseAnalysisResult(
            api_cost_estimate=cost,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            error="Failed to parse LLM response"
        )
    
    # Convert to DifferenceAnalysis objects
    analyses: list[DifferenceAnalysis] = []
    root_cause_counts: dict[str, int] = {}
    
    for item in analyses_json:
        try:
            analysis = DifferenceAnalysis(
                row_key_str=item.get("row_key", ""),
                column=item.get("column", ""),
                tool_value=item.get("tool_value", ""),
                truth_value=item.get("truth_value", ""),
                root_cause_category=item.get("root_cause_category", ""),
                explanation=item.get("explanation", ""),
                fix_recommendation=item.get("fix_recommendation")
            )
            analyses.append(analysis)
            
            # Count by category
            category = analysis.root_cause_category
            if category:
                root_cause_counts[category] = root_cause_counts.get(category, 0) + 1
        
        except Exception as exc:
            logger.warning(f"Failed to parse analysis item: {exc}")
            continue
    
    logger.info(
        f"Root cause analysis complete: {len(analyses)} differences analyzed, "
        f"cost: ${cost:.4f}"
    )
    
    return RootCauseAnalysisResult(
        analyses=analyses,
        root_cause_summary=root_cause_counts,
        api_cost_estimate=cost,
        input_tokens=input_tokens,
        output_tokens=output_tokens
    )
