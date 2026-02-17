"""
Column name mapping configuration.

Maps raw Excel column names to master schema column names.
Also provides KNOWN_HEADER_NAMES used by file_reader.py to detect header rows.

Source of truth: docs/SCHEMA.md — Column Mapping table.
"""

# ---------------------------------------------------------------------------
# Exact matches: raw name (lowercase) → master column name
# These are columns where the raw name matches the master name exactly
# (case-insensitive).
# ---------------------------------------------------------------------------
EXACT_MATCHES: dict[str, str] = {
    "photo file name": "Photo",
    "photo": "Photo",
    "shelf location": "Shelf Location",
    "shelf levels": "Shelf Levels",
    "shelf level": "Shelf Level",
    "brand": "Brand",
    "sub-brand": "Sub-brand",
    "flavor": "Flavor",
    "facings": "Facings",
    "packaging size (ml)": "Packaging Size (ml)",
    "processing method": "Processing Method",
    "hpp treatment": "HPP Treatment",
    "packaging type": "Packaging Type",
    "claims": "Claims",
    "stock status": "Stock Status",
    "est. linear meters": "Est. Linear Meters",
    "fridge number": "Fridge Number",
    "confidence score": "Confidence Score",
    "notes": "Notes",
}

# ---------------------------------------------------------------------------
# Known renames: raw name (lowercase) → master column name
# These are semantic renames where the raw file uses a different term.
# ---------------------------------------------------------------------------
KNOWN_RENAMES: dict[str, str] = {
    "segment": "Product Type",
    "sub-segment": "Need State",
    "branded / private label": "Branded/Private Label",
    "bonus": "Bonus/Promotions",
    # Price columns use various currency labels — all map to the same master col
    "price (gbp)": "Price (Local Currency)",
    "price (eur)": "Price (Local Currency)",
    "price (pounds)": "Price (Local Currency)",
    # Price per liter variants (kept as-is in raw, recalculated downstream)
    "price per liter (gbp)": "Price per Liter (EUR)",
    "price per liter (eur)": "Price per Liter (EUR)",
}

# ---------------------------------------------------------------------------
# Known header names: the union of all column names that could appear in a
# header row. Used by file_reader.py to detect which row is the header.
#
# Includes: master column names + all raw column name variants.
# All stored in lowercase for case-insensitive matching.
# ---------------------------------------------------------------------------
KNOWN_HEADER_NAMES: set[str] = {
    # Master column names
    "country",
    "city",
    "retailer",
    "store format",
    "store name",
    "photo",
    "shelf location",
    "shelf levels",
    "shelf level",
    "product type",
    "branded/private label",
    "brand",
    "sub-brand",
    "product name",
    "flavor",
    "facings",
    "price (local currency)",
    "currency",
    "price (eur)",
    "packaging size (ml)",
    "price per liter (eur)",
    "need state",
    "juice extraction method",
    "processing method",
    "hpp treatment",
    "packaging type",
    "claims",
    "bonus/promotions",
    "stock status",
    "est. linear meters",
    "fridge number",
    "confidence score",
    "notes",
    # Raw column name variants (as they appear in Excel files)
    "photo file name",
    "segment",
    "sub-segment",
    "branded / private label",
    "bonus",
    "price (gbp)",
    "price (pounds)",
    "price per liter (gbp)",
}
