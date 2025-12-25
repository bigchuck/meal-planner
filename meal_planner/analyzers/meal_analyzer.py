# meal_planner/analyzers/meal_analyzer.py
"""
Core meal analysis logic for template comparison.

Separates analysis calculations from command display logic,
allowing reuse by analyze and recommend commands.
"""
from typing import List, Dict, Any, Optional, Tuple
from meal_planner.models.analysis_result import (
    AnalysisResult, NutrientGap, NutrientExcess, DailyContext
)
from meal_planner.models.daily_totals import DailyTotals
from meal_planner.reports.report_builder import ReportBuilder


class MealAnalyzer:
    """
    Analyzes meals against nutritional templates.
    
    Provides gap and excess detection with priority scoring.
    """
    
    def __init__(self, master, nutrients, thresholds, user_prefs=None):
        """
        Initialize meal analyzer.
        
        Args:
            master: MasterLoader instance
            nutrients: NutrientsManager instance
            thresholds: ThresholdsManager instance
        """
        self.master = master
        self.nutrients = nutrients
        self.thresholds = thresholds
        self.user_prefs = user_prefs
    
    def calculate_analysis(
        self,
        items: List[Dict[str, Any]],
        template_path: str,
        meal_name: str,
        meal_id: Optional[str] = None,
        meal_description: Optional[str] = None,
        daily_context: Optional[DailyContext] = None
    ) -> AnalysisResult:
        """
        Analyze meal items against template.
        
        Args:
            items: List of food items
            template_path: Dot-notation template path (e.g., "breakfast.protein_low_carb")
            meal_name: Meal category (breakfast, lunch, etc.)
            meal_id: Optional workspace ID
            meal_description: Optional user description
            daily_context: Optional daily nutritional context
        
        Returns:
            AnalysisResult with gaps, excesses, and totals
        """
        # Calculate nutritional totals
        builder = ReportBuilder(self.master, self.nutrients)
        report = builder.build_from_items(items, title="Analysis")
        totals = report.totals
        
        # Get template
        template = self._get_template(template_path)
        if not template:
            raise ValueError(f"Template not found: {template_path}")
        
        # Analyze against template
        gaps = self._find_gaps(totals, template)
        excesses = self._find_excesses(totals, template)
        
        # Create result
        result = AnalysisResult(
            totals=totals,
            template=template,
            template_name=template_path,
            gaps=gaps,
            excesses=excesses,
            meal_items=items,
            meal_name=meal_name,
            meal_id=meal_id,
            meal_description=meal_description,
            daily_context=daily_context
        )
        
        return result
    
    def _get_template(self, template_path: str) -> Optional[Dict[str, Any]]:
        """
        Get template from thresholds by dot-notation path.
        
        Args:
            template_path: Path like "breakfast.protein_low_carb"
        
        Returns:
            Template dictionary or None if not found
        """
        # Prepend "meal_templates." if not present
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
    
    def _find_gaps(self, totals: DailyTotals, template: Dict[str, Any]) -> List[NutrientGap]:
        """
        Find nutrient deficits relative to template targets.
        
        Args:
            totals: Meal nutritional totals
            template: Template with targets
        
        Returns:
            List of NutrientGap objects
        """
        gaps = []
        targets = template.get("targets", {})
        
        # Map template nutrient keys to DailyTotals attributes
        nutrient_mapping = {
            "protein": ("protein_g", "g", 1),
            "carbs": ("carbs_g", "g", 2),
            "fat": ("fat_g", "g", 2),
            "fiber": ("fiber_g", "g", 2),
            "gl": ("glycemic_load", "", 2)
        }
        
        for template_key, target_def in targets.items():
            if template_key not in nutrient_mapping:
                continue
            
            attr_name, unit, priority = nutrient_mapping[template_key]
            current_value = getattr(totals, attr_name, 0.0)
            
            # Check for minimum target
            if "min" in target_def:
                min_val = target_def["min"]
                if current_value < min_val:
                    deficit = min_val - current_value
                    
                    gap = NutrientGap(
                        nutrient=template_key,
                        current=current_value,
                        target_min=min_val,
                        target_max=target_def.get("max"),
                        deficit=deficit,
                        priority=priority,
                        unit=unit
                    )
                    gaps.append(gap)
        
        # Sort by priority (lower number = higher priority)
        gaps.sort(key=lambda g: (g.priority, -g.deficit))
        
        return gaps
    
    def _find_excesses(self, totals: DailyTotals, template: Dict[str, Any]) -> List[NutrientExcess]:
        """
        Find nutrient surpluses relative to template thresholds.
        
        Args:
            totals: Meal nutritional totals
            template: Template with targets
        
        Returns:
            List of NutrientExcess objects
        """
        excesses = []
        targets = template.get("targets", {})
        
        # Map template nutrient keys to DailyTotals attributes
        nutrient_mapping = {
            "carbs": ("carbs_g", "g", 2),
            "fat": ("fat_g", "g", 2),
            "gl": ("glycemic_load", "", 1)
        }
        
        for template_key, target_def in targets.items():
            if template_key not in nutrient_mapping:
                continue
            
            attr_name, unit, priority = nutrient_mapping[template_key]
            current_value = getattr(totals, attr_name, 0.0)
            
            # Check for maximum threshold
            if "max" in target_def:
                max_val = target_def["max"]
                if current_value > max_val:
                    overage = current_value - max_val
                    
                    excess = NutrientExcess(
                        nutrient=template_key,
                        current=current_value,
                        threshold=max_val,
                        overage=overage,
                        priority=priority,
                        unit=unit
                    )
                    excesses.append(excess)
        
        # Sort by priority (lower number = higher priority)
        excesses.sort(key=lambda e: (e.priority, -e.overage))
        
        return excesses
    
    def calculate_daily_context(self, pending_items: List[Dict[str, Any]], 
                                current_meal_name: str) -> DailyContext:
        """
        Calculate daily nutritional context from earlier meals.
        
        Args:
            pending_items: All items in pending file
            current_meal_name: Name of meal being analyzed (exclude from context)
        
        Returns:
            DailyContext with deficits, excesses, budgets
        """
        # This is a placeholder - will be implemented when we handle pending analysis
        # For now, return empty context
        return DailyContext()