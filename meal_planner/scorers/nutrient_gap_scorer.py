# meal_planner/scorers/nutrient_gap_scorer.py
"""
Nutrient Gap Scorer - evaluates complete meals against nutritional targets.

Scores meals based on how well they meet template targets, considering
both gaps (deficits) and excesses. Higher scores for meals that closely
align with nutritional goals.
"""
from typing import Dict, Any, List

from .base_scorer import Scorer
from meal_planner.models.scoring_context import ScoringContext, ScoringResult


class NutrientGapScorer(Scorer):
    """
    Scores complete meals based on nutritional target alignment.
    
    Higher scores for meals that:
    - Meet or nearly meet all template targets
    - Have minimal gaps in priority nutrients (protein, fiber)
    - Avoid excessive amounts of any nutrient
    - Balance macronutrients appropriately
    
    Configuration parameters (from meal_plan_config.json):
    - gap_penalty_weights: Map of priority -> penalty multiplier (e.g., {1: 3.0, 2: 2.0, 3: 1.0})
    - excess_penalty_weight: Penalty for nutrient excesses (default 0.5)
    - perfect_match_bonus: Bonus for meals meeting all targets (default 0.1)
    - tolerance_pct: Acceptable deviation from targets as % (default 0.10 = 10%)
    """
    
    @property
    def name(self) -> str:
        return "nutrient_gap"
    
    def calculate_score(self, context: ScoringContext) -> ScoringResult:
        """
        Score meal based on nutritional target alignment.
        
        Args:
            context: Complete meal context with items, totals, and analysis
        
        Returns:
            ScoringResult with 0.0-1.0 score
        """
        # Need analysis result for gap/excess detection
        if not context.analysis_result:
            # No analysis available - return neutral score
            return ScoringResult(
                scorer_name=self.name,
                raw_score=0.5,
                details={
                    "reason": "No analysis result available",
                    "gap_penalties": [],
                    "excess_penalties": [],
                    "total_penalty": 0.0
                }
            )
        
        analysis = context.analysis_result
        
        # Calculate penalties for gaps and excesses
        gap_penalties = self._calculate_gap_penalties(analysis.gaps)
        excess_penalties = self._calculate_excess_penalties(analysis.excesses)
        
        # Sum penalties
        total_gap_penalty = sum(p['penalty'] for p in gap_penalties)
        total_excess_penalty = sum(p['penalty'] for p in excess_penalties)
        total_penalty = total_gap_penalty + total_excess_penalty
        
        # Start with perfect score, subtract penalties
        base_score = 1.0
        penalized_score = base_score - total_penalty
        
        # Apply bonus if meal is nearly perfect
        bonus = 0.0
        if len(gap_penalties) == 0 and len(excess_penalties) == 0:
            bonus = self.config.get("perfect_match_bonus", 0.1)
        
        final_score = self._clamp_score(penalized_score + bonus)
        
        return ScoringResult(
            scorer_name=self.name,
            raw_score=final_score,
            details={
                "gap_count": len(gap_penalties),
                "excess_count": len(excess_penalties),
                "gap_penalties": gap_penalties,
                "excess_penalties": excess_penalties,
                "total_gap_penalty": total_gap_penalty,
                "total_excess_penalty": total_excess_penalty,
                "total_penalty": total_penalty,
                "perfect_match_bonus": bonus,
                "base_score": base_score,
                "final_score": final_score
            }
        )
    
    # =========================================================================
    # Helper methods
    # =========================================================================
    
    def _calculate_gap_penalties(self, gaps: List) -> List[Dict[str, Any]]:
        """
        Calculate penalties for nutritional gaps.
        
        Gaps are weighted by priority - protein gaps matter more than fat gaps.
        Penalty is proportional to size of gap relative to target.
        
        NOTE: If gap has both min and max (a range), current value within range
        should not be penalized - those aren't real gaps!
        
        Args:
            gaps: List of NutrientGap objects from analysis
        
        Returns:
            List of penalty dicts with nutrient, deficit, priority, penalty
        """
        penalties = []
        
        # Get priority weights from config
        gap_penalty_weights = self.config.get("gap_penalty_weights", {
            '1': 3.0,  # Highest priority (protein)
            '2': 2.0,  # Medium priority (fiber, carbs)
            '3': 1.0   # Lower priority (fat, other)
        })

        # Tolerance for "close enough"
        tolerance_pct = self.config.get("tolerance_pct", 0.10)  # 10% tolerance
        
        for gap in gaps:
            # CRITICAL FIX: Skip if current value is within acceptable range
            # If there's a target_max, check if current is in [target_min, target_max]
            if gap.target_max is not None:
                # Range target (e.g., protein 25-35g)
                if gap.target_min <= gap.current <= gap.target_max:
                    # Current value is WITHIN range - not actually a gap!
                    continue
            
            # Calculate deficit as % of target
            target = gap.target_min
            if target > 0:
                deficit_pct = gap.deficit / target
            else:
                deficit_pct = 0.0
            
            # Apply tolerance - small gaps don't count
            if deficit_pct <= tolerance_pct:
                continue
            
            # Get priority weight
            priority = gap.priority
            weight = gap_penalty_weights.get(str(priority), 1.0)
            
            # Calculate penalty (normalized to 0-1 scale)
            # Deficit of 100% = full weight penalty
            # Deficit of 50% = half weight penalty
            raw_penalty = deficit_pct * weight
            
            penalties.append({
                "nutrient": gap.nutrient,
                "current": gap.current,
                "target_min": gap.target_min,
                "target_max": gap.target_max,
                "deficit": gap.deficit,
                "deficit_pct": deficit_pct,
                "priority": priority,
                "weight": weight,
                "penalty": raw_penalty,
                "unit": gap.unit
            })
        
        return penalties
    
    def _calculate_excess_penalties(self, excesses: List) -> List[Dict[str, Any]]:
        """
        Calculate penalties for nutritional excesses.
        
        Excesses are generally less severe than gaps, but still penalized.
        
        Args:
            excesses: List of NutrientExcess objects from analysis
        
        Returns:
            List of penalty dicts with nutrient, overage, penalty
        """
        penalties = []
        
        # Excess penalty weight (lower than gap penalties)
        excess_weight = self.config.get("excess_penalty_weight", 0.5)
        
        # Tolerance for excesses
        tolerance_pct = self.config.get("tolerance_pct", 0.10)
        
        for excess in excesses:
            # Calculate overage as % of threshold
            threshold = excess.threshold
            if threshold > 0:
                overage_pct = excess.overage / threshold
            else:
                overage_pct = 0.0
            
            # Apply tolerance
            if overage_pct <= tolerance_pct:
                continue
            
            # Calculate penalty
            raw_penalty = overage_pct * excess_weight
            
            penalties.append({
                "nutrient": excess.nutrient,
                "current": excess.current,
                "threshold": threshold,
                "overage": excess.overage,
                "overage_pct": overage_pct,
                "penalty": raw_penalty,
                "unit": excess.unit
            })
        
        return penalties