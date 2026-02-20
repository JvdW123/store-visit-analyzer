"""
Flavor profile classification configuration.

All keyword lists that drive Single_or_Blend and Flavor_Profile classification
live here. To support French, German, or other language datasets, add translated
ingredient names to the relevant lists below — the processing code imports these
without modification.

Keyword matching is accent-insensitive: "açaí" matches "acai", "clémentin" matches
"clementin", etc. Add keywords in their base (unaccented) form for simplicity, or
with accents — both work.

Segments (8 total):
    Orange      — single-flavor orange family only
    Apple       — single-flavor apple only
    Citrus      — all citrus except single orange
    Tropical    — mango, pineapple, passion fruit, coconut, and their blends
    Orchard     — pear, grape, elderflower, and blends (excl. single apple)
    Green & Root — ginger, turmeric, beetroot, spirulina, greens, and their blends
    Berry       — strawberry, raspberry, blueberry, blackcurrant, and their blends
    Other       — everything that does not match any of the above
"""

# ---------------------------------------------------------------------------
# Non-juice safeguard keywords (Layer 2 only)
#
# If Flavor_Clean contains any of these words, skip the Claims fallback and
# leave the SKU classified as Other. This prevents protein shakes, coffees,
# and teas from being misclassified via fruit ingredients listed in Claims.
# ---------------------------------------------------------------------------
NON_JUICE_SAFEGUARD_KEYWORDS: list[str] = [
    # Coffee
    "coffee",
    "latte",
    "cappuccino",
    "espresso",
    "mocha",
    "frappuccino",
    "cold brew",
    # Protein / dairy
    "protein",
    "milkshake",
    "milk shake",
    "milk drink",
    # Plant-based milk
    "oat drink",
    "oat milk",
    "soya",
    "almond",
    # Tea
    "tea",
    "iced tea",
    "mate",
    # Other non-juice formats
    "meal drink",
    "egg white",
]

# ---------------------------------------------------------------------------
# Base ingredients — suppressed when a more distinctive ingredient is present
#
# When a blend contains one of these alongside a keyword from another segment,
# the base ingredient's segment vote is suppressed so the distinctive segment
# wins. For example "Apple & Mango" → apple suppressed, mango wins → Tropical.
#
# Add language-specific translations here (e.g. "pomme" for French apple).
# ---------------------------------------------------------------------------
SUPPRESS_AS_BASE_INGREDIENT: list[str] = [
    "apple",
    "pear",
    "banana",
    "orange",
    # French translations
    "pomme",
    "poire",
    "banane",
    # German translations
    "apfel",
    "birne",
]

# ---------------------------------------------------------------------------
# Orange segment keywords
#
# Single-SKU orange family: plain orange, orange varieties, and sub-types.
# These are ONLY used to qualify a Single SKU as "Orange" in Layer 1.
# Blends containing orange fall through to general keyword matching.
#
# French: orange (same), clémentine | German: Orange (same), Clementine
# ---------------------------------------------------------------------------
ORANGE_KEYWORDS: list[str] = [
    "orange",
    "blood orange",
    "clementine",
    "clementines",
    "clementin",          # accent-stripped variant
    # French
    "sanguine",           # blood orange in French
    # German
    "blutorange",         # blood orange in German
]

# ---------------------------------------------------------------------------
# Apple segment keywords
#
# Single-SKU apple only. Covers all named apple varieties and style variants.
# French: pomme | German: Apfel (already in SUPPRESS list but check here too)
# ---------------------------------------------------------------------------
APPLE_KEYWORDS: list[str] = [
    "apple",
    "cloudy apple",
    "pink lady",
    "orchard apple",
    "crisp apple",
    "english apple",
    "pressed apple",
    "bramley",
    # French
    "pomme",
    # German
    "apfel",
]

# ---------------------------------------------------------------------------
# Citrus segment keywords
#
# All citrus EXCEPT plain orange (which has its own segment).
# Single lemon, lime, grapefruit, yuzu, and citrus blends.
# French: citron (lemon), citron vert (lime) | German: Zitrone, Limette
# ---------------------------------------------------------------------------
CITRUS_KEYWORDS: list[str] = [
    "lemon",
    "lime",
    "grapefruit",
    "pink grapefruit",
    "ruby grapefruit",
    "yuzu",
    "citrus",
    "lemonade",
    "sicilian",           # implies Sicilian lemon or Sicilian blood orange context
    # French
    "citron",
    "limon",
    # German
    "zitrone",
    "limette",
    "grapefruit",         # same in German
]

# ---------------------------------------------------------------------------
# Tropical segment keywords
#
# Mango, passion fruit, pineapple, coconut, guava, and exotic blends.
# Also claims blends like "Apple & Mango" where tropical fruit is distinctive.
# French: mangue, ananas | German: Mango (same), Ananas
# ---------------------------------------------------------------------------
TROPICAL_KEYWORDS: list[str] = [
    "mango",
    "passion fruit",
    "passionfruit",
    "passion",
    "pineapple",
    "coconut",
    "coconut water",
    "guava",
    "dragon fruit",
    "dragonfruit",
    "tropical",
    "exotic",
    "papaya",
    "lychee",
    "kiwi",
    "peach",
    "apricot",
    "nectarine",
    # French
    "mangue",
    "ananas",
    "coco",
    "peche",
    "abricot",
    # German
    "ananas",
    "kokos",
    "pfirsich",
]

# ---------------------------------------------------------------------------
# Orchard segment keywords
#
# Pear, grape, elderflower, plum, and orchard-fruit blends.
# Single apple goes to the Apple segment; blends with apple here are fine.
# French: poire, raisin | German: Birne, Traube
# ---------------------------------------------------------------------------
ORCHARD_KEYWORDS: list[str] = [
    "elderflower",
    "elder flower",
    "grape",
    "grapes",
    "pear",
    "pears",
    "prune",
    "plum",
    "rhubarb",
    "quince",
    # French
    "poire",
    "raisin",
    "sureau",             # elderflower in French
    "prune",              # same in French
    # German
    "birne",
    "traube",
    "holunder",           # elderflower in German
    "pflaume",            # plum in German
    "rhabarber",          # rhubarb in German
]

# ---------------------------------------------------------------------------
# Green & Root segment keywords
#
# Ginger, turmeric, beetroot, spirulina, kale, and functional greens blends.
# Tiebreak winner — this segment beats all others when co-present.
# French: gingembre, betterave | German: Ingwer, Rübe
# ---------------------------------------------------------------------------
GREEN_ROOT_KEYWORDS: list[str] = [
    "ginger",
    "turmeric",
    "tumeric",            # common misspelling
    "matcha",
    "spirulina",
    "spinach",
    "kale",
    "cucumber",
    "beetroot",
    "beet",
    "celery",
    "hemp",
    "chlorella",
    "lion's mane",
    "lions mane",
    "sea moss",
    "aloe",
    "aloe vera",
    "camu",
    "wheatgrass",
    "avocado",
    "greens",
    "green",              # for "Green Machine"-style Claims e.g. "Kale, Spinach, Green..."
    "cayenne",
    "pepper",
    "chilli",
    "chili",
    "jalapeno",
    "jalape",             # accent-stripped
    # French
    "gingembre",
    "curcuma",            # turmeric in French
    "betterave",          # beetroot in French
    "concombre",          # cucumber in French
    # German
    "ingwer",
    "kurkuma",            # turmeric in German
    "rote bete",          # beetroot in German
    "gurke",              # cucumber in German
]

# ---------------------------------------------------------------------------
# Berry segment keywords
#
# Strawberry, raspberry, blueberry, blackcurrant, pomegranate, cherry, and blends.
# French: fraise, framboise | German: Erdbeere, Himbeere
# ---------------------------------------------------------------------------
BERRY_KEYWORDS: list[str] = [
    "strawberry",
    "raspberry",
    "blueberry",
    "blackcurrant",
    "cranberry",
    "pomegranate",
    "cherry",
    "blackberry",
    "redcurrant",
    "acai",
    "acai",               # accent-stripped variant
    "gooseberry",
    "berry",
    "berries",
    "mixed berries",
    "summer berries",
    "forest fruits",
    "summer fruits",      # borderline, but often berry-based
    # French
    "fraise",
    "framboise",
    "cassis",             # blackcurrant in French
    "cerise",             # cherry in French
    "myrtille",           # blueberry in French
    # German
    "erdbeere",
    "himbeere",
    "heidelbeere",        # blueberry in German
    "schwarze johannisbeere",  # blackcurrant in German
    "kirsche",            # cherry in German
]

# ---------------------------------------------------------------------------
# Tiebreak priority
#
# When keyword matching finds hits in multiple segments, the segment listed
# FIRST in this list wins. Order: Green & Root → Tropical → Berry → Citrus → Orchard
#
# Orange and Apple are resolved before this tiebreak (Layer 1 special cases).
# ---------------------------------------------------------------------------
TIEBREAK_PRIORITY: list[str] = [
    "Green & Root",
    "Tropical",
    "Berry",
    "Citrus",
    "Orchard",
]

# ---------------------------------------------------------------------------
# All valid Flavor_Profile segment names (for validation and display)
# ---------------------------------------------------------------------------
ALL_SEGMENTS: list[str] = [
    "Orange",
    "Apple",
    "Citrus",
    "Tropical",
    "Orchard",
    "Green & Root",
    "Berry",
    "Other",
]

# ---------------------------------------------------------------------------
# Vegetable / plant-green ingredient keywords  (Contains_Vegetables column)
#
# Scanned across Flavor_Clean, Claims, Notes, and Product Name.
# Matching is case-insensitive and accent-insensitive.
# Single-word keywords use word-boundary matching so "greens" does NOT match
# "greenstone" or "evergreen". Multi-word phrases (e.g. "aloe vera",
# "sweet potato") use substring matching.
#
# Add language-specific translations here for French, German, etc.
# ---------------------------------------------------------------------------
VEGETABLE_KEYWORDS: list[str] = [
    # Core vegetable / plant-green ingredients
    "beetroot",
    "beet",
    "beets",
    "spinach",
    "kale",
    "cucumber",
    "celery",
    "carrot",
    "tomato",
    "avocado",
    "broccoli",
    "pepper",
    "sweet potato",
    "pumpkin",
    "spirulina",
    "chlorella",
    "wheatgrass",
    "aloe",
    "aloe vera",
    "gazpacho",
    "greens",
    # French translations
    "épinard",       # spinach
    "betterave",     # beetroot
    "concombre",     # cucumber
    "carotte",       # carrot
    # German translations
    "gurke",         # cucumber
    "karotte",       # carrot
    "spinat",        # spinach
]

# ---------------------------------------------------------------------------
# Ambiguity signal words for Layer 3 LLM triage  (Contains_Vegetables)
#
# Untagged Flavor_Clean values that contain any of these words (whole-word
# match) are sent to the LLM to decide Yes/No.  This catches products like
# "Green Goodness" or "Wonder Green" that have no explicit veggie keyword
# anywhere in any column.
# ---------------------------------------------------------------------------
VEGETABLE_AMBIGUITY_SIGNALS: list[str] = [
    "green",
    "detox",
    "cleanse",
    "garden",
    "veggie",
    "veg",
    "plant",
    "earth",
    "field",
]
