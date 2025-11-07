# Meal Plan Logger

A comprehensive meal planning and nutrition tracking application.

## Setup

1. Install dependencies:
```
   pip install -r requirements.txt
```

2. Configure mode in `config.py`:
   - `DEVELOPMENT` - Uses test data in `./data/`
   - `PRODUCTION` - Uses real data in `C:\data\mealplan\`

3. Run the application:
```
   python main.py
```

## Project Structure

- `meal_planner/` - Core application modules
- `data/` - Development/test data files
- `tests/` - Unit tests
- `mealplan_logger.py` - Original monolithic version (for reference)

## Development

Currently refactoring from monolithic `mealplan_logger.py` to modular structure.
