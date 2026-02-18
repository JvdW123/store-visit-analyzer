"""
Conflict detection for brand-based inference rules.

When brand mappings contradict explicit indicators (HPP Treatment, Claims, Notes),
conflicts are detected and flagged for manual review (yellow highlighting in output).
"""

from dataclasses import dataclass
from typing import Literal
import logging

logger = logging.getLogger(__name__)


@dataclass
class BrandConflict:
    """
    Represents a conflict between brand mapping and explicit indicators.
    
    Used to flag rows where brand-based inference contradicts explicit data
    in the row (e.g., brand says "Squeezed" but Claims say "from concentrate").
    """
    row_index: int
    column: Literal["Juice Extraction Method", "Processing Method"]
    brand_name: str
    brand_value: str  # What brand mapping says
    explicit_value: str  # What explicit indicators say
    explicit_source: str  # e.g., "HPP Treatment", "Claims: 'from concentrate'"
    similarity_score: int  # Brand match confidence (0-100)
    
    def __str__(self) -> str:
        return (
            f"Row {self.row_index}: {self.column} conflict - "
            f"Brand '{self.brand_name}' says '{self.brand_value}' but "
            f"{self.explicit_source} indicates '{self.explicit_value}'"
        )


def detect_juice_extraction_conflicts(
    row_index: int,
    brand_name: str,
    brand_extraction_method: str,
    similarity_score: int,
    hpp_treatment: str,
    processing_method: str,
    claims: str,
    notes: str
) -> BrandConflict | None:
    """
    Detect conflicts between brand mapping and explicit indicators for
    Juice Extraction Method.
    
    Checks if explicit indicators (HPP Treatment, Processing Method, Claims/Notes)
    contradict the brand's expected extraction method.
    
    Args:
        row_index: DataFrame row index
        brand_name: Matched brand name
        brand_extraction_method: What brand mapping says
        similarity_score: Brand match confidence
        hpp_treatment: HPP Treatment value
        processing_method: Processing Method value (raw, before normalization)
        claims: Claims text
        notes: Notes text
    
    Returns:
        BrandConflict if conflict detected, None otherwise
    """
    text_combined = (claims + " " + notes).lower()
    
    # Check for contradictory explicit indicators
    # These are the same rules used in _infer_juice_extraction_method
    
    # Rule: HPP Treatment == "Yes" → should be "Cold Pressed"
    if hpp_treatment == "Yes" and brand_extraction_method != "Cold Pressed":
        return BrandConflict(
            row_index=row_index,
            column="Juice Extraction Method",
            brand_name=brand_name,
            brand_value=brand_extraction_method,
            explicit_value="Cold Pressed",
            explicit_source="HPP Treatment = Yes",
            similarity_score=similarity_score
        )
    
    # Rule: Processing Method == "HPP" → should be "Cold Pressed"
    if processing_method == "HPP" and brand_extraction_method != "Cold Pressed":
        return BrandConflict(
            row_index=row_index,
            column="Juice Extraction Method",
            brand_name=brand_name,
            brand_value=brand_extraction_method,
            explicit_value="Cold Pressed",
            explicit_source="Processing Method = HPP",
            similarity_score=similarity_score
        )
    
    # Rule: Processing Method == "Freshly Squeezed" → should be "Squeezed"
    if processing_method == "Freshly Squeezed" and brand_extraction_method != "Squeezed":
        return BrandConflict(
            row_index=row_index,
            column="Juice Extraction Method",
            brand_name=brand_name,
            brand_value=brand_extraction_method,
            explicit_value="Squeezed",
            explicit_source="Processing Method = Freshly Squeezed",
            similarity_score=similarity_score
        )
    
    # Rule: Claims/Notes contain "not from concentrate" → should be "Squeezed"
    if "not from concentrate" in text_combined and brand_extraction_method != "Squeezed":
        return BrandConflict(
            row_index=row_index,
            column="Juice Extraction Method",
            brand_name=brand_name,
            brand_value=brand_extraction_method,
            explicit_value="Squeezed",
            explicit_source="Claims/Notes: 'not from concentrate'",
            similarity_score=similarity_score
        )
    
    # Rule: Claims/Notes contain "from concentrate" (but not "not from concentrate")
    # → should be "From Concentrate"
    if "from concentrate" in text_combined and "not from concentrate" not in text_combined:
        if brand_extraction_method != "From Concentrate":
            return BrandConflict(
                row_index=row_index,
                column="Juice Extraction Method",
                brand_name=brand_name,
                brand_value=brand_extraction_method,
                explicit_value="From Concentrate",
                explicit_source="Claims/Notes: 'from concentrate'",
                similarity_score=similarity_score
            )
    
    # Rule: Claims/Notes contain "cold pressed" → should be "Cold Pressed"
    if ("cold pressed" in text_combined or "cold-pressed" in text_combined):
        if brand_extraction_method != "Cold Pressed":
            return BrandConflict(
                row_index=row_index,
                column="Juice Extraction Method",
                brand_name=brand_name,
                brand_value=brand_extraction_method,
                explicit_value="Cold Pressed",
                explicit_source="Claims/Notes: 'cold pressed'",
                similarity_score=similarity_score
            )
    
    # Rule: Claims/Notes contain "squeezed" → should be "Squeezed"
    if "squeezed" in text_combined and brand_extraction_method != "Squeezed":
        return BrandConflict(
            row_index=row_index,
            column="Juice Extraction Method",
            brand_name=brand_name,
            brand_value=brand_extraction_method,
            explicit_value="Squeezed",
            explicit_source="Claims/Notes: 'squeezed'",
            similarity_score=similarity_score
        )
    
    return None


def detect_processing_method_conflicts(
    row_index: int,
    brand_name: str,
    brand_processing_method: str,
    similarity_score: int,
    hpp_treatment: str,
    processing_method: str,
    claims: str,
    notes: str
) -> BrandConflict | None:
    """
    Detect conflicts between brand mapping and explicit indicators for
    Processing Method.
    
    Args:
        row_index: DataFrame row index
        brand_name: Matched brand name
        brand_processing_method: What brand mapping says
        similarity_score: Brand match confidence
        hpp_treatment: HPP Treatment value
        processing_method: Processing Method value (raw, before normalization)
        claims: Claims text
        notes: Notes text
    
    Returns:
        BrandConflict if conflict detected, None otherwise
    """
    text_combined = (claims + " " + notes).lower()
    
    # Check for contradictory explicit indicators
    
    # Rule: HPP Treatment == "Yes" → should be "HPP"
    if hpp_treatment == "Yes" and brand_processing_method != "HPP":
        return BrandConflict(
            row_index=row_index,
            column="Processing Method",
            brand_name=brand_name,
            brand_value=brand_processing_method,
            explicit_value="HPP",
            explicit_source="HPP Treatment = Yes",
            similarity_score=similarity_score
        )
    
    # Rule: HPP Treatment == "No" → should be "Pasteurized" (or blank)
    if hpp_treatment == "No" and brand_processing_method == "HPP":
        return BrandConflict(
            row_index=row_index,
            column="Processing Method",
            brand_name=brand_name,
            brand_value=brand_processing_method,
            explicit_value="Pasteurized",
            explicit_source="HPP Treatment = No",
            similarity_score=similarity_score
        )
    
    # Rule: Processing Method already set to something different
    if processing_method and processing_method.strip():
        # Normalize for comparison
        proc_normalized = processing_method.strip()
        
        # Check if they're fundamentally different
        # (ignore case and minor variations)
        if proc_normalized.lower() in ["hpp", "hpp treated", "hpp treatment"]:
            if brand_processing_method != "HPP":
                return BrandConflict(
                    row_index=row_index,
                    column="Processing Method",
                    brand_name=brand_name,
                    brand_value=brand_processing_method,
                    explicit_value="HPP",
                    explicit_source=f"Processing Method = {processing_method}",
                    similarity_score=similarity_score
                )
        elif proc_normalized.lower() in ["pasteurized", "pasteurised", "flash pasteurized", "gently pasteurized"]:
            if brand_processing_method == "HPP":
                return BrandConflict(
                    row_index=row_index,
                    column="Processing Method",
                    brand_name=brand_name,
                    brand_value=brand_processing_method,
                    explicit_value="Pasteurized",
                    explicit_source=f"Processing Method = {processing_method}",
                    similarity_score=similarity_score
                )
    
    # Check Claims/Notes for processing indicators
    if "hpp" in text_combined and brand_processing_method != "HPP":
        return BrandConflict(
            row_index=row_index,
            column="Processing Method",
            brand_name=brand_name,
            brand_value=brand_processing_method,
            explicit_value="HPP",
            explicit_source="Claims/Notes: 'hpp'",
            similarity_score=similarity_score
        )
    
    if ("pasteurized" in text_combined or "pasteurised" in text_combined):
        if brand_processing_method == "HPP":
            return BrandConflict(
                row_index=row_index,
                column="Processing Method",
                brand_name=brand_name,
                brand_value=brand_processing_method,
                explicit_value="Pasteurized",
                explicit_source="Claims/Notes: 'pasteurized'",
                similarity_score=similarity_score
            )
    
    return None


def detect_conflicts(
    row_index: int,
    brand_name: str,
    brand_mapping: dict,
    similarity_score: int,
    hpp_treatment: str,
    processing_method: str,
    claims: str,
    notes: str
) -> list[BrandConflict]:
    """
    Detect all conflicts between brand mapping and explicit indicators.
    
    Checks both Juice Extraction Method and Processing Method for conflicts.
    
    Args:
        row_index: DataFrame row index
        brand_name: Matched brand name
        brand_mapping: Dict with juice_extraction_method and processing_method
        similarity_score: Brand match confidence
        hpp_treatment: HPP Treatment value
        processing_method: Processing Method value (raw)
        claims: Claims text
        notes: Notes text
    
    Returns:
        List of BrandConflict objects (empty if no conflicts)
    """
    conflicts = []
    
    # Check Juice Extraction Method conflicts
    extraction_conflict = detect_juice_extraction_conflicts(
        row_index=row_index,
        brand_name=brand_name,
        brand_extraction_method=brand_mapping["juice_extraction_method"],
        similarity_score=similarity_score,
        hpp_treatment=hpp_treatment,
        processing_method=processing_method,
        claims=claims,
        notes=notes
    )
    if extraction_conflict:
        conflicts.append(extraction_conflict)
        logger.warning(str(extraction_conflict))
    
    # Check Processing Method conflicts
    processing_conflict = detect_processing_method_conflicts(
        row_index=row_index,
        brand_name=brand_name,
        brand_processing_method=brand_mapping["processing_method"],
        similarity_score=similarity_score,
        hpp_treatment=hpp_treatment,
        processing_method=processing_method,
        claims=claims,
        notes=notes
    )
    if processing_conflict:
        conflicts.append(processing_conflict)
        logger.warning(str(processing_conflict))
    
    return conflicts
