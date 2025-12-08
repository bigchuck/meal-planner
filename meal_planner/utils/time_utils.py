"""
Time-related utility functions.
"""

# Canonical meal names in display order
MEAL_NAMES = [
    "BREAKFAST",
    "MORNING SNACK",
    "LUNCH",
    "AFTERNOON SNACK",
    "DINNER",
    "EVENING SNACK"
]


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


def categorize_time(time_str: str) -> str:
    """
    Categorize time string into meal name.
    
    Args:
        time_str: Time in HH:MM format
    
    Returns:
        Meal name or None
    """
    if not time_str:
        return None
    
    try:
        # Parse HH:MM
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        
        # Convert to minutes since midnight for easier comparison
        total_minutes = hour * 60 + minute
        
        # Time ranges (in minutes)
        # Breakfast: 05:00 - 10:29 (300 - 629)
        # Morning Snack: 10:30 - 11:59 (630 - 719)
        # Lunch: 12:00 - 14:29 (720 - 869)
        # Afternoon Snack: 14:30 - 16:59 (870 - 1019)
        # Dinner: 17:00 - 19:59 (1020 - 1199)
        # Evening Snack: 20:00 - 04:59 (1200+ or 0-299)
        
        if 300 <= total_minutes <= 629:
            return "BREAKFAST"
        elif 630 <= total_minutes <= 719:
            return "MORNING SNACK"
        elif 720 <= total_minutes <= 869:
            return "LUNCH"
        elif 870 <= total_minutes <= 1019:
            return "AFTERNOON SNACK"
        elif 1020 <= total_minutes <= 1199:
            return "DINNER"
        else:  # 1200+ or 0-299
            return "EVENING SNACK"
    except:
        return None