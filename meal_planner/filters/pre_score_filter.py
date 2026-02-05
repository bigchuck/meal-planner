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
    def __init__(self, locks: Dict[str, Any], meal_type: str, user_prefs=None, inventory: Optional[Dict[str, Any]] = None):
        """
        Initialize pre-score filter.
        
        Args:
            locks: Full lock configuration from workspace
                {"breakfast": {"include": {...}, "exclude": [...]}, "lunch": {...}, ...}
            meal_type: Meal type to filter for (e.g., "breakfast", "lunch")
            user_prefs: Optional UserPreferencesManager for exclude patterns
            inventory: Inventory data for reservation/depletion checks
        """
        # Extract meal-specific locks
        meal_locks = locks.get(meal_type, {"include": {}, "exclude": []})
        self.locks = meal_locks
        self.user_prefs = user_prefs
        self.collect_all = False  # Set by caller for accumulation mode
        self.inventory = inventory or {"leftovers": {}, "batch": {}, "rotating": {}}
    
    def set_collect_all(self, collect_all: bool) -> None:
        """Set whether to collect all rejection reasons."""
        self.collect_all = collect_all

    def filter_candidates(
        self,
        candidates: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Apply pre-score filters to candidates.
        
        Args:
            candidates: List of raw generated candidates
        
        Returns:
            Tuple of (passed_candidates, rejected_candidates)
        """
        filtered = []
        rejected = []
        
        for candidate in candidates:
            # Initialize rejection reasons if not present
            if "rejection_reasons" not in candidate:
                candidate["rejection_reasons"] = []
            
            # Extract food codes from candidate
            codes = self._extract_codes(candidate)
            
            # Track new rejection reasons from this filter
            new_reasons = []
            
            # Check lock filters (returns detailed reasons if failed)
            lock_violations = self._check_lock_filters(codes)
            if lock_violations:
                new_reasons.extend(lock_violations)
            
            # Check availability filter
            if not self._passes_availability_filter(codes):
                new_reasons.append("availability")

            # Check for reserved items
            reserved_items = self._check_reserved_items(codes)
            if reserved_items:
                new_reasons.extend([f"reserved:{code}" for code in reserved_items])
            
            # Check for depleted rotating items
            depleted_items = self._check_depleted_rotating(codes)
            if depleted_items:
                new_reasons.extend([f"depleted:{code}" for code in depleted_items])

            if new_reasons:
                # Add new reasons to candidate
                candidate["rejection_reasons"].extend(new_reasons)
                
                if self.collect_all:
                    # Continue processing - don't reject yet
                    filtered.append(candidate)
                else:
                    # Reject immediately (current behavior)
                    rejected.append(candidate)
            else:
                candidate["filter_passed"] = True
                filtered.append(candidate)

        return filtered, rejected    

    def _extract_codes(self, candidate: Dict[str, Any]) -> Set[str]:
        """
        Extract food codes from candidate items.
        
        Args:
            candidate: Candidate dict with items list
        
        Returns:
            Set of uppercase food codes
        """
        codes = set()
        items = candidate.get("meal", {}).get("items", [])
        
        for item in items:
            if "code" in item:
                codes.add(item["code"].upper())
        
        return codes
    
    def _check_lock_filters(self, codes: Set[str]) -> List[str]:
        """
        Check lock constraints and return detailed violation reasons.
        
        Args:
            codes: Set of food codes in candidate
        
        Returns:
            List of violation reasons (empty if all locks satisfied)
        """
        violations = []
        
        include_locks = self.locks.get("include", {})
        exclude_locks = self.locks.get("exclude", [])
        
        # Check exclude locks (hard reject with specific code/pattern)
        if exclude_locks:
            exclude_violations = self._find_exclude_violations(codes, exclude_locks)
            violations.extend(exclude_violations)
        
        # Check include locks (must have ALL required items)
        if include_locks:
            include_violations = self._find_include_violations(codes, include_locks)
            violations.extend(include_violations)
        
        return violations


    def _find_exclude_violations(
        self,
        codes: Set[str],
        exclude_locks: List[str]
    ) -> List[str]:
        """
        Find which exclude locks are violated.
        
        Args:
            codes: Food codes in candidate
            exclude_locks: List of patterns/codes to exclude
        
        Returns:
            List of violation reasons (e.g., "lock_exclude:DN.*", "lock_exclude:FI.8")
        """
        violations = []
        
        for lock in exclude_locks:
            if lock.endswith(".*"):
                # Pattern lock (e.g., "DN.*")
                pattern = lock[:-2]
                matching_codes = [code for code in codes if code.startswith(pattern)]
                if matching_codes:
                    # Show pattern and first matching code
                    violations.append(f"lock_exclude:{lock}({matching_codes[0]})")
            else:
                # Specific code lock
                if lock.upper() in codes:
                    violations.append(f"lock_exclude:{lock}")
        
        return violations


    def _find_include_violations(
        self,
        codes: Set[str],
        include_locks: Dict[str, float]
    ) -> List[str]:
        """
        Find which include locks are not satisfied.
        
        Args:
            codes: Food codes in candidate
            include_locks: Dict of {code: multiplier} that MUST be included
        
        Returns:
            List of violation reasons (e.g., "lock_missing:FI.8")
        """
        violations = []
        
        # Must satisfy ALL include lock entries
        for lock_code, lock_mult in include_locks.items():
            found = False
            
            if lock_code.endswith(".*"):
                # Pattern lock - check if any code matches pattern
                pattern = lock_code[:-2]
                for code in codes:
                    if code.startswith(pattern):
                        found = True
                        break
            else:
                # Specific code lock
                if lock_code.upper() in codes:
                    found = True
            
            # If this required item not found, add violation
            if not found:
                if lock_code.endswith(".*"):
                    violations.append(f"lock_missing:{lock_code}")
                else:
                    violations.append(f"lock_missing:{lock_code}({lock_mult:g}x)")
        
        return violations
    
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
    
    