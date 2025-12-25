# meal_planner/data/user_preferences_manager.py
"""
User preferences manager for food inventory and preferences.

Manages meal_plan_user_preferences.json with user-specific settings
like frozen portions, staple foods, and unavailable items.
"""
import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta


class UserPreferencesManager:
    """
    Manages user-specific food preferences and inventory.
    
    If file doesn't exist, creates default structure.
    Invalid files are reported but don't block the application.
    """
    
    def __init__(self, filepath: Path):
        """
        Initialize user preferences manager.
        
        Args:
            filepath: Path to user preferences JSON file
        """
        self.filepath = filepath
        self._prefs: Optional[Dict[str, Any]] = None
        self._validation_errors: List[str] = []
        self._is_valid = False
    
    def load(self) -> bool:
        """
        Load and validate user preferences from disk.
        
        Creates default file if it doesn't exist.
        
        Returns:
            True if loaded and valid, False otherwise
        """
        self._validation_errors.clear()
        self._is_valid = False
        self._prefs = None
        
        # Create default if doesn't exist
        if not self.filepath.exists():
            self._create_default_file()
            return self.load()  # Reload
        
        # Load JSON
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                self._prefs = json.load(f)
        except json.JSONDecodeError as e:
            self._validation_errors.append(
                f"Invalid JSON in user preferences: {e}"
            )
            return False
        except Exception as e:
            self._validation_errors.append(
                f"Error reading user preferences: {e}"
            )
            return False
        
        # Validate structure (lenient - missing sections are okay)
        self._validate_structure()
        
        # Always consider valid even with warnings
        # (user prefs are optional/extensible)
        self._is_valid = True
        return True
    
    @property
    def is_valid(self) -> bool:
        """Check if preferences are loaded and valid."""
        return self._is_valid
    
    @property
    def validation_errors(self) -> List[str]:
        """Get list of validation error messages."""
        return self._validation_errors.copy()
    
    def get_error_message(self) -> str:
        """Get formatted error message for display."""
        if not self._validation_errors:
            return "User preferences not loaded"
        
        if len(self._validation_errors) == 1:
            return self._validation_errors[0]
        
        return f"User preferences has {len(self._validation_errors)} issues"
    
    @property
    def prefs(self) -> Optional[Dict[str, Any]]:
        """Get preferences dict (None if invalid)."""
        return self._prefs if self._is_valid else None
    
    # =========================================================================
    # Frozen Portions
    # =========================================================================
    
    def get_frozen_portions(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Get frozen portion info for a code.
        
        Args:
            code: Food code
        
        Returns:
            Dict with 'name', 'portions_g', 'thaw_time_hours', 'notes'
            or None if not frozen or not found
        """
        if not self.is_valid:
            return None
        
        frozen = self._prefs.get('frozen_portions', {}).get('items', {})
        return frozen.get(code)
    
    def get_all_frozen_codes(self) -> List[str]:
        """Get list of all frozen food codes."""
        if not self.is_valid:
            return []
        
        frozen = self._prefs.get('frozen_portions', {}).get('items', {})
        return list(frozen.keys())
    
    # =========================================================================
    # Staple Foods
    # =========================================================================
    
    def get_staple_foods(self) -> List[str]:
        """Get list of staple food codes (always available)."""
        if not self.is_valid:
            return []
        
        return self._prefs.get('staple_foods', {}).get('codes', [])
    
    def is_staple(self, code: str) -> bool:
        """Check if code is a staple food."""
        return code in self.get_staple_foods()
    
    # =========================================================================
    # Unavailable Items
    # =========================================================================
    
    def is_unavailable(self, code: str) -> Tuple[bool, str]:
        """
        Check if code is unavailable.
        
        Args:
            code: Food code
        
        Returns:
            (is_unavailable, reason) where reason is "permanent", "temporary", or ""
        """
        if not self.is_valid:
            return False, ""
        
        unavail = self._prefs.get('unavailable_items', {})
        
        # Check permanent
        permanent = unavail.get('permanent', {}).get('codes', [])
        if code in permanent:
            return True, "permanent"
        
        # Check temporary
        temporary = unavail.get('temporary', {}).get('codes', [])
        if code in temporary:
            return True, "temporary"
        
        return False, ""
    
    def get_unavailable_codes(self, include_temporary: bool = True) -> List[str]:
        """
        Get list of unavailable codes.
        
        Args:
            include_temporary: Include temporary unavailable items
        
        Returns:
            List of food codes
        """
        if not self.is_valid:
            return []
        
        unavail = self._prefs.get('unavailable_items', {})
        codes = []
        
        # Always include permanent
        permanent = unavail.get('permanent', {}).get('codes', [])
        codes.extend(permanent)
        
        # Optionally include temporary
        if include_temporary:
            temporary = unavail.get('temporary', {}).get('codes', [])
            codes.extend(temporary)
        
        return codes
    
    # =========================================================================
    # Recently Used
    # =========================================================================
    
    def get_recently_used(self, days: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get recently used foods within time window.
        
        Args:
            days: Number of days to look back (uses window_days from prefs if None)
        
        Returns:
            List of dicts with 'code', 'last_used', 'frequency'
        """
        if not self.is_valid:
            return []
        
        recent = self._prefs.get('recently_used', {})
        window = days if days is not None else recent.get('window_days', 30)
        codes = recent.get('codes', [])
        
        # Filter by window
        cutoff = datetime.now() - timedelta(days=window)
        
        filtered = []
        for item in codes:
            last_used_str = item.get('last_used')
            if last_used_str:
                try:
                    last_used = datetime.fromisoformat(last_used_str)
                    if last_used >= cutoff:
                        filtered.append(item)
                except ValueError:
                    # Invalid date format, skip
                    continue
        
        return filtered
    
    def get_recently_used_codes(self, days: Optional[int] = None) -> List[str]:
        """Get just the codes from recently used foods."""
        items = self.get_recently_used(days)
        return [item['code'] for item in items]
    
    # =========================================================================
    # Validation
    # =========================================================================
    
    def _validate_structure(self) -> None:
        """Validate preferences structure (lenient)."""
        if not isinstance(self._prefs, dict):
            self._validation_errors.append("Root must be a JSON object")
            return
        
        # Optional sections - just warn if malformed
        if 'frozen_portions' in self._prefs:
            frozen = self._prefs['frozen_portions']
            if not isinstance(frozen, dict) or 'items' not in frozen:
                self._validation_errors.append(
                    "Warning: frozen_portions malformed"
                )
        
        if 'staple_foods' in self._prefs:
            staples = self._prefs['staple_foods']
            if not isinstance(staples, dict) or 'codes' not in staples:
                self._validation_errors.append(
                    "Warning: staple_foods malformed"
                )
        
        if 'unavailable_items' in self._prefs:
            unavail = self._prefs['unavailable_items']
            if not isinstance(unavail, dict):
                self._validation_errors.append(
                    "Warning: unavailable_items malformed"
                )
    
    def _create_default_file(self) -> None:
        """Create default user preferences file."""
        default = {
            "version": "1.0",
            "description": "User-specific food preferences and inventory",
            
            "frozen_portions": {
                "description": "Frozen foods with discrete portion sizes",
                "items": {
                    # Example entry (commented in JSON would need to be removed)
                }
            },
            
            "staple_foods": {
                "description": "Always-available foods (pantry/fridge staples)",
                "codes": [],
                "notes": "Add codes for eggs, spinach, etc."
            },
            
            "unavailable_items": {
                "description": "Foods to exclude from recommendations",
                "temporary": {
                    "description": "Temporarily out of stock",
                    "codes": [],
                    "notes": "Cleared manually after shopping"
                },
                "permanent": {
                    "description": "Never recommend (allergies, strong dislikes)",
                    "codes": [],
                    "notes": "Add codes for foods to avoid"
                }
            },
            
            "recently_used": {
                "description": "Track recently consumed foods",
                "window_days": 30,
                "codes": [],
                "notes": "Auto-updated by recommendation engine"
            }
        }
        
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(default, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._validation_errors.append(
                f"Could not create default preferences file: {e}"
            )