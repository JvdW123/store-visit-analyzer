"""
Generate a test PowerPoint presentation using mock data.

This script creates a complete 10-slide presentation with all chart types
to verify visual styling and layout.
"""

from pathlib import Path
import pandas as pd

from output.pptx_generator import generate_presentation
from output.style import DEFAULT_TEMPLATE_PATH, DEFAULT_LOGO_PATH

# Mock data matching the test fixtures
RETAILERS = ["Aldi", "Lidl", "M&S", "Sainsbury's", "Tesco", "Tesco Express", "Waitrose"]


def _make_share_by_category_df(
    groupby_col: str,
    category_col: str,
    categories: list[str],
) -> pd.DataFrame:
    """Create a mock DataFrame matching share_by_category() output."""
    rows = []
    for retailer in RETAILERS:
        total = 100.0
        per_cat = total / len(categories)
        for cat in categories:
            rows.append({
                groupby_col: retailer,
                category_col: cat,
                "Count": int(per_cat),
                "Percentage": per_cat,
            })
    return pd.DataFrame(rows)


def _make_market_fingerprint_data() -> dict[str, pd.DataFrame]:
    """Mock data for slide 1 (market_fingerprint return type)."""
    return {
        "product_type": _make_share_by_category_df(
            "Retailer", "Product Type",
            ["Pure Juices", "Smoothies", "Shots"],
        ),
        "pl_vs_branded": _make_share_by_category_df(
            "Retailer", "Branded/Private Label",
            ["Private Label", "Branded"],
        ),
        "extraction": _make_share_by_category_df(
            "Retailer", "Juice Extraction Method",
            ["Cold Pressed", "Centrifugal"],
        ),
        "hpp": _make_share_by_category_df(
            "Retailer", "HPP Treatment",
            ["Yes", "No"],
        ),
        "need_state": _make_share_by_category_df(
            "Retailer", "Need State",
            ["Indulgence", "Functional"],
        ),
    }


def _make_brand_heatmap_data() -> pd.DataFrame:
    """Mock data for slide 2 (brand_retailer_heatmap return type)."""
    brands = [f"Brand_{i}" for i in range(1, 11)]
    rows = []
    for brand in brands:
        row = {
            "Brand": brand,
            "Total Market Share": round(10.0 / len(brands), 1),
        }
        for retailer in RETAILERS:
            row[retailer] = round(100.0 / len(brands), 1)
        row["% Cold Pressed"] = 25.0
        row["% Functional"] = 15.0
        rows.append(row)
    
    # Add Private Label aggregated row
    pl_row = {
        "Brand": "Private Label",
        "Total Market Share": 15.0,
    }
    for retailer in RETAILERS:
        pl_row[retailer] = 12.0
    pl_row["% Cold Pressed"] = 30.0
    pl_row["% Functional"] = 20.0
    rows.append(pl_row)
    
    return pd.DataFrame(rows)


def _make_retailer_sizing_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Mock data for slide 3 (retailer_sizing return type)."""
    table_data = pd.DataFrame([
        {"Retailer": r, "Store Format": "Supermarket", "Avg SKU Count": 45, "Avg Facings": 120}
        for r in RETAILERS
    ])
    chart_data = pd.DataFrame([
        {"Retailer": r, "% PL": 30.0, "% HPP": 45.0, "% Cold Pressed": 25.0}
        for r in RETAILERS
    ])
    return table_data, chart_data


def _make_retailer_deep_dive_data() -> dict[str, pd.DataFrame]:
    """Mock data for slides 4-10 (retailer_deep_dive return type)."""
    return {
        "product_type": pd.DataFrame([
            {"Product Type": "Pure Juices", "Facings": 80},
            {"Product Type": "Smoothies", "Facings": 60},
            {"Product Type": "Shots", "Facings": 20},
        ]),
        "pl_vs_branded": pd.DataFrame([
            {"Branded/Private Label": "Branded", "Percentage": 65.0},
            {"Branded/Private Label": "Private Label", "Percentage": 35.0},
        ]),
        "extraction": pd.DataFrame([
            {"Juice Extraction Method": "Cold Pressed", "Percentage": 40.0},
            {"Juice Extraction Method": "Centrifugal", "Percentage": 60.0},
        ]),
        "need_state": pd.DataFrame([
            {"Need State": "Indulgence", "Percentage": 55.0},
            {"Need State": "Functional", "Percentage": 45.0},
        ]),
    }


def _make_complete_slide_data() -> dict[int, any]:
    """Create a complete set of mock data for all 10 slides."""
    slide_data = {
        1: _make_market_fingerprint_data(),
        2: _make_brand_heatmap_data(),
        3: _make_retailer_sizing_data(),
    }
    # Slides 4-10: retailer deep dives
    for slide_num in range(4, 11):
        slide_data[slide_num] = _make_retailer_deep_dive_data()
    return slide_data


if __name__ == "__main__":
    print("Generating test presentation...")
    
    slide_data = _make_complete_slide_data()
    output_path = Path("test_output_new.pptx")
    
    result = generate_presentation(
        slide_data=slide_data,
        template_path=DEFAULT_TEMPLATE_PATH,
        logo_path=DEFAULT_LOGO_PATH,
        output_path=output_path,
    )
    
    print(f"[OK] Presentation generated: {result}")
    print(f"  File size: {result.stat().st_size / 1024:.1f} KB")
