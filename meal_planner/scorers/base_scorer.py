# meal_planner/scorers/base_scorer.py
"""
Base scorer class for meal recommendation engine.

Defines the interface all scorers must implement. Scorers evaluate
COMPLETE MEALS (not individual foods) against various criteria.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

from meal_planner.models.scoring_context import ScoringContext, ScoringResult


class Scorer(ABC):
    """
    Abstract base class for meal scorers.
    
    Each scorer evaluates how well a COMPLETE MEAL fits within various criteria,
    returning a normalized score from 0.0 (poor fit) to 1.0 (excellent fit).
    
    Examples of scoring criteria:
    - Nutrient Gap: Does this meal meet nutritional targets?
    - Preference: Does this meal use preferred/available ingredients?
    - Portion Efficiency: Are portions reasonable and aligned with preferences?
    - Variety: Is this meal different from recent meals?
    - Staple Food: Does this meal incorporate designated staples?
    - Cost/Practicality: Is this meal practical given constraints?
    
    Scorers have access to:
    - Master food database (nutrients, portions, etc.)
    - Micronutrient data
    - Template/threshold information
    - User preferences (frozen portions, staples, etc.)
    - Scorer-specific configuration parameters
    """
    
    def __init__(self, config: Dict[str, Any], master, thresholds, user_prefs):
        """
        Initialize scorer.
        
        Args:
            config: Scorer-specific configuration from meal_plan_config.json
            master: MasterLoader instance
            thresholds: ThresholdsManager instance
            user_prefs: UserPreferencesManager instance
        """
        self.config = config
        self.master = master
        self.thresholds = thresholds
        self.user_prefs = user_prefs
    
    @abstractmethod
    def calculate_score(self, context: ScoringContext) -> ScoringResult:
        """
        Calculate score for a complete meal.
        
        Scorers should:
        1. Examine meal composition from context.items
        2. Evaluate against criteria (gaps, preferences, constraints)
        3. Return normalized 0.0-1.0 score with debug details
        
        Args:
            context: Scoring context with complete meal information
        
        Returns:
            ScoringResult with raw_score (0-1) and details dict
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        Scorer name (matches config key).
        
        Example: "nutrient_gap", "preference", "variety"
        """
        pass
    
    # =========================================================================
    # Helper methods available to all scorers
    # =========================================================================
    
    def _get_template_targets(self, template_path: str) -> Optional[Dict[str, Any]]:
        """
        Get template targets from thresholds.
        
        Args:
            template_path: Dot-notation path (e.g., "breakfast.protein_low_carb")
        
        Returns:
            Template dict with targets, guidelines, etc. or None if not found
        """
        if not template_path or not self.thresholds:
            return None
        
        # Prepend meal_templates if needed
        if not template_path.startswith("meal_templates."):
            template_path = f"meal_templates.{template_path}"
        
        # Navigate through nested structure
        parts = template_path.split(".")
        current = self.thresholds.thresholds
        
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        
        return current if isinstance(current, dict) else None
    
    def _get_template_guidelines(self, template_path: str) -> List[str]:
        """
        Get template guidelines.
        
        Args:
            template_path: Template path
        
        Returns:
            List of guideline strings
        """
        template = self._get_template_targets(template_path)
        if not template:
            return []
        
        return template.get("guidelines", [])
    
    def _extract_food_codes(self, items: List[Dict[str, Any]]) -> List[str]:
        """
        Extract food codes from items list.
        
        Args:
            items: Meal items (may include time markers)
        
        Returns:
            List of food codes (uppercase)
        """
        codes = []
        for item in items:
            if 'code' in item:
                codes.append(str(item['code']).upper())
        return codes
    
    def _count_frozen_items(self, items: List[Dict[str, Any]]) -> int:
        """
        Count items using frozen portions.
        
        Args:
            items: Meal items
        
        Returns:
            Count of frozen items
        """
        if not self.user_prefs:
            return 0
        
        count = 0
        for item in items:
            if 'code' in item:
                code = str(item['code']).upper()
                if self.user_prefs.get_frozen_multiplier(code) is not None:
                    count += 1
        
        return count
    
    def _count_staple_items(self, items: List[Dict[str, Any]]) -> int:
        """
        Count designated staple items in meal.
        
        Args:
            items: Meal items
        
        Returns:
            Count of staple items
        """
        if not self.user_prefs:
            return 0
        
        staples = self.user_prefs.get_staple_foods()
        staples_upper = [s.upper() for s in staples]
        
        count = 0
        for item in items:
            if 'code' in item:
                code = str(item['code']).upper()
                if code in staples_upper:
                    count += 1
        
        return count
    
    def _clamp_score(self, score: float) -> float:
        """
        Clamp score to valid 0.0-1.0 range.
        
        Args:
            score: Raw score value
        
        Returns:
            Clamped score
        """
        return max(0.0, min(1.0, score))