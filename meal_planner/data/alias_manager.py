# meal_planner/data/alias_manager.py
"""
Alias manager for code shortcuts.

Manages meal_plan_aliases.json with alias definitions.
"""
import json
from pathlib import Path
from typing import Optional, Dict, Any, List


class AliasManager:
    """
    Manages meal code aliases.
    
    Aliases are shortcuts that expand to multiple codes.
    """
    
    def __init__(self, filepath: Path):
        """
        Initialize alias manager.
        
        Args:
            filepath: Path to aliases JSON file
        """
        self.filepath = filepath
        self._aliases = None
    
    def load(self) -> Dict[str, Dict[str, Any]]:
        """
        Load aliases from disk.
        
        Returns empty dict if file doesn't exist (optional file).
        
        Returns:
            Dictionary of aliases keyed by code
        """
        if not self.filepath.exists():
            self._aliases = {}
            return self._aliases
        
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                self._aliases = json.load(f)
        except Exception:
            self._aliases = {}
        
        return self._aliases
    
    @property
    def aliases(self) -> Dict[str, Dict[str, Any]]:
        """Get aliases dict (loads if needed)."""
        if self._aliases is None:
            self.load()
        return self._aliases
    
    def lookup_alias(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Get alias definition for a code.
        
        Args:
            code: Alias code (case-insensitive)
        
        Returns:
            Dictionary with 'name', 'codes', and optional fields, or None
        """
        code_upper = code.upper().strip()
        
        for key, value in self.aliases.items():
            if key.upper().strip() == code_upper:
                return value
        
        return None
    
    def has_alias(self, code: str) -> bool:
        """
        Check if code is an alias.
        
        Args:
            code: Code to check
        
        Returns:
            True if alias exists
        """
        return self.lookup_alias(code) is not None
    
    def search(self, term: str) -> List[tuple]:
        """
        Search aliases by term.
        
        Args:
            term: Search term (searches code and name)
        
        Returns:
            List of (code, alias_dict) tuples
        """
        if not term.strip():
            return []
        
        term_lower = term.lower()
        results = []
        
        for code, alias_data in self.aliases.items():
            name = alias_data.get('name', '').lower()
            codes = alias_data.get('codes', '').lower()
            
            if (term_lower in code.lower() or 
                term_lower in name or 
                term_lower in codes):
                results.append((code, alias_data))
        
        return results