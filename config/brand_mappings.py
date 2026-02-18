"""
Brand-specific mappings for Juice Extraction Method and Processing Method.

This module provides brand-based inference rules with fuzzy matching to handle
spelling variations. Currently supports UK market only.

Usage:
    from config.brand_mappings import match_brand
    
    result = match_brand("Tropicanna")  # Handles typos
    if result:
        brand_name, mapping, score = result
        # mapping = {"juice_extraction_method": "Squeezed", "processing_method": "Pasteurized"}
"""

from rapidfuzz import fuzz
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# UK Market Brand Mappings
# ---------------------------------------------------------------------------
# Source: Brand analysis table (Feb 2026)
# Each brand maps to its known Juice Extraction Method and Processing Method
# ---------------------------------------------------------------------------

UK_BRAND_MAPPINGS = {
    # Cold-pressed + HPP brands
    "MOJU": {
        "juice_extraction_method": "Cold Pressed",
        "processing_method": "HPP"
    },
    "The Turmeric Co.": {
        "juice_extraction_method": "Cold Pressed",
        "processing_method": "HPP"
    },
    "Mockingbird": {
        "juice_extraction_method": "Cold Pressed",
        "processing_method": "HPP"
    },
    "Plenish": {
        "juice_extraction_method": "Cold Pressed",
        "processing_method": "HPP"
    },
    
    # Squeezed + Pasteurized brands
    "Innocent": {
        "juice_extraction_method": "Squeezed",
        "processing_method": "Pasteurized"
    },
    "Tropicana": {
        "juice_extraction_method": "Squeezed",
        "processing_method": "Pasteurized"
    },
    "Copella": {
        "juice_extraction_method": "Squeezed",
        "processing_method": "Pasteurized"
    },
    "Cawston Press": {
        "juice_extraction_method": "Squeezed",
        "processing_method": "Pasteurized"
    },
    "James White": {
        "juice_extraction_method": "Squeezed",
        "processing_method": "Pasteurized"
    },
    
    # From Concentrate + Pasteurized brands
    "Naked": {
        "juice_extraction_method": "From Concentrate",
        "processing_method": "Pasteurized"
    },
    "Juice Burst": {
        "juice_extraction_method": "From Concentrate",
        "processing_method": "Pasteurized"
    },
    "Happy Monkey": {
        "juice_extraction_method": "From Concentrate",
        "processing_method": "Pasteurized"
    },
    "Ocean Spray": {
        "juice_extraction_method": "From Concentrate",
        "processing_method": "Pasteurized"
    },
    "Welch's": {
        "juice_extraction_method": "From Concentrate",
        "processing_method": "Pasteurized"
    },
    "Don Simon": {
        "juice_extraction_method": "From Concentrate",
        "processing_method": "Pasteurized"
    },
    "Pommegreat": {
        "juice_extraction_method": "From Concentrate",
        "processing_method": "Pasteurized"
    },
    "POM": {  # Also known as "POM Wonderful"
        "juice_extraction_method": "From Concentrate",
        "processing_method": "Pasteurized"
    },
    "POM Wonderful": {  # Alternative name
        "juice_extraction_method": "From Concentrate",
        "processing_method": "Pasteurized"
    },
}

# Configuration
DEFAULT_COUNTRY = "UK"
BRAND_MATCHING_THRESHOLD = 85  # Minimum similarity score (0-100)

# Future expansion: Add other countries here
# US_BRAND_MAPPINGS = {...}
# FR_BRAND_MAPPINGS = {...}


def match_brand(
    input_brand: str,
    country: str = DEFAULT_COUNTRY,
    threshold: int = BRAND_MATCHING_THRESHOLD
) -> tuple[str, dict, int] | None:
    """
    Match input brand against known brands using fuzzy matching.
    
    Uses case-insensitive token sort ratio matching to handle:
    - Spelling variations (e.g., "Tropicanna" → "Tropicana")
    - Case differences (e.g., "INNOCENT" → "Innocent")
    - Extra whitespace
    
    Args:
        input_brand: Brand name from data (may contain typos)
        country: Country code for brand mapping (default: "UK")
        threshold: Minimum similarity score 0-100 (default: 85)
    
    Returns:
        Tuple of (matched_brand_name, mapping_dict, similarity_score) if match found,
        None if no match above threshold.
        
    Examples:
        >>> match_brand("Tropicana")
        ("Tropicana", {"juice_extraction_method": "Squeezed", ...}, 100)
        
        >>> match_brand("Tropicanna")  # Typo
        ("Tropicana", {"juice_extraction_method": "Squeezed", ...}, 92)
        
        >>> match_brand("Unknown Brand")
        None
    """
    if not input_brand or not isinstance(input_brand, str):
        return None
    
    input_brand = input_brand.strip()
    if not input_brand:
        return None
    
    # Get brand mappings for country
    if country == "UK":
        brand_mappings = UK_BRAND_MAPPINGS
    else:
        logger.warning(f"Country '{country}' not supported yet. Defaulting to UK.")
        brand_mappings = UK_BRAND_MAPPINGS
    
    # Find best match using fuzzy matching
    best_match = None
    best_score = 0
    best_brand = None
    
    for brand_name, mapping in brand_mappings.items():
        # Use token_sort_ratio for better handling of word order variations
        score = fuzz.token_sort_ratio(input_brand.lower(), brand_name.lower())
        
        if score > best_score:
            best_score = score
            best_match = mapping
            best_brand = brand_name
    
    # Return match if above threshold
    if best_score >= threshold:
        logger.info(
            f"Brand match: '{input_brand}' → '{best_brand}' "
            f"(similarity: {best_score}%)"
        )
        return best_brand, best_match, best_score
    
    logger.debug(
        f"No brand match for '{input_brand}' "
        f"(best: '{best_brand}' at {best_score}%, threshold: {threshold}%)"
    )
    return None


def get_all_brands(country: str = DEFAULT_COUNTRY) -> list[str]:
    """
    Get list of all known brands for a country.
    
    Args:
        country: Country code (default: "UK")
    
    Returns:
        List of brand names
    """
    if country == "UK":
        return list(UK_BRAND_MAPPINGS.keys())
    return []
