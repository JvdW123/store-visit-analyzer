"""
Master schema definitions for the consolidated output file.

Defines column order, data types, required fields, and valid categorical values.
Source of truth: docs/SCHEMA.md
"""

# Master column names in the exact output order.
# Every DataFrame produced by the pipeline ends up with these columns.
MASTER_COLUMNS: list[str] = [
    "Country",
    "City",
    "Retailer",
    "Store Format",
    "Store Name",
    "Photo",
    "Shelf Location",
    "Shelf Levels",
    "Shelf Level",
    "Product Type",
    "Branded/Private Label",
    "Brand",
    "Sub-brand",
    "Product Name",
    "Flavor",
    "Flavor_Clean",
    "Single_or_Blend",
    "Flavor_Profile",
    "Contains_Vegetables",
    "Facings",
    "Price (Local Currency)",
    "Currency",
    "Price (EUR)",
    "Packaging Size (ml)",
    "Price per Liter (EUR)",
    "Need State",
    "Juice Extraction Method",
    "Processing Method",
    "HPP Treatment",
    "Packaging Type",
    "Claims",
    "Bonus/Promotions",
    "Stock Status",
    "Est. Linear Meters",
    "Fridge Number",
    "Confidence Score",
    "Notes",
]

# Expected Python types for each column.
# "text" = str, "integer" = int, "float" = float
COLUMN_TYPES: dict[str, str] = {
    "Country": "text",
    "City": "text",
    "Retailer": "text",
    "Store Format": "text",
    "Store Name": "text",
    "Photo": "text",
    "Shelf Location": "text",
    "Shelf Levels": "integer",
    "Shelf Level": "text",
    "Product Type": "text",
    "Branded/Private Label": "text",
    "Brand": "text",
    "Sub-brand": "text",
    "Product Name": "text",
    "Flavor": "text",
    "Flavor_Clean": "text",
    "Single_or_Blend": "text",
    "Flavor_Profile": "text",
    "Contains_Vegetables": "text",
    "Facings": "integer",
    "Price (Local Currency)": "float",
    "Currency": "text",
    "Price (EUR)": "float",
    "Packaging Size (ml)": "integer",
    "Price per Liter (EUR)": "float",
    "Need State": "text",
    "Juice Extraction Method": "text",
    "Processing Method": "text",
    "HPP Treatment": "text",
    "Packaging Type": "text",
    "Claims": "text",
    "Bonus/Promotions": "text",
    "Stock Status": "text",
    "Est. Linear Meters": "float",
    "Fridge Number": "text",
    "Confidence Score": "integer",
    "Notes": "text",
}

# Columns that must be populated in the final output.
# Derived columns (Country, Currency, Store Name) are filled by the pipeline.
REQUIRED_COLUMNS: list[str] = [
    "Country",
    "City",
    "Retailer",
    "Store Name",
    "Currency",
]

# Valid categorical values for columns with constrained value sets.
# Values not in these sets are flagged for LLM or manual review.
VALID_VALUES: dict[str, set[str]] = {
    "Store Format": {"Hypermarket", "Supermarket", "Discount", "Convenience", "Other"},
    "Shelf Location": {
        "Chilled Section",
        "To-Go Section",
        "To-Go Section — Shots",
        "Meal Deal Section",
    },
    "Shelf Level": {"1st", "2nd", "3rd", "4th", "5th", "6th"},
    "Product Type": {"Pure Juices", "Smoothies", "Shots", "Other"},
    "Branded/Private Label": {"Branded", "Private Label"},
    "Need State": {"Indulgence", "Functional"},
    "Juice Extraction Method": {"Squeezed", "Cold Pressed", "From Concentrate", "NA/Centrifugal"},
    "Processing Method": {
        "Pasteurized",
        "HPP",
        "Raw",
    },
    "HPP Treatment": {"Yes", "No"},
    "Packaging Type": {"PET Bottle", "Tetra Pak", "Can", "Carton", "Glass Bottle"},
    "Stock Status": {"In Stock", "Out of Stock"},
    "Currency": {"GBP", "EUR"},
}
