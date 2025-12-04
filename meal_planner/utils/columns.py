"""
Column name resolution utilities.

Handles case-insensitive column name matching for DataFrames.
This is needed because CSV files may have inconsistent capitalization.
"""
import pandas as pd
from typing import Optional


def get_column(df: pd.DataFrame, name: str) -> Optional[str]:
    """
    Return actual column name matching `name` case-insensitively, or None.
    
    Args:
        df: DataFrame to search
        name: Column name to find (case-insensitive)
    
    Returns:
        Actual column name if found, None otherwise
    
    Example:
        >>> df = pd.DataFrame(columns=['Code', 'OPTION', 'Cal'])
        >>> get_column(df, 'code')
        'Code'
        >>> get_column(df, 'option')
        'OPTION'
        >>> get_column(df, 'missing')
        None
    """
    name_lower = name.lower()
    for col in df.columns:
        if str(col).lower() == name_lower:
            return col
    return None


def get_date_column(df: pd.DataFrame) -> str:
    """
    Get the date column name (case-insensitive).
    
    Args:
        df: DataFrame to search
    
    Returns:
        Actual column name, defaults to 'date' if not found
    """
    return get_column(df, "date") or "date"


def get_codes_column(df: pd.DataFrame) -> str:
    """
    Get the codes column name (case-insensitive).
    
    Args:
        df: DataFrame to search
    
    Returns:
        Actual column name, defaults to 'codes' if not found
    """
    return get_column(df, "codes") or "codes"


def get_sugar_column(df: pd.DataFrame) -> Optional[str]:
    """
    Return the sugar column name among common variants, or None.
    
    IMPORTANT: Prioritizes 'sugars_g' (the canonical column) over 'sugar_g'.
    
    Tries in order: sugars_g, sugar_g, sugars, sugar
    
    Args:
        df: DataFrame to search
    
    Returns:
        Actual column name if found, None otherwise
    """
    # CRITICAL: Check sugars_g FIRST (canonical column name)
    # This prevents accidentally using an empty sugar_g column
    for variant in ["sugars_g", "sugar_g", "sugars", "sugar"]:
        col = get_column(df, variant)
        if col:
            return col
    return None


class ColumnResolver:
    """
    Resolves and caches column names for a DataFrame.
    
    This is useful when you need to reference the same columns repeatedly
    within a function or module, avoiding repeated lookups.
    
    Example:
        >>> cols = ColumnResolver(master_df)
        >>> print(f"Code column: {cols.code}")
        >>> row_value = df.iloc[0][cols.cal]
    """
    
    def __init__(self, df: pd.DataFrame):
        """
        Initialize resolver for a DataFrame.
        
        Args:
            df: DataFrame to resolve columns for
        """
        self.df = df
        self._cache = {}
    
    def _resolve(self, name: str, default: Optional[str] = None) -> str:
        """Resolve and cache a column name."""
        if name not in self._cache:
            result = get_column(self.df, name)
            self._cache[name] = result if result else (default or name)
        return self._cache[name]
    
    @property
    def code(self) -> str:
        """Code column name."""
        return self._resolve("code", "code")
    
    @property
    def option(self) -> str:
        """Option column name."""
        return self._resolve("option", "option")
    
    @property
    def section(self) -> str:
        """Section column name."""
        return self._resolve("section", "section")
    
    @property
    def cal(self) -> str:
        """Calories column name."""
        return self._resolve("cal", "cal")
    
    @property
    def prot_g(self) -> str:
        """Protein column name."""
        return self._resolve("prot_g", "prot_g")
    
    @property
    def carbs_g(self) -> str:
        """Carbs column name."""
        return self._resolve("carbs_g", "carbs_g")
    
    @property
    def fat_g(self) -> str:
        """Fat column name."""
        return self._resolve("fat_g", "fat_g")
    
    @property
    def sugar_g(self) -> Optional[str]:
        """Sugar column name (may be None if not found)."""
        if "sugar_g" not in self._cache:
            self._cache["sugar_g"] = get_sugar_column(self.df)
        return self._cache["sugar_g"]
    
    @property
    def gi(self) -> Optional[str]:
        """GI column name (may be None if not found)."""
        if "gi" not in self._cache:
            self._cache["gi"] = get_column(self.df, "GI")
        return self._cache["gi"]
    
    @property
    def gl(self) -> Optional[str]:
        """GL column name (may be None if not found)."""
        if "gl" not in self._cache:
            self._cache["gl"] = get_column(self.df, "GL")
        return self._cache["gl"]
    
    @property
    def date(self) -> str:
        """Date column name."""
        return self._resolve("date", "date")
    
    @property
    def codes(self) -> str:
        """Codes column name."""
        return self._resolve("codes", "codes")
    
    def as_dict(self) -> dict:
        """
        Return all resolved columns as a dictionary.
        
        Returns:
            Dictionary mapping logical names to actual column names
        """
        return {
            "code": self.code,
            "option": self.option,
            "section": self.section,
            "cal": self.cal,
            "prot_g": self.prot_g,
            "carbs_g": self.carbs_g,
            "fat_g": self.fat_g,
            "sugar_g": self.sugar_g,
            "gi": self.gi,
            "gl": self.gl,
            "date": self.date,
            "codes": self.codes,
        }