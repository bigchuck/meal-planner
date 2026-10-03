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
        self._low_confidence_periods: List[Dict[str, Any]] = []
    
    def load(self) -> bool:
        """
        Load and validate user preferences from disk.
        
        Returns:
            True if loaded successfully, False otherwise
        """
        self._validation_errors.clear()
        self._prefs = None
        self._low_confidence_periods = []
        
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

    def get_low_confidence_periods(self) -> List[Dict[str, Any]]:
        """
        Get validated low-confidence logging periods.

        Returns:
            List of {'start': date, 'end': date, 'note': str}, sorted by start.
            Empty if the section is missing or preferences not loaded.
        """
        return [dict(p) for p in self._low_confidence_periods]

    def is_low_confidence(self, day: date) -> bool:
        """Check whether a date falls within a low-confidence period."""
        return any(p['start'] <= day <= p['end'] for p in self._low_confidence_periods)

    # =========================================================================
    # Validation
    # =========================================================================
    
    def _validate_structure(self) -> None:
        """Validate preferences structure (lenient)."""
        if not isinstance(self._prefs, dict):
            self._validation_errors.append("Root must be a JSON object")
            return

        self._validate_low_confidence_periods()

    def _validate_low_confidence_periods(self) -> None:
        """
        Validate and parse the optional low_confidence_periods section.

        A missing section is silent. Malformed entries are reported in
        validation errors and skipped; valid entries are kept.
        """
        section = self._prefs.get('low_confidence_periods')
        if section is None:
            return

        key = 'low_confidence_periods'
        if not isinstance(section, list):
            self._validation_errors.append(f"{key} must be a list")
            return

        parsed = []
        for i, entry in enumerate(section):
            where = f"{key}[{i}]"
            if not isinstance(entry, dict):
                self._validation_errors.append(f"{where}: must be an object")
                continue

            try:
                start = date.fromisoformat(str(entry.get('start')))
                end = date.fromisoformat(str(entry.get('end')))
            except ValueError:
                self._validation_errors.append(
                    f"{where}: start/end must be YYYY-MM-DD dates"
                )
                continue

            if end < start:
                self._validation_errors.append(f"{where}: end before start")
                continue

            note = entry.get('note', '')
            if not isinstance(note, str):
                self._validation_errors.append(f"{where}: note must be a string")
                continue

            parsed.append({'start': start, 'end': end, 'note': note, 'index': i})

        # Reject overlaps (keep the earlier-starting period)
        parsed.sort(key=lambda p: p['start'])
        kept = []
        for p in parsed:
            if kept and p['start'] <= kept[-1]['end']:
                self._validation_errors.append(
                    f"{key}[{p['index']}]: overlaps {key}[{kept[-1]['index']}]"
                )
                continue
            kept.append(p)

        self._low_confidence_periods = [
            {'start': p['start'], 'end': p['end'], 'note': p['note']} for p in kept
        ]

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

