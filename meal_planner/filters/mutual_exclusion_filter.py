# meal_planner/filters/mutual_exclusion_filter.py
"""
Mutual exclusion filter for meal candidates.

Enforces mutual exclusion rules where only items from one group
can be present in a meal.
"""
from typing import List, Dict, Any, Set, Tuple, Optional
from .base_filter import BaseFilter


class MutualExclusionFilter(BaseFilter):
    """
    Filters meal candidates based on mutual exclusion rules.
    
    Rules enforce that only items from ONE group (out of 2+ defined groups)
    can be present in a meal. For example:
    - Group 1: [yogurt]
    - Group 2: [breakfast meats]
    - Policy: max_one_group
    
    A meal can have yogurt OR meat, but not both.
    """
    
    def __init__(
        self,
        meal_type: str,
        thresholds_mgr,
        exclusion_rules: List[Dict[str, Any]]
    ):
        """
        Initialize mutual exclusion filter.
        
        Args:
            meal_type: Meal category (breakfast, lunch, dinner, etc.)
            thresholds_mgr: ThresholdsManager instance for pool resolution
            exclusion_rules: List of exclusion rule dicts from config
                Each rule has:
                - name: Rule identifier
                - groups: List of groups (each can be code, list, or pool ref)
                - policy: "max_one_group" (only this policy for now)
        """
        super().__init__()
        
        self.meal_type = meal_type
        self.thresholds_mgr = thresholds_mgr
        self.exclusion_rules = exclusion_rules
        
        # Resolve all pool references to actual food codes
        self._resolve_groups()
    
    def set_collect_all(self, collect_all: bool) -> None:
        """Set whether to collect all rejection reasons."""
        self.collect_all = collect_all
    
    def _resolve_groups(self) -> None:
        """
        Resolve all group definitions to sets of food codes.
        
        Handles:
        - Single codes: "ot.1a" -> {"ot.1a"}
        - Lists: ["ot.1a", "ot.1b"] -> {"ot.1a", "ot.1b"}
        - Pool refs: "pool:breakfast_meats" -> {all codes in pool}
        """
        for rule in self.exclusion_rules:
            if not rule.get("enabled", True):
                continue
            resolved_groups = []
            
            for group in rule.get("groups", []):
                resolved_codes = self._resolve_group_to_codes(group)
                resolved_groups.append(resolved_codes)
            
            # Store resolved groups back in rule
            rule["_resolved_groups"] = resolved_groups
    
    def _resolve_group_to_codes(self, group: Any) -> Set[str]:
        """
        Resolve a single group definition to a set of food codes.
        
        Args:
            group: Can be:
                - String (single code): "ot.1a"
                - String (pool ref): "pool:breakfast_meats"
                - List of strings: ["ot.1a", "ot.1b"]
        
        Returns:
            Set of food codes
        """
        codes = set()
        
        if isinstance(group, str):
            if group.startswith("pool:"):
                # Pool reference - expand it
                pool_name = group[5:]  # Remove "pool:" prefix
                pool_codes = self.thresholds_mgr.expand_pool(pool_name)
                codes.update(pool_codes)
            else:
                # Single food code
                codes.add(group)
        
        elif isinstance(group, list):
            # List of codes or pool refs
            for item in group:
                if isinstance(item, str):
                    if item.startswith("pool:"):
                        pool_name = item[5:]
                        pool_codes = self.thresholds_mgr.expand_pool(pool_name)
                        codes.update(pool_codes)
                    else:
                        codes.add(item)
        
        return codes
    
    def filter_candidates(
        self,
        candidates: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Apply mutual exclusion filters to candidates.
        
        Args:
            candidates: List of candidate dicts with 'rejection_reasons' field
        
        Returns:
            Tuple of (passed_candidates, rejected_candidates)
        """
        passed = []
        rejected = []
        
        for candidate in candidates:
            # Get food codes in this candidate
            candidate_codes = self._extract_candidate_codes(candidate)
            
            # Check each exclusion rule
            violations = []
            for rule in self.exclusion_rules:
                if not rule.get("enabled", True):
                    continue
                violation = self._check_rule(candidate_codes, rule)
                if violation:
                    violations.append(violation)
            
            # Handle violations
            if violations:
                # Add rejection reasons
                for violation in violations:
                    candidate["rejection_reasons"].append(violation)
                
                if self.collect_all:
                    passed.append(candidate)
                else:
                    rejected.append(candidate)
            else:
                passed.append(candidate)
        
        return passed, rejected
    
    def _extract_candidate_codes(self, candidate: Dict[str, Any]) -> Set[str]:
        """
        Extract all food codes from candidate items.
        
        Args:
            candidate: Candidate dict with 'items' field
        
        Returns:
            Set of food codes (lowercase for matching)
        """
        codes = set()
        items = candidate.get("meal", {}).get("items", [])
        
        for item in items:
            code = item.get("code", "")
            if code:
                codes.add(code.lower())
        
        return codes
    
    def _check_rule(
        self,
        candidate_codes: Set[str],
        rule: Dict[str, Any]
    ) -> Optional[str]:
        """
        Check if candidate violates a mutual exclusion rule.
        
        Args:
            candidate_codes: Set of food codes in candidate
            rule: Exclusion rule with _resolved_groups
        
        Returns:
            Violation message if rule violated, None otherwise
        """
        policy = rule.get("policy", "max_one_group")
        resolved_groups = rule.get("_resolved_groups", [])
        rule_name = rule.get("name", "unnamed_rule")
        
        if policy != "max_one_group":
            # Future: support other policies like "max_two_groups"
            return None
        
        # Count how many groups have at least one item present
        groups_with_items = 0
        present_groups = []
        
        for idx, group_codes in enumerate(resolved_groups):
            # Check if any code from this group is in the candidate
            group_codes_lower = {c.lower() for c in group_codes}
            if candidate_codes & group_codes_lower:
                groups_with_items += 1
                present_groups.append(idx + 1)  # 1-indexed for user readability
        
        # Violation if more than one group is present
        if groups_with_items > 1:
            return (
                f"mutual_exclusion({rule_name}): "
                f"items from {groups_with_items} groups present "
                f"(groups {present_groups}), max allowed is 1"
            )
        
        return None