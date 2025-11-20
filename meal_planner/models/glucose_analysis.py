"""
Data model for glucose analysis and prediction
"""

"""
Glucose risk analysis models for meals.
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from meal_planner.models import DailyTotals


@dataclass
class GlucoseAnalysis:
    """
    Glucose risk metrics for a meal.
    
    Calculated from meal totals and provides risk factor analysis.
    """
    meal_name: str
    totals: DailyTotals
    
    # Calculated metrics
    carb_fiber_ratio: float = 0.0
    sugar_pct_of_carbs: float = 0.0
    gl_per_100_cal: float = 0.0
    is_meal: bool = True  # vs snack
    
    # Risk indicators
    risk_score: float = 0.0  # 0-10 scale
    warnings: List[str] = None
    
    def __post_init__(self):
        """Calculate derived metrics."""
        if self.warnings is None:
            self.warnings = []
        
        # Calculate ratios
        if self.totals.carbs_g > 0:
            self.sugar_pct_of_carbs = (self.totals.sugar_g / self.totals.carbs_g) * 100
        
        if self.totals.calories > 0:
            self.gl_per_100_cal = (self.totals.glycemic_load / self.totals.calories) * 100
        
        # Calculate risk score and warnings
        self._calculate_risk()
    
    def _calculate_risk(self) -> None:
        """Calculate composite risk score and identify warnings."""
        score = 0.0
        
        # High GL (>20 = high, >10 = moderate)
        if self.totals.glycemic_load > 20:
            score += 3.0
            self.warnings.append(f"High GL: {int(self.totals.glycemic_load)}")
        elif self.totals.glycemic_load > 10:
            score += 1.5
        
        # High sugar percentage (>40% = high)
        if self.sugar_pct_of_carbs > 40:
            score += 2.0
            self.warnings.append(f"High sugar %: {int(self.sugar_pct_of_carbs)}%")
        
        # GL concentration (>10 per 100 cal = high)
        if self.gl_per_100_cal > 10:
            score += 2.0
            self.warnings.append(f"High GL density: {self.gl_per_100_cal:.1f}/100cal")
        
        # Large carb load (>60g in single meal)
        if self.totals.carbs_g > 60:
            score += 2.0
            self.warnings.append(f"Large carb load: {int(self.totals.carbs_g)}g")
        
        # Low protein ratio (protein < 20% of carbs by weight)
        if self.totals.carbs_g > 0:
            prot_ratio = self.totals.protein_g / self.totals.carbs_g
            if prot_ratio < 0.2:
                score += 1.0
                self.warnings.append(f"Low protein buffer: {int(prot_ratio * 100)}%")
        
        self.risk_score = min(score, 10.0)
    
    def get_risk_level(self) -> str:
        """Get risk category."""
        if self.risk_score >= 7:
            return "HIGH"
        elif self.risk_score >= 4:
            return "MODERATE"
        else:
            return "LOW"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "meal_name": self.meal_name,
            "gl": self.totals.glycemic_load,
            "carbs_g": self.totals.carbs_g,
            "sugar_g": self.totals.sugar_g,
            "protein_g": self.totals.protein_g,
            "calories": self.totals.calories,
            "sugar_pct_of_carbs": self.sugar_pct_of_carbs,
            "gl_per_100_cal": self.gl_per_100_cal,
            "risk_score": self.risk_score,
            "risk_level": self.get_risk_level(),
            "warnings": self.warnings.copy(),
        }
    
    def format_summary(self) -> str:
        """Format single-line summary."""
        risk_level = self.get_risk_level()
        return (f"{self.meal_name:15} | "
                f"Risk: {risk_level:8} ({self.risk_score:.1f}) | "
                f"GL: {int(self.totals.glycemic_load):3} | "
                f"Sugar: {int(self.sugar_pct_of_carbs):2}% of carbs")
    
    def format_detail(self) -> str:
        """Format detailed analysis."""
        lines = []
        lines.append(f"=== {self.meal_name} ===")
        lines.append(f"Risk Level: {self.get_risk_level()} (score: {self.risk_score:.1f}/10)")
        lines.append("")
        lines.append("Metrics:")
        lines.append(f"  Glycemic Load: {int(self.totals.glycemic_load)}")
        lines.append(f"  Total Carbs: {int(self.totals.carbs_g)}g")
        lines.append(f"  Sugars: {int(self.totals.sugar_g)}g ({int(self.sugar_pct_of_carbs)}% of carbs)")
        lines.append(f"  Protein: {int(self.totals.protein_g)}g")
        lines.append(f"  GL per 100 cal: {self.gl_per_100_cal:.1f}")
        
        if self.warnings:
            lines.append("")
            lines.append("⚠ Warnings:")
            for w in self.warnings:
                lines.append(f"  • {w}")
        
        return "\n".join(lines)


def analyze_meal(meal_name: str, meal_totals: DailyTotals) -> GlucoseAnalysis:
    """
    Create glucose analysis for a meal.
    
    Args:
        meal_name: Name of meal (BREAKFAST, LUNCH, etc.)
        meal_totals: DailyTotals for the meal
    
    Returns:
        GlucoseAnalysis instance
    """
    return GlucoseAnalysis(meal_name=meal_name, totals=meal_totals)