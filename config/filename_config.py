"""
Filename parsing configuration.

Known retailers, cities, format keywords, and suffix patterns used by
processing/filename_parser.py to extract metadata from Excel filenames.

Source of truth: docs/FILENAME_CONFIG.md
"""

import re

# ---------------------------------------------------------------------------
# Known retailers: key (lowercase) → canonical display name.
# The parser tries longest keys first so "tesco express" matches before
# "tesco", and "marks and spencer" before "marks".
# ---------------------------------------------------------------------------
KNOWN_RETAILERS: dict[str, str] = {
    # Multi-word retailers (longest first in practice — the parser sorts)
    "tesco_express": "Tesco Express",
    "tesco express": "Tesco Express",
    "marks_and_spencer": "M&S",
    "marks_spencer": "M&S",
    "marks and spencer": "M&S",
    # Single-word / short retailers
    "aldi": "Aldi",
    "lidl": "Lidl",
    "m&s": "M&S",
    "m_s": "M&S",
    "ms": "M&S",
    "sainsburys": "Sainsbury's",
    "sainsbury": "Sainsbury's",
    "sainsbury's": "Sainsbury's",
    "tesco": "Tesco",
    "waitrose": "Waitrose",
    # Future: French retailers
    # "carrefour": "Carrefour",
    # "leclerc": "E.Leclerc",
    # "monoprix": "Monoprix",
    # Future: German retailers
    # "edeka": "Edeka",
    # "rewe": "REWE",
}

# ---------------------------------------------------------------------------
# Known cities: key (lowercase) → canonical display name.
# Multi-word cities like "covent garden" must appear as a single key.
# ---------------------------------------------------------------------------
KNOWN_CITIES: dict[str, str] = {
    # UK — multi-word cities first (parser sorts by length)
    "covent garden": "Covent Garden",
    "covent_garden": "Covent Garden",
    # UK — single-word cities
    "fulham": "Fulham",
    "balham": "Balham",
    "pimlico": "Pimlico",
    "vauxhall": "Vauxhall",
    "strand": "Strand",
    "oval": "Oval",
    # Add more as new store visits are conducted
}

# ---------------------------------------------------------------------------
# Store format keywords: key (lowercase) → canonical display name.
# Matched via substring search in the cleaned filename (handles cases like
# "LargeShelf" where the keyword is concatenated with another word).
# Note: "express" is part of retailer "Tesco Express", NOT a format.
# ---------------------------------------------------------------------------
FORMAT_KEYWORDS: dict[str, str] = {
    "small": "Small",
    "medium": "Medium",
    "large": "Large",
}

# ---------------------------------------------------------------------------
# Suffixes to strip from the filename before parsing.
# Applied iteratively — order matters (longer/more-specific first).
# ---------------------------------------------------------------------------
SUFFIXES_TO_STRIP: list[str] = [
    "_shelf_analysis",
    "_juice_analysis",
    "_shelf",
    "_juice",
    "_analysis",
    "_checked",
    "_corrected",
    "_v2",
    "_v3",
    "__1_",
    "_-_",
]

# ---------------------------------------------------------------------------
# Regex pattern to strip trailing copy indicators like " (1)", " (2)", etc.
# Applied after extension removal but before other cleaning.
# ---------------------------------------------------------------------------
COPY_INDICATOR_PATTERN: re.Pattern = re.compile(r"\s*\(\d+\)\s*$")

# ---------------------------------------------------------------------------
# Country → retailer lists for the per-file metadata dropdowns.
# Each country maps to a list of known retailers.  "Other" is always last
# and triggers a free-text input in the UI.
# ---------------------------------------------------------------------------
COUNTRY_RETAILERS: dict[str, list[str]] = {
    "United Kingdom": [
        "Tesco", "Tesco Express", "Sainsbury's", "Asda", "Morrisons",
        "Aldi", "Lidl", "Waitrose", "M&S", "Co-op", "Iceland", "Ocado",
        "SPAR", "Other",
    ],
    "France": [
        "E.Leclerc", "Carrefour", "Carrefour Market", "Carrefour City",
        "Intermarché", "Système U", "Auchan", "Lidl", "Aldi", "Casino",
        "Monoprix", "Franprix", "Picard", "Other",
    ],
    "Germany": [
        "Edeka", "REWE", "Lidl", "Aldi Nord", "Aldi Süd", "Kaufland",
        "Penny", "Netto", "dm", "Globus", "tegut", "SPAR", "Other",
    ],
    "Netherlands": [
        "Albert Heijn", "Jumbo", "Lidl", "Aldi", "PLUS", "Dirk",
        "DekaMarkt", "Hoogvliet", "SPAR", "Ekoplaza", "Other",
    ],
    "Spain": [
        "Mercadona", "Carrefour", "Lidl", "Aldi", "Dia", "Eroski",
        "Consum", "Alcampo", "El Corte Inglés", "Bon Preu", "Other",
    ],
}

# ---------------------------------------------------------------------------
# Store format options for the per-file metadata dropdown.
# "Other" triggers a free-text input in the UI.
# ---------------------------------------------------------------------------
STORE_FORMATS: list[str] = [
    "Hypermarket", "Supermarket", "Discount", "Convenience", "Other",
]

# ---------------------------------------------------------------------------
# Supported countries — derived from COUNTRY_RETAILERS keys.
# ---------------------------------------------------------------------------
COUNTRIES: list[str] = list(COUNTRY_RETAILERS.keys())
