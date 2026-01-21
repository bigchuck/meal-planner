# meal_planner/filters/pre_score_filter.py
"""
Pre-score filtering for meal candidates.

Applies availability and lock constraints before scoring to reduce
the candidate pool to only viable options.
"""
from typing import List, Dict, Any, Set, Tuple 
import re


class PreScoreFilter:
    """
    Filters meal candidates before scoring.
    
    Current filters:
    - Lock constraints (include/exclude patterns and codes)
    - Availability (exclude_from_recommendations patterns)
    
    Future filters:
    - Frozen portion availability
    - Ingredient blacklist
    - Complexity constraints
    """
    
    def __init__(self, locks: Dict[str, Any], user_prefs=None):
        """
        Initialize pre-score filter.
        
        Args:
            locks: Lock configuration from workspace
                   {"include": {"SO.*": ["SO.1", "SO.11"]}, "exclude": ["DN."]}
            user_prefs: Optional UserPreferencesManager for exclude patterns
        """
        self.locks = locks
        self.user_prefs = user_prefs
    
    def filter_candidates(
        self,
        candidates: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Apply all pre-score filters to candidates.
        
        Args:
            candidates: List of raw generated candidates
        
        Returns:
            List of candidates that pass all filters
        """
        filtered = []
        filtered_out = []
        
        for candidate in candidates:
            # Extract food codes from candidate
            codes = self._extract_codes(candidate)
                    # Track rejection reasons
            rejection_reasons = []
            
            if not self._passes_lock_filters(codes):
                rejection_reasons.append("lock_constraint")
            if not self._passes_availability_filter(codes):
                rejection_reasons.append("availability")
            
            if rejection_reasons:
                candidate["rejection_reasons"] = rejection_reasons
                filtered_out.append(candidate)
            else:
                candidate["filter_passed"] = True
                filtered.append(candidate)

        return filtered, filtered_out
    
    def _extract_codes(self, candidate: Dict[str, Any]) -> Set[str]:
        """
        Extract food codes from candidate items.
        
        Args:
            candidate: Candidate dict with items list
        
        Returns:
            Set of uppercase food codes
        """
        codes = set()
        items = candidate.get("items", [])
        
        for item in items:
            if "code" in item:
                codes.add(item["code"].upper())
        
        return codes
    
    def _passes_lock_filters(self, codes: Set[str]) -> bool:
        """
        Check if candidate passes lock constraints.
        
        Lock rules:
        - If include locks exist, candidate MUST contain at least one locked item
        - If exclude locks exist, candidate MUST NOT contain any excluded items
        
        Args:
            codes: Set of food codes in candidate
        
        Returns:
            True if candidate passes lock filters
        """
        include_locks = self.locks.get("include", {})
        exclude_locks = self.locks.get("exclude", [])
        
        # Check exclude locks first (hard reject)
        if exclude_locks:
            if self._matches_exclude_locks(codes, exclude_locks):
                return False
        
        # Check include locks (must have at least one)
        if include_locks:
            if not self._matches_include_locks(codes, include_locks):
                return False
        
        return True
    
    def _matches_exclude_locks(
        self,
        codes: Set[str],
        exclude_locks: List[str]
    ) -> bool:
        """
        Check if any codes match exclude locks.
        
        Args:
            codes: Food codes in candidate
            exclude_locks: List of patterns/codes to exclude
        
        Returns:
            True if candidate contains excluded items (REJECT)
        """
        for lock in exclude_locks:
            if lock.endswith(".*"):
                # Pattern lock (e.g., "DN.*")
                pattern = lock[:-2]  # Remove .*
                for code in codes:
                    if code.startswith(pattern):
                        return True
            else:
                # Specific code lock
                if lock.upper() in codes:
                    return True
        
        return False
    
    def _matches_include_locks(
        self,
        codes: Set[str],
        include_locks: Dict[str, List[str]]
    ) -> bool:
        """
        Check if candidate contains at least one included item.
        
        Args:
            codes: Food codes in candidate
            include_locks: Dict of pattern -> [codes] or code -> []
        
        Returns:
            True if candidate contains at least one locked item (ACCEPT)
        """
        for lock_key, lock_codes in include_locks.items():
            if lock_key.endswith(".*"):
                # Pattern lock - check if any code matches pattern
                pattern = lock_key[:-2]
                for code in codes:
                    if code.startswith(pattern):
                        return True
                
                # Check specific codes in the pattern lock
                for lock_code in lock_codes:
                    if lock_code.upper() in codes:
                        return True
            else:
                # Specific code lock
                if lock_key.upper() in codes:
                    return True
        
        return False
    
    def _passes_availability_filter(self, codes: Set[str]) -> bool:
        """
        Check if candidate passes availability constraints.
        
        Uses exclude_from_recommendations in user preferences.
        
        Args:
            codes: Food codes in candidate
        
        Returns:
            True if candidate doesn't use unavailable items
        """
        if not self.user_prefs or not self.user_prefs.is_valid:
            return True
        
        prefs = self.user_prefs._prefs
        if not prefs:
            return True
        
        exclude_config = prefs.get("exclude_from_recommendations", {})
        exclude_patterns = exclude_config.get("patterns", [])
        exclude_items = exclude_config.get("items", [])
        
        # Check patterns
        for pattern in exclude_patterns:
            if pattern.endswith("."):
                # Pattern like "DN."
                for code in codes:
                    if code.startswith(pattern):
                        return False
        
        # Check specific items
        for item in exclude_items:
            if item.upper() in codes:
                return False
        
        return True
    
    def get_filter_stats(
        self,
        original_count: int,
        filtered_count: int
    ) -> str:
        """
        Get human-readable filter statistics.
        
        Args:
            original_count: Number of raw candidates
            filtered_count: Number after filtering
        
        Returns:
            Formatted stats string
        """
        rejected = original_count - filtered_count
        
        if rejected == 0:
            return f"All {original_count} candidates passed filters"
        
        percent = (rejected / original_count * 100) if original_count > 0 else 0
        
        return f"Filtered {rejected}/{original_count} candidates ({percent:.1f}% rejected)"