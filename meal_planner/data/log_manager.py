"""
Daily log manager for meal plan entries.

Handles CRUD operations on the daily log CSV file containing
historical meal entries with their nutritional totals.
"""
import pandas as pd
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import date

from meal_planner.utils import ColumnResolver, get_date_column, get_codes_column


class LogManager:
    """
    Manages the daily meal log CSV file.
    
    Provides methods to read, write, update, and query logged meals.
    """
    
    def __init__(self, filepath: Path):
        """
        Initialize log manager.
        
        Args:
            filepath: Path to daily log CSV file
        """
        self.filepath = filepath
        self._df = None
        self._cols = None
    
    def load(self) -> pd.DataFrame:
        """
        Load log from disk, creating if it doesn't exist.
        
        Returns:
            DataFrame containing log data
        """
        try:
            self._df = pd.read_csv(self.filepath)
            
            # Ensure required columns exist
            required_cols = ['date', 'codes', 'cal', 'prot_g', 'carbs_g', 'fat_g']
            
            # Case-insensitive check
            existing_lower = {str(c).lower() for c in self._df.columns}
            
            # Add missing columns
            if 'gl' not in existing_lower:
                self._df['gl'] = 0
            if 'sugar_g' not in existing_lower:
                self._df['sugar_g'] = 0
            
        except FileNotFoundError:
            # Create empty log with proper structure
            self._df = pd.DataFrame(columns=[
                'date', 'codes', 'cal', 'prot_g', 'carbs_g', 'fat_g', 'gl', 'sugar_g'
            ])
        
        self._cols = ColumnResolver(self._df)
        return self._df
    
    @property
    def df(self) -> pd.DataFrame:
        """Get the log DataFrame (loads if needed)."""
        if self._df is None:
            self.load()
        return self._df
    
    @property
    def cols(self) -> ColumnResolver:
        """Get column resolver for log DataFrame."""
        if self._cols is None:
            self.load()
        return self._cols
    
    def save(self) -> None:
        """Save log to disk."""
        if self._df is not None:
            self._df.to_csv(self.filepath, index=False)
    
    def reload(self) -> pd.DataFrame:
        """Reload log from disk (discards cached data)."""
        self._df = None
        self._cols = None
        return self.load()
    
    def get_entries_for_date(self, query_date: str) -> pd.DataFrame:
        """
        Get all log entries for a specific date.
        
        Args:
            query_date: Date string (YYYY-MM-DD)
        
        Returns:
            DataFrame of entries for that date (may be empty)
        """
        date_col = self.cols.date
        return self.df[self.df[date_col].astype(str) == str(query_date)].copy()
    
    def append_entry(self, entry: Dict[str, Any]) -> None:
        """
        Append a new entry to the log.
        
        Args:
            entry: Dictionary with keys: date, codes, cal, prot_g, carbs_g, fat_g, gl, sugar_g
        
        Example:
            >>> log = LogManager("log.csv")
            >>> log.append_entry({
            ...     'date': '2025-01-15',
            ...     'codes': 'B.1, S2.4',
            ...     'cal': 500,
            ...     'prot_g': 30,
            ...     'carbs_g': 50,
            ...     'fat_g': 15,
            ...     'gl': 20
            ...     'sugar_g': 10,
            ... })
            >>> log.save()
        """
        # Ensure all required fields are present
        required = ['date', 'codes', 'cal', 'prot_g', 'carbs_g', 'fat_g']
        for field in required:
            if field not in entry:
                raise ValueError(f"Missing required field: {field}")
        
        # Add optional fields with defaults
        if 'sugar_g' not in entry:
            entry['sugar_g'] = 0
        if 'gl' not in entry:
            entry['gl'] = 0
        
        # Append to DataFrame
        new_row = pd.DataFrame([entry])
        self._df = pd.concat([self._df, new_row], ignore_index=True)
    
    def update_date(self, query_date: str, codes: str, totals: Dict[str, float]) -> bool:
        """
        Update the first entry for a date with new codes and totals.
        
        Args:
            query_date: Date to update (YYYY-MM-DD)
            codes: New codes string
            totals: Dictionary with cal, prot_g, carbs_g, fat_g, gl, sugar_g
        
        Returns:
            True if entry was found and updated, False otherwise
        
        Example:
            >>> log.update_date('2025-01-15', 'B.1 x2', {
            ...     'cal': 600, 'prot_g': 40, 'carbs_g': 60,
            ...     'fat_g': 20, 'gl': 25, 'sugar_g': 15
            ... })
        """
        date_col = self.cols.date
        codes_col = self.cols.codes
        
        # Find entries for this date
        mask = self.df[date_col].astype(str) == str(query_date)
        indices = self.df.index[mask].tolist()
        
        if not indices:
            return False
        
        # Update first entry
        idx = indices[0]
        self._df.at[idx, codes_col] = codes
        self._df.at[idx, self.cols.cal] = int(round(totals.get('cal', 0)))
        self._df.at[idx, self.cols.prot_g] = int(round(totals.get('prot_g', 0)))
        self._df.at[idx, self.cols.carbs_g] = int(round(totals.get('carbs_g', 0)))
        self._df.at[idx, self.cols.fat_g] = int(round(totals.get('fat_g', 0)))
        
        # Handle sugar_g and gl (may not exist in older logs)
        gl_col = self.cols.gl
        if gl_col:
            self._df.at[idx, gl_col] = int(round(totals.get('gl', 0)))
        sugar_col = self.cols.sugar_g
        if sugar_col:
            self._df.at[idx, sugar_col] = int(round(totals.get('sugar_g', 0)))
        
        
        return True
    
    def delete_date(self, query_date: str) -> int:
        """
        Delete all entries for a specific date.
        
        Args:
            query_date: Date to delete (YYYY-MM-DD)
        
        Returns:
            Number of entries deleted
        """
        date_col = self.cols.date
        
        before_count = len(self._df)
        self._df = self._df[self._df[date_col].astype(str) != str(query_date)].reset_index(drop=True)
        after_count = len(self._df)
        
        return before_count - after_count
    
    def get_date_range(self, start_date: Optional[str] = None, 
                       end_date: Optional[str] = None) -> pd.DataFrame:
        """
        Get entries within a date range (inclusive).
        
        Args:
            start_date: Start date (YYYY-MM-DD), None for no lower bound
            end_date: End date (YYYY-MM-DD), None for no upper bound
        
        Returns:
            Filtered DataFrame
        """
        date_col = self.cols.date
        result = self.df.copy()
        
        if start_date:
            result = result[result[date_col].astype(str) >= str(start_date)]
        if end_date:
            result = result[result[date_col].astype(str) <= str(end_date)]
        
        return result
    
    def ensure_numeric_columns(self) -> None:
        """
        Ensure nutrient columns are numeric type.
        
        Converts string values to numbers, replacing errors with 0.
        """
        numeric_cols = [
            self.cols.cal,
            self.cols.prot_g,
            self.cols.carbs_g,
            self.cols.fat_g,
        ]
        
        if self.cols.sugar_g:
            numeric_cols.append(self.cols.sugar_g)
        if self.cols.gl:
            numeric_cols.append(self.cols.gl)
        
        for col in numeric_cols:
            if col in self._df.columns:
                self._df[col] = pd.to_numeric(self._df[col], errors='coerce').fillna(0)
    
    def get_summary(self, start_date: Optional[str] = None,
                    end_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Get summary statistics for a date range.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        
        Returns:
            Dictionary with totals and averages
        """
        df = self.get_date_range(start_date, end_date)
        
        if df.empty:
            return {
                'total_days': 0,
                'totals': {},
                'averages': {}
            }
        
        self.ensure_numeric_columns()
        
        total_days = len(df)
        
        totals = {
            'cal': int(df[self.cols.cal].sum()),
            'prot_g': int(df[self.cols.prot_g].sum()),
            'carbs_g': int(df[self.cols.carbs_g].sum()),
            'fat_g': int(df[self.cols.fat_g].sum()),
        }
        
        averages = {
            'cal': int(round(df[self.cols.cal].mean())),
            'prot_g': int(round(df[self.cols.prot_g].mean())),
            'carbs_g': int(round(df[self.cols.carbs_g].mean())),
            'fat_g': int(round(df[self.cols.fat_g].mean())),
        }
        
        if self.cols.gl:
            totals['gl'] = int(df[self.cols.gl].sum())
            averages['gl'] = int(round(df[self.cols.gl].mean()))

        if self.cols.sugar_g:
            totals['sugar_g'] = int(df[self.cols.sugar_g].sum())
            averages['sugar_g'] = int(round(df[self.cols.sugar_g].mean()))

        return {
            'total_days': total_days,
            'totals': totals,
            'averages': averages
        }


# Convenience functions for backward compatibility
def ensure_log(filepath: Path) -> pd.DataFrame:
    """Load or create log file (backward compatible)."""
    manager = LogManager(filepath)
    return manager.load()


def save_log(log: pd.DataFrame, filepath: Path) -> None:
    """Save log DataFrame (backward compatible)."""
    log.to_csv(filepath, index=False)