"""
Configuration for Meal Planner application.

Toggle between PRODUCTION and DEVELOPMENT mode.
"""
import os
from pathlib import Path

# ==================== MODE SELECTION ====================
# Change this to switch between production and development data
MODE = "DEVELOPMENT"  # Options: "PRODUCTION" or "DEVELOPMENT"
MODE = "PRODUCTION"
# ========================================================

# Base paths
PROJECT_ROOT = Path(__file__).parent
PRODUCTION_DATA_PATH = Path(r"C:\data\mealplan")
DEVELOPMENT_DATA_PATH = PROJECT_ROOT / "data"

# print(PROJECT_ROOT)
# print(DEVELOPMENT_DATA_PATH)

# Select data path based on mode
if MODE == "PRODUCTION":
    DATA_PATH = PRODUCTION_DATA_PATH
    print("⚠️  WARNING: Running in PRODUCTION mode - using real data!")
elif MODE == "DEVELOPMENT":
    DATA_PATH = DEVELOPMENT_DATA_PATH
    print("✓ Running in DEVELOPMENT mode - using test data copy")
else:
    raise ValueError(f"Invalid MODE: {MODE}. Must be 'PRODUCTION' or 'DEVELOPMENT'")

# File paths
MASTER_FILE = DATA_PATH / "meal_plan_master.csv"
LOG_FILE = DATA_PATH / "meal_plan_daily_log.csv"
PENDING_FILE = DATA_PATH / "meal_plan_pending.json"
NUTRIENTS_FILE = DATA_PATH / "meal_plan_nutrients.csv"
RECIPES_FILE = DATA_PATH / "meal_plan_recipes.csv"
ALIASES_FILE = DATA_PATH / "meal_plan_aliases.json"

print(f"Using these files: ")
print(f"  master: {MASTER_FILE}")
print(f"  log: {LOG_FILE}")
print(f"  pending: {PENDING_FILE}")
print(f"  nutrients: {NUTRIENTS_FILE}")
print(f"  recipes: {RECIPES_FILE}")
print(f"  aliases: {ALIASES_FILE}")

# Verify files exist
def verify_data_files():
    """Check that all required data files exist."""
    missing = []
    
    # Master and Log are required
    for file_path in [MASTER_FILE, LOG_FILE]:
        if not file_path.exists():
            missing.append(str(file_path))
    
    # Pending file is optional (created on first 'start')
    # Just check that it's not there, but don't error
    
    if missing:
        raise FileNotFoundError(
            f"Missing data files in {MODE} mode:\n" + 
            "\n".join(f"  - {f}" for f in missing)
        )
    
    return True

# Chart output
CHART_OUTPUT_FILE = DATA_PATH / "meal_plan_trend.jpg"

# Application settings
DEFAULT_CHART_WINDOW = 7  # days for moving average
DATE_FORMAT = "%Y-%m-%d"

if __name__ == "__main__":
    # Test configuration
    print(f"\nMode: {MODE}")
    print(f"Data Path: {DATA_PATH}")
    print(f"Master File: {MASTER_FILE}")
    print(f"Log File: {LOG_FILE}")
    print(f"Pending File: {PENDING_FILE}")
    print(f"\nFiles exist: {verify_data_files()}")