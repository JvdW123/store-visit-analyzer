"""
Contains_Vegetables column — three-layer tagging approach.

After Flavor_Profile is classified, this module adds:

    Contains_Vegetables  — "Yes" if the SKU contains a vegetable or plant-green
                           ingredient, blank otherwise.

Tagging layers:
    Layer 1 (deterministic): keyword scan across Flavor_Clean, Claims, Notes,
                             and Product Name.
    Layer 2 (deterministic): propagation — if ANY row for a given Flavor_Clean
                             was tagged Yes in Layer 1, ALL rows with that
                             Flavor_Clean get Yes.
    Layer 3 (LLM):           sends remaining untagged products whose Flavor_Clean
                             contains an ambiguity signal word to Claude Sonnet;
                             results cached in vegetable_tag_cache.json.

Public API:
    tag_contains_vegetables(df, api_key, cache_path) -> tuple[pd.DataFrame, dict]
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path

import pandas as pd

from config.llm_config import MODEL_ID
from config.flavor_profile_config import (
    VEGETABLE_AMBIGUITY_SIGNALS,
    VEGETABLE_KEYWORDS,
)

logger = logging.getLogger(__name__)

# Columns scanned for vegetable keywords in Layer 1.
_SCAN_COLUMNS = ["Flavor_Clean", "Claims", "Notes", "Product Name"]

_LAYER3_PROMPT_TEMPLATE = """\
You are a product classifier for supermarket shelf audit data.

For each product below, based on ALL available information (flavor name, claims,
notes, product name), does this product likely contain vegetables or plant-green
ingredients such as spinach, kale, cucumber, beetroot, spirulina, chlorella,
wheatgrass, aloe, or similar plant-green ingredients?

Answer Yes or No for each product.

Products to evaluate:
{items_json}

Return a JSON object where each key is the Flavor_Clean value and each value is
either "Yes" or "No". Example:
{{
  "Green Goodness": "Yes",
  "Green Escape": "No",
  "Wonder Green": "Yes"
}}

Return ONLY the JSON object. No extra text or markdown.
"""


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def tag_contains_vegetables(
    df: pd.DataFrame,
    api_key: str | None,
    cache_path: str = "vegetable_tag_cache.json",
) -> tuple[pd.DataFrame, dict[str, int]]:
    """
    Add the Contains_Vegetables column to the DataFrame.

    Runs three tagging layers in order:
        1. Deterministic keyword scan on Flavor_Clean, Claims, Notes,
           and Product Name.
        2. Propagation: if any row for a Flavor_Clean was tagged Yes,
           all rows for that Flavor_Clean get Yes.
        3. LLM for remaining untagged products whose Flavor_Clean contains
           an ambiguity signal word (skipped when no api_key).

    Contains_Vegetables is inserted immediately after Flavor_Profile.
    Blank means "not identified as containing vegetables".

    Args:
        df: DataFrame after classify_flavor_profile has been applied.
        api_key: Anthropic API key for Layer 3. May be None.
        cache_path: Path to the persistent Layer 3 JSON cache file.

    Returns:
        Tuple of:
            - DataFrame with Contains_Vegetables column added.
            - Summary dict with keys "layer1", "layer2", "layer3" holding
              the number of SKUs (rows) tagged by each layer.
    """
    result = df.copy()
    result["Contains_Vegetables"] = ""

    # ── Layer 1: deterministic keyword scan ───────────────────────────────
    result = _layer1_tag(result)
    layer1_count = (result["Contains_Vegetables"] == "Yes").sum()
    logger.info(
        f"Vegetable Tagger Layer 1: {layer1_count} SKUs tagged via keyword scan"
    )

    # ── Layer 2: propagation by Flavor_Clean ──────────────────────────────
    result, layer2_count = _layer2_propagate(result)
    logger.info(
        f"Vegetable Tagger Layer 2: {layer2_count} additional SKUs tagged via propagation"
    )

    # ── Layer 3: LLM for ambiguous untagged products ──────────────────────
    layer3_count = 0
    if api_key:
        result, layer3_count = _apply_layer3(result, api_key, cache_path)
        logger.info(
            f"Vegetable Tagger Layer 3: {layer3_count} additional SKUs tagged via LLM"
        )
    else:
        ambiguous_count = _count_ambiguous_untagged(result)
        logger.info(
            f"Vegetable Tagger Layer 3 skipped — no API key. "
            f"{ambiguous_count} ambiguous untagged products not evaluated."
        )

    # ── Reorder so Contains_Vegetables sits after Flavor_Profile ──────────
    result = _reorder_columns(result)

    total_yes = (result["Contains_Vegetables"] == "Yes").sum()
    logger.info(
        f"Vegetable Tagger complete: {total_yes} SKUs tagged Yes in total "
        f"(L1={layer1_count}, L2={layer2_count}, L3={layer3_count})"
    )

    summary = {"layer1": int(layer1_count), "layer2": int(layer2_count), "layer3": int(layer3_count)}
    return result, summary


# ═══════════════════════════════════════════════════════════════════════════
# Layer 1 — keyword scan
# ═══════════════════════════════════════════════════════════════════════════

def _layer1_tag(df: pd.DataFrame) -> pd.DataFrame:
    """
    Layer 1: scan four columns for vegetable keywords, row by row.

    Sets Contains_Vegetables = "Yes" for any row where at least one of
    Flavor_Clean, Claims, Notes, or Product Name contains a keyword match.

    Args:
        df: DataFrame with Contains_Vegetables column initialised to "".

    Returns:
        DataFrame with Contains_Vegetables updated.
    """
    result = df.copy()

    def _row_has_veggie(row: pd.Series) -> str:
        for col in _SCAN_COLUMNS:
            raw_value = row.get(col, "")
            if pd.isna(raw_value) or not str(raw_value).strip():
                continue
            normalized = _normalize_for_matching(str(raw_value))
            if _contains_vegetable_keyword(normalized):
                return "Yes"
        return ""

    result["Contains_Vegetables"] = result.apply(_row_has_veggie, axis=1)
    return result


def _contains_vegetable_keyword(normalized_text: str) -> bool:
    """
    Return True if the normalized text contains any vegetable keyword.

    Single-word keywords are matched with word boundaries to avoid
    false positives (e.g. "greens" must not match "evergreen").
    Multi-word phrases use simple substring matching.

    Args:
        normalized_text: Accent-stripped, lowercased text.

    Returns:
        True if a vegetable keyword is found.
    """
    for keyword in VEGETABLE_KEYWORDS:
        normalized_keyword = _normalize_for_matching(keyword)
        if " " in normalized_keyword:
            # Phrase match — substring is sufficient
            if normalized_keyword in normalized_text:
                return True
        else:
            # Single word — require word boundary
            pattern = rf"\b{re.escape(normalized_keyword)}\b"
            if re.search(pattern, normalized_text):
                return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
# Layer 2 — propagation by Flavor_Clean
# ═══════════════════════════════════════════════════════════════════════════

def _layer2_propagate(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Layer 2: propagate Yes across all rows sharing the same Flavor_Clean.

    If any row for a given Flavor_Clean was tagged Yes in Layer 1, every
    other row with that Flavor_Clean also gets Yes.  This catches the common
    case where the same product has inconsistent Claims/Notes across rows.

    Args:
        df: DataFrame after Layer 1.

    Returns:
        Tuple of (updated DataFrame, count of newly tagged rows).
    """
    if "Flavor_Clean" not in df.columns:
        return df, 0

    result = df.copy()

    before_count = (result["Contains_Vegetables"] == "Yes").sum()

    # Build the set of Flavor_Clean values that have at least one Yes row
    yes_flavors = set(
        result.loc[result["Contains_Vegetables"] == "Yes", "Flavor_Clean"]
        .dropna()
        .astype(str)
        .unique()
    )

    if yes_flavors:
        propagation_mask = (
            result["Flavor_Clean"].astype(str).isin(yes_flavors)
            & (result["Contains_Vegetables"] != "Yes")
        )
        result.loc[propagation_mask, "Contains_Vegetables"] = "Yes"

    after_count = (result["Contains_Vegetables"] == "Yes").sum()
    newly_tagged = int(after_count - before_count)
    return result, newly_tagged


# ═══════════════════════════════════════════════════════════════════════════
# Layer 3 — LLM for ambiguous untagged products
# ═══════════════════════════════════════════════════════════════════════════

def _apply_layer3(
    df: pd.DataFrame,
    api_key: str,
    cache_path: str,
) -> tuple[pd.DataFrame, int]:
    """
    Layer 3: LLM Yes/No decision for ambiguous untagged products.

    Only products whose Flavor_Clean contains an ambiguity signal word
    (whole-word match) are sent to the LLM.  For each qualifying Flavor_Clean,
    all distinct Claims, Notes, and Product Name values across all rows are
    aggregated to give the LLM maximum context.

    Results are cached in vegetable_tag_cache.json so the LLM is called at
    most once per unique Flavor_Clean value, across all sessions.

    Args:
        df: DataFrame after Layers 1 and 2.
        api_key: Anthropic API key.
        cache_path: Path to the persistent JSON cache file.

    Returns:
        Tuple of (updated DataFrame, count of newly tagged rows).
    """
    result = df.copy()

    # Find untagged rows whose Flavor_Clean contains an ambiguity signal
    untagged_mask = result["Contains_Vegetables"] != "Yes"
    untagged_rows = result[untagged_mask].copy()

    if untagged_rows.empty or "Flavor_Clean" not in untagged_rows.columns:
        return result, 0

    ambiguous_mask = untagged_rows["Flavor_Clean"].apply(
        lambda value: _has_ambiguity_signal(str(value)) if pd.notna(value) else False
    )
    ambiguous_rows = untagged_rows[ambiguous_mask]

    if ambiguous_rows.empty:
        logger.info("Vegetable Tagger Layer 3: no ambiguous untagged products found")
        return result, 0

    unique_ambiguous_flavors = (
        ambiguous_rows["Flavor_Clean"]
        .dropna()
        .astype(str)
        .pipe(lambda series: series[series.str.strip() != ""])
        .unique()
        .tolist()
    )

    cache = _load_cache(cache_path)

    new_flavors = [flavor for flavor in unique_ambiguous_flavors if flavor not in cache]
    logger.info(
        f"Vegetable Tagger Layer 3: {len(unique_ambiguous_flavors)} ambiguous flavors, "
        f"{len(new_flavors)} not in cache"
    )

    if new_flavors:
        # Build rich context items — aggregate ALL rows for each flavor
        items = _build_llm_items(result, new_flavors)
        llm_mapping = _call_llm(items, api_key)
        if llm_mapping:
            valid_mapping = {
                flavor: answer
                for flavor, answer in llm_mapping.items()
                if answer in ("Yes", "No")
            }
            cache.update(valid_mapping)
            _save_cache(cache_path, cache)
            logger.info(
                f"Vegetable Tagger Layer 3: cache updated with {len(valid_mapping)} new entries"
            )

    # Apply cached answers to all matching untagged rows
    before_count = (result["Contains_Vegetables"] == "Yes").sum()

    def _apply_cache(row: pd.Series) -> str:
        flavor = row.get("Flavor_Clean")
        if pd.isna(flavor) or not str(flavor).strip():
            return row.get("Contains_Vegetables", "")
        cached_answer = cache.get(str(flavor))
        if cached_answer == "Yes":
            return "Yes"
        return row.get("Contains_Vegetables", "")

    updateable_index = ambiguous_rows.index
    result.loc[updateable_index, "Contains_Vegetables"] = (
        result.loc[updateable_index].apply(_apply_cache, axis=1)
    )

    after_count = (result["Contains_Vegetables"] == "Yes").sum()
    newly_tagged = int(after_count - before_count)
    return result, newly_tagged


def _has_ambiguity_signal(flavor_clean: str) -> bool:
    """
    Return True if the Flavor_Clean value contains any ambiguity signal word.

    Uses whole-word matching so "garden" matches "Garden Blend" but not
    "gardening".

    Args:
        flavor_clean: The Flavor_Clean string.

    Returns:
        True if at least one ambiguity signal word is found.
    """
    normalized = _normalize_for_matching(flavor_clean)
    for signal in VEGETABLE_AMBIGUITY_SIGNALS:
        normalized_signal = _normalize_for_matching(signal)
        pattern = rf"\b{re.escape(normalized_signal)}\b"
        if re.search(pattern, normalized):
            return True
    return False


def _count_ambiguous_untagged(df: pd.DataFrame) -> int:
    """
    Count unique Flavor_Clean values that are untagged but have ambiguity signals.

    Used for the Layer 3 skip log message when no API key is configured.

    Args:
        df: DataFrame after Layers 1 and 2.

    Returns:
        Number of unique ambiguous untagged Flavor_Clean values.
    """
    if "Flavor_Clean" not in df.columns:
        return 0

    untagged = df[df["Contains_Vegetables"] != "Yes"]
    if untagged.empty:
        return 0

    return int(
        untagged["Flavor_Clean"]
        .dropna()
        .astype(str)
        .apply(_has_ambiguity_signal)
        .sum()
    )


def _build_llm_items(
    df: pd.DataFrame,
    new_flavors: list[str],
) -> list[dict[str, str]]:
    """
    Build a list of rich context dicts for the LLM prompt.

    For each Flavor_Clean value, aggregates ALL distinct Claims, Notes, and
    Product Name values found across every row with that flavor (not just the
    first row).  This maximises the chance the LLM sees the one row that
    contains the revealing ingredient information.

    Args:
        df: Full DataFrame (all rows, not just untagged ones).
        new_flavors: Flavor_Clean values not yet in the cache.

    Returns:
        List of dicts with keys: flavor_clean, claims, notes, product_name.
    """
    items: list[dict[str, str]] = []

    for flavor in new_flavors:
        matching_rows = df[df["Flavor_Clean"].astype(str) == flavor]
        if matching_rows.empty:
            continue

        def _collect_distinct(col: str) -> str:
            """Return semicolon-separated distinct non-empty values for a column."""
            values = (
                matching_rows[col]
                .dropna()
                .astype(str)
                .str.strip()
                .pipe(lambda series: series[series != ""])
                .unique()
                .tolist()
                if col in matching_rows.columns
                else []
            )
            return "; ".join(values) if values else ""

        items.append({
            "flavor_clean":  flavor,
            "claims":        _collect_distinct("Claims"),
            "notes":         _collect_distinct("Notes"),
            "product_name":  _collect_distinct("Product Name"),
        })

    return items


def _call_llm(
    items: list[dict[str, str]],
    api_key: str,
) -> dict[str, str] | None:
    """
    Send ambiguous untagged products to Claude Sonnet for a Yes/No decision.

    Args:
        items: List of dicts (flavor_clean, claims, notes, product_name).
        api_key: Anthropic API key.

    Returns:
        Dict mapping Flavor_Clean → "Yes" or "No", or None on failure.
    """
    import anthropic

    items_json = json.dumps(items, ensure_ascii=False, indent=2)
    prompt = _LAYER3_PROMPT_TEMPLATE.format(items_json=items_json)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=MODEL_ID,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = message.content[0].text
        input_tokens = message.usage.input_tokens
        output_tokens = message.usage.output_tokens
        cost = (input_tokens * 3.0 / 1_000_000) + (output_tokens * 15.0 / 1_000_000)
        logger.info(
            f"Vegetable Tagger Layer 3 LLM call: "
            f"{input_tokens} in / {output_tokens} out tokens, est. cost ${cost:.4f}"
        )
    except Exception as exc:
        logger.error(f"Vegetable Tagger Layer 3 LLM call failed: {exc}")
        return None

    return _parse_llm_response(response_text)


def _parse_llm_response(response_text: str) -> dict[str, str] | None:
    """
    Parse the JSON object returned by the Layer 3 LLM prompt.

    Handles optional markdown code fences. Returns None on parse failure.

    Args:
        response_text: Raw text response from the LLM.

    Returns:
        Dict mapping Flavor_Clean → "Yes"/"No", or None on failure.
    """
    if not response_text:
        return None

    fenced = re.search(r"```(?:json)?\s*\n?(.*?)```", response_text, re.DOTALL)
    text = fenced.group(1).strip() if fenced else response_text.strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        logger.error(
            f"Vegetable Tagger Layer 3: no JSON object in LLM response. "
            f"First 300 chars: {response_text[:300]}"
        )
        return None

    text = text[start:end + 1]
    text = re.sub(r",\s*([}\]])", r"\1", text)  # fix trailing commas

    try:
        mapping = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error(f"Vegetable Tagger Layer 3: failed to parse JSON response: {exc}")
        return None

    if not isinstance(mapping, dict):
        logger.error("Vegetable Tagger Layer 3: LLM response is not a JSON object")
        return None

    return mapping


# ═══════════════════════════════════════════════════════════════════════════
# Accent normalization (shared with flavor_profiler pattern)
# ═══════════════════════════════════════════════════════════════════════════

def _normalize_for_matching(text: str) -> str:
    """
    Strip accents and lowercase text for accent-insensitive keyword matching.

    Original values in the DataFrame are preserved; this is only for comparison.

    Examples:
        "Épinard" → "epinard"
        "Bétterave" → "betterave"

    Args:
        text: Input string (may contain accented characters).

    Returns:
        Lowercased, accent-stripped string.
    """
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower()


# ═══════════════════════════════════════════════════════════════════════════
# Column ordering
# ═══════════════════════════════════════════════════════════════════════════

def _reorder_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Move Contains_Vegetables to sit immediately after Flavor_Profile.

    Falls back to inserting after Flavor_Clean if Flavor_Profile is absent,
    or appends to the end if neither anchor column is present.

    Args:
        df: DataFrame containing Contains_Vegetables.

    Returns:
        DataFrame with Contains_Vegetables in the correct position.
    """
    cols = list(df.columns)

    if "Contains_Vegetables" not in cols:
        return df

    cols.remove("Contains_Vegetables")

    if "Flavor_Profile" in cols:
        insert_pos = cols.index("Flavor_Profile") + 1
    elif "Flavor_Clean" in cols:
        insert_pos = cols.index("Flavor_Clean") + 1
    else:
        insert_pos = len(cols)

    cols.insert(insert_pos, "Contains_Vegetables")
    return df[cols]


# ═══════════════════════════════════════════════════════════════════════════
# Cache helpers
# ═══════════════════════════════════════════════════════════════════════════

def _load_cache(path: str) -> dict[str, str]:
    """
    Load the Layer 3 vegetable tag cache from disk.

    Returns an empty dict if the file does not exist or cannot be parsed.

    Args:
        path: File path to the JSON cache.

    Returns:
        Dict mapping Flavor_Clean → "Yes" or "No".
    """
    cache_path = Path(path)
    if not cache_path.exists():
        return {}
    try:
        with cache_path.open("r", encoding="utf-8") as file_handle:
            data = json.load(file_handle)
        if not isinstance(data, dict):
            logger.warning(
                f"Vegetable tag cache {path} is not a JSON object — starting fresh"
            )
            return {}
        return data
    except Exception as exc:
        logger.warning(
            f"Failed to load vegetable tag cache from {path}: {exc} — starting fresh"
        )
        return {}


def _save_cache(path: str, cache: dict[str, str]) -> None:
    """
    Persist the Layer 3 vegetable tag cache to disk as pretty-printed JSON.

    Args:
        path: File path to write.
        cache: Dict mapping Flavor_Clean → "Yes" or "No".
    """
    try:
        cache_path = Path(path)
        with cache_path.open("w", encoding="utf-8") as file_handle:
            json.dump(cache, file_handle, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception as exc:
        logger.error(f"Failed to save vegetable tag cache to {path}: {exc}")
