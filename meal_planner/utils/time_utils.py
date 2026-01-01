"""
Time-related utility functions.
"""

from typing import List, Tuple, Dict, Any, Optional

# Canonical meal names in display order
MEAL_NAMES = [
    "BREAKFAST",
    "MORNING SNACK",
    "LUNCH",
    "AFTERNOON SNACK",
    "DINNER",
    "EVENING SNACK"
]

_cached_boundaries = None

def initialize_meal_boundaries(user_prefs_manager):
    """
    Initialize meal time boundaries from user preferences.
    
    Call this once during app initialization. Parses the boundaries
    from user preferences and caches them for use by categorize_time().
    
    If boundaries are missing or invalid, boundaries remain None and
    categorize_time() will return None for all times (requiring user
    to fix their configuration).
    
    Args:
        user_prefs_manager: UserPreferencesManager instance
    """
    global _cached_boundaries
    
    _cached_boundaries = None  # Reset
    
    # Validate user preferences are loaded
    if not user_prefs_manager or not user_prefs_manager.is_valid:
        print("Warning: User preferences not loaded - meal time categorization disabled")
        print("Check meal_plan_user_preferences.json")
        return
    
    # Get boundaries config
    boundaries_config = user_prefs_manager.get_meal_time_boundaries()
    if not boundaries_config:
        print("Warning: meal_time_boundaries not found in user preferences")
        print("Meal time categorization disabled - please add meal_time_boundaries section")
        return
    
    # Build and cache boundaries
    try:
        _cached_boundaries = _build_boundaries_from_config(boundaries_config)
        # print(f"Loaded {len(set(b[0] for b in _cached_boundaries))} meal time boundaries")
    except Exception as e:
        print(f"Error parsing meal_time_boundaries: {e}")
        print("Meal time categorization disabled - please fix configuration")
        _cached_boundaries = None


def normalize_meal_name(input_name: str) -> str:
    """
    Normalize meal name input to canonical form.
    Handles various input formats:
    - "EVENING SNACK" (quoted with spaces)
    - "EVENING_SNACK" (underscores)
    - "EVENINGSNACK" (concatenated)
    - "evening snack" (lowercase)
    
    Args:
        input_name: User input meal name
    
    Returns:
        Canonical meal name or original input if no match
    """
    if not input_name:
        return input_name
    
    # Normalize: uppercase, replace underscores with spaces
    normalized = input_name.upper().replace("_", " ").strip()
    
    # Direct match
    if normalized in MEAL_NAMES:
        return normalized
    
    # Try removing all spaces for concatenated format
    compact = normalized.replace(" ", "")
    for meal in MEAL_NAMES:
        if compact == meal.replace(" ", ""):
            return meal
    
    # No match found, return original
    return input_name


def categorize_time(time_str: str, meal_override: str = None) -> str:
    """
    Categorize time string into meal name.
    
    Uses boundaries from user preferences (must be initialized first).
    Returns None if boundaries not configured or time invalid.

    Args:
        time_str: Time in HH:MM format
        meal_override: Optional explicit meal category to use instead of time-based logic

    
    Returns:
        Meal name or None
    """
    
    if meal_override:
        return meal_override

    if not time_str:
        return None
    
    # Get boundaries (returns None if not initialized)
    boundaries = _get_meal_boundaries()
    if boundaries is None:
        return None
    
    try:
        # Parse HH:MM
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        
        # Convert to minutes since midnight for easier comparison
        total_minutes = hour * 60 + minute

        # Find matching boundary
        for meal_name, start_min, end_min in boundaries:
            if start_min <= total_minutes <= end_min:
                return meal_name

        # No match found (shouldn't happen with proper config)
        return None  

    except:
        return None
    
def _parse_time_to_minutes(time_str: str) -> int:
    """
    Convert HH:MM time string to minutes since midnight.
    
    Args:
        time_str: Time in HH:MM format
    
    Returns:
        Minutes since midnight (0-1439)
    
    Raises:
        ValueError: If time_str is invalid
    """
    parts = time_str.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format: {time_str}")
    
    hour = int(parts[0])
    minute = int(parts[1])
    
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid time values: {time_str}")
    
    return hour * 60 + minute

def _build_boundaries_from_config(boundaries_config: Dict[str, Dict[str, str]]) -> List[Tuple[str, int, int]]:
    """
    Build sorted list of (meal_name, start_minutes, end_minutes) from config.
    
    Special handling for EVENING SNACK which wraps around midnight.
    
    Args:
        boundaries_config: Dictionary from user preferences
    
    Returns:
        List of tuples sorted by start time, with EVENING SNACK split if needed
    
    Example output:
        [
            ("BREAKFAST", 300, 629),
            ("MORNING SNACK", 630, 719),
            ("LUNCH", 720, 869),
            ("AFTERNOON SNACK", 870, 1019),
            ("DINNER", 1020, 1199),
            ("EVENING SNACK", 1200, 1439),  # Evening part
            ("EVENING SNACK", 0, 299)       # Morning part (wraps)
        ]
    """
    boundaries = []
    
    for meal_name, times in boundaries_config.items():
        start_str = times.get('start', '')
        end_str = times.get('end', '')
        
        if not start_str or not end_str:
            continue
        
        try:
            start_min = _parse_time_to_minutes(start_str)
            end_min = _parse_time_to_minutes(end_str)
            
            # Check if this wraps around midnight
            if end_min < start_min:
                # Split into two ranges
                # Part 1: start_min to end of day (1439)
                boundaries.append((meal_name, start_min, 1439))
                # Part 2: start of day (0) to end_min
                boundaries.append((meal_name, 0, end_min))
            else:
                # Normal range
                boundaries.append((meal_name, start_min, end_min))
        
        except ValueError:
            # Skip invalid entries
            continue
    
    # Sort by start time
    boundaries.sort(key=lambda x: x[1])
    
    return boundaries

def _get_meal_boundaries() -> Optional[List[Tuple[str, int, int]]]:
    """
    Get cached meal boundaries.
    
    Returns:
        List of (meal_name, start_minutes, end_minutes) tuples,
        or None if not initialized or configuration invalid
    """
    return _cached_boundaries