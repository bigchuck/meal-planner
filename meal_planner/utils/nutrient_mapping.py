# meal_planner/utils/nutrient_mapping.py
"""
Centralized nutrient name mapping and conversion utilities.

Provides canonical mappings between:
- Template keys (e.g., "calories", "protein")
- DailyTotals attributes (e.g., totals.calories, totals.protein_g)
- CSV/database column names (e.g., "cal", "prot_g")
- Display names (e.g., "Cal", "Protein")

This eliminates duplication across analyzers, filters, and scorers.
"""
from typing import Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class NutrientSpec:
    """
    Complete specification for a nutrient.
    
    Attributes:
        template_key: Key used in meal_templates config (e.g., "calories")
        totals_attr: Attribute name in DailyTotals (e.g., "calories")
        csv_key: Key in CSV/database (e.g., "cal")
        unit: Display unit (e.g., "g", "mg", "")
        display_name: Human-readable name (e.g., "Calories", "Protein")
        default_priority: Default priority level (1=critical, 2=important, 3=nice-to-have)
    """
    template_key: str
    totals_attr: str
    csv_key: str
    unit: str
    display_name: str
    default_priority: int = 2


# Canonical nutrient specifications
NUTRIENT_SPECS = {
    "calories": NutrientSpec(
        template_key="calories",
        totals_attr="calories",
        csv_key="cal",
        unit="",
        display_name="Calories",
        default_priority=2
    ),
    "protein": NutrientSpec(
        template_key="protein",
        totals_attr="protein_g",
        csv_key="prot_g",
        unit="g",
        display_name="Protein",
        default_priority=1
    ),
    "carbs": NutrientSpec(
        template_key="carbs",
        totals_attr="carbs_g",
        csv_key="carbs_g",
        unit="g",
        display_name="Carbs",
        default_priority=2
    ),
    "fat": NutrientSpec(
        template_key="fat",
        totals_attr="fat_g",
        csv_key="fat_g",
        unit="g",
        display_name="Fat",
        default_priority=2
    ),
    "fiber": NutrientSpec(
        template_key="fiber",
        totals_attr="fiber_g",
        csv_key="fiber_g",
        unit="g",
        display_name="Fiber",
        default_priority=2
    ),
    "sugar": NutrientSpec(
        template_key="sugar",
        totals_attr="sugar_g",
        csv_key="sugar_g",
        unit="g",
        display_name="Sugar",
        default_priority=2
    ),
    "gl": NutrientSpec(
        template_key="gl",
        totals_attr="glycemic_load",
        csv_key="GL",
        unit="",
        display_name="GL",
        default_priority=1
    ),
}


def get_nutrient_spec(template_key: str) -> Optional[NutrientSpec]:
    """
    Get nutrient specification by template key.
    
    Args:
        template_key: Template key (e.g., "calories", "protein")
    
    Returns:
        NutrientSpec if found, None otherwise
    
    Example:
        >>> spec = get_nutrient_spec("calories")
        >>> spec.totals_attr
        'calories'
        >>> spec.csv_key
        'cal'
    """
    return NUTRIENT_SPECS.get(template_key)


def get_analyzer_mapping(priorities: Optional[Dict[str, int]] = None) -> Dict[str, Tuple[str, str, int]]:
    """
    Get nutrient mapping for MealAnalyzer gap/excess detection.
    
    Maps template_key -> (totals_attr, unit, priority)
    
    Args:
        priorities: Optional priority overrides from config
    
    Returns:
        Dict mapping template keys to (attribute, unit, priority) tuples
    
    Example:
        >>> mapping = get_analyzer_mapping()
        >>> mapping["calories"]
        ('calories', '', 2)
        >>> mapping["protein"]
        ('protein_g', 'g', 1)
    """
    priorities = priorities or {}
    
    return {
        key: (
            spec.totals_attr,
            spec.unit,
            priorities.get(key, spec.default_priority)
        )
        for key, spec in NUTRIENT_SPECS.items()
    }


def get_filter_totals_mapping() -> Dict[str, str]:
    """
    Get nutrient mapping for filter totals calculation.
    
    Maps template_key -> csv_key for accumulating totals from master.csv.
    
    Returns:
        Dict mapping template keys to CSV column names
    
    Example:
        >>> mapping = get_filter_totals_mapping()
        >>> mapping["calories"]
        'cal'
        >>> mapping["protein"]
        'prot_g'
    """
    return {
        key: spec.csv_key
        for key, spec in NUTRIENT_SPECS.items()
    }


def init_totals_dict() -> Dict[str, float]:
    """
    Initialize empty totals dictionary with all nutrient keys.
    
    Uses template_key as dict key (for consistency with config layer).
    
    Returns:
        Dict with all nutrients initialized to 0.0
    
    Example:
        >>> totals = init_totals_dict()
        >>> totals["calories"]
        0.0
        >>> totals["protein"]
        0.0
    """
    return {key: 0.0 for key in NUTRIENT_SPECS.keys()}


def validate_template_targets(targets: Dict[str, any]) -> Tuple[bool, list]:
    """
    Validate that template targets use recognized nutrient keys.
    
    Args:
        targets: Template targets dict
    
    Returns:
        Tuple of (is_valid, list_of_unknown_keys)
    
    Example:
        >>> valid, unknown = validate_template_targets({"calories": {}, "protein": {}})
        >>> valid
        True
        >>> valid, unknown = validate_template_targets({"invalid_nutrient": {}})
        >>> unknown
        ['invalid_nutrient']
    """
    unknown_keys = [key for key in targets.keys() if key not in NUTRIENT_SPECS]
    return len(unknown_keys) == 0, unknown_keys


# Convenience functions for common use cases

def get_all_template_keys() -> list:
    """Get list of all valid template keys."""
    return list(NUTRIENT_SPECS.keys())


def get_display_name(template_key: str) -> str:
    """Get display name for a template key, with fallback."""
    spec = NUTRIENT_SPECS.get(template_key)
    return spec.display_name if spec else template_key.title()


def get_unit(template_key: str) -> str:
    """Get unit for a template key, with fallback."""
    spec = NUTRIENT_SPECS.get(template_key)
    return spec.unit if spec else ""