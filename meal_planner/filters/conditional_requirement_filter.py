# meal_planner/filters/conditional_requirement_filter.py
"""
Conditional requirement filter for meal candidates.

Enforces conditional rules where presence of certain items requires
other items to be present with min/max constraints.
"""
from typing import List, Dict, Any, Set, Tuple, Optional
from .base_filter import BaseFilter


class ConditionalRequirementFilter(BaseFilter):
    """
    Filters meal candidates based on conditional requirement rules.
    
    Rules enforce "if X present, then Y required" logic with min/max.
    For example:
    - If yogurt present, must have 1-2 fruits
    - If soup present, must have 1+ vegetable
    
    Rules can specify:
    - if_present: Trigger items (codes, lists, or pool refs)
    - then_require.from: Required items (codes, lists, or pool refs)
    - then_require.min: Minimum count required
    - then_require.max: Maximum count allowed
    """
    
    def __init__(
        self,
        meal_type: str,
        thresholds_mgr,
        requirement_rules: List[Dict[str, Any]]
    ):
        """
        Initialize conditional requirement filter.
        
        Args:
            meal_type: Meal category (breakfast, lunch, dinner, etc.)
            thresholds_mgr: ThresholdsManager instance for pool resolution
            requirement_rules: List of requirement rule dicts from config
                Each rule has:
                - name: Rule identifier
                - if_present: Trigger codes/list/pool
                - then_require: Dict with 'from', 'min', 'max'
        """
        super().__init__()
        
        self.meal_type = meal_type
        self.thresholds_mgr = thresholds_mgr
        self.requirement_rules = requirement_rules
        
        # Resolve all pool references to actual food codes
        self._resolve_rules()
    
    def set_collect_all(self, collect_all: bool) -> None:
        """Set whether to collect all rejection reasons."""
        self.collect_all = collect_all
    
    def _resolve_rules(self) -> None:
        """
        Resolve all rule definitions to sets of food codes.
        
        Resolves both if_present and then_require.from fields.
        """
        for rule in self.requirement_rules:
            if not rule.get("enabled", True):
                continue

            # Resolve if_present trigger codes
            if_present = rule.get("if_present", [])
            rule["_resolved_triggers"] = self._resolve_to_codes(if_present)
            
            # Resolve then_require.from required codes
            then_require = rule.get("then_require", {})
            required_from = then_require.get("from", [])
            rule["_resolved_required"] = self._resolve_to_codes(required_from)
    
    def _resolve_to_codes(self, spec: Any) -> Set[str]:
        """
        Resolve a code specification to a set of food codes.
        
        Args:
            spec: Can be:
                - String (single code): "ot.1a"
                - String (pool ref): "pool:breakfast_meats"
                - List of strings: ["ot.1a", "ot.1b"]
        
        Returns:
            Set of food codes
        """
        codes = set()
        
        if isinstance(spec, str):
            if spec.startswith("pool:"):
                # Pool reference - expand it
                pool_name = spec[5:]  # Remove "pool:" prefix
                pool_codes = self.thresholds_mgr.expand_pool(pool_name)
                codes.update(pool_codes)
            else:
                # Single food code
                codes.add(spec)
        
        elif isinstance(spec, list):
            # List of codes or pool refs
            for item in spec:
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
        Apply conditional requirement filters to candidates.
        
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
            # Check each conditional rule
            violations = []
            for rule in self.requirement_rules:
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
        Check if candidate violates a conditional requirement rule.
        
        Args:
            candidate_codes: Set of food codes in candidate
            rule: Requirement rule with _resolved_triggers and _resolved_required
        
        Returns:
            Violation message if rule violated, None otherwise
        """
        triggers = rule.get("_resolved_triggers", set())
        required = rule.get("_resolved_required", set())
        then_require = rule.get("then_require", {})
        min_count = then_require.get("min", 1)
        max_count = then_require.get("max", None)
        rule_name = rule.get("name", "unnamed_rule")
        
        # Check if any trigger is present
        triggers_lower = {c.lower() for c in triggers}
        trigger_present = bool(candidate_codes & triggers_lower)
        
        if not trigger_present:
            # Rule doesn't apply to this candidate
            return None
        
        # Trigger is present, check if required items meet min/max
        required_lower = {c.lower() for c in required}
        present_required = candidate_codes & required_lower
        required_count = len(present_required)
        
        # Check minimum requirement
        if required_count < min_count:
            return (
                f"conditional_requirement({rule_name}): "
                f"trigger present but only {required_count} required items found, "
                f"need at least {min_count}"
            )
        
        # Check maximum requirement (if specified)
        if max_count is not None and required_count > max_count:
            return (
                f"conditional_requirement({rule_name}): "
                f"trigger present and {required_count} required items found, "
                f"max allowed is {max_count}"
            )
        
        return None