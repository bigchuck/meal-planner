# meal_planner/models/scoring_context.py
"""
Scoring context models for meal recommendation engine.

Defines the context in which MEAL scoring occurs. Scorers evaluate
complete meals (not individual foods) against templates and preferences.
"""
from enum import Enum
from dataclasses import dataclass
from typing import List, Dict, Any, Optional


class MealLocation(Enum):
    """
    Enum representing where a meal is located in the system.
    
    PENDING: Meal in pending.json (current day being built)
    WORKSPACE: Meal in planning workspace (search results and invented meals)
    CANDIDATE: Recommendation engine suggestion (not yet persisted)
    """
    PENDING = "pending"
    WORKSPACE = "workspace"
    CANDIDATE = "candidate"


@dataclass
class ScoringContext:
    """
    Context for scoring a complete meal.
    
    Contains all information needed to evaluate how well a meal fits
    nutritional goals, preferences, and constraints.
    """
    
    # Meal identification
    location: MealLocation
    meal_id: Optional[str]  # None for PENDING, ID string for WORKSPACE/CANDIDATE
    meal_category: str  # "breakfast", "lunch", "dinner", "morning snack", etc.
    
    # Template context
    template_path: Optional[str] = None  # e.g., "breakfast.protein_low_carb"
    
    # Meal composition (these will be analyzed by scorers)
    items: List[Dict[str, Any]] = None  # Food items in meal
    totals: Optional[Dict[str, float]] = None  # Current nutritional totals
    
    # Analysis context (gaps, excesses, constraints)
    analysis_result: Any = None  # AnalysisResult object if analyzed
    
    def __post_init__(self):
        """Ensure items list is initialized."""
        if self.items is None:
            self.items = []
    
    def has_items(self) -> bool:
        """Check if meal has any items."""
        return len(self.items) > 0
    
    def item_count(self) -> int:
        """Get number of items in meal."""
        return len(self.items)


@dataclass
class ScoringResult:
    """
    Result from a scorer's evaluation of a meal.
    
    Contains:
    - Normalized score (0.0 to 1.0)
    - Detailed breakdown for debugging
    - Weighted score calculation
    """
    
    scorer_name: str
    raw_score: float  # 0.0 (worst fit) to 1.0 (perfect fit)
    details: Dict[str, Any]  # Debug information, scorer-specific
    
    def get_weighted_score(self, weight: float) -> float:
        """
        Calculate weighted score.
        
        Args:
            weight: Weight from recommendation_weights config
        
        Returns:
            raw_score * weight
        """
        return self.raw_score * weight
    
    def __str__(self) -> str:
        """String representation for debugging."""
        return f"{self.scorer_name}: {self.raw_score:.3f}"


@dataclass
class AggregateScore:
    """
    Aggregated score from multiple scorers for a complete meal.
    
    Combines individual scorer results with weights to produce
    final recommendation score.
    """
    
    meal_id: str  # Meal identifier
    meal_category: str  # breakfast, lunch, etc.
    individual_scores: List[ScoringResult]  # Raw scores from each scorer
    weights: Dict[str, float]  # Weights from config
    final_score: float  # Weighted aggregate
    
    def get_breakdown(self) -> List[Dict[str, Any]]:
        """
        Get detailed breakdown of score components.
        
        Returns:
            List of dicts with scorer_name, raw_score, weight, contribution
        """
        breakdown = []
        for result in self.individual_scores:
            weight = self.weights.get(result.scorer_name, 0.0)
            contribution = result.raw_score * weight
            
            breakdown.append({
                'scorer': result.scorer_name,
                'raw_score': result.raw_score,
                'weight': weight,
                'contribution': contribution
            })
        
        return breakdown
    
    def __str__(self) -> str:
        """String representation showing final score."""
        return f"Meal {self.meal_id} ({self.meal_category}): {self.final_score:.3f}"