# meal_planner/scorers/__init__.py
"""
Scorer modules for meal recommendation engine.

Scorers evaluate COMPLETE MEALS (not individual foods) against various
criteria to generate recommendations. Each scorer focuses on a specific
aspect and returns a 0-1 normalized score.
"""
from .base_scorer import Scorer
from .nutrient_gap_scorer import NutrientGapScorer

# Scorer registry - maps scorer names to classes
SCORER_REGISTRY = {
    "nutrient_gap": NutrientGapScorer,
}


def create_scorer(scorer_name: str, config, master, nutrients, thresholds, user_prefs):
    """
    Factory function to create scorer instances.
    
    Args:
        scorer_name: Name of scorer (e.g., "nutrient_gap")
        config: Scorer-specific config from meal_plan_config.json
        master: MasterLoader instance
        nutrients: NutrientsManager instance
        thresholds: ThresholdsManager instance
        user_prefs: UserPreferencesManager instance
    
    Returns:
        Scorer instance
    
    Raises:
        ValueError: If scorer_name not found in registry
    """
    if scorer_name not in SCORER_REGISTRY:
        raise ValueError(
            f"Unknown scorer: {scorer_name}. "
            f"Available: {list(SCORER_REGISTRY.keys())}"
        )
    
    scorer_class = SCORER_REGISTRY[scorer_name]
    return scorer_class(config, master, nutrients, thresholds, user_prefs)


def get_available_scorers():
    """
    Get list of available scorer names.
    
    Returns:
        List of scorer names
    """
    return list(SCORER_REGISTRY.keys())


__all__ = [
    'Scorer',
    'NutrientGapScorer',
    'PreferenceScorer',
    'SCORER_REGISTRY',
    'create_scorer',
    'get_available_scorers',
]