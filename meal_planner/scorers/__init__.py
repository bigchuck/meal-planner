# meal_planner/scorers/__init__.py
"""
Scorer modules for meal recommendation engine.

Scorers evaluate COMPLETE MEALS (not individual foods) against various
criteria to generate recommendations. Each scorer focuses on a specific
aspect and returns a 0-1 normalized score.
"""
from .base_scorer import Scorer
from .nutrient_gap_scorer import NutrientGapScorer
from .diversity_context import DiversityContext, DailyCountTally, IntradayMealPresence, InterdayGroupPresence
from .daily_count_scorer import DailyCountScorer
from .intraday_scorer import IntradayScorer
from .interday_scorer import InterdayScorer

# Scorer registry - maps scorer names to classes
SCORER_REGISTRY = {
    "nutrient_gap": NutrientGapScorer,
    "daily_count":  DailyCountScorer,
    "intraday":     IntradayScorer,
    "interday":     InterdayScorer,
}


def create_scorer(scorer_name: str, config, master, thresholds, user_prefs, diversity_context):
    """
    Factory function to create scorer instances.
    
    Args:
        scorer_name: Name of scorer (e.g., "nutrient_gap")
        config: Scorer-specific config from meal_plan_config.json
        master: MasterLoader instance
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

    # DailyCountScorer takes an extra diversity_context argument
    if scorer_name in ("daily_count", "intraday", "interday"):
        return scorer_class(config, master, thresholds, user_prefs,
                            diversity_context=diversity_context)

    return scorer_class(config, master, thresholds, user_prefs)

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
    'DiversityContext',
    'DailyCountTally',
    'IntradayMealPresence',
    'DailyCountScorer',
    'IntradayScorer',
    'InterdayGroupPresence',
]