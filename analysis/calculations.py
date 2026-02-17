"""
Pure calculation functions for slide data generation.

Each function takes a master DataFrame and returns structured DataFrames
ready for charting. No side effects, no file I/O, no plotting — just
data transformations.

All functions handle edge cases gracefully:
- Missing columns → raise ValueError
- Empty DataFrames → return empty with correct schema
- NaN values → excluded from calculations
- Division by zero → return 0.0
"""

import logging
from typing import Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def _validate_required_columns(df: pd.DataFrame, required: list[str]) -> None:
    """
    Raise ValueError if any required columns are missing from df.
    
    Args:
        df: DataFrame to validate
        required: List of column names that must be present
        
    Raises:
        ValueError: If any required columns are missing
    """
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(
            f"Missing required columns: {missing}. "
            f"Available columns: {list(df.columns)}"
        )


def _safe_percentage(numerator: float, denominator: float) -> float:
    """
    Calculate percentage, handling division by zero.
    
    Args:
        numerator: Numerator value
        denominator: Denominator value
        
    Returns:
        (numerator / denominator) * 100, or 0.0 if denominator is 0
    """
    if denominator == 0 or pd.isna(denominator):
        return 0.0
    return (numerator / denominator) * 100


def share_by_category(
    df: pd.DataFrame,
    groupby: str,
    category_col: str,
    value_col: str = "Facings"
) -> pd.DataFrame:
    """
    Calculate percentage share of a category within each group.
    
    Used for: Slide 1 (Market Fingerprint) — 5 different category breakdowns
    
    Args:
        df: Master DataFrame from Tool A
        groupby: Column to group by (e.g., "Retailer")
        category_col: Column to calculate shares for (e.g., "Product Type")
        value_col: Column to sum for shares (default "Facings")
        
    Returns:
        DataFrame with columns: [groupby, category_col, "Count", "Percentage"]
        Example:
            | Retailer | Product Type | Count | Percentage |
            |----------|--------------|-------|------------|
            | Aldi     | Pure Juices  | 120   | 45.5       |
            | Aldi     | Smoothies    | 80    | 30.3       |
            | Aldi     | Shots        | 64    | 24.2       |
            | Lidl     | Pure Juices  | 95    | 52.8       |
            ...
            
    Edge Cases:
        - Missing category_col values → excluded from calculation
        - Empty df → return empty DataFrame with correct schema
        - Division by zero → percentage = 0.0
    """
    _validate_required_columns(df, [groupby, category_col, value_col])
    
    # Define output schema
    output_columns = [groupby, category_col, "Count", "Percentage"]
    
    # Handle empty DataFrame
    if df.empty:
        return pd.DataFrame(columns=output_columns)
    
    # Filter out rows where category_col is NaN
    df_filtered = df[df[category_col].notna()].copy()
    
    if df_filtered.empty:
        return pd.DataFrame(columns=output_columns)
    
    # Group by both dimensions and sum the value column
    grouped = (
        df_filtered
        .groupby([groupby, category_col], dropna=False)[value_col]
        .sum()
        .reset_index()
        .rename(columns={value_col: "Count"})
    )
    
    # Calculate total per group for percentage calculation
    group_totals = (
        grouped
        .groupby(groupby)["Count"]
        .sum()
        .reset_index()
        .rename(columns={"Count": "Total"})
    )
    
    # Merge totals and calculate percentage
    result = grouped.merge(group_totals, on=groupby)
    result["Percentage"] = result.apply(
        lambda row: _safe_percentage(row["Count"], row["Total"]),
        axis=1
    )
    
    # Drop the Total column and sort
    result = result[[groupby, category_col, "Count", "Percentage"]]
    result = result.sort_values([groupby, "Percentage"], ascending=[True, False])
    
    return result.reset_index(drop=True)


def brand_retailer_heatmap(
    df: pd.DataFrame,
    top_n: int = 15
) -> pd.DataFrame:
    """
    Generate brand × retailer heatmap data with additional metrics.
    
    Used for: Slide 2 (Brand Landscape)
    
    Args:
        df: Master DataFrame from Tool A
        top_n: Number of top brands to include (default 15)
        
    Returns:
        DataFrame with columns:
            ["Brand", "Total Market Share", 
             "Aldi", "Lidl", "M&S", "Sainsbury's", "Tesco", "Tesco Express", "Waitrose",
             "% Cold Pressed", "% Functional"]
        
        - Total Market Share: brand facings / grand total (%)
        - Retailer columns: brand facings at retailer / total retailer facings (%)
        - % Cold Pressed: brand facings that are Cold Pressed / brand total (%)
        - % Functional: brand facings that are Functional / brand total (%)
        
        Sorted by Total Market Share descending.
        
    Edge Cases:
        - Fewer than top_n brands → return all available
        - Brand not present at a retailer → 0.0
        - Missing Brand column → raise ValueError
        - Division by zero → 0.0
    """
    _validate_required_columns(df, ["Brand", "Retailer", "Facings"])
    
    # Define retailers in order
    retailers = ["Aldi", "Lidl", "M&S", "Sainsbury's", "Tesco", "Tesco Express", "Waitrose"]
    
    # Define output schema
    output_columns = ["Brand", "Total Market Share"] + retailers + ["% Cold Pressed", "% Functional"]
    
    # Handle empty DataFrame
    if df.empty:
        return pd.DataFrame(columns=output_columns)
    
    # Filter out rows with missing Brand
    df_filtered = df[df["Brand"].notna()].copy()
    
    if df_filtered.empty:
        return pd.DataFrame(columns=output_columns)
    
    # Check if we have the Branded/Private Label column
    has_pl_column = "Branded/Private Label" in df_filtered.columns
    
    # Calculate total facings per brand
    brand_totals = (
        df_filtered
        .groupby("Brand")["Facings"]
        .sum()
        .reset_index()
        .rename(columns={"Facings": "Total_Facings"})
    )
    
    # Select top N brands (excluding space for Private Label aggregate if needed)
    # If we have PL column, reserve 1 spot for the aggregate row
    top_count = min(top_n - 1 if has_pl_column else top_n, len(brand_totals))
    brand_totals = brand_totals.nlargest(top_count, "Total_Facings")
    top_brands = brand_totals["Brand"].tolist()
    
    # Filter to top brands only
    df_top = df_filtered[df_filtered["Brand"].isin(top_brands)].copy()
    
    # Calculate grand total for market share
    grand_total = df_filtered["Facings"].sum()
    
    # Calculate Total Market Share
    brand_totals["Total Market Share"] = brand_totals["Total_Facings"].apply(
        lambda x: _safe_percentage(x, grand_total)
    )
    
    # Initialize result with Brand and Total Market Share
    result = brand_totals[["Brand", "Total Market Share"]].copy()
    
    # Calculate share per retailer
    for retailer in retailers:
        # Get retailer total facings
        retailer_total = df_filtered[df_filtered["Retailer"] == retailer]["Facings"].sum()
        
        # Get brand facings at this retailer
        brand_at_retailer = (
            df_top[df_top["Retailer"] == retailer]
            .groupby("Brand")["Facings"]
            .sum()
            .reset_index()
            .rename(columns={"Facings": f"{retailer}_Facings"})
        )
        
        # Merge and calculate percentage
        result = result.merge(brand_at_retailer, on="Brand", how="left")
        result[f"{retailer}_Facings"] = result[f"{retailer}_Facings"].fillna(0)
        result[retailer] = result[f"{retailer}_Facings"].apply(
            lambda x: _safe_percentage(x, retailer_total)
        )
        result = result.drop(columns=[f"{retailer}_Facings"])
    
    # Calculate % Cold Pressed (if column exists)
    if "Juice Extraction Method" in df_top.columns:
        cold_pressed = (
            df_top[df_top["Juice Extraction Method"] == "Cold Pressed"]
            .groupby("Brand")["Facings"]
            .sum()
            .reset_index()
            .rename(columns={"Facings": "Cold_Pressed_Facings"})
        )
        result = result.merge(cold_pressed, on="Brand", how="left")
        result["Cold_Pressed_Facings"] = result["Cold_Pressed_Facings"].fillna(0)
        result["% Cold Pressed"] = result.apply(
            lambda row: _safe_percentage(
                row["Cold_Pressed_Facings"],
                brand_totals[brand_totals["Brand"] == row["Brand"]]["Total_Facings"].iloc[0]
            ),
            axis=1
        )
        result = result.drop(columns=["Cold_Pressed_Facings"])
    else:
        result["% Cold Pressed"] = 0.0
    
    # Calculate % Functional (if column exists)
    if "Need State" in df_top.columns:
        functional = (
            df_top[df_top["Need State"] == "Functional"]
            .groupby("Brand")["Facings"]
            .sum()
            .reset_index()
            .rename(columns={"Facings": "Functional_Facings"})
        )
        result = result.merge(functional, on="Brand", how="left")
        result["Functional_Facings"] = result["Functional_Facings"].fillna(0)
        result["% Functional"] = result.apply(
            lambda row: _safe_percentage(
                row["Functional_Facings"],
                brand_totals[brand_totals["Brand"] == row["Brand"]]["Total_Facings"].iloc[0]
            ),
            axis=1
        )
        result = result.drop(columns=["Functional_Facings"])
    else:
        result["% Functional"] = 0.0
    
    # Add aggregated "Private Label" row if the column exists
    if has_pl_column:
        # Get all Private Label products
        pl_df = df_filtered[df_filtered["Branded/Private Label"] == "Private Label"].copy()
        
        if not pl_df.empty:
            pl_total_facings = pl_df["Facings"].sum()
            pl_market_share = _safe_percentage(pl_total_facings, grand_total)
            
            # Build the Private Label row
            pl_row = {"Brand": "Private Label", "Total Market Share": pl_market_share}
            
            # Calculate share per retailer
            for retailer in retailers:
                retailer_total = df_filtered[df_filtered["Retailer"] == retailer]["Facings"].sum()
                pl_retailer_facings = pl_df[pl_df["Retailer"] == retailer]["Facings"].sum()
                pl_row[retailer] = _safe_percentage(pl_retailer_facings, retailer_total)
            
            # Calculate % Cold Pressed for Private Label
            if "Juice Extraction Method" in pl_df.columns:
                pl_cp_facings = pl_df[pl_df["Juice Extraction Method"] == "Cold Pressed"]["Facings"].sum()
                pl_row["% Cold Pressed"] = _safe_percentage(pl_cp_facings, pl_total_facings)
            else:
                pl_row["% Cold Pressed"] = 0.0
            
            # Calculate % Functional for Private Label
            if "Need State" in pl_df.columns:
                pl_func_facings = pl_df[pl_df["Need State"] == "Functional"]["Facings"].sum()
                pl_row["% Functional"] = _safe_percentage(pl_func_facings, pl_total_facings)
            else:
                pl_row["% Functional"] = 0.0
            
            # Append the Private Label row
            result = pd.concat([result, pd.DataFrame([pl_row])], ignore_index=True)
    
    # Sort by Total Market Share descending
    result = result.sort_values("Total Market Share", ascending=False)
    
    # Ensure all output columns are present
    for col in output_columns:
        if col not in result.columns:
            result[col] = 0.0
    
    return result[output_columns].reset_index(drop=True)


def retailer_sizing(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Calculate retailer sizing metrics: SKU counts and category shares.
    
    Used for: Slide 3 (Retailer Sizing) — table + chart
    
    Args:
        df: Master DataFrame from Tool A
        
    Returns:
        Tuple of (table_data, chart_data):
        
        table_data: DataFrame with columns:
            ["Retailer", "Store Format", "Avg SKU Count", "Avg Facings"]
            - One row per retailer × format combination
            - Avg SKU Count: unique products per store
            - Avg Facings: total facings per store
            
        chart_data: DataFrame with columns:
            ["Retailer", "% PL", "% HPP", "% Cold Pressed"]
            - One row per retailer
            - Each % is share of total facings for that retailer
            
    Edge Cases:
        - Retailer with no Store Format → format = "Unknown"
        - Single store per retailer × format → avg = that store's value
        - Missing category values → excluded from percentage calculation
    """
    _validate_required_columns(df, ["Retailer", "Store Name", "Facings"])
    
    # Handle empty DataFrame
    if df.empty:
        table_data = pd.DataFrame(columns=["Retailer", "Store Format", "Avg SKU Count", "Avg Facings"])
        chart_data = pd.DataFrame(columns=["Retailer", "% PL", "% HPP", "% Cold Pressed"])
        return table_data, chart_data
    
    # Fill missing Store Format with "Unknown"
    df_copy = df.copy()
    if "Store Format" not in df_copy.columns:
        df_copy["Store Format"] = "Unknown"
    else:
        df_copy["Store Format"] = df_copy["Store Format"].fillna("Unknown")
    
    # TABLE DATA: Calculate per-store metrics, then average by retailer × format
    store_metrics = (
        df_copy
        .groupby(["Retailer", "Store Format", "Store Name"])
        .agg(
            SKU_Count=("Product Name", "nunique"),
            Total_Facings=("Facings", "sum")
        )
        .reset_index()
    )
    
    table_data = (
        store_metrics
        .groupby(["Retailer", "Store Format"])
        .agg(
            Avg_SKU_Count=("SKU_Count", "mean"),
            Avg_Facings=("Total_Facings", "mean")
        )
        .reset_index()
        .rename(columns={
            "Avg_SKU_Count": "Avg SKU Count",
            "Avg_Facings": "Avg Facings"
        })
    )
    
    # Round to whole numbers for readability
    table_data["Avg SKU Count"] = table_data["Avg SKU Count"].round(0).astype(int)
    table_data["Avg Facings"] = table_data["Avg Facings"].round(0).astype(int)
    
    # CHART DATA: Calculate category shares per retailer
    retailers = df_copy["Retailer"].unique()
    chart_rows = []
    
    for retailer in retailers:
        retailer_df = df_copy[df_copy["Retailer"] == retailer]
        total_facings = retailer_df["Facings"].sum()
        
        # % PL
        if "Branded/Private Label" in retailer_df.columns:
            pl_facings = retailer_df[
                retailer_df["Branded/Private Label"] == "Private Label"
            ]["Facings"].sum()
            pct_pl = _safe_percentage(pl_facings, total_facings)
        else:
            pct_pl = 0.0
        
        # % HPP
        if "HPP Treatment" in retailer_df.columns:
            hpp_facings = retailer_df[
                retailer_df["HPP Treatment"] == "Yes"
            ]["Facings"].sum()
            pct_hpp = _safe_percentage(hpp_facings, total_facings)
        else:
            pct_hpp = 0.0
        
        # % Cold Pressed
        if "Juice Extraction Method" in retailer_df.columns:
            cp_facings = retailer_df[
                retailer_df["Juice Extraction Method"] == "Cold Pressed"
            ]["Facings"].sum()
            pct_cp = _safe_percentage(cp_facings, total_facings)
        else:
            pct_cp = 0.0
        
        chart_rows.append({
            "Retailer": retailer,
            "% PL": pct_pl,
            "% HPP": pct_hpp,
            "% Cold Pressed": pct_cp
        })
    
    chart_data = pd.DataFrame(chart_rows)
    
    return table_data, chart_data


def retailer_deep_dive(
    df: pd.DataFrame,
    retailer: str
) -> dict[str, pd.DataFrame]:
    """
    Generate all four charts for a single retailer's deep dive slide.
    
    Used for: Slides 4-10 (Retailer Deep Dives)
    
    Args:
        df: Master DataFrame from Tool A
        retailer: Retailer name (e.g., "Aldi")
        
    Returns:
        Dict with keys: ["product_type", "pl_vs_branded", "extraction", "need_state"]
        Each value is a DataFrame:
        
        - product_type: ["Product Type", "Facings"]
        - pl_vs_branded: ["Branded/Private Label", "Percentage"]
        - extraction: ["Juice Extraction Method", "Percentage"]
        - need_state: ["Need State", "Percentage"]
        
    Edge Cases:
        - Retailer not in data → return empty DataFrames with correct schema
        - Missing category values → excluded from calculation
        - Only one category present → other categories have 0 rows
    """
    _validate_required_columns(df, ["Retailer", "Facings"])
    
    # Filter to retailer
    retailer_df = df[df["Retailer"] == retailer].copy()
    
    # Initialize result dict with empty DataFrames
    result = {
        "product_type": pd.DataFrame(columns=["Product Type", "Facings"]),
        "pl_vs_branded": pd.DataFrame(columns=["Branded/Private Label", "Percentage"]),
        "extraction": pd.DataFrame(columns=["Juice Extraction Method", "Percentage"]),
        "need_state": pd.DataFrame(columns=["Need State", "Percentage"])
    }
    
    # If retailer not found, return empty DataFrames
    if retailer_df.empty:
        logger.warning(f"Retailer '{retailer}' not found in data")
        return result
    
    total_facings = retailer_df["Facings"].sum()
    
    # 1. Product Type (absolute facings)
    if "Product Type" in retailer_df.columns:
        product_type_df = (
            retailer_df[retailer_df["Product Type"].notna()]
            .groupby("Product Type")["Facings"]
            .sum()
            .reset_index()
            .sort_values("Facings", ascending=False)
        )
        result["product_type"] = product_type_df
    
    # 2. PL vs Branded (percentage)
    if "Branded/Private Label" in retailer_df.columns:
        pl_branded_df = (
            retailer_df[retailer_df["Branded/Private Label"].notna()]
            .groupby("Branded/Private Label")["Facings"]
            .sum()
            .reset_index()
        )
        pl_branded_df["Percentage"] = pl_branded_df["Facings"].apply(
            lambda x: _safe_percentage(x, total_facings)
        )
        result["pl_vs_branded"] = pl_branded_df[["Branded/Private Label", "Percentage"]]
    
    # 3. Juice Extraction Method (percentage)
    if "Juice Extraction Method" in retailer_df.columns:
        extraction_df = (
            retailer_df[retailer_df["Juice Extraction Method"].notna()]
            .groupby("Juice Extraction Method")["Facings"]
            .sum()
            .reset_index()
        )
        extraction_df["Percentage"] = extraction_df["Facings"].apply(
            lambda x: _safe_percentage(x, total_facings)
        )
        result["extraction"] = extraction_df[["Juice Extraction Method", "Percentage"]]
    
    # 4. Need State (percentage)
    if "Need State" in retailer_df.columns:
        need_state_df = (
            retailer_df[retailer_df["Need State"].notna()]
            .groupby("Need State")["Facings"]
            .sum()
            .reset_index()
        )
        need_state_df["Percentage"] = need_state_df["Facings"].apply(
            lambda x: _safe_percentage(x, total_facings)
        )
        result["need_state"] = need_state_df[["Need State", "Percentage"]]
    
    return result


def market_fingerprint(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Generate all five category breakdowns for the Market Fingerprint slide.
    
    Used for: Slide 1 (Market Fingerprint)
    
    Args:
        df: Master DataFrame from Tool A
        
    Returns:
        Dict with keys: ["product_type", "pl_vs_branded", "extraction", "hpp", "need_state"]
        Each value is a DataFrame from share_by_category():
            ["Retailer", category_col, "Count", "Percentage"]
            
    Edge Cases:
        - Same as share_by_category() for each category
    """
    _validate_required_columns(df, ["Retailer", "Facings"])
    
    result = {}
    
    # 1. Product Type
    if "Product Type" in df.columns:
        result["product_type"] = share_by_category(
            df, groupby="Retailer", category_col="Product Type"
        )
    else:
        result["product_type"] = pd.DataFrame(
            columns=["Retailer", "Product Type", "Count", "Percentage"]
        )
    
    # 2. PL vs Branded
    if "Branded/Private Label" in df.columns:
        result["pl_vs_branded"] = share_by_category(
            df, groupby="Retailer", category_col="Branded/Private Label"
        )
    else:
        result["pl_vs_branded"] = pd.DataFrame(
            columns=["Retailer", "Branded/Private Label", "Count", "Percentage"]
        )
    
    # 3. Juice Extraction Method
    if "Juice Extraction Method" in df.columns:
        result["extraction"] = share_by_category(
            df, groupby="Retailer", category_col="Juice Extraction Method"
        )
    else:
        result["extraction"] = pd.DataFrame(
            columns=["Retailer", "Juice Extraction Method", "Count", "Percentage"]
        )
    
    # 4. HPP Treatment
    if "HPP Treatment" in df.columns:
        result["hpp"] = share_by_category(
            df, groupby="Retailer", category_col="HPP Treatment"
        )
    else:
        result["hpp"] = pd.DataFrame(
            columns=["Retailer", "HPP Treatment", "Count", "Percentage"]
        )
    
    # 5. Need State
    if "Need State" in df.columns:
        result["need_state"] = share_by_category(
            df, groupby="Retailer", category_col="Need State"
        )
    else:
        result["need_state"] = pd.DataFrame(
            columns=["Retailer", "Need State", "Count", "Percentage"]
        )
    
    return result
