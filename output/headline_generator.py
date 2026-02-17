"""
AI-powered headline generator for presentation slides.

Uses a single batched Claude Sonnet API call to generate punchy, insight-driven
headlines for all 10 slides at once. Falls back to the static title_template
from storyline config when no API key is available or the call fails.
"""

import json
import logging
from typing import Any

import pandas as pd

from config.storyline import STORYLINE, SlideConfig

logger = logging.getLogger(__name__)

# Claude model for headline generation (same as used elsewhere in the project)
HEADLINE_MODEL = "claude-sonnet-4-20250514"
MAX_HEADLINE_WORDS = 15


def _summarize_slide_data(slide_number: int, slide_data: Any) -> str:
    """
    Create a compact text summary of a slide's data for the LLM prompt.

    Keeps the summary small to fit all 10 slides in one API call.
    Shows top 5 rows and key statistics.

    Args:
        slide_number: The slide number (1-10)
        slide_data: Data returned by the analysis function

    Returns:
        A compact multi-line string summary
    """
    if slide_data is None:
        return f"Slide {slide_number}: No data available"

    lines = [f"Slide {slide_number}:"]

    if isinstance(slide_data, pd.DataFrame):
        # Single DataFrame (slide 2: heatmap)
        lines.append(f"  Columns: {list(slide_data.columns)}")
        lines.append(f"  Rows: {len(slide_data)}")
        if not slide_data.empty:
            # Show top 5 rows as compact text
            top_rows = slide_data.head(5).to_string(index=False, max_colwidth=20)
            lines.append(f"  Top rows:\n{top_rows}")

    elif isinstance(slide_data, tuple):
        # Tuple of DataFrames (slide 3: table + chart)
        for idx, df_item in enumerate(slide_data):
            if isinstance(df_item, pd.DataFrame) and not df_item.empty:
                lines.append(f"  Part {idx + 1} columns: {list(df_item.columns)}")
                top_rows = df_item.head(5).to_string(index=False, max_colwidth=20)
                lines.append(f"  Top rows:\n{top_rows}")

    elif isinstance(slide_data, dict):
        # Dict of DataFrames (slides 1, 4-10)
        for key, df_item in slide_data.items():
            if isinstance(df_item, pd.DataFrame) and not df_item.empty:
                lines.append(f"  {key}: {len(df_item)} rows")
                # Show a compact summary: first 3 rows
                top_rows = df_item.head(3).to_string(index=False, max_colwidth=20)
                lines.append(f"{top_rows}")

    return "\n".join(lines)


def _build_batch_prompt(
    slide_data: dict[int, Any],
) -> str:
    """
    Build the prompt for a single batched API call that generates
    headlines for all slides at once.

    Args:
        slide_data: Dict mapping slide_number (1-10) to slide data

    Returns:
        The full prompt string
    """
    # Collect summaries for all slides
    summaries: list[str] = []
    for slide_config in STORYLINE:
        slide_num = slide_config["slide_number"]
        title = slide_config["title_template"]
        data = slide_data.get(slide_num)
        summary = _summarize_slide_data(slide_num, data)
        summaries.append(f"--- {title} ---\n{summary}")

    data_block = "\n\n".join(summaries)

    prompt = f"""You are a strategy consultant writing slide headlines for a chilled juice & smoothie
shelf analysis presentation. The client is Fruity Line, a premium juice brand.

For each of the 10 slides below, write a punchy, insight-driven headline (max {MAX_HEADLINE_WORDS} words).
Headlines should highlight the single most interesting finding from the data.

Good examples:
- "Private label captures 42% of shelf space at discounters — but only 8% at Waitrose"
- "Cold pressed dominates M&S with 65% share — virtually absent at Aldi"
- "Tesco leads in SKU variety with 48 unique products per store"

Rules:
- Max {MAX_HEADLINE_WORDS} words per headline
- Use specific numbers from the data
- Be insightful, not descriptive (not just "Market overview")
- Use en-dash (—) for contrast statements
- Do NOT use quotes around headlines

DATA:
{data_block}

Return your answer as a JSON array of 10 objects, each with "slide_number" (int) and "headline" (string).
Example: [{{"slide_number": 1, "headline": "Your headline here"}}, ...]

Return ONLY the JSON array, no other text."""

    return prompt


def generate_all_headlines(
    slide_data: dict[int, Any],
    api_key: str | None = None,
) -> dict[int, str]:
    """
    Generate headlines for all slides in a single batched API call.

    If no API key is provided or the call fails, falls back to the
    static title_template from storyline config for every slide.

    Args:
        slide_data: Dict mapping slide_number (1-10) to analysis data
        api_key: Anthropic API key. If None, uses fallback titles.

    Returns:
        Dict mapping slide_number to headline string
    """
    # Build fallback headlines from config
    fallback_headlines = {
        slide_config["slide_number"]: slide_config["title_template"]
        for slide_config in STORYLINE
    }

    if not api_key:
        logger.info("No API key provided — using fallback title templates for headlines")
        return fallback_headlines

    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not available — using fallback headlines")
        return fallback_headlines

    prompt = _build_batch_prompt(slide_data)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=HEADLINE_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract the text content from the response
        response_text = response.content[0].text.strip()

        # Parse JSON response
        headlines_list = json.loads(response_text)

        # Map to dict
        headlines: dict[int, str] = {}
        for item in headlines_list:
            slide_num = int(item["slide_number"])
            headline = str(item["headline"]).strip()

            # Validate: use fallback if headline is empty or too long
            word_count = len(headline.split())
            if not headline or word_count > MAX_HEADLINE_WORDS + 5:
                logger.warning(
                    f"Slide {slide_num}: headline rejected "
                    f"(empty={not headline}, words={word_count}), using fallback"
                )
                headlines[slide_num] = fallback_headlines.get(
                    slide_num, f"Slide {slide_num}"
                )
            else:
                headlines[slide_num] = headline

        # Fill in any missing slides with fallback
        for slide_num in fallback_headlines:
            if slide_num not in headlines:
                logger.warning(
                    f"Slide {slide_num}: no headline in API response, using fallback"
                )
                headlines[slide_num] = fallback_headlines[slide_num]

        logger.info(f"Generated {len(headlines)} headlines via Sonnet API (batch call)")
        return headlines

    except json.JSONDecodeError as exc:
        logger.warning(f"Failed to parse headline JSON from API: {exc} — using fallbacks")
        return fallback_headlines

    except Exception as exc:
        logger.warning(f"Headline generation API call failed: {exc} — using fallbacks")
        return fallback_headlines
