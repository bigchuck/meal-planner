"""
Master meal database operations.

Handles loading and querying the master CSV file containing
all available meal codes and their nutritional information.
"""
import pandas as pd
from typing import Optional, Dict, Any
from pathlib import Path

from meal_planner.utils import ColumnResolver


class MasterLoader:
    """
    Loads and provides access to the master meal database.
    
    The master file contains all available meal codes with their
    nutritional information (calories, protein, carbs, fat, etc.).
    
    Optionally joins micronutrients and recipes from separate files.
    """
    
    def __init__(self, filepath: Path, nutrients_file: Path = None, recipes_file: Path = None):
        """
        Initialize loader with path to master CSV file.
        
        Args:
            filepath: Path to master CSV file
            nutrients_file: Optional path to nutrients CSV
            recipes_file: Optional path to recipes CSV (not joined, just stored)
        """
        self.filepath = filepath
        self.nutrients_file = nutrients_file
        self.recipes_file = recipes_file
        self._df = None
        self._cols = None
    
    def load(self) -> pd.DataFrame:
        """
        Load master file from disk.
        
        Returns:
            DataFrame containing master data
        
        Raises:
            FileNotFoundError: If master file doesn't exist
        """
        self._df = pd.read_csv(self.filepath)
        self._cols = ColumnResolver(self._df)
        return self._df
    
    @property
    def df(self) -> pd.DataFrame:
        """Get the master DataFrame (loads if needed)."""
        if self._df is None:
            self.load()
        return self._df
    
    @property
    def cols(self) -> ColumnResolver:
        """Get column resolver for master DataFrame."""
        if self._cols is None:
            self.load()
        return self._cols
    
    def reload(self) -> pd.DataFrame:
        """
        Reload master file from disk (discards cached data).
        
        Returns:
            Freshly loaded DataFrame
        """
        self._df = None
        self._cols = None
        return self.load()
    
    def lookup_code(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Look up a meal code and return its data.
        
        Args:
            code: Meal code to look up (case-insensitive)
        
        Returns:
            Dictionary of meal data if found, None otherwise
        
        Example:
            >>> loader = MasterLoader("master.csv")
            >>> row = loader.lookup_code("B.1")
            >>> print(row['option'], row['cal'])
        """
        code_upper = code.upper()
        code_col = self.cols.code
        
        # Case-insensitive match
        match = self.df[self.df[code_col].str.upper() == code_upper]
        
        if match.empty:
            return None
        
        return match.iloc[0].to_dict()
    
    def search(self, term: str) -> pd.DataFrame:
        """
        Search for meals matching a term with boolean logic support.
        
        Supports:
        - Quoted phrases: "green beans" (exact phrase)
        - Boolean operators: AND, OR, NOT
        - Default: spaces = AND
        - Code patterns: "fr." matches codes starting with FR.
        
        Args:
            term: Search query (case-insensitive)
        
        Returns:
            DataFrame of matching rows
        
        Examples:
            >>> loader.search("chicken")           # substring match
            >>> loader.search("green beans")       # both words (AND)
            >>> loader.search('"green beans"')     # exact phrase
            >>> loader.search("chicken OR fish")   # either word
            >>> loader.search("beans NOT green")   # beans but not green
            >>> loader.search("fr.")               # codes starting with FR.
        """
        from meal_planner.utils.search import hybrid_search
        
        if not term.strip():
            return pd.DataFrame()
        
        return hybrid_search(self.df, term.strip())
    
    def get_nutrient_totals(self, code: str, multiplier: float = 1.0) -> Optional[Dict[str, float]]:
        """
        Get nutrient totals for a code with optional multiplier.
        
        Args:
            code: Meal code
            multiplier: Amount multiplier (e.g., 0.5 for half portion)
        
        Returns:
            Dictionary with nutrient totals, or None if code not found
        
        Example:
            >>> loader = MasterLoader("master.csv")
            >>> nutrients = loader.get_nutrient_totals("B.1", multiplier=1.5)
            >>> print(f"Calories: {nutrients['cal']}")
        """
        row = self.lookup_code(code)
        if row is None:
            return None
        
        cols = self.cols
        
        def safe_multiply(key):
            """Safely multiply a nutrient value."""
            val = row.get(key, 0)
            try:
                return float(val) * multiplier
            except (ValueError, TypeError):
                return 0.0
        
        return {
            'cal': safe_multiply(cols.cal),
            'prot_g': safe_multiply(cols.prot_g),
            'carbs_g': safe_multiply(cols.carbs_g),
            'fat_g': safe_multiply(cols.fat_g),
            'sugar_g': safe_multiply(cols.sugar_g) if cols.sugar_g else 0.0,
            'gl': safe_multiply(cols.gl) if cols.gl else 0.0,
        }


# Convenience functions for backward compatibility with original code
def load_master(filepath: Path) -> pd.DataFrame:
    """
    Load master file (simple function for backward compatibility).
    
    Args:
        filepath: Path to master CSV
    
    Returns:
        DataFrame containing master data
    """
    return pd.read_csv(filepath)


def lookup_code_row(code: str, master: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """
    Look up a code in master DataFrame (backward compatible).
    
    Args:
        code: Meal code (case-insensitive)
        master: Master DataFrame
    
    Returns:
        Dictionary of row data if found, None otherwise
    """
    cols = ColumnResolver(master)
    code_col = cols.code
    
    match = master[master[code_col].str.upper() == code.upper()]
    if match.empty:
        return None
    
    return match.iloc[0].to_dict()