# Filename Parsing Configuration
# How the tool extracts Retailer, City, and Store Format from Excel filenames

---

## Strategy

Use a **configuration-driven lookup** approach rather than hardcoded regex. Known retailer names and cities are matched against the filename using fuzzy matching. This handles spelling variations and new files without code changes — just update the config lists.

---

## Known Retailers

```python
KNOWN_RETAILERS = {
    # key (lowercase) → canonical display name
    "aldi": "Aldi",
    "lidl": "Lidl",
    "m&s": "M&S",
    "m_s": "M&S",
    "ms": "M&S",
    "marks_and_spencer": "M&S",
    "marks_spencer": "M&S",
    "marks and spencer": "M&S",
    "sainsburys": "Sainsbury's",
    "sainsbury": "Sainsbury's",
    "sainsbury's": "Sainsbury's",
    "tesco_express": "Tesco Express",
    "tesco express": "Tesco Express",
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
```

**Important:** Match longest retailer names first (e.g., "Tesco Express" before "Tesco") to avoid partial matches.

---

## Known Cities

```python
KNOWN_CITIES = {
    # key (lowercase) → canonical display name
    # UK
    "fulham": "Fulham",
    "balham": "Balham",
    "pimlico": "Pimlico",
    "vauxhall": "Vauxhall",
    "covent_garden": "Covent Garden",
    "covent garden": "Covent Garden",
    "strand": "Strand",
    "oval": "Oval",
    # Add more as new store visits are conducted
}
```

---

## Store Format Keywords

```python
FORMAT_KEYWORDS = {
    "small": "Small",
    "medium": "Medium",
    "large": "Large",
    # Note: "express" is part of retailer name "Tesco Express", NOT a format
}
```

---

## Filename Suffixes to Strip

Before parsing, remove these common suffixes to clean up the filename:

```python
SUFFIXES_TO_STRIP = [
    "_checked", "_corrected", "_v2", "_v3",
    "_analysis", "_shelf_analysis", "_shelf",
    "_juice_analysis", "_juice",
    "__1_", "_-_",
]
```

---

## Parsing Algorithm

```
1. Take filename, remove .xlsx extension
2. Lowercase the filename
3. Strip known suffixes (iteratively)
4. Replace underscores with spaces
5. Search for known retailers (longest match first)
   → If found: extract and remove from remaining string
   → If not found: flag for user confirmation
6. Search for known cities in remaining string
   → If found: extract
   → If not found: use fuzzy match against KNOWN_CITIES
   → If still not found: flag for user confirmation
7. Search for format keywords in remaining string
   → If found: extract
   → If not found: leave Store Format blank
8. Return: { retailer, city, store_format, confidence_score }
```

**Confidence scoring:**
- Exact retailer match + exact city match → 100%
- Exact retailer + fuzzy city (score > 80) → 90%
- Fuzzy retailer (score > 80) + exact city → 85%
- Any field below 80% fuzzy match → flag for user confirmation

---

## Adding New Retailers/Cities

When expanding to new countries or new store visits:
1. Add entries to `KNOWN_RETAILERS` and `KNOWN_CITIES` in `config/filename_config.py`
2. No code changes needed — the parser uses these dicts dynamically
