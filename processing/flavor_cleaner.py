"""
Flavor column cleaning pipeline — two-layer approach.

Layer 1 (deterministic, per value):
    Seven regex/lookup rules that are safe to apply to any dataset.
    Applied per-file after LLM extraction, producing Flavor_Original,
    Flavor_Clean, and Flavor_Needs_Review columns.

Layer 2 (LLM, post-merge):
    One batch API call over all unique post-L1 values not already in the
    persistent cache.  Results are written to flavor_clean_cache.json and
    applied to Flavor_Clean.  Flags values containing [NEEDS_FLAVOR] in
    Flavor_Needs_Review.

Public API:
    apply_layer1_rules(value)          -> str
    apply_layer1_to_dataframe(df)      -> pd.DataFrame
    harmonize_flavors_with_llm(df, api_key, cache_path) -> pd.DataFrame
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pandas as pd

from config.normalization_rules import FLAVOR_MAP, FLAVOR_WORD_MAP

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Rule 1.2 — Title Case exceptions
# ═══════════════════════════════════════════════════════════════════════════

# Words that stay lowercase when they appear mid-string.
_LOWERCASE_EXCEPTIONS: set[str] = {
    "and", "with", "from", "no", "per", "of", "a", "the",
    # French
    "en", "et", "de", "du", "des", "le", "la", "les",
    # German
    "und", "mit", "von",
}

# Words that must remain fully uppercase regardless of position.
_UPPERCASE_WORDS: set[str] = {"OJ", "HPP", "NFC", "AB", "EC"}


# ═══════════════════════════════════════════════════════════════════════════
# Rule 1.4 — Volume/size patterns
# ═══════════════════════════════════════════════════════════════════════════

_VOLUME_PATTERN = re.compile(
    r"\(?\d+(\.\d+)?\s*"
    r"(?:ml|ML|mL|cl|CL|cL|l|L|ltr|litre|liter)"
    r"\)?",
    re.IGNORECASE,
)


# ═══════════════════════════════════════════════════════════════════════════
# Rule 1.5 — Pack-count descriptors
# ═══════════════════════════════════════════════════════════════════════════

_PACK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b\d+\s*[x×]\s*", re.IGNORECASE),           # 3x, 10x
    re.compile(r"\b[x×]\d+\b", re.IGNORECASE),               # x4, x7
    re.compile(r"\bmulti-?pack\b", re.IGNORECASE),            # multipack, multi-pack
    re.compile(r"\bbig\s+pack(\s*\d+)?\b", re.IGNORECASE),   # Big Pack, Big Pack 10
    re.compile(r"\(\s*single\s*\)", re.IGNORECASE),           # (single)
    re.compile(r"\(\s*\d+\s*pack\s*\)", re.IGNORECASE),       # (4 pack)
    re.compile(r"\(\s*(?:small|large|carton|offer)\s*\)", re.IGNORECASE),
    re.compile(r"\bdosing\s+bottle\b", re.IGNORECASE),
    re.compile(r"\(\s*\d+\s*[x×]\s*shots?\s*\)", re.IGNORECASE),  # (7x Shots)
    re.compile(r"\b\d+\s*(?:inside|pack)\b", re.IGNORECASE),  # 10 inside
]


# ═══════════════════════════════════════════════════════════════════════════
# Rule 1.6 — Promotional / offer tags
# ═══════════════════════════════════════════════════════════════════════════

_PROMO_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\(\s*offer\s*\)", re.IGNORECASE),
    re.compile(r"\bsave\s+\d+%?\b", re.IGNORECASE),
    re.compile(r"\bonly\s+[£€$]\d+\b", re.IGNORECASE),
    re.compile(r"\b(?:was|now)\s*[-–]?\s*[£€$]?\d+\.?\d*\b", re.IGNORECASE),
    re.compile(r"\baldi\s+price\s+match\b", re.IGNORECASE),
    re.compile(r"\beveryday\s+value\b", re.IGNORECASE),
    re.compile(r"\(\s*new\s*\)|\bnew\b(?=\s*$)", re.IGNORECASE),
    re.compile(r"\bback\s+soon\b", re.IGNORECASE),
]


# ═══════════════════════════════════════════════════════════════════════════
# Layer 2 LLM prompt
# ═══════════════════════════════════════════════════════════════════════════

_LAYER2_PROMPT_TEMPLATE = """\
You are a data cleaning assistant for supermarket shelf audit data. I will give \
you a list of unique flavor values from a product database. These have already been \
mechanically cleaned (whitespace, case, sizes, pack formats removed).

Your task: for each flavor, return a standardized flavor_clean value.

Apply these cleaning principles:

1. REMOVE PRODUCT-TYPE WORDS that describe what the product is, not what it tastes like:
   - Remove: "Juice", "Smoothie", "Shot", "Shots", "Drink", "Super Smoothie"
   - KEEP product-type words when they ARE the product identity: "Coconut Water",
     "Kombucha", "Kefir", "Lemonade", "Latte", "Cold Brew", "Milkshake",
     "Iced Tea", "Oat Drink"
   - KEEP when removing would make the flavor meaningless (e.g., "Breakfast Juice"
     → keep "Breakfast", "Green Juice" → keep "Green")

2. REMOVE PROCESSING/ORIGIN DESCRIPTORS that belong in other columns:
   - Remove: "Freshly Squeezed", "Freshly Pressed", "Pressed", "Pure",
     "Pure Squeezed", "From Concentrate", "Not from Concentrate"
   - KEEP brand range names that look like processing terms: "Raw" (Savse/Mockingbird),
     "Fresh Root" (MOJU), "Fresh & Light" (Tesco), "Original" (Tropicana),
     "Perfectly Pressed" (Waitrose). When unsure, keep it.

3. SINGULARIZE FRUIT NAMES:
   - Strawberries→Strawberry, Mangoes→Mango, Apples→Apple, Oranges→Orange,
     Bananas→Banana, Cherries→Cherry, Pineapples→Pineapple, Blueberries→Blueberry,
     Raspberries→Raspberry, Peaches→Peach, Coconuts→Coconut,
     Blackcurrants→Blackcurrant, Kiwis→Kiwi
   - Do NOT singularize concept names: "Summer Fruits", "Tropical Fruits", "Mixed Fruits"

4. STANDARDIZE MULTI-INGREDIENT SEPARATORS:
   - 3+ ingredients: A, B & C (comma between all, ampersand before last)
   - 2 ingredients: A & B

5. STANDARDIZE TEXTURE DESCRIPTORS (orange juice):
   - "with Bits", "with Juicy Bits", "Extra Pulpy" → "with Bits"
   - "No Bits", "with No Bits", "Smooth" (when describing orange) → "Smooth"

6. REMOVE AUDIENCE/RANGE PREFIXES:
   - Remove: "Kids Smoothie", "Kids Super Smoothie", "Kids Vitamin Shots", "Kids"
   - Remove brand sub-range prefixes like "Defend:", "Revitalise:",
     "Super Smoothie," when followed by actual ingredients

7. FIX REMAINING SPELLING ERRORS you can identify.

8. FLAG AMBIGUOUS FLAVORS: If a value is purely a functional benefit name with no
   flavor information (e.g., "Defence", "Immunity", "Energy", "Boost", "Revitalise"),
   keep it as-is but append " [NEEDS_FLAVOR]".

Return ONLY a JSON object where keys are the exact input values and values are the
cleaned output. No markdown fences, no extra text. Example:
{{
  "Apple Juice": "Apple",
  "Strawberry, Banana & Apple Smoothie": "Strawberry, Banana & Apple",
  "Freshly Squeezed Orange with Bits": "Orange with Bits",
  "Mangoes, Apples & Passion Fruits": "Mango, Apple & Passion Fruit",
  "Defence": "Defence [NEEDS_FLAVOR]"
}}

Here is the list of unique flavor values to clean:

{flavor_list_json}
"""


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def apply_layer1_rules(value: str) -> str:
    """
    Apply all seven deterministic Layer 1 cleaning rules to a single flavor string.

    Rules are applied in order:
        1.1 Trim & collapse whitespace
        1.2 Title Case (with lowercase/uppercase exceptions)
        1.3 Standardize connector words to &
        1.4 Remove volume/size indicators
        1.5 Remove pack-count descriptors
        1.6 Remove promotional/offer tags
        1.7 Standardize compound ingredient spellings

    Args:
        value: Raw flavor string (may be None or empty).

    Returns:
        Cleaned flavor string, or the original value if it was blank/None.
    """
    if not value or not str(value).strip():
        return value

    v = str(value)

    # Rule 1.1 — trim + collapse whitespace
    v = _rule_1_1(v)

    # Rule 1.2 — title case with exceptions
    v = _rule_1_2(v)

    # Rule 1.3 — connector words → &
    v = _rule_1_3(v)

    # Rule 1.4 — strip volume/size
    v = _rule_1_4(v)

    # Rule 1.5 — strip pack-count descriptors
    v = _rule_1_5(v)

    # Rule 1.6 — strip promotional tags
    v = _rule_1_6(v)

    # Rule 1.1 again after removals to clean up stray spaces
    v = _rule_1_1(v)

    # Rule 1.7 — compound ingredient spelling (FLAVOR_MAP exact + FLAVOR_WORD_MAP)
    v = _rule_1_7(v)

    return v


def apply_layer1_to_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run Layer 1 over the entire Flavor column of a DataFrame.

    Creates three new columns:
        Flavor_Original   — snapshot of Flavor before any Layer 1/2 cleaning
        Flavor_Clean      — result of Layer 1 (to be further refined by Layer 2)
        Flavor_Needs_Review — False for all rows (Layer 2 may set to True later)

    Does NOT modify the existing Flavor column so the rest of the pipeline
    continues to use it unchanged.

    Args:
        df: DataFrame that must contain a Flavor column.

    Returns:
        DataFrame with the three new columns appended.
    """
    result = df.copy()

    if "Flavor" not in result.columns:
        logger.warning("apply_layer1_to_dataframe: no Flavor column found — skipping")
        result["Flavor_Original"] = None
        result["Flavor_Clean"] = None
        result["Flavor_Needs_Review"] = False
        return result

    result["Flavor_Original"] = result["Flavor"]
    result["Flavor_Clean"] = result["Flavor"].apply(
        lambda v: apply_layer1_rules(v) if pd.notna(v) and str(v).strip() else v
    )
    result["Flavor_Needs_Review"] = False

    changed = (result["Flavor_Clean"] != result["Flavor_Original"]).sum()
    logger.info(f"Layer 1 flavor cleaning: {changed} values modified out of {len(result)}")

    return result


def harmonize_flavors_with_llm(
    df: pd.DataFrame,
    api_key: str | None,
    cache_path: str = "flavor_clean_cache.json",
) -> pd.DataFrame:
    """
    Run Layer 2 flavor harmonization using the LLM over unique Flavor_Clean values.

    Workflow:
        1. Collect unique non-blank Flavor_Clean values.
        2. Check the cache — only send values NOT already cached to the LLM.
        3. Call Claude Sonnet with a single batch prompt.
        4. Merge LLM results into the cache and persist it.
        5. Apply the full cache mapping to Flavor_Clean.
        6. Extract [NEEDS_FLAVOR] flags into Flavor_Needs_Review.

    If api_key is None or Flavor_Clean is absent, the step is skipped silently.

    Args:
        df: Merged DataFrame containing Flavor_Clean column.
        api_key: Anthropic API key.
        cache_path: Path to the persistent JSON cache file.

    Returns:
        DataFrame with Flavor_Clean updated and Flavor_Needs_Review set.
    """
    result = df.copy()

    if "Flavor_Clean" not in result.columns:
        logger.warning("harmonize_flavors_with_llm: Flavor_Clean column not found — skipping")
        return result

    if not api_key:
        logger.info("harmonize_flavors_with_llm: no API key — skipping Layer 2")
        return result

    # Collect unique non-blank values
    unique_values: list[str] = (
        result["Flavor_Clean"]
        .dropna()
        .astype(str)
        .pipe(lambda s: s[s.str.strip() != ""])
        .unique()
        .tolist()
    )

    if not unique_values:
        logger.info("harmonize_flavors_with_llm: no flavor values to process")
        return result

    # Load cache
    cache = _load_cache(cache_path)

    # Determine which values are new (not in cache)
    new_values = [v for v in unique_values if v not in cache]

    if new_values:
        logger.info(
            f"Layer 2: {len(new_values)} new values to send to LLM "
            f"({len(unique_values) - len(new_values)} already cached)"
        )
        llm_mapping = _call_llm_for_harmonization(new_values, api_key)
        if llm_mapping:
            cache.update(llm_mapping)
            _save_cache(cache_path, cache)
            logger.info(f"Layer 2: cache updated with {len(llm_mapping)} new entries")
    else:
        logger.info(f"Layer 2: all {len(unique_values)} values already in cache — no LLM call needed")

    # Apply full cache mapping to Flavor_Clean
    def _apply_cache(v: object) -> object:
        if pd.isna(v) or str(v).strip() == "":
            return v
        return cache.get(str(v), v)

    result["Flavor_Clean"] = result["Flavor_Clean"].apply(_apply_cache)

    # Set Flavor_Needs_Review for [NEEDS_FLAVOR] values; strip the tag from Flavor_Clean
    needs_review_mask = (
        result["Flavor_Clean"]
        .astype(str)
        .str.contains(r"\[NEEDS_FLAVOR\]", na=False)
    )
    result.loc[needs_review_mask, "Flavor_Needs_Review"] = True
    result["Flavor_Clean"] = result["Flavor_Clean"].astype(str).str.replace(
        r"\s*\[NEEDS_FLAVOR\]", "", regex=True
    ).str.strip()
    # Restore NaN for blank strings
    result["Flavor_Clean"] = result["Flavor_Clean"].replace("", None)
    result["Flavor_Clean"] = result["Flavor_Clean"].replace("nan", None)

    flagged_count = needs_review_mask.sum()
    if flagged_count:
        logger.info(f"Layer 2: {flagged_count} rows flagged as Flavor_Needs_Review")

    return result


# ═══════════════════════════════════════════════════════════════════════════
# Layer 1 rule implementations
# ═══════════════════════════════════════════════════════════════════════════

def _rule_1_1(v: str) -> str:
    """Trim and collapse internal whitespace."""
    return re.sub(r" {2,}", " ", v.strip())


def _rule_1_2(v: str) -> str:
    """
    Title Case with lowercase exceptions and uppercase preservation.

    Words in _LOWERCASE_EXCEPTIONS stay lowercase unless they are the first
    word.  Words in _UPPERCASE_WORDS are forced to their canonical uppercase
    form regardless of position.
    """
    words = v.split(" ")
    result: list[str] = []
    for i, word in enumerate(words):
        # Strip punctuation suffix/prefix for comparison
        core = word.strip("(),;:")
        upper_core = core.upper()
        lower_core = core.lower()

        if upper_core in _UPPERCASE_WORDS:
            # Replace the core with the canonical uppercase form, keep surrounding punctuation
            result.append(word.replace(core, upper_core))
        elif i > 0 and lower_core in _LOWERCASE_EXCEPTIONS:
            result.append(word.lower())
        else:
            result.append(word.capitalize())
    return " ".join(result)


def _rule_1_3(v: str) -> str:
    """Replace connector words (and/et/und) with &."""
    v = re.sub(r"\s+and\s+", " & ", v, flags=re.IGNORECASE)
    v = re.sub(r"\s+et\s+", " & ", v, flags=re.IGNORECASE)
    v = re.sub(r"\s+und\s+", " & ", v, flags=re.IGNORECASE)
    return v


def _rule_1_4(v: str) -> str:
    """Strip volume/size indicators."""
    return _VOLUME_PATTERN.sub("", v).strip()


def _rule_1_5(v: str) -> str:
    """Strip pack-count and multipack descriptors."""
    for pattern in _PACK_PATTERNS:
        v = pattern.sub("", v)
    return v.strip()


def _rule_1_6(v: str) -> str:
    """Strip promotional/offer tags."""
    for pattern in _PROMO_PATTERNS:
        v = pattern.sub("", v)
    return v.strip()


def _rule_1_7(v: str) -> str:
    """
    Standardize compound ingredient spellings.

    First checks FLAVOR_MAP for an exact (case-insensitive) replacement of the
    whole string.  Then applies FLAVOR_WORD_MAP as word-level substring
    replacements.  Finally normalises "/" separators to " & ".
    """
    lookup_key = v.lower()
    if lookup_key in FLAVOR_MAP:
        return FLAVOR_MAP[lookup_key]

    # Separator normalisation: "/" → " & "
    v = re.sub(r"\s*/\s*", " & ", v)

    # Word-level spelling replacements
    for raw_word, canonical in FLAVOR_WORD_MAP.items():
        pattern = re.compile(re.escape(raw_word), re.IGNORECASE)
        v = pattern.sub(canonical, v)

    return v


# ═══════════════════════════════════════════════════════════════════════════
# Layer 2 helpers
# ═══════════════════════════════════════════════════════════════════════════

def _call_llm_for_harmonization(
    values: list[str],
    api_key: str,
) -> dict[str, str] | None:
    """
    Send a list of flavor values to Claude Sonnet for Layer 2 harmonization.

    Returns a dict mapping input value → cleaned value, or None on failure.
    """
    import anthropic

    flavor_list_json = json.dumps(values, ensure_ascii=False, indent=2)
    prompt = _LAYER2_PROMPT_TEMPLATE.format(flavor_list_json=flavor_list_json)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=16384,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = message.content[0].text
        input_tokens = message.usage.input_tokens
        output_tokens = message.usage.output_tokens
        cost = (input_tokens * 3.0 / 1_000_000) + (output_tokens * 15.0 / 1_000_000)
        logger.info(
            f"Layer 2 LLM call: {input_tokens} in / {output_tokens} out tokens, "
            f"est. cost ${cost:.4f}"
        )
    except Exception as exc:
        logger.error(f"Layer 2 LLM API call failed: {exc}")
        return None

    return _parse_harmonization_response(response_text)


def _parse_harmonization_response(response_text: str) -> dict[str, str] | None:
    """
    Parse the JSON object returned by the Layer 2 LLM prompt.

    Handles optional markdown code fences around the JSON.
    """
    if not response_text:
        return None

    # Strip markdown code fences if present
    fenced = re.search(r"```(?:json)?\s*\n?(.*?)```", response_text, re.DOTALL)
    text = fenced.group(1).strip() if fenced else response_text.strip()

    # Find the JSON object boundaries
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        logger.error(
            f"Layer 2: no JSON object found in LLM response. "
            f"First 300 chars: {response_text[:300]}"
        )
        return None

    text = text[start : end + 1]
    # Fix trailing commas
    text = re.sub(r",\s*([}\]])", r"\1", text)

    try:
        mapping = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error(f"Layer 2: failed to parse JSON response: {exc}")
        return None

    if not isinstance(mapping, dict):
        logger.error("Layer 2: LLM response is not a JSON object")
        return None

    return mapping


def _load_cache(path: str) -> dict[str, str]:
    """Load the flavor clean cache from disk. Returns empty dict if file not found."""
    cache_path = Path(path)
    if not cache_path.exists():
        return {}
    try:
        with cache_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.warning(f"Cache file {path} does not contain a JSON object — starting fresh")
            return {}
        return data
    except Exception as exc:
        logger.warning(f"Failed to load flavor cache from {path}: {exc} — starting fresh")
        return {}


def _save_cache(path: str, cache: dict[str, str]) -> None:
    """Persist the flavor clean cache to disk as pretty-printed JSON."""
    try:
        cache_path = Path(path)
        with cache_path.open("w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception as exc:
        logger.error(f"Failed to save flavor cache to {path}: {exc}")
