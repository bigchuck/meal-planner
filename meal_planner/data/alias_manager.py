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
    
    def search(self, query: str) -> List[tuple]:
        """
        Search aliases with boolean logic support.
        
        Supports same query syntax as master search:
        - Quoted phrases: "green beans"
        - Boolean: AND, OR, NOT
        - Default: spaces = AND
        
        Args:
            query: Search query (searches code, name, and codes fields)
        
        Returns:
            List of (code, alias_dict) tuples
        """
        if not query.strip():
            return []
        
        from meal_planner.utils.search import parse_search_query
        import re
        import string
        
        # Parse query into clauses
        clauses = parse_search_query(query)
        
        if not clauses:
            return []
        
        results = []
        
        # Check each alias
        for code, alias_data in self.aliases.items():
            # Build searchable text (normalized)
            name = alias_data.get('name', '')
            codes = alias_data.get('codes', '')
            
            searchable = f"{code} {name} {codes}".lower()
            # Remove punctuation for matching
            searchable_normalized = searchable.translate(str.maketrans("", "", string.punctuation))
            
            # Check if alias matches any clause (OR between clauses)
            matches = False
            
            for clause in clauses:
                clause_matches = True
                
                # All positive terms must match (AND within clause)
                for term in clause["pos"]:
                    term_lower = term.lower()
                    term_normalized = term_lower.translate(str.maketrans("", "", string.punctuation))
                    
                    # Check both original and normalized
                    if term_lower not in searchable and term_normalized not in searchable_normalized:
                        clause_matches = False
                        break
                
                # No negative terms can match (NOT)
                if clause_matches:
                    for term in clause["neg"]:
                        term_lower = term.lower()
                        term_normalized = term_lower.translate(str.maketrans("", "", string.punctuation))
                        
                        if term_lower in searchable or term_normalized in searchable_normalized:
                            clause_matches = False
                            break
                
                if clause_matches:
                    matches = True
                    break  # Found a matching clause
            
            if matches:
                results.append((code, alias_data))
        
        return results