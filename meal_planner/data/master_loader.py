"""
Master meal database operations.

Handles loading and querying the master CSV file containing
all available meal codes and their nutritional information.
"""
import pandas as pd
from typing import Optional, Dict, Any, Tuple, List
from pathlib import Path

from meal_planner.utils import ColumnResolver

def _natural_sort_key(code: str) -> Tuple[str, str, int, str]:
    """
    Create a sort key for natural ordering of codes.
    
    Handles multiple patterns:
    - SO.1, SO.10, SO.13 -> ('SO.', '', 1, '')
    - SO.5b, SO.7a -> ('SO.', '', 5, 'b')
    - VE.T1, VE.T2 -> ('VE.', 'T', 1, '')
    - VE.MIX -> ('VE.', 'MIX', 0, '')
    
    Args:
        code: Code string to parse
    
    Returns:
        Tuple of (prefix, alpha_part, numeric_part, suffix) for sorting
    
    Examples:
        >>> _natural_sort_key("SO.1")
        ('SO.', '', 1, '')
        >>> _natural_sort_key("SO.13")
        ('SO.', '', 13, '')
        >>> _natural_sort_key("SO.5b")
        ('SO.', '', 5, 'b')
        >>> _natural_sort_key("VE.T1")
        ('VE.', 'T', 1, '')
        >>> _natural_sort_key("VE.MIX")
        ('VE.', 'MIX', 0, '')
    """
    import re
    
    code_upper = str(code).upper()
    
    # Split on the first dot
    if '.' not in code_upper:
        return (code_upper, '', 0, '')
    
    prefix, rest = code_upper.split('.', 1)
    prefix_with_dot = prefix + '.'
    
    # Match the part after the dot: [ALPHA][NUMBER][ALPHA]
    # Examples: "1", "10", "5b", "T1", "T2", "MIX"
    match = re.match(r'^([A-Za-z]*)(\d*)([A-Za-z]*)$', rest)
    
    if not match:
        # Fallback if pattern doesn't match
        return (prefix_with_dot, rest, 0, '')
    
    alpha_part = match.group(1)
    number_str = match.group(2)
    suffix_part = match.group(3)
    
    # Convert number to int (0 if empty)
    number = int(number_str) if number_str else 0
    
    return (prefix_with_dot, alpha_part, number, suffix_part)

class MasterLoader:
    """
    Loads and provides access to the master meal database.
    
    The master file contains all available meal codes with their
    nutritional information (calories, protein, carbs, fat, etc.).
    
    Optionally joins micronutrients and recipes from separate files.
    """
    
    def __init__(self, filepath: Path):
        """
        Initialize loader with path to master JSON file.
        
        Args:
            filepath: Path to master JSON file
        """
        self.filepath = filepath
        self._master_dict = None  # Source of truth: dict keyed by code
        self._df = None           # Derived view: flattened DataFrame
        self._cols = None

    def load(self) -> pd.DataFrame:
        """
        Load master file from disk (JSON format).
        
        Returns:
            DataFrame containing master data
        
        Raises:
            FileNotFoundError: If master file doesn't exist
        """
        self._master_dict = self._load_master_json()
        self._rebuild_dataframe()
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

    @property
    def nutrients_df(self) -> pd.DataFrame:
        """
        Get nutrients as DataFrame (compatibility with old NutrientsManager).
        
        Returns DataFrame with columns: code, fiber_g, sodium_mg, potassium_mg,
        vitA_mcg, vitC_mg, iron_mg
        """
        if not self._master_dict:
            self.load()
        
        rows = []
        for code, entry in self._master_dict.items():
            nutrients = entry.get('nutrients', {})
            if nutrients:  # Only include entries that have nutrients
                row = {'code': code}
                row.update(nutrients)
                rows.append(row)
        
        if not rows:
            # Return empty DataFrame with proper columns
            return pd.DataFrame(columns=['code', 'fiber_g', 'sodium_mg', 
                                        'potassium_mg', 'vitA_mcg', 'vitC_mg', 'iron_mg'])
        
        return pd.DataFrame(rows)

    @property
    def recipes_df(self) -> pd.DataFrame:
        """
        Get recipes as DataFrame (compatibility with old RecipesManager).
        
        Returns DataFrame with columns: code, ingredients
        """
        if not self._master_dict:
            self.load()
        
        rows = []
        for code, entry in self._master_dict.items():
            recipe = entry.get('recipe', '')
            if recipe:  # Only include entries that have recipes
                rows.append({'code': code, 'ingredients': recipe})
        
        if not rows:
            return pd.DataFrame(columns=['code', 'ingredients'])
        
        return pd.DataFrame(rows)

    def reload(self) -> pd.DataFrame:
        """
        Reload master file from disk (discards cached data).
        
        Returns:
            Freshly loaded DataFrame
        """
        self._master_dict = None
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
        
        Results are sorted naturally (SO.1, SO.2, ... SO.10, SO.11).
        
        Args:
            term: Search query (case-insensitive)
        
        Returns:
            DataFrame of matching rows, sorted naturally by code
        """
        from meal_planner.utils.search import hybrid_search
        
        if not term.strip():
            return pd.DataFrame()
        
        results = hybrid_search(self.df, term.strip())
        
        # Sort results naturally by code
        if not results.empty:
            code_col = self.cols.code
            results = results.copy()
            # Create temporary sort key column
            results['_sort_key'] = results[code_col].apply(_natural_sort_key)
            # Sort by the key
            results = results.sort_values('_sort_key')
            # Drop the temporary column
            results = results.drop(columns=['_sort_key']).reset_index(drop=True)
        
        return results
    
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

    def _load_master_json(self) -> Dict[str, Dict[str, Any]]:
        """
        Load master.json and build dictionary keyed by code.
        
        Validates:
        - Required fields present
        - No duplicate codes
        - Valid data types for macros
        
        Returns:
            Dictionary mapping code -> entry dict
        
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If JSON is invalid, has duplicates, or missing required fields
        """
        import json
        
        with open(self.filepath, 'r') as f:
            entries = json.load(f)
        
        if not isinstance(entries, list):
            raise ValueError("master.json must contain a list of entries")
        
        # Build dict keyed by code (uppercase for lookups)
        master_dict = {}
        errors = []
        
        for idx, entry in enumerate(entries):
            # Validate required fields
            if 'code' not in entry:
                errors.append(f"Entry {idx}: missing 'code' field")
                continue
            
            code = str(entry['code']).upper()
            
            # Check for duplicates
            if code in master_dict:
                errors.append(f"Entry {idx}: duplicate code '{code}'")
                continue
            
            # Validate required fields
            required = ['section', 'description', 'macros']
            missing = [f for f in required if f not in entry]
            if missing:
                errors.append(f"Code {code}: missing required fields: {', '.join(missing)}")
                continue
            
            # Validate macros structure
            macros = entry.get('macros', {})
            if not isinstance(macros, dict):
                errors.append(f"Code {code}: 'macros' must be a dict")
                continue
            
            required_macros = ['cal', 'prot_g', 'carbs_g', 'fat_g', 'GI', 'GL', 'sugar_g']
            missing_macros = [m for m in required_macros if m not in macros]
            if missing_macros:
                errors.append(f"Code {code}: missing macros: {', '.join(missing_macros)}")
                continue
            
            # Validate numeric types
            try:
                for key in required_macros:
                    float(macros[key])  # Will raise if not numeric
            except (ValueError, TypeError) as e:
                errors.append(f"Code {code}: invalid macro value - {e}")
                continue
            
            # Validate nutrients if present
            if 'nutrients' in entry:
                nutrients = entry['nutrients']
                if not isinstance(nutrients, dict):
                    errors.append(f"Code {code}: 'nutrients' must be a dict")
                    continue
                
                try:
                    for key, val in nutrients.items():
                        float(val)
                except (ValueError, TypeError) as e:
                    errors.append(f"Code {code}: invalid nutrient value - {e}")
                    continue
            
            master_dict[code] = entry
        
        if errors:
            raise ValueError(f"Validation errors in master.json:\n  " + "\n  ".join(errors))
        
        return master_dict

    def _rebuild_dataframe(self) -> None:
        """
        Rebuild food_master_df from master_dict.
        
        Flattens nested structure for backward compatibility.
        Maps 'description' field to 'option' column for compatibility.
        Creates DataFrame with columns: code, section, option, cal, prot_g, carbs_g, 
        fat_g, GI, GL, sugar_g, fiber_g, sodium_mg, potassium_mg, vitA_mcg, vitC_mg, 
        iron_mg, recipe, date_added, portion
        """
        if not self._master_dict:
            self._df = pd.DataFrame()
            self._cols = None
            return
        
        rows = []
        for code, entry in self._master_dict.items():
            # Base columns
            row = {
                'code': code,
                'section': entry.get('section', ''),
                'option': entry.get('description'),
                'date_added': entry.get('date_added', ''),
                'portion': entry.get('portion', ''),
            }
            
            # Flatten macros
            macros = entry.get('macros', {})
            row.update({
                'cal': macros.get('cal', 0.0),
                'prot_g': macros.get('prot_g', 0.0),
                'carbs_g': macros.get('carbs_g', 0.0),
                'fat_g': macros.get('fat_g', 0.0),
                'GI': macros.get('GI', 0.0),
                'GL': macros.get('GL', 0.0),
                'sugar_g': macros.get('sugar_g', 0.0),
            })
            
            # Flatten nutrients (if present)
            nutrients = entry.get('nutrients', {})
            row.update({
                'fiber_g': nutrients.get('fiber_g', 0.0),
                'sodium_mg': nutrients.get('sodium_mg', 0.0),
                'potassium_mg': nutrients.get('potassium_mg', 0.0),
                'vitA_mcg': nutrients.get('vitA_mcg', 0.0),
                'vitC_mg': nutrients.get('vitC_mg', 0.0),
                'iron_mg': nutrients.get('iron_mg', 0.0),
            })
            
            # Recipe (if present)
            row['recipe'] = entry.get('recipe', '')
            
            rows.append(row)
        
        self._df = pd.DataFrame(rows)
        
        # Sort naturally by code
        self._df['_sort_key'] = self._df['code'].apply(_natural_sort_key)
        self._df = self._df.sort_values('_sort_key').drop('_sort_key', axis=1).reset_index(drop=True)
        
        self._cols = ColumnResolver(self._df)

    def _save_master_json(self) -> None:
        """
        Save master_dict to JSON file with natural sorting.
        
        Converts dictionary back to sorted list format for storage.
        """
        import json
        from datetime import datetime
        
        if not self._master_dict:
            raise ValueError("No data to save")
        
        # Convert dict to list, sorted naturally by code
        entries = []
        sorted_codes = sorted(self._master_dict.keys(), key=_natural_sort_key)
        
        for code in sorted_codes:
            entries.append(self._master_dict[code])
        
        # Write to file
        with open(self.filepath, 'w') as f:
            json.dump(entries, f, indent=2)

    def add_or_update_entry(self, code: str, section: str, option: str,
                       macros: Dict[str, float], nutrients: Dict[str, float] = None,
                       recipe: str = None, portion: str = None) -> bool:
        """
        Add or update an entry in master_dict.
        
        Args:
            code: Food code (will be uppercased)
            section: Food section/category
            option: Food description (stored as 'description' in JSON)
            macros: Dict with cal, prot_g, carbs_g, fat_g, GI, GL, sugar_g
            nutrients: Optional dict with fiber_g, sodium_mg, etc.
            recipe: Optional recipe/ingredients string
            portion: Optional portion description
        
        Returns:
            True if entry was added, False if updated
        """
        from datetime import date
        
        code = code.upper()
        
        # Check if adding or updating
        existing = self._master_dict.get(code)
        is_new = existing is None
        
        if existing:
            # Preserve nutrients, recipe, and other optional fields
            entry = existing.copy()
            # Update only the fields we're setting
            entry['section'] = section
            entry['description'] = option
            entry['macros'] = macros

        else:
            # Build entry
            entry = {
                'code': code,
                'section': section,
                'description': option,  # Store as 'description' in JSON
                'macros': macros,
            }
        
        # Add optional fields if provided
        if nutrients:
            entry['nutrients'] = nutrients
        
        if recipe:
            entry['recipe'] = recipe
        
        if portion:
            entry['portion'] = portion
        
        # Add date_added for new entries
        if is_new:
            entry['date_added'] = str(date.today())
        else:
            # Preserve existing date_added
            if code in self._master_dict and 'date_added' in self._master_dict[code]:
                entry['date_added'] = self._master_dict[code]['date_added']
        
        # Update dict
        self._master_dict[code] = entry
        
        # Rebuild DataFrame
        self._rebuild_dataframe()
        
        return is_new

    def update_nutrients(self, code: str, nutrients: Dict[str, float]) -> bool:
        """
        Update nutrients for an existing entry.
        
        Args:
            code: Food code
            nutrients: Dict with nutrient values (fiber_g, sodium_mg, etc.)
        
        Returns:
            True if updated, False if code not found
        """
        code = code.upper()
        
        if code not in self._master_dict:
            return False
        
        # Update or create nutrients dict
        self._master_dict[code]['nutrients'] = nutrients
        
        # Rebuild DataFrame
        self._rebuild_dataframe()
        
        return True

    def update_recipe(self, code: str, recipe: str) -> bool:
        """
        Update recipe for an existing entry.
        
        Args:
            code: Food code
            recipe: Recipe/ingredients string
        
        Returns:
            True if updated, False if code not found
        """
        code = code.upper()
        
        if code not in self._master_dict:
            return False
        
        self._master_dict[code]['recipe'] = recipe
        
        # Rebuild DataFrame
        self._rebuild_dataframe()
        
        return True

    def save(self) -> None:
        """Save current state to disk."""
        self._save_master_json()

    def validate_entry(self, code: str) -> Dict[str, Any]:
        """
        Validate an entry's data quality.
        
        Checks:
        - Macros sum appropriately (calories ~= 4*prot + 4*carbs + 9*fat)
        - Reasonable value ranges
        - Required fields present
        
        Args:
            code: Food code to validate
        
        Returns:
            Dict with 'valid' (bool) and 'issues' (list of strings)
        """
        code = code.upper()
        
        if code not in self._master_dict:
            return {'valid': False, 'issues': [f"Code {code} not found"]}
        
        entry = self._master_dict[code]
        issues = []
        
        # Check macros
        macros = entry.get('macros', {})
        cal = macros.get('cal', 0)
        prot_g = macros.get('prot_g', 0)
        carbs_g = macros.get('carbs_g', 0)
        fat_g = macros.get('fat_g', 0)
        
        # Calculate expected calories (4-4-9 rule)
        expected_cal = (prot_g * 4) + (carbs_g * 4) + (fat_g * 9)
        if expected_cal > 0:
            diff_pct = abs(cal - expected_cal) / expected_cal * 100
            if diff_pct > 10:  # Allow 10% variance
                issues.append(f"Calorie mismatch: {cal} cal vs {expected_cal:.0f} expected ({diff_pct:.1f}% diff)")
        
        # Check for negative values
        for key, val in macros.items():
            if val < 0:
                issues.append(f"Negative value: {key}={val}")
        
        # Check for unreasonable values
        if cal > 2000:
            issues.append(f"Unusually high calories: {cal}")
        if prot_g > 200:
            issues.append(f"Unusually high protein: {prot_g}g")
        if carbs_g > 300:
            issues.append(f"Unusually high carbs: {carbs_g}g")
        if fat_g > 150:
            issues.append(f"Unusually high fat: {fat_g}g")
        
        # Check GI/GL relationship
        GI = macros.get('GI', 0)
        GL = macros.get('GL', 0)
        if GI > 0 and GL == 0 and carbs_g > 5:
            issues.append(f"Has GI ({GI}) but GL is 0 with {carbs_g}g carbs")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues
        }
    
    def get_all_codes(self) -> List[str]:
        """
        Get list of all food codes.
        
        Returns:
            List of codes, sorted naturally
        """
        if not self._master_dict:
            self.load()
        
        return sorted(self._master_dict.keys(), key=_natural_sort_key)

    def get_codes_by_section(self, section: str) -> List[str]:
        """
        Get all codes in a section.
        
        Args:
            section: Section name (case-insensitive)
        
        Returns:
            List of codes in that section, sorted naturally
        """
        if not self._master_dict:
            self.load()
        
        section_upper = section.upper()
        codes = [
            code for code, entry in self._master_dict.items()
            if entry.get('section', '').upper() == section_upper
        ]
        
        return sorted(codes, key=_natural_sort_key)

    def get_sections(self) -> List[str]:
        """
        Get list of all unique sections.
        
        Returns:
            Sorted list of section names
        """
        if not self._master_dict:
            self.load()
        
        sections = set(entry.get('section', '') for entry in self._master_dict.values())
        return sorted(sections)

    def get_nutrients(self, code: str) -> Optional[Dict[str, float]]:
        """
        Get nutrients for a code.
        
        Args:
            code: Food code
        
        Returns:
            Dict of nutrients or None if not found or no nutrients defined
        """
        code = code.upper()
        
        if code not in self._master_dict:
            return None
        
        return self._master_dict[code].get('nutrients')

    def get_recipe(self, code: str) -> Optional[str]:
        """
        Get recipe/ingredients for a code.
        
        Args:
            code: Food code
        
        Returns:
            Recipe string or None if not found or no recipe defined
        """
        code = code.upper()
        
        if code not in self._master_dict:
            return None
        
        return self._master_dict[code].get('recipe')

    def format_recipe(self, code: str) -> Optional[str]:
        """
        Format recipe with nice display (compatibility with old RecipesManager).
        
        Args:
            code: Food code
        
        Returns:
            Formatted recipe string or None
        """
        entry = self.lookup_code(code)
        
        if not entry:
            return None
        
        recipe = entry.get('recipe', '')
        if not recipe:
            return None
        
        option = entry.get('option', '')
        
        # Format output
        lines = [f"Recipe for {code} ({option}):", ""]
        
        # Split ingredients and format as bullet list
        ingredients = recipe.split(',')
        for ingredient in ingredients:
            lines.append(f"  • {ingredient.strip()}")
        
        return "\n".join(lines)

    def check_integrity(self) -> Dict[str, Any]:
        """
        Check overall data integrity.
        
        Returns:
            Dict with statistics and issues found
        """
        if not self._master_dict:
            self.load()
        
        stats = {
            'total_entries': len(self._master_dict),
            'sections': len(self.get_sections()),
            'with_nutrients': 0,
            'with_recipes': 0,
            'with_portions': 0,
            'issues': []
        }
        
        for code, entry in self._master_dict.items():
            if 'nutrients' in entry and entry['nutrients']:
                stats['with_nutrients'] += 1
            
            if 'recipe' in entry and entry['recipe']:
                stats['with_recipes'] += 1
            
            if 'portion' in entry and entry['portion']:
                stats['with_portions'] += 1
            
            # Validate each entry
            validation = self.validate_entry(code)
            if not validation['valid']:
                stats['issues'].extend([f"{code}: {issue}" for issue in validation['issues']])
        
        return stats

    def delete_entry(self, code: str) -> bool:
        """
        Delete an entry from master_dict.
        
        Args:
            code: Food code to delete
        
        Returns:
            True if deleted, False if not found
        """
        code = code.upper()
        
        if code not in self._master_dict:
            return False
        
        del self._master_dict[code]
        self._rebuild_dataframe()
        
        return True
    
    def get_entry_structured(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Get entry with hierarchical structure preserved (macros, nutrients nested).
        Use this for update operations to avoid clobbering other sections.
        
        Args:
            code: Food code
            
        Returns:
            Dict with nested structure, or None if not found
        """
        code_upper = code.upper()
        return self._master_dict.get(code_upper)