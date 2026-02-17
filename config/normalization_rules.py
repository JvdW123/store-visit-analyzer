"""
Deterministic normalization lookup tables.

Each dict maps a raw value (lowercased, stripped) to its canonical form.
Values not found in these dicts are flagged for LLM review.

An empty string ("") as the mapped value means "convert to blank" — the
normalizer will turn it into NaN to uphold the global rule: blank = we don't know.

Source of truth: docs/RULES.md — Deterministic Normalization Lookup Tables.
"""

# ---------------------------------------------------------------------------
# Product Type (raw column: "Segment")
# ---------------------------------------------------------------------------
PRODUCT_TYPE_MAP: dict[str, str] = {
    "pure juices": "Pure Juices",
    "pure juice": "Pure Juices",
    "smoothies": "Smoothies",
    "smoothie": "Smoothies",
    "shots": "Shots",
    "shot": "Shots",
    "other": "Other",
}

# ---------------------------------------------------------------------------
# Need State (raw column: "Sub-segment")
# ---------------------------------------------------------------------------
NEED_STATE_MAP: dict[str, str] = {
    "indulgence": "Indulgence",
    "indulgent": "Indulgence",
    "functional": "Functional",
}

# ---------------------------------------------------------------------------
# Branded / Private Label
# ---------------------------------------------------------------------------
BRANDED_PRIVATE_LABEL_MAP: dict[str, str] = {
    "branded": "Branded",
    "private label": "Private Label",
    "pirvate lable": "Private Label",  # known typo in source files
}

# ---------------------------------------------------------------------------
# Processing Method
# ---------------------------------------------------------------------------
PROCESSING_METHOD_MAP: dict[str, str] = {
    "pasteurized": "Pasteurized",
    "pasteurised": "Pasteurized",
    "flash pasteurised": "Pasteurized",
    "cold-pressed": "",       # blank — informs Juice Extraction Method, not Processing Method
    "cold pressed": "",       # blank — informs Juice Extraction Method, not Processing Method
    "pressed": "",            # blank — informs Juice Extraction Method, not Processing Method
    "unpasteurised": "",      # blank — removed as Processing Method value
    "unpasteurized": "",      # blank — removed as Processing Method value
    "not pasteurised": "",    # blank — removed as Processing Method value
    "freshly squeezed": "",   # blank — informs Juice Extraction Method, not Processing Method
    "hpp": "HPP",
    "hpp treated": "HPP",
    "hpp treatment": "HPP",
    "unknown": "",  # blank — we don't know
    "unkown": "",   # common typo
}

# ---------------------------------------------------------------------------
# HPP Treatment
# ---------------------------------------------------------------------------
HPP_TREATMENT_MAP: dict[str, str] = {
    "yes": "Yes",
    "hpp treatment": "Yes",
    "hpp treated": "Yes",
    "no": "No",
    "pasteurized": "No",
    "pasteurised": "No",
    "unknown": "",           # blank
    "unkown": "",            # common typo
    "unsure": "",            # blank
    "cold pressed ? assumed": "",  # blank — uncertain
}

# ---------------------------------------------------------------------------
# Packaging Type
# ---------------------------------------------------------------------------
PACKAGING_TYPE_MAP: dict[str, str] = {
    "pet bottle": "PET Bottle",
    "tetra pak": "Tetra Pak",
    "tetrapak": "Tetra Pak",
    "can": "Can",
    "carton": "Carton",
    "carton (multi-pack)": "Carton",
    "glass bottle": "Glass Bottle",
}

# ---------------------------------------------------------------------------
# Shelf Level
# ---------------------------------------------------------------------------
SHELF_LEVEL_MAP: dict[str, str] = {
    "1st": "1st",
    "1st (top)": "1st",
    "1": "1st",
    "top": "1st",
    "2nd": "2nd",
    "2": "2nd",
    "3rd": "3rd",
    "3": "3rd",
    "4th": "4th",
    "4": "4th",
    "5th": "5th",
    "5th (bottom)": "5th",
    "5": "5th",
    "bottom": "5th",
    "6th": "6th",
    "6": "6th",
    "unknown": "",   # blank
    "unkown": "",    # common typo
}

# ---------------------------------------------------------------------------
# Stock Status
# ---------------------------------------------------------------------------
STOCK_STATUS_MAP: dict[str, str] = {
    "in stock": "In Stock",
    "out of stock": "Out of Stock",
}

# ---------------------------------------------------------------------------
# Shelf Location — only exact matches handled deterministically.
# All other non-blank values are sent to the LLM for classification.
# ---------------------------------------------------------------------------
SHELF_LOCATION_MAP: dict[str, str] = {
    "chilled section": "Chilled Section",
    "chilled drinks section": "Chilled Section",
    "to-go section": "To-Go Section",
    "to-go section — shots": "To-Go Section — Shots",
    "to-go section - shots": "To-Go Section — Shots",
    "meal deal section": "Meal Deal Section",
}

# ---------------------------------------------------------------------------
# Flavor — Post-extraction normalization.
# Applied AFTER LLM extraction to standardize conjunction formats.
# Unlike other maps, this is not for invalid-value rejection — Flavor is
# free text.  Exact matches (lowercased) are replaced; unmatched values
# are left as-is.  A general separator normalizer (/ → &) is also applied.
# ---------------------------------------------------------------------------
FLAVOR_MAP: dict[str, str] = {
    "strawberry banana": "Strawberry & Banana",
    "ginger/turmeric": "Ginger & Turmeric",
    "ginger / turmeric": "Ginger & Turmeric",
}

# ---------------------------------------------------------------------------
# Master lookup: maps master column name → its normalization dict.
# Used by the normalizer to iterate over all categorical columns generically.
# ---------------------------------------------------------------------------
COLUMN_TO_RULE_MAP: dict[str, dict[str, str]] = {
    "Product Type": PRODUCT_TYPE_MAP,
    "Need State": NEED_STATE_MAP,
    "Branded/Private Label": BRANDED_PRIVATE_LABEL_MAP,
    "Processing Method": PROCESSING_METHOD_MAP,
    "HPP Treatment": HPP_TREATMENT_MAP,
    "Packaging Type": PACKAGING_TYPE_MAP,
    "Shelf Level": SHELF_LEVEL_MAP,
    "Stock Status": STOCK_STATUS_MAP,
    "Shelf Location": SHELF_LOCATION_MAP,
}

# ---------------------------------------------------------------------------
# Columns that are ALWAYS sent to LLM for non-blank, non-lookup values.
# (Juice Extraction Method used to be here but now has deterministic rules
# with LLM fallback — handled directly in normalizer.py.)
# ---------------------------------------------------------------------------
LLM_ONLY_COLUMNS: set[str] = set()

# Columns where non-matched values should be flagged for LLM rather than
# left as-is.  This is all columns in COLUMN_TO_RULE_MAP plus LLM_ONLY_COLUMNS.
FLAGGABLE_COLUMNS: set[str] = set(COLUMN_TO_RULE_MAP.keys()) | LLM_ONLY_COLUMNS
