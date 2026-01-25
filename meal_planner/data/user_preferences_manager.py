# meal_planner/data/user_preferences_manager.py
"""
User preferences manager/
"""
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import date, timedelta
import pandas as pd

class UserPreferencesManager:
    """
    Manages user-specific food preferences and inventory.
    
    Handles:
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
            
    def _create_default_file(self) -> None:
        """Create default user preferences file."""
        default = {
            "version": "1.0",
            "description": "User-specific food preferences and inventory",
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

