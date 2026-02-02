# meal_planner/filters/leftover_match_filter.py
"""
Leftover match filter for meal candidates.

Validates that candidates using leftover items match the exact multipliers
available in inventory.
"""
from typing import List, Dict, Any, Set, Tuple


class LeftoverMatchFilter:
    """
    Filters meal candidates based on leftover availability and portion matching.
    
    Rules:
    - Leftovers must match exact multiplier (within 0.1% tolerance)
    - Candidates under-using leftovers can optionally pass with penalty score
    - Candidates over-using leftovers are rejected
    """
    
    def __init__(self, inventory: Dict[str, Any], allow_under_use: bool = False):
        """
        Initialize leftover match filter.
        
        Args:
            inventory: Inventory section from workspace
                      {"leftovers": {code: {multiplier, ...}}, ...}
            allow_under_use: If True, allow under-use with penalty (future scorer)
        """
        self.inventory = inventory
        self.allow_under_use = allow_under_use
        
        # Tolerance for multiplier matching (0.1%)
        self.MATCH_TOLERANCE = 0.001

        self.collect_all = False  # Set by caller for accumulation mode

    def set_collect_all(self, collect_all: bool) -> None:
        """Set whether to collect all rejection reasons."""
        self.collect_all = collect_all
    
    def filter_candidates(
        self,
        candidates: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Apply leftover matching filter to candidates.
        
        Args:
            candidates: List of candidates to filter
        
        Returns:
            Tuple of (passed_candidates, rejected_candidates)
        """
        passed = []
        rejected = []
        
        for candidate in candidates:
            # Initialize rejection reasons if not present
            if "rejection_reasons" not in candidate:
                candidate["rejection_reasons"] = []
            
            # Check leftover usage
            leftover_items = self._extract_leftover_items(candidate)
            
            if not leftover_items:
                # No leftovers used - pass through
                passed.append(candidate)
                continue
            
            # Validate each leftover
            new_rejection_reasons = []
            under_use_warnings = []
            
            for code, candidate_mult in leftover_items.items():
                result = self._validate_leftover_usage(code, candidate_mult)
                
                if result["status"] == "reject":
                    new_rejection_reasons.append(result["reason"])
                elif result["status"] == "under_use":
                    under_use_warnings.append(result["reason"])
            
            if new_rejection_reasons:
                # Add new reasons to candidate
                candidate["rejection_reasons"].extend(new_rejection_reasons)
                
                if self.collect_all:
                    # Continue processing - don't reject yet
                    # Still record warnings
                    if under_use_warnings:
                        candidate["leftover_under_use"] = under_use_warnings
                    passed.append(candidate)
                else:
                    # Reject immediately (current behavior)
                    rejected.append(candidate)
            else:
                # Passed (possibly with warnings)
                if under_use_warnings:
                    candidate["leftover_under_use"] = under_use_warnings
                passed.append(candidate)
        
        return passed, rejected
    
    def _extract_leftover_items(self, candidate: Dict[str, Any]) -> Dict[str, float]:
        """
        Extract leftover food codes and their multipliers from candidate.
        
        Args:
            candidate: Candidate dict with items list
        
        Returns:
            Dict of {code: multiplier} for leftovers only
        """
        leftover_items = {}
        leftovers = self.inventory.get("leftovers", {})
        
        for item in candidate.get("items", []):
            code = item.get("code", "").upper()
            mult = item.get("mult", 1.0)
            
            # Check if this code is in leftover inventory
            if code in leftovers:
                leftover_items[code] = mult
        
        return leftover_items
    
    def _validate_leftover_usage(
        self,
        code: str,
        candidate_mult: float
    ) -> Dict[str, str]:
        """
        Validate that candidate's use of leftover matches inventory.
        
        Args:
            code: Food code
            candidate_mult: Multiplier in candidate
        
        Returns:
            Dict with status and reason
            status: "pass", "reject", or "under_use"
        """
        leftovers = self.inventory.get("leftovers", {})
        
        if code not in leftovers:
            # Not in inventory - this shouldn't happen if filtering is correct
            return {
                "status": "reject",
                "reason": f"leftover_not_found: {code}"
            }
        
        inventory_mult = leftovers[code].get("multiplier", 1.0)
        
        # Check for exact match (within tolerance)
        if abs(candidate_mult - inventory_mult) <= self.MATCH_TOLERANCE:
            return {"status": "pass", "reason": ""}
        
        # Check for over-use (always reject)
        if candidate_mult > inventory_mult:
            return {
                "status": "reject",
                "reason": f"leftover_overuse: {code} needs {candidate_mult:g}x but only {inventory_mult:g}x available"
            }
        
        # Under-use
        if self.allow_under_use:
            waste_pct = ((inventory_mult - candidate_mult) / inventory_mult) * 100
            return {
                "status": "under_use",
                "reason": f"{code}: uses {candidate_mult:g}x of {inventory_mult:g}x ({waste_pct:.1f}% waste)"
            }
        else:
            # Reject under-use if not allowed
            return {
                "status": "reject",
                "reason": f"leftover_mismatch: {code} uses {candidate_mult:g}x but inventory has {inventory_mult:g}x"
            }
    
    def get_filter_stats(
        self,
        original_count: int,
        filtered_count: int
    ) -> str:
        """
        Get human-readable filter statistics.
        
        Args:
            original_count: Number of candidates before filtering
            filtered_count: Number after filtering
        
        Returns:
            Formatted stats string
        """
        rejected = original_count - filtered_count
        
        if rejected == 0:
            return f"All {original_count} candidates match leftover portions"
        
        percent = (rejected / original_count * 100) if original_count > 0 else 0
        
        return f"Rejected {rejected}/{original_count} for leftover mismatch ({percent:.1f}%)"