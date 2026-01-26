"""
Recipes manager for ingredient lists.

Manages meal_plan_recipes.csv with code as the lookup key.
"""
import pandas as pd
from pathlib import Path
from typing import Optional


class RecipesManager:
    """
    Manages optional recipe ingredient lists.
    
    Keyed by code (matches master.csv codes).
    File format: code,ingredients
    """
    
    def __init__(self, filepath: Path):
        """
        Initialize recipes manager.
        
        Args:
            filepath: Path to recipes CSV file
        """
        self.filepath = filepath
        self._df = None
    
    def load(self) -> pd.DataFrame:
        """
        Load recipes from disk.
        
        Returns empty DataFrame if file doesn't exist (optional file).
        
        Returns:
            DataFrame with recipe data (code, ingredients)
        """
        if not self.filepath.exists():
            self._df = pd.DataFrame(columns=["code", "ingredients"])
            return self._df
        
        try:
            self._df = pd.read_csv(self.filepath)
        except Exception:
            self._df = pd.DataFrame(columns=["code", "ingredients"])
        
        return self._df
    
    @property
    def df(self) -> pd.DataFrame:
        """Get recipes DataFrame (loads if needed)."""
        if self._df is None:
            self.load()
        return self._df
    
    def get_recipe(self, code: str) -> Optional[str]:
        """
        Get ingredient list for a specific code.
        
        Args:
            code: Meal code (case-insensitive)
        
        Returns:
            Ingredients string, or None if not found
        
        Example:
            >>> mgr.get_recipe("SO.11")
            "16oz lean steak, 1 lb dry beans, 11oz okra, ..."
        """
        if self.df.empty:
            return None
        
        code_upper = code.upper().strip()
        
        # Find code column (case-insensitive)
        code_col = None
        for col in self.df.columns:
            if str(col).lower() == "code":
                code_col = col
                break
        
        if code_col is None:
            return None
        
        # Match
        match = self.df[self.df[code_col].str.upper().str.strip() == code_upper]
        
        if match.empty:
            return None
        
        # Find ingredients column
        ing_col = None
        for col in self.df.columns:
            if str(col).lower() == "ingredients":
                ing_col = col
                break
        
        if ing_col is None:
            return None
        
        return str(match.iloc[0][ing_col])
    
    def has_recipe(self, code: str) -> bool:
        """
        Check if code has a recipe.
        
        Args:
            code: Meal code
        
        Returns:
            True if recipe exists
        """
        return self.get_recipe(code) is not None
    
    def format_recipe(self, code: str) -> Optional[str]:
        """
        Format recipe as readable text.
        
        Args:
            code: Meal code
        
        Returns:
            Formatted recipe string, or None if not found
        """
        ingredients = self.get_recipe(code)
        
        if ingredients is None:
            return None
        
        lines = []
        lines.append(f"[{code}] Ingredients:")
        lines.append("─" * 60)
        
        # Split ingredients by commas, but respect parentheses
        ing_list = self._split_respecting_parens(ingredients)
        for ing in ing_list:
            lines.append(f"  • {ing}")
        
        lines.append("")
        
        return "\n".join(lines)

    def _split_respecting_parens(self, text: str) -> list:
        """
        Split text on commas, but not commas inside parentheses.
        
        Args:
            text: Text to split
        
        Returns:
            List of parts
        """
        parts = []
        current = []
        paren_depth = 0
        
        for char in text:
            if char == '(':
                paren_depth += 1
                current.append(char)
            elif char == ')':
                paren_depth -= 1
                current.append(char)
            elif char == ',' and paren_depth == 0:
                # Comma outside parentheses - split here
                parts.append(''.join(current).strip())
                current = []
            else:
                current.append(char)
        
        # Add remaining
        if current:
            parts.append(''.join(current).strip())
        
        return parts