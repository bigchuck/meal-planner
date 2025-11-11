"""
Micronutrients manager for optional nutrient tracking.

Manages meal_plan_nutrients.csv with micronutrient data keyed by code.
"""
import pandas as pd
from pathlib import Path
from typing import Optional, Dict


class NutrientsManager:
    """
    Manages optional micronutrient data.
    
    Keyed by code (matches master.csv codes).
    """
    
    def __init__(self, filepath: Path):
        """
        Initialize nutrients manager.
        
        Args:
            filepath: Path to nutrients CSV file
        """
        self.filepath = filepath
        self._df = None
    
    def load(self) -> pd.DataFrame:
        """
        Load nutrients from disk.
        
        Returns empty DataFrame if file doesn't exist (optional file).
        
        Returns:
            DataFrame with nutrient data
        """
        if not self.filepath.exists():
            # File is optional - return empty DataFrame
            self._df = pd.DataFrame(columns=["code"])
            return self._df
        
        try:
            self._df = pd.read_csv(self.filepath)
        except Exception:
            # Corrupted or missing - return empty
            self._df = pd.DataFrame(columns=["code"])
        
        return self._df
    
    @property
    def df(self) -> pd.DataFrame:
        """Get nutrients DataFrame (loads if needed)."""
        if self._df is None:
            self.load()
        return self._df
    
    def get_nutrients_for_code(self, code: str) -> Optional[Dict[str, float]]:
        """
        Get micronutrients for a specific code.
        
        Args:
            code: Meal code (case-insensitive)
        
        Returns:
            Dictionary of nutrient values, or None if not found
        
        Example:
            >>> mgr.get_nutrients_for_code("SO.11")
            {'fiber_g': 6.0, 'sodium_mg': 850.0, ...}
        """
        if self.df.empty:
            return None
        
        # Case-insensitive lookup
        code_upper = code.upper()
        
        # Handle case-insensitive column name
        code_col = None
        for col in self.df.columns:
            if str(col).lower() == "code":
                code_col = col
                break
        
        if code_col is None:
            return None
        
        match = self.df[self.df[code_col].str.upper() == code_upper]
        
        if match.empty:
            return None
        
        # Return as dict, excluding the code column
        row = match.iloc[0].to_dict()
        row.pop(code_col, None)  # Remove code key
        
        return row
    
    def has_nutrients(self, code: str) -> bool:
        """
        Check if code has micronutrient data.
        
        Args:
            code: Meal code
        
        Returns:
            True if nutrients are available
        """
        return self.get_nutrients_for_code(code) is not None
    
    def get_available_nutrients(self) -> list:
        """
        Get list of available nutrient column names.
        
        Returns:
            List of nutrient names (excluding 'code' column)
        """
        if self.df.empty:
            return []
        
        # Get all columns except 'code'
        cols = [c for c in self.df.columns if str(c).lower() != "code"]
        return cols