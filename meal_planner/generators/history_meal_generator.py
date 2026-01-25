# meal_planner/generators/meal_generator.py
"""
Meal candidate generation for recommendation engine.

Phase 1: Extracts meals from history (bootstraps pipeline)
Future: Template-based generation, component assembly, AI suggestions
"""
from typing import List, Dict, Any, Optional
from datetime import date, timedelta
import pandas as pd

from meal_planner.data import MasterLoader, LogManager
from meal_planner.utils import get_date_column, get_codes_column
from meal_planner.utils.time_utils import categorize_time
from meal_planner.parsers import parse_selection_to_items


class HistoryMealGenerator:
    """
    Generates meal candidates for recommendation engine.
    
    Current implementation: Extracts meals from historical log data.
    This bootstraps the recommendation pipeline using proven meals.
    
    Future enhancements:
    - Template-based generation using component pools
    - Constraint-driven assembly
    - AI-powered suggestions
    - Hybrid approaches (history + modifications)
    """
    
    def __init__(self, master: MasterLoader, log: LogManager):
        """
        Initialize meal generator.
        
        Args:
            master: Master food database
            log: Daily log manager
        """
        self.master = master
        self.log = log
    
    def generate_candidates(
        self,
        meal_type: str,
        max_candidates: int = 10,
        lookback_days: int = 60,
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate meal candidates for a specific meal type.
        
        Phase 1: Searches history for meals matching the type.
        
        Args:
            meal_type: Meal category (breakfast, lunch, dinner, snack names)
            max_candidates: Maximum number of candidates to return
            lookback_days: How many days back to search
            context: Optional context (daily totals, constraints, etc.) - not used yet
        
        Returns:
            List of candidate meal dictionaries with:
            - id: Candidate ID (assigned by workspace manager when saved)
            - meal_type: Meal category (breakfast, lunch, dinner, snack names)
            - items: List of food items
            - source_date: Original date from history
            - generation_method: "history_search"
    
        """
        # Phase 1: Use history search
        candidates = self._generate_from_history(
            meal_type=meal_type,
            max_results=max_candidates,
            lookback_days=lookback_days
        )
        
        return candidates
    
    # =========================================================================
    # Phase 1: History-based generation
    # =========================================================================
    
    def _generate_from_history(
        self,
        meal_type: str,
        max_results: int,
        lookback_days: int
    ) -> List[Dict[str, Any]]:
        """
        Extract meals from history matching the meal type.
        
        This reuses the logic from PlanCommand._search_history() but returns
        candidates in the standard generation format.
        
        Args:
            meal_type: Meal category to search for
            max_results: Maximum candidates to return
            lookback_days: Days to look back
        
        Returns:
            List of candidate meal dictionaries
        """
        log_df = self.log.df
        
        if log_df.empty:
            return []
        
        # Get column names
        date_col = get_date_column(log_df)
        codes_col = get_codes_column(log_df)
        
        if not date_col or not codes_col:
            return []
        
        # Filter by date range
        today = date.today()
        start_date = today - timedelta(days=lookback_days)
        
        log_df[date_col] = pd.to_datetime(log_df[date_col], errors='coerce')
        mask = (log_df[date_col] >= str(start_date)) & (log_df[date_col] <= str(today))
        recent_df = log_df[mask]
        
        if recent_df.empty:
            return []
        
        # Extract meals matching the type
        candidates = []
        
        for _, row in recent_df.iterrows():
            meal_date = str(row[date_col])[:10]
            codes_str = str(row[codes_col])
            
            # Parse the codes string into items
            try:
                items = parse_selection_to_items(codes_str)
            except Exception:
                continue
            
            if not items:
                continue
            
            meal_items = self._filter_to_meal(items, meal_type)
            if meal_items:
                candidate = {
                    "meal_type": meal_type,  # CHANGED from meal_name
                    "items": meal_items,
                    "source_date": meal_date,
                    "generation_method": "history_search",
                    "description": f"From {meal_date}"
                }
                candidates.append(candidate)
                    
                if len(candidates) >= max_results:
                    return candidates
        
        return candidates
    
    def _filter_to_meal(self, items: List[Dict[str, Any]], meal_name: str) -> List[Dict[str, Any]]:
        """Filter items to only those in the specified meal (matches report_command logic)."""
        filtered = []
        current_meal = None
        
        for item in items:
            # Check if this is a time marker (has 'time' key but no 'code' key)
            if isinstance(item, dict) and 'time' in item and 'code' not in item:
                # Categorize meal name from time
                time_str = item.get('time', '')
                meal_override = item.get('meal_override')
                current_meal = categorize_time(time_str, meal_override)
            elif current_meal and current_meal.lower() == meal_name.lower():
                # Include this item if we're in the target meal
                filtered.append(item)
        
        return filtered
    
    # =========================================================================
    # Future: Template-based generation (placeholders)
    # =========================================================================
    
    def _generate_from_template(
        self,
        template_path: str,
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Generate meals using template and component pools.
        
        FUTURE: Phase 2 or 3 implementation
        
        Will use:
        - Template structure (from meal_templates in config)
        - Component pools (protein sources, vegetables, starches, etc.)
        - Constraints (frozen portions, availability, locks)
        - Context (gaps from earlier meals)
        
        Returns:
            List of generated candidates
        """
        # Placeholder for future implementation
        raise NotImplementedError("Template-based generation not yet implemented")
    
    def _generate_from_ai(
        self,
        meal_type: str,
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Generate meals using AI suggestions.
        
        FUTURE: Phase 3+ implementation
        
        Could use:
        - LLM-based meal composition
        - Learned patterns from user history
        - Contextual awareness (season, time, preferences)
        
        Returns:
            List of AI-generated candidates
        """
        # Placeholder for future implementation
        raise NotImplementedError("AI-based generation not yet implemented")
    
    def _hybrid_generation(
        self,
        meal_type: str,
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Combine multiple generation strategies.
        
        FUTURE: Advanced implementation
        
        Could blend:
        - History-based candidates (proven meals)
        - Template variations (structured diversity)
        - AI suggestions (novel combinations)
        - Modified favorites (swap one component)
        
        Returns:
            Blended list of candidates from multiple sources
        """
        # Placeholder for future implementation
        raise NotImplementedError("Hybrid generation not yet implemented")