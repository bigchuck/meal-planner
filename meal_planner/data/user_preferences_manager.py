# meal_planner/data/user_preferences_manager.py
"""
User preferences manager for personal food inventory and constraints.

Manages meal_plan_user_preferences.json with frozen portions, staples,
and unavailable items.
"""
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import date, timedelta


class UserPreferencesManager:
    """
    Manages user-specific food preferences and inventory.
    
    Handles:
    - Frozen portions (pre-portioned frozen foods)
    - Staple foods (always available items)
    - Unavailable items (foods to exclude from recommendations)
    - Recently used foods (from log history)
    """
    
    def __init__(self, filepath: Path, log_manager=None):
        """
        Initialize user preferences manager.
        
        Args:
            filepath: Path to user preferences JSON file
            log_manager: Optional LogManager for recently_used queries
        """
        self.filepath = filepath
        self.log_manager = log_manager
        self._prefs: Optional[Dict[str, Any]] = None
        self._validation_errors: List[str] = []
    
    def load(self) -> bool:
        """
        Load and validate user preferences from disk.
        
        Returns:
            True if loaded successfully, False otherwise
        """
        self._validation_errors.clear()
        self._prefs = None
        
        # Check file exists
        if not self.filepath.exists():
            self._create_default_file()
            return self.load()  # Retry after creating default
        
        # Load JSON
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                self._prefs = json.load(f)
        except json.JSONDecodeError as e:
            self._validation_errors.append(f"Invalid JSON: {e}")
            return False
        except Exception as e:
            self._validation_errors.append(f"Error reading file: {e}")
            return False
        
        # Validate structure (lenient - warnings only)
        self._validate_structure()
        
        return True
    
    @property
    def is_valid(self) -> bool:
        """Check if preferences are loaded."""
        return self._prefs is not None
    
    @property
    def validation_errors(self) -> List[str]:
        """Get list of validation warnings."""
        return self._validation_errors.copy()
    
    def get_error_message(self) -> str:
        """
        Get formatted error message for display.
        
        Returns:
            Single-line error summary
        """
        if not self._validation_errors:
            return "User preferences not loaded"
        
        if len(self._validation_errors) == 1:
            return self._validation_errors[0]
        
        return f"User preferences: {len(self._validation_errors)} warnings"
    
    # =========================================================================
    # Accessors
    # =========================================================================
    
    def get_frozen_multiplier(self, code: str) -> Optional[float]:
        """
        Get frozen portion multiplier for a food code.
        
        Returns multiplier of the master.csv portion (NOT 100g - portions vary by item).
        Checks specific items first, then patterns. Items override patterns.
        
        Args:
            code: Food code (e.g., "MT.10", "FI.3")
        
        Returns:
            Multiplier (e.g., 1.5 means 1.5x the master.csv portion for this item), 
            or None if not frozen
        
        Examples:
            master.csv has MT.10 with portion "4 oz" (113g)
            Config: {"patterns": {"MT.": 1}, "items": {"MT.10": 2}}
            
            get_frozen_multiplier("MT.10") → 2.0 
            → Means 2 × (4 oz) = 8 oz frozen portion
            
            master.csv has FI.3 with portion "6 oz" (170g)
            Config: {"patterns": {"FI.": 1.5}, "items": {}}
            
            get_frozen_multiplier("FI.3") → 1.5
            → Means 1.5 × (6 oz) = 9 oz frozen portion
        """
        if not self.is_valid:
            return None
        
        frozen = self._prefs.get('frozen_portions', {})
        code_upper = code.upper().strip()
        
        # Check specific items first (highest priority)
        items = frozen.get('items', {})
        if isinstance(items, dict) and code_upper in items:
            try:
                return float(items[code_upper])
            except (TypeError, ValueError):
                pass  # Skip invalid entries
        
        # Check patterns (lower priority)
        patterns = frozen.get('patterns', {})
        if isinstance(patterns, dict):
            for pattern, multiplier in patterns.items():
                pattern_upper = str(pattern).upper().strip()
                if code_upper.startswith(pattern_upper):
                    try:
                        return float(multiplier)
                    except (TypeError, ValueError):
                        pass  # Skip invalid entries
        
        # No match found
        return None
    
    def get_staple_foods(self) -> List[str]:
        """
        Get list of always-available staple foods.
        
        Returns:
            List of food codes (uppercase)
            Example: ["EG.1", "BV.4", "VE.T1"]
        """
        if not self.is_valid:
            return []
        
        staples = self._prefs.get('staple_foods', {})
        codes = staples.get('codes', [])
        
        # Normalize to uppercase
        return [str(code).upper().strip() for code in codes if code]
    
    def get_unavailable_items(self) -> List[str]:
        """
        Get list of foods to exclude from recommendations.
        
        Includes both permanent exclusions (codes) and temporary exclusions (temporary).
        
        Returns:
            List of food codes (uppercase)
            Example: ["DA.3", "SW.7", "FI.9"]
        """
        if not self.is_valid:
            return []
        
        unavail = self._prefs.get('unavailable_items', {})
        
        # Get permanent exclusions
        codes = unavail.get('codes', [])
        permanent = [str(code).upper().strip() for code in codes if code]
        
        # Get temporary exclusions (e.g., shopping list items)
        temp_codes = unavail.get('temporary', [])
        temporary = [str(code).upper().strip() for code in temp_codes if code]
        
        # Combine both lists
        return permanent + temporary
    
    def get_leftover_friendly(self) -> List[str]:
        """
        Get list of code patterns for leftover-friendly foods.
        
        Returns:
            List of code prefixes (uppercase)
            Example: ["MT.", "FI.", "SO.", "CH."]
        """
        if not self.is_valid:
            return []
        
        leftover = self._prefs.get('leftover_friendly', {})
        patterns = leftover.get('patterns', [])
        
        # Normalize to uppercase
        return [str(pattern).upper().strip() for pattern in patterns if pattern]
    
    def get_leftover_excludes(self) -> List[str]:
        """
        Get list of specific codes to exclude from leftovers.
        
        These are items that match leftover patterns but aren't actually
        leftovers (e.g., beef jerky, shelf-stable items).
        
        Returns:
            List of food codes (uppercase) to exclude
            Example: ["MT.11", "MT.5"] (jerky, snacks)
        """
        if not self.is_valid:
            return []
        
        leftover = self._prefs.get('leftover_friendly', {})
        excludes = leftover.get('exclude', [])
        
        # Normalize to uppercase
        return [str(code).upper().strip() for code in excludes if code]
    
    def is_excluded_from_recommendations(self, code: str) -> bool:
        """
        Check if a code should be excluded from recommendations.
        
        Checks both patterns and specific items. Items override patterns.
        Used for restaurant items, takeout, delivery-only foods.
        
        Args:
            code: Food code to check (e.g., "DN.5", "FI.25")
        
        Returns:
            True if code should be excluded from recommendations
        
        Examples:
            With config: {"patterns": ["DN."], "items": ["FI.25"]}
            - is_excluded_from_recommendations("DN.5") → True (pattern match)
            - is_excluded_from_recommendations("FI.25") → True (specific item)
            - is_excluded_from_recommendations("MT.10") → False (no match)
        """
        if not self.is_valid:
            return False
        
        exclude_section = self._prefs.get('exclude_from_recommendations', {})
        code_upper = code.upper().strip()
        
        # Check specific items first (highest priority)
        items = exclude_section.get('items', [])
        if isinstance(items, list):
            items_upper = [str(item).upper().strip() for item in items if item]
            if code_upper in items_upper:
                return True
        
        # Check patterns (lower priority)
        patterns = exclude_section.get('patterns', [])
        if isinstance(patterns, list):
            for pattern in patterns:
                pattern_upper = str(pattern).upper().strip()
                if code_upper.startswith(pattern_upper):
                    return True
        
        return False
    
    def get_recently_used(self, days: int = 7) -> List[str]:
        """
        Get list of food codes used in the last N days.
        
        Args:
            days: Number of days to look back (default 7)
        
        Returns:
            List of unique food codes (uppercase), sorted by frequency
        """
        if not self.log_manager:
            return []
        
        # Calculate date range
        today = date.today()
        start_date = today - timedelta(days=days)
        
        # Get log entries in range
        log_df = self.log_manager.df
        if log_df.empty:
            return []
        
        # Get date column
        from meal_planner.utils import get_date_column
        date_col = get_date_column(log_df)
        if date_col is None:
            return []
        
        # Filter to date range
        log_df[date_col] = pd.to_datetime(log_df[date_col], errors='coerce')
        mask = (log_df[date_col] >= str(start_date)) & (log_df[date_col] <= str(today))
        recent_df = log_df[mask]
        
        if recent_df.empty:
            return []
        
        # Extract codes
        from meal_planner.utils import get_codes_column
        codes_col = get_codes_column(recent_df)
        if codes_col is None:
            return []
        
        # Parse all codes from recent entries
        from meal_planner.parsers import parse_selection_to_items
        all_codes = []
        
        for codes_str in recent_df[codes_col]:
            if not codes_str or str(codes_str).strip() == '':
                continue
            
            try:
                items = parse_selection_to_items(str(codes_str))
                for item in items:
                    if 'code' in item:
                        all_codes.append(item['code'].upper())
            except Exception:
                pass  # Skip malformed entries
        
        # Count frequencies and return sorted by usage
        from collections import Counter
        code_counts = Counter(all_codes)
        
        # Return codes sorted by frequency (most used first)
        return [code for code, count in code_counts.most_common()]

    def get_command_history_size(self) -> int:
        """
        Get command history size preference.
        
        Returns:
            Number of history entries to retain (default 10)
        """
        if not self._prefs:
            return 10
        
        size_config = self._prefs.get('command_history_size', {})
        
        # Handle both object format and simple int format
        if isinstance(size_config, dict):
            return size_config.get('value', 10)
        elif isinstance(size_config, int):
            return size_config
        else:
            return 10

    # =========================================================================
    # Validation
    # =========================================================================
    
    def _validate_structure(self) -> None:
        """Validate preferences structure (lenient)."""
        if not isinstance(self._prefs, dict):
            self._validation_errors.append("Root must be a JSON object")
            return
        
        # Validate frozen_portions
        if 'frozen_portions' in self._prefs:
            frozen = self._prefs['frozen_portions']
            if not isinstance(frozen, dict):
                self._validation_errors.append("Warning: frozen_portions must be an object")
            else:
                # Check for patterns key
                if 'patterns' in frozen and not isinstance(frozen.get('patterns'), dict):
                    self._validation_errors.append("Warning: frozen_portions.patterns must be an object")
                # Check for items key
                if 'items' in frozen and not isinstance(frozen.get('items'), dict):
                    self._validation_errors.append("Warning: frozen_portions.items must be an object")
        
        # Validate staple_foods
        if 'staple_foods' in self._prefs:
            staples = self._prefs['staple_foods']
            if not isinstance(staples, dict):
                self._validation_errors.append("Warning: staple_foods must be an object")
            elif 'codes' not in staples:
                self._validation_errors.append("Warning: staple_foods missing 'codes' key")
            elif not isinstance(staples.get('codes'), list):
                self._validation_errors.append("Warning: staple_foods.codes must be an array")
        
        # Validate unavailable_items
        if 'unavailable_items' in self._prefs:
            unavail = self._prefs['unavailable_items']
            if not isinstance(unavail, dict):
                self._validation_errors.append("Warning: unavailable_items must be an object")
            else:
                if 'codes' in unavail and not isinstance(unavail.get('codes'), list):
                    self._validation_errors.append("Warning: unavailable_items.codes must be an array")
                if 'temporary' in unavail and not isinstance(unavail.get('temporary'), list):
                    self._validation_errors.append("Warning: unavailable_items.temporary must be an array")
        
        # Validate leftover_friendly
        if 'leftover_friendly' in self._prefs:
            leftover = self._prefs['leftover_friendly']
            if not isinstance(leftover, dict):
                self._validation_errors.append("Warning: leftover_friendly must be an object")
            else:
                if 'patterns' in leftover and not isinstance(leftover.get('patterns'), list):
                    self._validation_errors.append("Warning: leftover_friendly.patterns must be an array")
                if 'exclude' in leftover and not isinstance(leftover.get('exclude'), list):
                    self._validation_errors.append("Warning: leftover_friendly.exclude must be an array")
        
        # Validate exclude_from_recommendations
        if 'exclude_from_recommendations' in self._prefs:
            exclude = self._prefs['exclude_from_recommendations']
            if not isinstance(exclude, dict):
                self._validation_errors.append("Warning: exclude_from_recommendations must be an object")
            else:
                if 'patterns' in exclude and not isinstance(exclude.get('patterns'), list):
                    self._validation_errors.append("Warning: exclude_from_recommendations.patterns must be an array")
                if 'items' in exclude and not isinstance(exclude.get('items'), list):
                    self._validation_errors.append("Warning: exclude_from_recommendations.items must be an array")
    
    def _create_default_file(self) -> None:
        """Create default user preferences file."""
        default = {
            "version": "1.0",
            "description": "User-specific food preferences and inventory",
            
            "frozen_portions": {
                "description": "Frozen foods with portion multipliers",
                "patterns": {},
                "items": {},
                "notes": "Multipliers of master.csv portions. Patterns: MT.: 1.5 (all meats 1.5x). Items: MT.10: 2 (MT.10 specifically 2x). Items override patterns."
            },
            
            "staple_foods": {
                "description": "Always-available foods (pantry/fridge staples)",
                "codes": [],
                "notes": "Example: EG.1, BV.4, VE.T1 for eggs, spinach, tomatoes"
            },
            
            "unavailable_items": {
                "description": "Foods to exclude from recommendations",
                "codes": [],
                "temporary": [],
                "notes": "codes = permanent exclusions (allergies, dislikes). temporary = shopping list items (exclude now, buy later)"
            },
            
            "leftover_friendly": {
                "description": "Food patterns that work well as leftovers",
                "patterns": [
                    "MT.",
                    "FI.",
                    "SO.",
                    "CH."
                ],
                "exclude": [],
                "notes": "patterns = categories to include. exclude = specific items to skip (e.g., MT.11 for beef jerky). Exclude overrides patterns."
            },
            
            "exclude_from_recommendations": {
                "description": "Items to exclude from meal planning recommendations",
                "patterns": [],
                "items": [],
                "notes": "Restaurant items, takeout, delivery-only foods. Items you can eat but can't prepare at home. Items override patterns."
            }
        }
        
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(default, f, indent=2, ensure_ascii=False)

    def get_meal_time_boundaries(self) -> Optional[Dict[str, Dict[str, str]]]:
        """
        Get meal time boundaries configuration.
        
        Returns:
            Dictionary mapping meal names to their time ranges:
            {
                "BREAKFAST": {"start": "05:00", "end": "10:29"},
                "MORNING SNACK": {"start": "10:30", "end": "11:59"},
                "LUNCH": {"start": "12:00", "end": "14:29"},
                "AFTERNOON SNACK": {"start": "14:30", "end": "16:59"},
                "DINNER": {"start": "17:00", "end": "19:59"},
                "EVENING SNACK": {"start": "20:00", "end": "04:59"}
            }
            Returns None if preferences not loaded.
        
        Example usage:
            boundaries = user_prefs.get_meal_time_boundaries()
            if boundaries:
                breakfast_times = boundaries.get("BREAKFAST")
                print(f"Breakfast: {breakfast_times['start']} to {breakfast_times['end']}")
        """
        if not self._prefs:
            return None
        
        # Get the meal_time_boundaries section
        boundaries_config = self._prefs.get('meal_time_boundaries', {})
        
        # Return the nested 'boundaries' dictionary
        return boundaries_config.get('boundaries', {})


    # Example of what it returns when config is present:
    # {
    #     "BREAKFAST": {"start": "05:00", "end": "10:29", "description": "Early morning meal"},
    #     "MORNING SNACK": {"start": "10:30", "end": "11:59", "description": "Mid-morning snack"},
    #     "LUNCH": {"start": "12:00", "end": "14:29", "description": "Midday meal"},
    #     "AFTERNOON SNACK": {"start": "14:30", "end": "16:59", "description": "Mid-afternoon snack"},
    #     "DINNER": {"start": "17:00", "end": "19:59", "description": "Evening meal"},
    #     "EVENING SNACK": {"start": "20:00", "end": "04:59", "description": "Late evening/night snack"}
    # }

    # Returns {} (empty dict) if meal_time_boundaries section exists but 'boundaries' key is missing
    # Returns None if self._prefs is None (preferences not loaded)


# Add pandas import at top
import pandas as pd