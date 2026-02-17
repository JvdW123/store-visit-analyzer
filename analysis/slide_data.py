"""
Slide data orchestrator for Tool B.

Connects the storyline configuration to the calculation functions.
Reads the config, calls the right functions, returns structured slide data.

This module acts as the bridge between declarative configuration (storyline.py)
and pure calculation functions (calculations.py).
"""

import logging
from typing import Any

import pandas as pd

from config import storyline
from analysis import calculations

logger = logging.getLogger(__name__)


def _call_analysis_function(
    func_name: str,
    df: pd.DataFrame,
    params: dict
) -> Any:
    """
    Dynamically call an analysis function by name.
    
    Args:
        func_name: Name of function in calculations.py
        df: Master DataFrame
        params: Dict of parameters to pass to the function
        
    Returns:
        Result from the analysis function
        
    Raises:
        AttributeError: If function doesn't exist in calculations.py
        TypeError: If params don't match function signature
    """
    # Get the function from calculations module
    if not hasattr(calculations, func_name):
        raise AttributeError(
            f"Function '{func_name}' not found in calculations module. "
            f"Available functions: {[name for name in dir(calculations) if not name.startswith('_')]}"
        )
    
    func = getattr(calculations, func_name)
    
    # Call the function with df and unpacked params
    return func(df, **params)


def generate_slide_data(
    master_df: pd.DataFrame,
    slide_number: int
) -> Any:
    """
    Generate data for a single slide.
    
    Args:
        master_df: Master DataFrame from Tool A
        slide_number: 1-10
        
    Returns:
        Slide data (format depends on analysis function)
        
    Raises:
        ValueError: If slide_number invalid or config missing
    """
    # Get slide config
    slide_config = storyline.get_slide_config(slide_number)
    
    # Extract function name and params
    func_name = slide_config["analysis_function"]
    params = slide_config["params"]
    
    logger.info(
        f"Generating data for slide {slide_number}: {slide_config['title_template']}"
    )
    
    # Call the analysis function
    try:
        result = _call_analysis_function(func_name, master_df, params)
        logger.info(f"Successfully generated data for slide {slide_number}")
        return result
    except Exception as e:
        logger.error(
            f"Error generating data for slide {slide_number}: {e}",
            exc_info=True
        )
        raise


def generate_all_slide_data(master_df: pd.DataFrame) -> dict[int, Any]:
    """
    Generate data for all slides in the storyline.
    
    Args:
        master_df: Master DataFrame from Tool A (SKU Data sheet)
        
    Returns:
        Dict mapping slide_number (1-10) to slide data.
        Slide data format depends on the analysis function:
        - Single DataFrame: the DataFrame itself
        - Multiple DataFrames: dict[str, pd.DataFrame]
        - Tuple: tuple of DataFrames
        
        Example:
        {
            1: {"product_type": df1, "pl_vs_branded": df2, ...},
            2: df_heatmap,
            3: (df_table, df_chart),
            4: {"product_type": df1, "pl_vs_branded": df2, ...},
            ...
        }
        
    Raises:
        ValueError: If master_df is missing required columns
        
    Logs:
        - Info: Processing each slide
        - Warning: If a slide fails (but continues processing others)
        - Error: If critical failure (missing columns, invalid config)
    """
    # Validate storyline configuration first
    validation_errors = storyline.validate_storyline()
    if validation_errors:
        error_msg = "Storyline validation failed:\n" + "\n".join(validation_errors)
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # Validate master_df has basic required columns
    required_base_columns = ["Retailer", "Facings"]
    missing = [col for col in required_base_columns if col not in master_df.columns]
    if missing:
        raise ValueError(
            f"Master DataFrame missing required columns: {missing}. "
            f"Available columns: {list(master_df.columns)}"
        )
    
    logger.info(f"Starting slide data generation for {len(storyline.STORYLINE)} slides")
    
    results = {}
    failed_slides = []
    
    # Process each slide
    for slide_config in storyline.STORYLINE:
        slide_num = slide_config["slide_number"]
        
        try:
            slide_data = generate_slide_data(master_df, slide_num)
            results[slide_num] = slide_data
            
        except Exception as e:
            logger.warning(
                f"Failed to generate data for slide {slide_num} "
                f"({slide_config['title_template']}): {e}"
            )
            failed_slides.append(slide_num)
            # Store None to indicate failure but continue processing
            results[slide_num] = None
    
    # Log summary
    successful = len(results) - len(failed_slides)
    logger.info(
        f"Slide data generation complete: {successful}/{len(storyline.STORYLINE)} successful"
    )
    
    if failed_slides:
        logger.warning(f"Failed slides: {failed_slides}")
    
    return results
