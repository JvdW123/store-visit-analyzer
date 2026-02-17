"""
Storyline configuration for Tool B slide deck.

Defines the structure, content, and visual style for all 10 slides.
Each slide is configured declaratively with metadata that drives the
analysis engine and PowerPoint generator.

Source of truth for: slide order, titles, chart types, analysis functions,
brand colors, and chart color schemes.
"""

from typing import Any, TypedDict


class SlideConfig(TypedDict):
    """Configuration for a single slide."""
    slide_number: int
    title_template: str
    chart_type: str
    analysis_function: str
    params: dict[str, Any]
    layout: dict[str, Any]


# Brand colors for Fruity Line visual identity
BRAND_COLORS: dict[str, str] = {
    "primary": "#FF6B35",      # Fruity Line orange
    "secondary": "#004E89",    # Deep blue
    "accent": "#F7B801",       # Golden yellow
    "neutral_dark": "#2C3E50", # Dark gray
    "neutral_light": "#ECF0F1" # Light gray
}

# Chart color schemes for consistent visual style
CHART_COLORS: dict[str, Any] = {
    # For categorical data (Product Type, etc.)
    "categorical": [
        "#FF6B35",  # Orange
        "#004E89",  # Blue
        "#F7B801",  # Yellow
        "#1B998B",  # Teal
        "#C73E1D",  # Red
        "#6A4C93",  # Purple
    ],
    
    # For binary splits (PL vs Branded, HPP vs non-HPP)
    "binary": ["#FF6B35", "#004E89"],
    
    # For heatmaps (low to high)
    "heatmap": ["#FFFFFF", "#FFE5D9", "#FFCAB0", "#FF6B35", "#C73E1D"],
    
    # For retailers (consistent across all charts)
    "retailers": {
        "Aldi": "#00A0E3",
        "Lidl": "#FFD500",
        "M&S": "#006747",
        "Sainsbury's": "#F06C00",
        "Tesco": "#00539F",
        "Tesco Express": "#00539F",  # Same as Tesco
        "Waitrose": "#008C45",
    }
}

# Complete storyline: all 10 slides in order
STORYLINE: list[SlideConfig] = [
    # Slide 1: Market Fingerprint
    {
        "slide_number": 1,
        "title_template": "Market Fingerprint",
        "chart_type": "grouped_bar_grid",
        "analysis_function": "market_fingerprint",
        "params": {},
        "layout": {
            "charts": [
                {
                    "title": "% by Product Type",
                    "groupby": "Retailer",
                    "category": "Product Type"
                },
                {
                    "title": "% PL vs Branded",
                    "groupby": "Retailer",
                    "category": "Branded/Private Label"
                },
                {
                    "title": "% Cold Pressed vs Other",
                    "groupby": "Retailer",
                    "category": "Juice Extraction Method"
                },
                {
                    "title": "% HPP vs Non-HPP",
                    "groupby": "Retailer",
                    "category": "HPP Treatment"
                },
                {
                    "title": "% Indulgence vs Functional",
                    "groupby": "Retailer",
                    "category": "Need State"
                },
            ]
        }
    },
    
    # Slide 2: Brand Landscape
    {
        "slide_number": 2,
        "title_template": "Brand Landscape",
        "chart_type": "heatmap",
        "analysis_function": "brand_retailer_heatmap",
        "params": {"top_n": 15},
        "layout": {
            "columns": [
                "Brand",
                "Total Market Share",
                "Aldi",
                "Lidl",
                "M&S",
                "Sainsbury's",
                "Tesco",
                "Tesco Express",
                "Waitrose",
                "% Cold Pressed",
                "% Functional"
            ]
        }
    },
    
    # Slide 3: Retailer Sizing
    {
        "slide_number": 3,
        "title_template": "Retailer Sizing",
        "chart_type": "combo",
        "analysis_function": "retailer_sizing",
        "params": {},
        "layout": {
            "table_columns": [
                "Retailer",
                "Store Format",
                "Avg SKU Count",
                "Avg Facings"
            ],
            "chart_metrics": ["% PL", "% HPP", "% Cold Pressed"]
        }
    },
    
    # Slides 4-10: Retailer Deep Dives
    {
        "slide_number": 4,
        "title_template": "Aldi Deep Dive",
        "chart_type": "four_bar_grid",
        "analysis_function": "retailer_deep_dive",
        "params": {"retailer": "Aldi"},
        "layout": {
            "charts": [
                {
                    "title": "Facings by Product Type",
                    "category": "Product Type",
                    "metric": "absolute"
                },
                {
                    "title": "% PL vs Branded",
                    "category": "Branded/Private Label",
                    "metric": "percentage"
                },
                {
                    "title": "% Cold Pressed vs Other",
                    "category": "Juice Extraction Method",
                    "metric": "percentage"
                },
                {
                    "title": "% Indulgence vs Functional",
                    "category": "Need State",
                    "metric": "percentage"
                },
            ]
        }
    },
    {
        "slide_number": 5,
        "title_template": "Lidl Deep Dive",
        "chart_type": "four_bar_grid",
        "analysis_function": "retailer_deep_dive",
        "params": {"retailer": "Lidl"},
        "layout": {
            "charts": [
                {
                    "title": "Facings by Product Type",
                    "category": "Product Type",
                    "metric": "absolute"
                },
                {
                    "title": "% PL vs Branded",
                    "category": "Branded/Private Label",
                    "metric": "percentage"
                },
                {
                    "title": "% Cold Pressed vs Other",
                    "category": "Juice Extraction Method",
                    "metric": "percentage"
                },
                {
                    "title": "% Indulgence vs Functional",
                    "category": "Need State",
                    "metric": "percentage"
                },
            ]
        }
    },
    {
        "slide_number": 6,
        "title_template": "M&S Deep Dive",
        "chart_type": "four_bar_grid",
        "analysis_function": "retailer_deep_dive",
        "params": {"retailer": "M&S"},
        "layout": {
            "charts": [
                {
                    "title": "Facings by Product Type",
                    "category": "Product Type",
                    "metric": "absolute"
                },
                {
                    "title": "% PL vs Branded",
                    "category": "Branded/Private Label",
                    "metric": "percentage"
                },
                {
                    "title": "% Cold Pressed vs Other",
                    "category": "Juice Extraction Method",
                    "metric": "percentage"
                },
                {
                    "title": "% Indulgence vs Functional",
                    "category": "Need State",
                    "metric": "percentage"
                },
            ]
        }
    },
    {
        "slide_number": 7,
        "title_template": "Sainsbury's Deep Dive",
        "chart_type": "four_bar_grid",
        "analysis_function": "retailer_deep_dive",
        "params": {"retailer": "Sainsbury's"},
        "layout": {
            "charts": [
                {
                    "title": "Facings by Product Type",
                    "category": "Product Type",
                    "metric": "absolute"
                },
                {
                    "title": "% PL vs Branded",
                    "category": "Branded/Private Label",
                    "metric": "percentage"
                },
                {
                    "title": "% Cold Pressed vs Other",
                    "category": "Juice Extraction Method",
                    "metric": "percentage"
                },
                {
                    "title": "% Indulgence vs Functional",
                    "category": "Need State",
                    "metric": "percentage"
                },
            ]
        }
    },
    {
        "slide_number": 8,
        "title_template": "Tesco Deep Dive",
        "chart_type": "four_bar_grid",
        "analysis_function": "retailer_deep_dive",
        "params": {"retailer": "Tesco"},
        "layout": {
            "charts": [
                {
                    "title": "Facings by Product Type",
                    "category": "Product Type",
                    "metric": "absolute"
                },
                {
                    "title": "% PL vs Branded",
                    "category": "Branded/Private Label",
                    "metric": "percentage"
                },
                {
                    "title": "% Cold Pressed vs Other",
                    "category": "Juice Extraction Method",
                    "metric": "percentage"
                },
                {
                    "title": "% Indulgence vs Functional",
                    "category": "Need State",
                    "metric": "percentage"
                },
            ]
        }
    },
    {
        "slide_number": 9,
        "title_template": "Tesco Express Deep Dive",
        "chart_type": "four_bar_grid",
        "analysis_function": "retailer_deep_dive",
        "params": {"retailer": "Tesco Express"},
        "layout": {
            "charts": [
                {
                    "title": "Facings by Product Type",
                    "category": "Product Type",
                    "metric": "absolute"
                },
                {
                    "title": "% PL vs Branded",
                    "category": "Branded/Private Label",
                    "metric": "percentage"
                },
                {
                    "title": "% Cold Pressed vs Other",
                    "category": "Juice Extraction Method",
                    "metric": "percentage"
                },
                {
                    "title": "% Indulgence vs Functional",
                    "category": "Need State",
                    "metric": "percentage"
                },
            ]
        }
    },
    {
        "slide_number": 10,
        "title_template": "Waitrose Deep Dive",
        "chart_type": "four_bar_grid",
        "analysis_function": "retailer_deep_dive",
        "params": {"retailer": "Waitrose"},
        "layout": {
            "charts": [
                {
                    "title": "Facings by Product Type",
                    "category": "Product Type",
                    "metric": "absolute"
                },
                {
                    "title": "% PL vs Branded",
                    "category": "Branded/Private Label",
                    "metric": "percentage"
                },
                {
                    "title": "% Cold Pressed vs Other",
                    "category": "Juice Extraction Method",
                    "metric": "percentage"
                },
                {
                    "title": "% Indulgence vs Functional",
                    "category": "Need State",
                    "metric": "percentage"
                },
            ]
        }
    },
]


def get_slide_config(slide_number: int) -> SlideConfig:
    """
    Retrieve configuration for a specific slide.
    
    Args:
        slide_number: 1-10
        
    Returns:
        SlideConfig dict for that slide
        
    Raises:
        ValueError: If slide_number not in range 1-10
    """
    if not 1 <= slide_number <= 10:
        raise ValueError(f"Slide number must be 1-10, got {slide_number}")
    
    for slide in STORYLINE:
        if slide["slide_number"] == slide_number:
            return slide
    
    raise ValueError(f"Slide {slide_number} not found in STORYLINE")


def get_retailer_slides() -> list[SlideConfig]:
    """
    Get all retailer deep dive slide configs (slides 4-10).
    
    Returns:
        List of 7 SlideConfig dicts, one per retailer
    """
    return [slide for slide in STORYLINE if 4 <= slide["slide_number"] <= 10]


def validate_storyline() -> list[str]:
    """
    Validate STORYLINE config for completeness and consistency.
    
    Checks:
    - All slide numbers 1-10 present and unique
    - All analysis_function names are non-empty strings
    - All required keys present in each slide config
    - All chart_types are valid
    
    Returns:
        List of validation error messages (empty if valid)
    """
    errors: list[str] = []
    
    # Check slide numbers
    slide_numbers = [slide["slide_number"] for slide in STORYLINE]
    expected_numbers = list(range(1, 11))
    
    if sorted(slide_numbers) != expected_numbers:
        errors.append(
            f"Slide numbers must be 1-10 (unique). Found: {sorted(slide_numbers)}"
        )
    
    # Check each slide config
    required_keys = [
        "slide_number",
        "title_template",
        "chart_type",
        "analysis_function",
        "params",
        "layout"
    ]
    
    valid_chart_types = [
        "grouped_bar_grid",
        "heatmap",
        "combo",
        "four_bar_grid"
    ]
    
    for slide in STORYLINE:
        slide_num = slide.get("slide_number", "unknown")
        
        # Check required keys
        for key in required_keys:
            if key not in slide:
                errors.append(f"Slide {slide_num}: missing required key '{key}'")
        
        # Check analysis_function is non-empty
        func_name = slide.get("analysis_function", "")
        if not func_name or not isinstance(func_name, str):
            errors.append(
                f"Slide {slide_num}: analysis_function must be a non-empty string"
            )
        
        # Check chart_type is valid
        chart_type = slide.get("chart_type", "")
        if chart_type not in valid_chart_types:
            errors.append(
                f"Slide {slide_num}: invalid chart_type '{chart_type}'. "
                f"Must be one of: {valid_chart_types}"
            )
    
    return errors
