"""
Fuzzy string matching utilities.

Wraps the thefuzz library to provide a simple best-match interface used by
filename_parser, column_mapper, and normalizer modules.
"""

import logging

from thefuzz import fuzz

logger = logging.getLogger(__name__)


def best_match(
    value: str,
    candidates: dict[str, str],
    threshold: int = 80,
) -> tuple[str | None, int]:
    """
    Find the best fuzzy match for *value* among *candidates* keys.

    Uses token_sort_ratio which handles word reordering well (e.g.
    "Shelf Analysis" vs "Analysis Shelf").

    Args:
        value: The string to match (will be lowercased internally).
        candidates: Dict of candidate_key (lowercase) → canonical_value.
        threshold: Minimum score (0-100) to accept a match.

    Returns:
        (canonical_value, score) if a match is found at or above threshold,
        or (None, 0) if no match qualifies.
    """
    if not value or not candidates:
        return None, 0

    value_lower = value.strip().lower()

    best_canonical: str | None = None
    best_score: int = 0

    for candidate_key, canonical_value in candidates.items():
        score = fuzz.token_sort_ratio(value_lower, candidate_key)
        if score > best_score:
            best_score = score
            best_canonical = canonical_value

    if best_score >= threshold:
        logger.debug(
            f"Fuzzy matched '{value}' → '{best_canonical}' (score={best_score})"
        )
        return best_canonical, best_score

    logger.debug(
        f"No fuzzy match for '{value}' above threshold {threshold} "
        f"(best was '{best_canonical}' at {best_score})"
    )
    return None, 0
