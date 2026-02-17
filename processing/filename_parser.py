"""
Filename parser — extracts Retailer, City, and Store Format from filenames.

Uses a configuration-driven lookup approach: known retailer names and cities
are matched against the cleaned filename using exact substring matching first,
then fuzzy matching as a fallback.  Format keywords are extracted via
substring search (handles concatenated cases like "LargeShelf").

Public API:
    parse_filename(filename) → FilenameParseResult

See docs/FILENAME_CONFIG.md for the parsing algorithm and known values.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from config.filename_config import (
    COPY_INDICATOR_PATTERN,
    FORMAT_KEYWORDS,
    KNOWN_CITIES,
    KNOWN_RETAILERS,
    SUFFIXES_TO_STRIP,
)
from utils.fuzzy_match import best_match

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Data class
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class FilenameParseResult:
    """Result of parsing a single filename for metadata."""

    retailer: str | None        # Canonical retailer name, or None
    city: str | None            # Canonical city name, or None
    store_format: str | None    # "Small", "Medium", "Large", or None
    confidence: int             # 0-100 overall confidence score
    raw_filename: str           # Original filename for audit trail


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def parse_filename(filename: str) -> FilenameParseResult:
    """
    Extract Retailer, City, and Store Format from a filename.

    Follows the algorithm documented in docs/FILENAME_CONFIG.md:
      1. Strip extension
      2. Strip copy indicators like " (1)"
      3. Lowercase
      4. Normalize " - " to " "
      5. Strip known suffixes iteratively
      6. Replace underscores with spaces
      7. Match retailer (longest key first, exact substring)
      8. Match city in remaining string (exact then fuzzy)
      9. Match format keywords via substring search
      10. Compute confidence score

    Args:
        filename: The Excel filename (with or without path/extension).

    Returns:
        FilenameParseResult with extracted metadata and confidence score.
    """
    raw_filename = filename
    # If a full path was passed, extract just the filename
    filename = Path(filename).name

    cleaned = _clean_filename(filename)
    logger.info(f"Parsing filename '{raw_filename}' → cleaned: '{cleaned}'")

    retailer, remaining, retailer_score = _match_retailer(cleaned)
    city, city_score = _match_city(remaining)
    store_format = _match_format(remaining)
    confidence = _compute_confidence(retailer_score, city_score)

    result = FilenameParseResult(
        retailer=retailer,
        city=city,
        store_format=store_format,
        confidence=confidence,
        raw_filename=raw_filename,
    )

    logger.info(
        f"Parsed '{raw_filename}': retailer={result.retailer}, "
        f"city={result.city}, format={result.store_format}, "
        f"confidence={result.confidence}%"
    )

    return result


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════

def _clean_filename(filename: str) -> str:
    """
    Prepare a filename for parsing by removing noise.

    Steps:
      1. Strip .xlsx / .xls extension
      2. Strip copy indicators like " (1)"
      3. Lowercase
      4. Normalize " - " separators to spaces
      5. Strip known suffixes iteratively
      6. Replace underscores with spaces
      7. Collapse multiple spaces to one and strip edges

    Args:
        filename: Raw filename (just the name, no directory path).

    Returns:
        Cleaned, lowercased string ready for retailer/city/format matching.
    """
    # 1. Strip extension
    name = re.sub(r"\.xlsx?$", "", filename, flags=re.IGNORECASE)

    # 2. Strip copy indicators like " (1)", " (2)"
    name = COPY_INDICATOR_PATTERN.sub("", name)

    # 3. Lowercase
    name = name.lower()

    # 4. Normalize " - " to a space (e.g. "Analysis - Checked" → "Analysis Checked")
    name = name.replace(" - ", " ")

    # 5. Strip known suffixes iteratively (repeat until no more matches)
    changed = True
    while changed:
        changed = False
        for suffix in SUFFIXES_TO_STRIP:
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                changed = True

    # 6. Replace underscores with spaces
    name = name.replace("_", " ")

    # 7. Collapse multiple spaces and strip
    name = re.sub(r"\s+", " ", name).strip()

    return name


def _match_retailer(cleaned: str) -> tuple[str | None, str, int]:
    """
    Find a known retailer name in the cleaned filename.

    Tries exact substring matching with longest keys first to avoid
    partial matches (e.g. "tesco express" before "tesco").

    Falls back to fuzzy matching if no exact substring is found.

    Args:
        cleaned: The cleaned, lowercased filename string.

    Returns:
        (canonical_retailer, remaining_string, match_score)
        - canonical_retailer: e.g. "Tesco Express", or None
        - remaining_string: cleaned string with the retailer removed
        - match_score: 100 for exact substring, fuzzy score otherwise, 0 if none
    """
    # Sort keys longest-first to match "tesco express" before "tesco"
    sorted_keys = sorted(KNOWN_RETAILERS.keys(), key=len, reverse=True)

    for key in sorted_keys:
        if key in cleaned:
            canonical = KNOWN_RETAILERS[key]
            # Remove the matched retailer from the string
            remaining = cleaned.replace(key, "", 1).strip()
            remaining = re.sub(r"\s+", " ", remaining).strip()
            logger.debug(f"Retailer exact match: '{key}' → '{canonical}'")
            return canonical, remaining, 100

    # Fuzzy fallback: try to match remaining words against retailer keys
    canonical, score = best_match(cleaned, KNOWN_RETAILERS, threshold=80)
    if canonical is not None:
        logger.debug(f"Retailer fuzzy match: '{cleaned}' → '{canonical}' ({score})")
        return canonical, cleaned, score

    logger.warning(f"No retailer match found in '{cleaned}'")
    return None, cleaned, 0


def _match_city(remaining: str) -> tuple[str | None, int]:
    """
    Find a known city name in the remaining string (after retailer removal).

    Tries exact substring matching (longest keys first), then fuzzy fallback.

    Args:
        remaining: The cleaned string with the retailer already removed.

    Returns:
        (canonical_city, match_score) — e.g. ("Covent Garden", 100) or (None, 0).
    """
    # Sort keys longest-first so "covent garden" matches before shorter names
    sorted_keys = sorted(KNOWN_CITIES.keys(), key=len, reverse=True)

    for key in sorted_keys:
        if key in remaining:
            canonical = KNOWN_CITIES[key]
            logger.debug(f"City exact match: '{key}' → '{canonical}'")
            return canonical, 100

    # Fuzzy fallback against the remaining string
    # Split into individual words and try matching each word and pairs
    words = remaining.split()
    candidates_to_try: list[str] = []

    # Try pairs of adjacent words (for multi-word cities)
    for i in range(len(words) - 1):
        candidates_to_try.append(f"{words[i]} {words[i + 1]}")

    # Try individual words
    candidates_to_try.extend(words)

    best_city: str | None = None
    best_city_score: int = 0

    for candidate in candidates_to_try:
        city, score = best_match(candidate, KNOWN_CITIES, threshold=80)
        if city is not None and score > best_city_score:
            best_city = city
            best_city_score = score

    if best_city is not None:
        logger.debug(
            f"City fuzzy match: '{remaining}' → '{best_city}' ({best_city_score})"
        )
        return best_city, best_city_score

    logger.warning(f"No city match found in '{remaining}'")
    return None, 0


def _match_format(remaining: str) -> str | None:
    """
    Find a store format keyword in the remaining string.

    Uses substring matching to handle concatenated cases like "largeshelf"
    where "large" is not a standalone word.

    Args:
        remaining: The cleaned string (retailer may or may not be removed).

    Returns:
        Canonical format string ("Small", "Medium", "Large") or None.
    """
    # Sort by length descending in case we ever have overlapping keywords
    sorted_keys = sorted(FORMAT_KEYWORDS.keys(), key=len, reverse=True)

    for keyword in sorted_keys:
        if keyword in remaining:
            canonical = FORMAT_KEYWORDS[keyword]
            logger.debug(f"Format match: '{keyword}' → '{canonical}'")
            return canonical

    return None


def _compute_confidence(retailer_score: int, city_score: int) -> int:
    """
    Compute an overall confidence score from retailer and city match quality.

    Scoring rules (from docs/FILENAME_CONFIG.md):
      - Exact retailer + exact city → 100
      - Exact retailer + fuzzy city (>80) → 90
      - Fuzzy retailer (>80) + exact city → 85
      - Both fuzzy → min(retailer_score, city_score)
      - Missing retailer or city → 50 (flag for user confirmation)

    Args:
        retailer_score: 0-100 match score for retailer (100 = exact substring).
        city_score: 0-100 match score for city (100 = exact substring).

    Returns:
        Overall confidence percentage (0-100).
    """
    if retailer_score == 0 or city_score == 0:
        # One or both fields could not be determined
        return 50

    if retailer_score == 100 and city_score == 100:
        return 100

    if retailer_score == 100 and city_score >= 80:
        return 90

    if retailer_score >= 80 and city_score == 100:
        return 85

    # Both fuzzy — return the weaker score as overall confidence
    return min(retailer_score, city_score)
