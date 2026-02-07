# meal_planner/filters/nutrient_constraint_filter.py
"""
Nutrient constraint filter for meal candidates.

Enforces hard and soft nutrient limits from meal_generation templates.
"""
from typing import List, Dict, Any, Tuple, Optional
from .base_filter import BaseFilter
from meal_planner.utils.nutrient_mapping import init_totals_dict, get_filter_totals_mapping, get_nutrient_spec



class NutrientConstraintFilter(BaseFilter):
    """
    Filters meal candidates based on nutrient constraints from generation templates.
    
    Enforcement semantics:
    - hard: Reject candidates outside the bound
    - soft: Allow candidates outside but apply scoring penalty within tolerance,
            reject beyond tolerance
    
    Tolerance behavior:
    - For soft max: allows up to (max * tolerance), e.g., 35 * 1.10 = 38.5
    - For soft min: allows down to (min / tolerance), e.g., 10 / 2.0 = 5.0
    """
    
    def __init__(
        self,
        master,
        thresholds_mgr,
        meal_type: str,
        template_name: str
    ):
        """
        Initialize nutrient constraint filter.
        
        Args:
            master: MasterLoader instance
            thresholds_mgr: ThresholdsManager instance
            meal_type: Meal category (breakfast, lunch, dinner, etc.)
            template_name: Generation template name (e.g., "protein_low_carb")
        """
        super().__init__()
        
        self.master = master
        self.thresholds_mgr = thresholds_mgr
        self.meal_type = meal_type
        self.template_name = template_name
        
        # Check collect_all setting from thresholds
        self.collect_all = self.thresholds_mgr.thresholds.get(
            "recommendation", {}
        ).get("collect_all_rejection_reasons", False)
        
        # Resolve actual nutrient limits from template references
        self.nutrient_constraints = self._resolve_constraints()
    
    def _resolve_constraints(self) -> Optional[Dict[str, Any]]:
        """
        Resolve nutrient constraints by combining targets_ref values with enforcement policies.
        
        Returns:
            Dict mapping nutrient -> resolved constraint spec, or None if not available
        """
        # Get enforcement policies from meal_filters (NEW LOCATION)
        meal_filters = self.thresholds_mgr.thresholds.get("meal_filters", {})
        meal_type_filters = meal_filters.get(self.meal_type, {})
        nutrient_constraints_section = meal_type_filters.get("nutrient_constraints", {})
        nutrient_constraints = nutrient_constraints_section.get(self.template_name, {})
        
        if not nutrient_constraints:
            return None  # No constraints to enforce
        
        # Get targets_ref from generation template
        meal_gen = self.thresholds_mgr.get_meal_generation()
        if not meal_gen:
            return None
        
        gen_template = meal_gen.get(self.meal_type, {}).get(self.template_name)
        if not gen_template:
            return None
        
        # Get targets_ref to find the meal_template
        targets_ref = gen_template.get("targets_ref")
        if not targets_ref:
            return None
        
        # Parse targets_ref: "meal_templates.breakfast.protein_low_carb"
        ref_parts = targets_ref.split(".")
        if len(ref_parts) < 3 or ref_parts[0] != "meal_templates":
            return None
        
        target_meal_type = ref_parts[1]
        target_template = ref_parts[2]
        
        # Get actual min/max values from meal_template
        meal_templates = self.thresholds_mgr.thresholds.get("meal_templates", {})
        meal_template = meal_templates.get(target_meal_type, {}).get(target_template)
        if not meal_template:
            return None
        
        template_thresholds = meal_template.get("targets", {})
        
        # Combine enforcement policies with actual values
        resolved = {}
        
        for nutrient, enforcement in nutrient_constraints.items():
            # Get actual min/max from meal_template
            nutrient_threshold = template_thresholds.get(nutrient, {})
            
            if not nutrient_threshold:
                continue  # Skip if no threshold defined
            
            actual_min = nutrient_threshold.get("min")
            actual_max = nutrient_threshold.get("max")
            
            # Build resolved constraint
            constraint = {
                "min_value": actual_min,
                "max_value": actual_max,
                "min_enforcement": enforcement.get("min_enforcement"),
                "max_enforcement": enforcement.get("max_enforcement"),
                "tolerance": enforcement.get("tolerance")
            }
            
            resolved[nutrient] = constraint

        return resolved
    
    def filter_candidates(
        self,
        candidates: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Apply nutrient constraint filtering to candidates.
        
        Args:
            candidates: List of raw generated candidates
        
        Returns:
            Tuple of (passed_candidates, rejected_candidates)
        """
        if not self.nutrient_constraints:
            # No constraints to enforce - all pass
            return candidates, []
        
        passed = []
        rejected = []
        
        for candidate in candidates:
            # Initialize rejection reasons if not present
            if "rejection_reasons" not in candidate:
                candidate["rejection_reasons"] = []
    
            # Calculate nutrient totals for this candidate
            totals = self._calculate_totals(candidate)
            
            # Check against all constraints
            violations = self._check_violations(totals)
            
            if violations:
                # Add rejection reasons
                candidate["rejection_reasons"].extend(
                    [f"nutrient:{v}" for v in violations]
                )
                
                if self.collect_all:
                    # Continue processing - don't reject yet
                    passed.append(candidate)
                else:
                    # Reject immediately (current behavior)
                    rejected.append(candidate)
            else:
                # Check for soft violations (will be penalized by scorer)
                soft_violations = self._check_soft_violations(totals)
                if soft_violations:
                    candidate["soft_nutrient_violations"] = soft_violations
                
                passed.append(candidate)
        
        return passed, rejected    

    def _calculate_totals(self, candidate):
        items = candidate.get("meal", {}).get("items", [])
        if not items:
            return {}
        
        # Initialize with correct keys from utils
        totals_dict = init_totals_dict()  # Returns {"calories": 0, "protein": 0, ...}
        
        # Get mapping from template keys to CSV keys
        csv_mapping = get_filter_totals_mapping()  # {"calories": "cal", "protein": "prot_g", ...}
        
        for item in items:
            code = str(item["code"]).upper()
            mult = float(item.get("mult", 1.0))
            food = self.master.lookup_code(code)
            
            # Use mapping to accumulate - no more hardcoded keys
            for template_key, csv_key in csv_mapping.items():
                totals_dict[template_key] += food.get(csv_key, 0) * mult
        
        return totals_dict
    
    def _check_violations(self, totals: Dict[str, float]) -> List[str]:
        """
        Check for hard constraint violations that should reject the candidate.
        
        Args:
            totals: Nutrient totals dict
        
        Returns:
            List of violation descriptions (empty if all pass)
        """
        violations = []
        
        for nutrient, constraint in self.nutrient_constraints.items():
            value = totals.get(nutrient, 0)
            min_val = constraint.get("min_value")
            max_val = constraint.get("max_value")
            min_enforcement = constraint.get("min_enforcement")
            max_enforcement = constraint.get("max_enforcement")
            tolerance = constraint.get("tolerance", 1.0)
            
            # Check hard minimum
            if min_val is not None and min_enforcement == "hard":
                if value < min_val:
                    violations.append(f"{nutrient}<{min_val:.1f}(hard)")
            
            # Check hard maximum
            if max_val is not None and max_enforcement == "hard":
                if value > max_val:
                    violations.append(f"{nutrient}>{max_val:.1f}(hard)")
            
            # Check soft minimum beyond tolerance
            if min_val is not None and min_enforcement == "soft":
                tolerable_min = min_val / tolerance
                if value < tolerable_min:
                    violations.append(f"{nutrient}<{tolerable_min:.1f}(soft_limit)")
            
            # Check soft maximum beyond tolerance
            if max_val is not None and max_enforcement == "soft":
                tolerable_max = max_val * tolerance
                if value > tolerable_max:
                    violations.append(f"{nutrient}>{tolerable_max:.1f}(soft_limit)")
        
        return violations
    
    def _check_soft_violations(self, totals: Dict[str, float]) -> List[Dict[str, Any]]:
        """
        Check for soft violations within tolerance (will be penalized, not rejected).
        
        Args:
            totals: Nutrient totals dict
        
        Returns:
            List of soft violation details for scoring
        """
        soft_violations = []
        
        for nutrient, constraint in self.nutrient_constraints.items():
            value = totals.get(nutrient, 0)
            min_val = constraint.get("min_value")
            max_val = constraint.get("max_value")
            min_enforcement = constraint.get("min_enforcement")
            max_enforcement = constraint.get("max_enforcement")
            tolerance = constraint.get("tolerance", 1.0)
            
            # Check soft minimum (below target but within tolerance)
            if min_val is not None and min_enforcement == "soft":
                if value < min_val:
                    tolerable_min = min_val / tolerance
                    if value >= tolerable_min:  # Within tolerance
                        soft_violations.append({
                            "nutrient": nutrient,
                            "target": min_val,
                            "value": value,
                            "type": "below_min",
                            "deficit": min_val - value
                        })
            
            # Check soft maximum (above target but within tolerance)
            if max_val is not None and max_enforcement == "soft":
                if value > max_val:
                    tolerable_max = max_val * tolerance
                    if value <= tolerable_max:  # Within tolerance
                        soft_violations.append({
                            "nutrient": nutrient,
                            "target": max_val,
                            "value": value,
                            "type": "above_max",
                            "excess": value - max_val
                        })
        
        return soft_violations
    
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
            return f"All {original_count} candidates met nutrient constraints"
        
        percent = (rejected / original_count * 100) if original_count > 0 else 0
        
        return f"Rejected {rejected}/{original_count} for nutrient violations ({percent:.1f}%)"