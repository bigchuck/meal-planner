# meal_planner/filters/pre_score_filter.py
"""
Pre-score filtering for meal candidates.

Applies availability and lock constraints before scoring to reduce
the candidate pool to only viable options.
"""
from typing import List, Dict, Any, Set, Tuple, Optional
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
    
    def __init__(self, locks: Dict[str, Any], user_prefs=None, inventory: Optional[Dict[str, Any]] = None):
        """
        Initialize pre-score filter.
        
        Args:
            locks: Lock configuration from workspace
                   {"include": {"SO.*": ["SO.1", "SO.11"]}, "exclude": ["DN."]}
            user_prefs: Optional UserPreferencesManager for exclude patterns
        """
        self.locks = locks
        self.user_prefs = user_prefs
        self.inventory = inventory or {"leftovers": {}, "batch": {}, "rotating": {}}
    
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

            # Check for reserved items
            reserved_items = self._check_reserved_items(codes)
            if reserved_items:
                rejection_reasons.extend([f"reserved:{code}" for code in reserved_items])
            
            # Check for depleted rotating items
            depleted_items = self._check_depleted_rotating(codes)
            if depleted_items:
                rejection_reasons.extend([f"depleted:{code}" for code in depleted_items])

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
        Check if candidate contains ALL included items (AND logic).
        
        Args:
            codes: Food codes in candidate
            include_locks: Dict of pattern -> [codes] or code -> []
        
        Returns:
            True if candidate contains ALL locked items (PASS)
            False if candidate missing ANY locked item (REJECT)
        """
        # Must satisfy ALL lock entries
        for lock_key, lock_codes in include_locks.items():
            found = False
            
            if lock_key.endswith(".*"):
                # Pattern lock - check if any code matches pattern
                pattern = lock_key[:-2]
                for code in codes:
                    if code.startswith(pattern):
                        found = True
                        break
                
                # Also check specific codes in the pattern lock
                if not found:
                    for lock_code in lock_codes:
                        if lock_code.upper() in codes:
                            found = True
                            break
            else:
                # Specific code lock
                if lock_key.upper() in codes:
                    found = True
            
            # If this lock entry not satisfied, reject
            if not found:
                return False
        
        # All lock entries satisfied
        return True
    
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
        filtered_count: int,
        rejected_by_type: Optional[Dict[str, int]] = None
    ) -> str:
        """
        Get human-readable filter statistics.
        
        Args:
            original_count: Number of raw candidates
            filtered_count: Number after filtering
            rejected_by_type: Optional breakdown of rejection reasons
        
        Returns:
            Formatted stats string
        """
        rejected = original_count - filtered_count
        
        if rejected == 0:
            return f"All {original_count} candidates passed filters"
        
        percent = (rejected / original_count * 100) if original_count > 0 else 0
        
        base_stats = f"Filtered {rejected}/{original_count} candidates ({percent:.1f}% rejected)"
        
        if rejected_by_type:
            details = []
            for reason, count in rejected_by_type.items():
                details.append(f"{reason}: {count}")
            if details:
                base_stats += " [" + ", ".join(details) + "]"
    
        return base_stats

    def _check_reserved_items(self, codes: Set[str]) -> List[str]:
        '''
        Check if any codes are reserved in inventory.
        
        Args:
            codes: Food codes in candidate
        
        Returns:
            List of reserved codes found
        '''
        reserved_codes = []
        
        # Check leftovers
        for code in codes:
            if code in self.inventory.get("leftovers", {}):
                leftover_item = self.inventory["leftovers"][code]
                if leftover_item.get("reserved", False):
                    reserved_codes.append(code)
            
            # Check batch items
            if code in self.inventory.get("batch", {}):
                batch_item = self.inventory["batch"][code]
                if batch_item.get("reserved", False):
                    reserved_codes.append(code)
            
            # Check rotating items
            if code in self.inventory.get("rotating", {}):
                rotating_item = self.inventory["rotating"][code]
                if rotating_item.get("reserved", False):
                    reserved_codes.append(code)
        
        return reserved_codes
    
    def _check_depleted_rotating(self, codes: Set[str]) -> List[str]:
        '''
        Check if any codes are depleted rotating items.
        
        Args:
            codes: Food codes in candidate
        
        Returns:
            List of depleted rotating codes found
        '''
        depleted_codes = []
        
        rotating_items = self.inventory.get("rotating", {})
        
        for code in codes:
            if code in rotating_items:
                status = rotating_items[code].get("status", "available")
                if status == "depleted":
                    depleted_codes.append(code)
        
        return depleted_codes
    
    