# meal_planner/models/analysis_result.py
"""
Analysis result models for meal template comparison.

Defines structures for gaps, excesses, and overall analysis results.
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from .daily_totals import DailyTotals


@dataclass
class NutrientGap:
    """Represents a nutrient deficit relative to template target."""
    
    nutrient: str           # Nutrient key (e.g., 'protein_g')
    current: float          # Current value
    target_min: float       # Minimum target
    target_max: Optional[float]  # Maximum target (if range)
    deficit: float          # How much below minimum
    priority: int           # 1=critical, 2=important, 3=nice-to-have
    unit: str              # Unit string (e.g., 'g', '')
    
    def __str__(self) -> str:
        """String representation of gap."""
        if self.target_max is not None:
            return (f"{self.nutrient}: {self.current:.1f}{self.unit} "
                   f"(target: {self.target_min:.1f}-{self.target_max:.1f}{self.unit}, "
                   f"{self.deficit:.1f}{self.unit} below)")
        else:
            return (f"{self.nutrient}: {self.current:.1f}{self.unit} "
                   f"(min: {self.target_min:.1f}{self.unit}, "
                   f"{self.deficit:.1f}{self.unit} below)")


@dataclass
class NutrientExcess:
    """Represents a nutrient surplus relative to template threshold."""
    
    nutrient: str           # Nutrient key (e.g., 'sugar_g')
    current: float          # Current value
    threshold: float        # Maximum threshold
    overage: float          # How much above threshold
    priority: int           # 1=critical, 2=important, 3=nice-to-have
    unit: str              # Unit string (e.g., 'g', '')
    
    def __str__(self) -> str:
        """String representation of excess."""
        return (f"{self.nutrient}: {self.current:.1f}{self.unit} "
               f"(max: {self.threshold:.1f}{self.unit}, "
               f"{self.overage:.1f}{self.unit} over)")


@dataclass
class DailyContext:
    """Daily nutritional context from earlier meals."""
    
    protein_deficit: float = 0.0
    fiber_deficit: float = 0.0
    sugar_excess: float = 0.0
    calories_consumed: float = 0.0
    
    # Budget remaining for day
    sugar_budget_remaining: float = 0.0
    calorie_budget_remaining: float = 0.0
    
    def has_deficits(self) -> bool:
        """Check if there are any deficits."""
        return (self.protein_deficit > 0 or self.fiber_deficit > 0)
    
    def has_excesses(self) -> bool:
        """Check if there are any excesses."""
        return self.sugar_excess > 0


@dataclass
class AnalysisResult:
    """Complete analysis result for a meal."""
    
    # Core data
    totals: DailyTotals                    # Nutritional totals
    template: Dict[str, Any]               # Template being analyzed against
    template_name: str                     # Template name (e.g., "breakfast.protein_low_carb")
    
    # Analysis results
    gaps: List[NutrientGap]               # Nutrient deficits
    excesses: List[NutrientExcess]        # Nutrient surpluses
    
    # Meal context
    meal_items: List[Dict[str, Any]]      # Items in the meal
    meal_name: str                         # Meal category (breakfast, lunch, etc.)
    meal_id: Optional[str] = None         # Workspace ID if applicable
    meal_description: Optional[str] = None  # User description if set
    
    # Daily context (if analyzing pending)
    daily_context: Optional[DailyContext] = None
    
    def has_issues(self) -> bool:
        """Check if analysis found any gaps or excesses."""
        return len(self.gaps) > 0 or len(self.excesses) > 0
    
    def get_gap_count(self) -> int:
        """Get number of gaps."""
        return len(self.gaps)
    
    def get_excess_count(self) -> int:
        """Get number of excesses."""
        return len(self.excesses)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'totals': self.totals.to_dict() if hasattr(self.totals, 'to_dict') else {},
            'template_name': self.template_name,
            'meal_name': self.meal_name,
            'meal_id': self.meal_id,
            'meal_description': self.meal_description,
            'gaps': [
                {
                    'nutrient': g.nutrient,
                    'current': g.current,
                    'target_min': g.target_min,
                    'target_max': g.target_max,
                    'deficit': g.deficit,
                    'priority': g.priority,
                    'unit': g.unit
                }
                for g in self.gaps
            ],
            'excesses': [
                {
                    'nutrient': e.nutrient,
                    'current': e.current,
                    'threshold': e.threshold,
                    'overage': e.overage,
                    'priority': e.priority,
                    'unit': e.unit
                }
                for e in self.excesses
            ],
            'daily_context': {
                'protein_deficit': self.daily_context.protein_deficit,
                'fiber_deficit': self.daily_context.fiber_deficit,
                'sugar_excess': self.daily_context.sugar_excess,
                'calories_consumed': self.daily_context.calories_consumed,
                'sugar_budget_remaining': self.daily_context.sugar_budget_remaining,
                'calorie_budget_remaining': self.daily_context.calorie_budget_remaining
            } if self.daily_context else None
        }