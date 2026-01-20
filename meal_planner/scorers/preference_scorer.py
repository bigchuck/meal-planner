# meal_planner/scorers/preference_scorer.py
"""
Preference Scorer - evaluates meals based on user preferences.

Scores meals based on how well they align with user preferences:
- Frozen portions (pre-portioned frozen foods)
- Staple items (always-available pantry/fridge items)
- Unavailable items (foods to avoid)

Higher scores for meals that use preferred/available ingredients.
"""
from typing import Dict, Any, List

from .base_scorer import Scorer
from meal_planner.models.scoring_context import ScoringContext, ScoringResult


class PreferenceScorer(Scorer):
    """
    Scores meals based on ingredient preferences and availability.
    
    Higher scores for meals that:
    - Use frozen portion items (convenient, pre-portioned)
    - Use staple items (always available, reduce shopping)
    - Avoid unavailable items (out of stock, allergies, dislikes)
    
    Configuration parameters (from meal_plan_config.json):
    - frozen_item_bonus: Bonus per frozen item (default 0.05)
    - staple_item_bonus: Bonus per staple item (default 0.03)
    - unavailable_item_penalty: Penalty per unavailable item (default 0.5)
    - base_score: Starting score (default 0.5)
    """
    
    @property
    def name(self) -> str:
        return "preference"
    
    def calculate_score(self, context: ScoringContext) -> ScoringResult:
        """
        Score meal based on ingredient preferences.
        
        Args:
            context: Complete meal context with items
        
        Returns:
            ScoringResult with 0.0-1.0 score
        """
        # Need items to evaluate
        if not context.has_items():
            return ScoringResult(
                scorer_name=self.name,
                raw_score=0.5,
                details={
                    "reason": "No items in meal",
                    "frozen_count": 0,
                    "staple_count": 0,
                    "unavailable_count": 0
                }
            )
        
        # Extract food codes from items
        food_codes = self._extract_food_codes(context.items)
        
        if not food_codes:
            return ScoringResult(
                scorer_name=self.name,
                raw_score=0.5,
                details={
                    "reason": "No food codes in meal",
                    "frozen_count": 0,
                    "staple_count": 0,
                    "unavailable_count": 0
                }
            )
        
        # Count preference categories
        frozen_items = self._identify_frozen_items(food_codes)
        staple_items = self._identify_staple_items(food_codes)
        unavailable_items = self._identify_unavailable_items(food_codes)
        
        # Calculate score
        base_score = self.config.get("base_score", 0.5)
        
        frozen_bonus_per_item = self.config.get("frozen_item_bonus", 0.05)
        staple_bonus_per_item = self.config.get("staple_item_bonus", 0.03)
        unavailable_penalty_per_item = self.config.get("unavailable_item_penalty", 0.5)
        
        # Apply bonuses and penalties
        frozen_bonus = len(frozen_items) * frozen_bonus_per_item
        staple_bonus = len(staple_items) * staple_bonus_per_item
        unavailable_penalty = len(unavailable_items) * unavailable_penalty_per_item
        
        raw_score = base_score + frozen_bonus + staple_bonus - unavailable_penalty
        final_score = self._clamp_score(raw_score)
        
        return ScoringResult(
            scorer_name=self.name,
            raw_score=final_score,
            details={
                "total_items": len(food_codes),
                "frozen_count": len(frozen_items),
                "frozen_items": frozen_items,
                "staple_count": len(staple_items),
                "staple_items": staple_items,
                "unavailable_count": len(unavailable_items),
                "unavailable_items": unavailable_items,
                "base_score": base_score,
                "frozen_bonus": frozen_bonus,
                "staple_bonus": staple_bonus,
                "unavailable_penalty": unavailable_penalty,
                "raw_score_before_clamp": raw_score,
                "final_score": final_score
            }
        )
    
    # =========================================================================
    # Helper methods
    # =========================================================================
    
    def _identify_frozen_items(self, food_codes: List[str]) -> List[str]:
        """
        Identify which food codes have frozen portions defined.
        
        Args:
            food_codes: List of food codes in meal
        
        Returns:
            List of codes with frozen portions
        """
        frozen = []
        
        if not self.user_prefs:
            return frozen
        
        for code in food_codes:
            if self.user_prefs.get_frozen_multiplier(code) is not None:
                frozen.append(code)
        
        return frozen
    
    def _identify_staple_items(self, food_codes: List[str]) -> List[str]:
        """
        Identify which food codes are designated staples.
        
        Args:
            food_codes: List of food codes in meal
        
        Returns:
            List of codes that are staples
        """
        staple_items = []
        
        if not self.user_prefs:
            return staple_items
        
        staples = self.user_prefs.get_staple_foods()
        staples_upper = [s.upper() for s in staples]
        
        for code in food_codes:
            if code.upper() in staples_upper:
                staple_items.append(code)
        
        return staple_items
    
    def _identify_unavailable_items(self, food_codes: List[str]) -> List[str]:
        """
        Identify which food codes are unavailable (should be avoided).
        
        Args:
            food_codes: List of food codes in meal
        
        Returns:
            List of codes that are unavailable
        """
        unavailable_items = []
        
        if not self.user_prefs:
            return unavailable_items
        
        unavailable = self.user_prefs.get_unavailable_items()
        unavailable_upper = [u.upper() for u in unavailable]
        
        for code in food_codes:
            if code.upper() in unavailable_upper:
                unavailable_items.append(code)
        
        return unavailable_items