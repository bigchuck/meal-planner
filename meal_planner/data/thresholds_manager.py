# meal_planner/data/thresholds_manager.py
"""
Thresholds manager for nutritional risk scoring parameters.

Manages meal_plan_thresholds.json with all hardcoded thresholds
externalized for user configuration.
"""
import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple


class ThresholdsManager:
    """
    Manages nutritional thresholds configuration.
    
    If file doesn't exist or is invalid, thresholds-dependent features
    are disabled with clear error messages.
    """
    
    def __init__(self, filepath: Path):
        """
        Initialize thresholds manager.
        
        Args:
            filepath: Path to thresholds JSON file
        """
        self.filepath = filepath
        self._thresholds: Optional[Dict[str, Any]] = None
        self._validation_errors: List[str] = []
        self._is_valid = False
    
    def load(self) -> bool:
        """
        Load and validate thresholds from disk.
        
        Returns:
            True if loaded and valid, False otherwise
        """
        self._validation_errors.clear()
        self._is_valid = False
        self._thresholds = None
        
        # Check file exists
        if not self.filepath.exists():
            self._validation_errors.append(
                f"Thresholds file not found: {self.filepath}"
            )
            return False
        
        # Load JSON
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                self._thresholds = json.load(f)
        except json.JSONDecodeError as e:
            self._validation_errors.append(
                f"Invalid JSON in thresholds file: {e}"
            )
            return False
        except Exception as e:
            self._validation_errors.append(
                f"Error reading thresholds file: {e}"
            )
            return False
        
        # Validate structure
        self._validate_structure()

        if self._validation_errors:
            self._is_valid = False
            self._thresholds = None
            return False
        
        self._is_valid = True
        return True
    
    @property
    def is_valid(self) -> bool:
        """Check if thresholds are loaded and valid."""
        return self._is_valid
    
    @property
    def validation_errors(self) -> List[str]:
        """Get list of validation error messages."""
        return self._validation_errors.copy()
    
    @property
    def thresholds(self) -> Optional[Dict[str, Any]]:
        """Get thresholds dict (None if invalid)."""
        return self._thresholds if self._is_valid else None
    
    def get_daily_targets(self) -> Optional[Dict[str, Any]]:
        """Get daily targets section."""
        if not self.is_valid:
            return None
        return self._thresholds.get('daily_targets')
    
    def get_glucose_scoring(self) -> Optional[Dict[str, Any]]:
        """Get glucose scoring section."""
        if not self.is_valid:
            return None
        return self._thresholds.get('glucose_scoring')
    
    def get_curve_classification(self) -> Optional[Dict[str, Any]]:
        """Get curve classification section."""
        if not self.is_valid:
            return None
        return self._thresholds.get('curve_classification')
    
    def get_explain_messages(self) -> Optional[Dict[str, Any]]:
        """Get explain messages section."""
        if not self.is_valid:
            return None
        return self._thresholds.get('explain_messages')
    
    def get_daily_planning(self) -> Optional[Dict[str, Any]]:
        """Get daily planning section."""
        if not self.is_valid:
            return None
        return self._thresholds.get('daily_planning')

    def get_default_meal_sequence(self) -> List[str]:
        """
        Get default meal sequence for daily planning.
        
        Returns:
            List of meal names in sequence order, or empty list if not available
        """
        if not self.is_valid:
            return []
        
        planning = self._thresholds.get('daily_planning', {})
        return planning.get('default_meal_sequence', [])

    def get_snack_bridge_rules(self) -> Optional[Dict[str, Any]]:
        """
        Get snack bridge rules configuration.
        
        Returns:
            Dict with enable_auto_snack_suggestions, min_gap_to_trigger, snack_categories
        """
        if not self.is_valid:
            return None
        
        planning = self._thresholds.get('daily_planning', {})
        return planning.get('snack_bridge_rules')

    def get_context_propagation(self) -> Optional[Dict[str, Any]]:
        """
        Get context propagation configuration.
        
        Returns:
            Dict with track_cumulative_totals, propagate_deficits, propagate_excesses, reset_on_new_day
        """
        if not self.is_valid:
            return None
        
        planning = self._thresholds.get('daily_planning', {})
        return planning.get('context_propagation')

    def should_propagate_deficit(self, nutrient: str) -> bool:
        """
        Check if a nutrient deficit should propagate across meals.
        
        Args:
            nutrient: Nutrient name (e.g., 'protein', 'fiber')
        
        Returns:
            True if deficit should carry forward between meals
        """
        context_config = self.get_context_propagation()
        if not context_config:
            return False
        
        propagate_list = context_config.get('propagate_deficits', [])
        return nutrient in propagate_list

    def should_propagate_excess(self, nutrient: str) -> bool:
        """
        Check if a nutrient excess should propagate across meals.
        
        Args:
            nutrient: Nutrient name (e.g., 'sugar', 'gl')
        
        Returns:
            True if excess should carry forward between meals
        """
        context_config = self.get_context_propagation()
        if not context_config:
            return False
        
        propagate_list = context_config.get('propagate_excesses', [])
        return nutrient in propagate_list
        
    def get_value_for_range(self, value: float, ranges: List[Dict]) -> Optional[Dict]:
        """
        Find the appropriate range entry for a value.
        
        Args:
            value: Numeric value to classify
            ranges: List of range dicts with 'max' keys
        
        Returns:
            The matching range dict, or None if ranges invalid
        """
        if not ranges:
            return None
        
        for range_def in ranges:
            max_val = range_def.get('max')
            if max_val is None or value <= max_val:
                return range_def
        
        # Fallback to last range
        return ranges[-1]
    
    def _validate_structure(self) -> None:
        """Validate thresholds structure and content."""
        if not isinstance(self._thresholds, dict):
            self._validation_errors.append("Root must be a JSON object")
            return
        
        # Check required top-level sections
        required_sections = [
            'daily_targets',
            'glucose_scoring',
            'curve_classification',
            'explain_messages',
            'meal_templates',
            'daily_planning'
        ]
        missing = [k for k in required_sections if k not in self._thresholds]
        if missing:
            self._validation_errors.append(
                f"Missing required sections: {', '.join(missing)}"
            )
       
        # Validate daily_targets
        if 'daily_targets' in self._thresholds:
            self._validate_daily_targets()
        
        # Validate glucose_scoring
        if 'glucose_scoring' in self._thresholds:
            self._validate_glucose_scoring()
        
        # Validate curve_classification
        if 'curve_classification' in self._thresholds:
            self._validate_curve_classification()
        
        # Validate explain_messages
        if 'explain_messages' in self._thresholds:
            self._validate_explain_messages()

        # Validate meal categories exist
        if 'meal_templates' in self._thresholds:
            meal_templates = self._thresholds['meal_templates']
            if not isinstance(meal_templates, dict):
                self._validation_errors.append("meal_templates must be a dictionary")
            else:
                required_meals = ['breakfast', 'lunch', 'dinner', 
                                'morning snack', 'afternoon snack', 'evening snack']
                missing_meals = [m for m in required_meals if m not in meal_templates]
                if missing_meals:
                    # Warning only - don't fail validation
                    print(f"Warning: Missing meal template categories: {', '.join(missing_meals)}")
    
        # Validate daily_planning for multi-meal 
        if 'daily_planning' in self._thresholds:
            self._validate_daily_planning()

        # Validate component_pools (optional but if present must be valid)
        if 'component_pools' in self._thresholds:
            self._validate_component_pools()
     
        # Validate meal_generation (optional but if present must be valid)
        if 'meal_generation' in self._thresholds:
            self._validate_meal_generation()

    
    def _validate_daily_targets(self) -> None:
        """Validate daily_targets section."""
        targets = self._thresholds['daily_targets']
        
        if not isinstance(targets, dict):
            self._validation_errors.append("daily_targets must be an object")
            return
        
        required_fields = [
            'sugar_g', 'glycemic_load', 'protein_g',
            'fat_pct', 'carbs_pct', 'calories_min', 'calories_max'
        ]
        
        for field in required_fields:
            if field not in targets:
                self._validation_errors.append(
                    f"daily_targets missing field: '{field}'"
                )
            elif not isinstance(targets[field], (int, float)):
                self._validation_errors.append(
                    f"daily_targets.{field} must be a number"
                )
    
    def _validate_glucose_scoring(self) -> None:
        """Validate glucose_scoring section."""
        scoring = self._thresholds['glucose_scoring']
        
        if not isinstance(scoring, dict):
            self._validation_errors.append("glucose_scoring must be an object")
            return
        
        # Validate range arrays
        range_fields = [
            'carb_risk_ranges',
            'gi_speed_factors',
            'fat_delay_ranges',
            'protein_tail_ranges',
            'fiber_buffer_ranges',
            'risk_rating_thresholds'
        ]
        
        for field in range_fields:
            if field not in scoring:
                self._validation_errors.append(
                    f"glucose_scoring missing: '{field}'"
                )
            else:
                self._validate_range_array(scoring[field], f"glucose_scoring.{field}")
        
        # Validate weights
        if 'risk_score_weights' in scoring:
            weights = scoring['risk_score_weights']
            if not isinstance(weights, dict):
                self._validation_errors.append(
                    "glucose_scoring.risk_score_weights must be an object"
                )
            else:
                for key in ['fat_delay', 'protein_tail', 'fiber_buffer']:
                    if key not in weights:
                        self._validation_errors.append(
                            f"risk_score_weights missing: '{key}'"
                        )
                    elif not isinstance(weights[key], (int, float)):
                        self._validation_errors.append(
                            f"risk_score_weights.{key} must be a number"
                        )
    
    def _validate_curve_classification(self) -> None:
        """Validate curve_classification section."""
        curves = self._thresholds['curve_classification']
        
        if not isinstance(curves, dict):
            self._validation_errors.append("curve_classification must be an object")
            return
        
        # Check for required rule sets
        required_rules = [
            'very_low_carb_max',
            'delayed_spike',
            'double_hump',
            'blunted_spike',
            'spike_then_dip'
        ]
        
        for rule in required_rules:
            if rule not in curves:
                self._validation_errors.append(
                    f"curve_classification missing: '{rule}'"
                )
    
    def _validate_explain_messages(self) -> None:
        """Validate explain_messages section."""
        messages = self._thresholds['explain_messages']
        
        if not isinstance(messages, dict):
            self._validation_errors.append("explain_messages must be an object")
            return
        
        # Validate message range arrays
        range_fields = [
            'carb_risk_messages',
            'gi_factor_messages',
            'fat_delay_messages',
            'protein_tail_messages',
            'fiber_buffer_messages',
            'risk_score_interpretation'
        ]
        
        for field in range_fields:
            if field not in messages:
                self._validation_errors.append(
                    f"explain_messages missing: '{field}'"
                )
            else:
                ranges = messages[field]
                if not isinstance(ranges, list):
                    self._validation_errors.append(
                        f"explain_messages.{field} must be an array"
                    )
                else:
                    for i, entry in enumerate(ranges):
                        if not isinstance(entry, dict):
                            self._validation_errors.append(
                                f"explain_messages.{field}[{i}] must be an object"
                            )
                        elif 'message' not in entry:
                            self._validation_errors.append(
                                f"explain_messages.{field}[{i}] missing 'message'"
                            )

    def _validate_daily_planning(self) -> None:
        """Validate daily_planning section."""
        planning = self._thresholds['daily_planning']
        
        if not isinstance(planning, dict):
            self._validation_errors.append("daily_planning must be an object")
            return
        
        # Validate default_meal_sequence
        if 'default_meal_sequence' not in planning:
            self._validation_errors.append("daily_planning missing: 'default_meal_sequence'")
        else:
            sequence = planning['default_meal_sequence']
            if not isinstance(sequence, list):
                self._validation_errors.append("default_meal_sequence must be an array")
            elif len(sequence) == 0:
                self._validation_errors.append("default_meal_sequence cannot be empty")
        
        # Validate snack_bridge_rules
        if 'snack_bridge_rules' not in planning:
            self._validation_errors.append("daily_planning missing: 'snack_bridge_rules'")
        else:
            rules = planning['snack_bridge_rules']
            if not isinstance(rules, dict):
                self._validation_errors.append("snack_bridge_rules must be an object")
            else:
                # Check enable_auto_snack_suggestions
                if 'enable_auto_snack_suggestions' not in rules:
                    self._validation_errors.append("snack_bridge_rules missing: 'enable_auto_snack_suggestions'")
                elif not isinstance(rules['enable_auto_snack_suggestions'], bool):
                    self._validation_errors.append("enable_auto_snack_suggestions must be boolean")
                
                # Check min_gap_to_trigger
                if 'min_gap_to_trigger' not in rules:
                    self._validation_errors.append("snack_bridge_rules missing: 'min_gap_to_trigger'")
                elif not isinstance(rules['min_gap_to_trigger'], dict):
                    self._validation_errors.append("min_gap_to_trigger must be an object")
                
                # Check snack_categories
                if 'snack_categories' not in rules:
                    self._validation_errors.append("snack_bridge_rules missing: 'snack_categories'")
                elif not isinstance(rules['snack_categories'], list):
                    self._validation_errors.append("snack_categories must be an array")
        
        # Validate context_propagation
        if 'context_propagation' not in planning:
            self._validation_errors.append("daily_planning missing: 'context_propagation'")
        else:
            context = planning['context_propagation']
            if not isinstance(context, dict):
                self._validation_errors.append("context_propagation must be an object")
            else:
                # Check track_cumulative_totals
                if 'track_cumulative_totals' not in context:
                    self._validation_errors.append("context_propagation missing: 'track_cumulative_totals'")
                elif not isinstance(context['track_cumulative_totals'], bool):
                    self._validation_errors.append("track_cumulative_totals must be boolean")
                
                # Check propagate_deficits
                if 'propagate_deficits' not in context:
                    self._validation_errors.append("context_propagation missing: 'propagate_deficits'")
                elif not isinstance(context['propagate_deficits'], list):
                    self._validation_errors.append("propagate_deficits must be an array")
                
                # Check propagate_excesses
                if 'propagate_excesses' not in context:
                    self._validation_errors.append("context_propagation missing: 'propagate_excesses'")
                elif not isinstance(context['propagate_excesses'], list):
                    self._validation_errors.append("propagate_excesses must be an array")
                
                # Check reset_on_new_day
                if 'reset_on_new_day' not in context:
                    self._validation_errors.append("context_propagation missing: 'reset_on_new_day'")
                elif not isinstance(context['reset_on_new_day'], bool):
                    self._validation_errors.append("reset_on_new_day must be boolean")

    def _validate_range_array(self, ranges: Any, path: str) -> None:
        """Validate a range array structure."""
        if not isinstance(ranges, list):
            self._validation_errors.append(f"{path} must be an array")
            return
        
        if not ranges:
            self._validation_errors.append(f"{path} cannot be empty")
            return
        
        # Check each range entry
        prev_max = None
        for i, entry in enumerate(ranges):
            if not isinstance(entry, dict):
                self._validation_errors.append(
                    f"{path}[{i}] must be an object"
                )
                continue
            
            if 'max' not in entry:
                self._validation_errors.append(
                    f"{path}[{i}] missing 'max' field"
                )
                continue
            
            max_val = entry['max']
            
            # Check ordering (except for None which should be last)
            if max_val is not None:
                if not isinstance(max_val, (int, float)):
                    self._validation_errors.append(
                        f"{path}[{i}].max must be a number or null"
                    )
                elif prev_max is not None and max_val <= prev_max:
                    self._validation_errors.append(
                        f"{path}[{i}].max must be greater than previous max"
                    )
                prev_max = max_val
        
        # Last entry should have max: null
        if ranges[-1].get('max') is not None:
            self._validation_errors.append(
                f"{path}: last entry should have 'max': null"
            )

    def get_recommendation_weights(self) -> Dict[str, float]:
        """Get scorer weights from config."""
        return self.thresholds.get("recommendation_weights", {})

    def get_scorer_config(self, scorer_name: str) -> Dict[str, Any]:
        """Get configuration for specific scorer."""
        scorers = self.thresholds.get("scorers", {})
        return scorers.get(scorer_name, {})
    
    """
    Additional validation methods for ThresholdsManager to support component_pools
    and meal_generation sections.

    """

    def _validate_component_pools(self) -> None:
        """Validate component_pools section."""
        pools = self._thresholds['component_pools']
        
        if not isinstance(pools, dict):
            self._validation_errors.append("component_pools must be an object")
            return
        
        # Track all pool names for reference validation
        pool_names = set(pools.keys())
        
        # Validate each pool
        for pool_name, pool_contents in pools.items():
            if not isinstance(pool_contents, list):
                self._validation_errors.append(
                    f"component_pools.{pool_name} must be an array"
                )
                continue
            
            if len(pool_contents) == 0:
                self._validation_errors.append(
                    f"component_pools.{pool_name} cannot be empty"
                )
                continue
            
            # Check each item in pool
            for i, item in enumerate(pool_contents):
                if not isinstance(item, str):
                    self._validation_errors.append(
                        f"component_pools.{pool_name}[{i}] must be a string"
                    )
                    continue
                
                # If it's a reference (starts with @), validate target exists
                if item.startswith('@'):
                    ref_name = item[1:]  # Strip @
                    if ref_name not in pool_names:
                        self._validation_errors.append(
                            f"component_pools.{pool_name}[{i}]: reference '@{ref_name}' not found"
                        )
                # Otherwise it should be a food code (basic format check)
                elif not item or '.' not in item:
                    self._validation_errors.append(
                        f"component_pools.{pool_name}[{i}]: invalid food code '{item}' (expected format: XX.YY)"
                    )
        
        # Check for circular references
        self._check_circular_pool_references(pools)


    def _check_circular_pool_references(self, pools: Dict[str, List[str]]) -> None:
        """Check for circular references in component pools."""
        
        def has_cycle(pool_name: str, path: set) -> bool:
            """DFS to detect cycles using only path tracking."""
            if pool_name in path:
                return True  # Found a back edge - cycle!
            
            if pool_name not in pools:
                return False
            
            path.add(pool_name)
            
            # Check all references
            for item in pools[pool_name]:
                if isinstance(item, str) and item.startswith('@'):
                    ref_name = item[1:]
                    if has_cycle(ref_name, path):
                        return True
            
            path.remove(pool_name)
            return False
        
        # Check each pool for cycles
        for pool_name in pools:
            if has_cycle(pool_name, set()):
                self._validation_errors.append(
                    f"component_pools: circular reference detected involving '{pool_name}'"
                )
                break

    def _validate_meal_generation(self) -> None:
        """Validate meal_generation section."""
        meal_gen = self._thresholds['meal_generation']
        
        if not isinstance(meal_gen, dict):
            self._validation_errors.append("meal_generation must be an object")
            return
        
        # Get component pools for validation
        pools = self._thresholds.get('component_pools', {})
        pool_names = set(pools.keys()) if isinstance(pools, dict) else set()
        
        # Get meal_templates for targets_ref validation
        meal_templates = self._thresholds.get('meal_templates', {})
        
        # Validate each meal category
        for meal_name, templates in meal_gen.items():
            if not isinstance(templates, dict):
                self._validation_errors.append(
                    f"meal_generation.{meal_name} must be an object"
                )
                continue
            
            # Validate each generation template
            for template_name, template in templates.items():
                path = f"meal_generation.{meal_name}.{template_name}"
                self._validate_generation_template(template, path, pool_names, meal_templates)


    def _validate_generation_template(
        self, 
        template: Any, 
        path: str,
        pool_names: set,
        meal_templates: Dict[str, Any]
    ) -> None:
        """
        Validate a single generation template.
        
        Args:
            template: Generation template dict
            path: Dot-notation path for error messages
            pool_names: Set of valid pool names
            meal_templates: Meal templates for targets_ref validation
        """
        if not isinstance(template, dict):
            self._validation_errors.append(f"{path} must be an object")
            return
        
        # Validate targets_ref
        if 'targets_ref' not in template:
            self._validation_errors.append(f"{path} missing: 'targets_ref'")
        else:
            targets_ref = template['targets_ref']
            if not isinstance(targets_ref, str):
                self._validation_errors.append(f"{path}.targets_ref must be a string")
            else:
                # Validate targets_ref path exists
                self._validate_targets_ref(targets_ref, path, meal_templates)
        
        # Validate components
        if 'components' not in template:
            self._validation_errors.append(f"{path} missing: 'components'")
        else:
            components = template['components']
            if not isinstance(components, dict):
                self._validation_errors.append(f"{path}.components must be an object")
            elif len(components) == 0:
                self._validation_errors.append(f"{path}.components cannot be empty")
            else:
                for comp_name, comp_spec in components.items():
                    self._validate_component_spec(
                        comp_spec, 
                        f"{path}.components.{comp_name}",
                        pool_names
                    )
        
        # Validate constraints (optional)
        if 'constraints' in template:
            constraints = template['constraints']
            if not isinstance(constraints, dict):
                self._validation_errors.append(f"{path}.constraints must be an object")
            else:
                self._validate_constraints(constraints, f"{path}.constraints")


    def _validate_targets_ref(
        self,
        targets_ref: str,
        path: str,
        meal_templates: Dict[str, Any]
    ) -> None:
        """
        Validate that targets_ref path exists in meal_templates.
        
        Args:
            targets_ref: Path like "meal_templates.breakfast.protein_low_carb"
            path: Current validation path for error messages
            meal_templates: meal_templates section
        """
        # Must start with meal_templates
        if not targets_ref.startswith("meal_templates."):
            self._validation_errors.append(
                f"{path}.targets_ref must start with 'meal_templates.'"
            )
            return
        
        # Navigate the path
        parts = targets_ref.split(".")[1:]  # Skip 'meal_templates'
        current = meal_templates
        
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                self._validation_errors.append(
                    f"{path}.targets_ref: path '{targets_ref}' not found in meal_templates"
                )
                return
            current = current[part]
        
        # Verify it has targets
        if isinstance(current, dict) and 'targets' not in current:
            self._validation_errors.append(
                f"{path}.targets_ref: '{targets_ref}' has no 'targets' section"
            )


    def _validate_component_spec(
        self,
        comp_spec: Any,
        path: str,
        pool_names: set
    ) -> None:
        """
        Validate a component specification.
        
        Args:
            comp_spec: Component spec dict
            path: Dot-notation path for error messages
            pool_names: Set of valid pool names
        """
        if not isinstance(comp_spec, dict):
            self._validation_errors.append(f"{path} must be an object")
            return
        
        # Must have either pool_ref OR pool (but not both)
        has_pool_ref = 'pool_ref' in comp_spec
        has_pool = 'pool' in comp_spec
        
        if not has_pool_ref and not has_pool:
            self._validation_errors.append(
                f"{path} must have either 'pool_ref' or 'pool'"
            )
        elif has_pool_ref and has_pool:
            self._validation_errors.append(
                f"{path} cannot have both 'pool_ref' and 'pool'"
            )
        
        # Validate pool_ref if present
        if has_pool_ref:
            pool_ref = comp_spec['pool_ref']
            if not isinstance(pool_ref, str):
                self._validation_errors.append(f"{path}.pool_ref must be a string")
            elif pool_ref not in pool_names:
                self._validation_errors.append(
                    f"{path}.pool_ref: pool '{pool_ref}' not found in component_pools"
                )
        
        # Validate pool if present
        if has_pool:
            pool = comp_spec['pool']
            if not isinstance(pool, list):
                self._validation_errors.append(f"{path}.pool must be an array")
            elif len(pool) == 0:
                self._validation_errors.append(f"{path}.pool cannot be empty")
        
        # Validate count
        if 'count' not in comp_spec:
            self._validation_errors.append(f"{path} missing: 'count'")
        else:
            count = comp_spec['count']
            if not isinstance(count, dict):
                self._validation_errors.append(f"{path}.count must be an object")
            else:
                # Validate min/max
                if 'min' not in count:
                    self._validation_errors.append(f"{path}.count missing: 'min'")
                elif not isinstance(count['min'], int) or count['min'] < 0:
                    self._validation_errors.append(
                        f"{path}.count.min must be a non-negative integer"
                    )
                
                if 'max' not in count:
                    self._validation_errors.append(f"{path}.count missing: 'max'")
                elif not isinstance(count['max'], int) or count['max'] < 0:
                    self._validation_errors.append(
                        f"{path}.count.max must be a non-negative integer"
                    )
                
                # Check min <= max
                if 'min' in count and 'max' in count:
                    if isinstance(count['min'], int) and isinstance(count['max'], int):
                        if count['min'] > count['max']:
                            self._validation_errors.append(
                                f"{path}.count: min ({count['min']}) > max ({count['max']})"
                            )
        
        # Validate required
        if 'required' not in comp_spec:
            self._validation_errors.append(f"{path} missing: 'required'")
        elif not isinstance(comp_spec['required'], bool):
            self._validation_errors.append(f"{path}.required must be a boolean")


    def _validate_constraints(self, constraints: Dict[str, Any], path: str) -> None:
        """
        Validate constraints section.
        
        Args:
            constraints: Constraints dict
            path: Dot-notation path for error messages
        """
        # Validate max_total_components (optional)
        if 'max_total_components' in constraints:
            max_comp = constraints['max_total_components']
            if not isinstance(max_comp, int) or max_comp < 1:
                self._validation_errors.append(
                    f"{path}.max_total_components must be a positive integer"
                )
        
        # Validate base_code_uniqueness (optional)
        if 'base_code_uniqueness' in constraints:
            uniqueness = constraints['base_code_uniqueness']
            if not isinstance(uniqueness, bool):
                self._validation_errors.append(
                    f"{path}.base_code_uniqueness must be a boolean"
                )
        
        # Validate nutrient_limits (optional)
        if 'nutrient_limits' in constraints:
            limits = constraints['nutrient_limits']
            if not isinstance(limits, dict):
                self._validation_errors.append(f"{path}.nutrient_limits must be an object")
            else:
                for nutrient, limit_spec in limits.items():
                    self._validate_nutrient_limit(
                        limit_spec,
                        f"{path}.nutrient_limits.{nutrient}"
                    )


    def _validate_nutrient_limit(self, limit_spec: Any, path: str) -> None:
        """
        Validate a nutrient limit specification.
        
        Args:
            limit_spec: Nutrient limit dict
            path: Dot-notation path for error messages
        """
        if not isinstance(limit_spec, dict):
            self._validation_errors.append(f"{path} must be an object")
            return
        
        # Validate numeric fields
        numeric_fields = ['hard_min', 'hard_max', 'soft_min', 'soft_max', 
                        'soft_max_tolerance', 'tolerance']
        for field in numeric_fields:
            if field in limit_spec:
                value = limit_spec[field]
                if not isinstance(value, (int, float)) or value < 0:
                    self._validation_errors.append(
                        f"{path}.{field} must be a non-negative number"
                    )
        
        # Validate boolean fields
        boolean_fields = ['reject_below_min', 'reject_above_max', 'no_minimum',
                        'penalty_above_max', 'penalty_out_of_range']
        for field in boolean_fields:
            if field in limit_spec:
                value = limit_spec[field]
                if not isinstance(value, bool):
                    self._validation_errors.append(
                        f"{path}.{field} must be a boolean"
                    )
        
        # Logical validations
        if 'hard_min' in limit_spec and 'soft_min' in limit_spec:
            if limit_spec['hard_min'] > limit_spec['soft_min']:
                self._validation_errors.append(
                    f"{path}: hard_min cannot be greater than soft_min"
                )
        
        if 'soft_max' in limit_spec and 'hard_max' in limit_spec:
            if limit_spec['soft_max'] > limit_spec['hard_max']:
                self._validation_errors.append(
                    f"{path}: soft_max cannot be greater than hard_max"
                )
        
        if 'soft_max_tolerance' in limit_spec:
            if 'soft_max' not in limit_spec:
                self._validation_errors.append(
                    f"{path}: soft_max_tolerance requires soft_max to be defined"
                )
            elif limit_spec['soft_max_tolerance'] < 1.0:
                self._validation_errors.append(
                    f"{path}.soft_max_tolerance must be >= 1.0"
                )


    # Add these getter methods to the ThresholdsManager class:

    def get_component_pools(self) -> Optional[Dict[str, List[str]]]:
        """
        Get component pools section.
        
        Returns:
            Dict of pool_name -> list of food codes/references, or None if not valid
        """
        if not self.is_valid:
            return None
        return self._thresholds.get('component_pools')


    def get_meal_generation(self) -> Optional[Dict[str, Any]]:
        """
        Get meal generation section.
        
        Returns:
            Dict of meal categories -> generation templates, or None if not valid
        """
        if not self.is_valid:
            return None
        return self._thresholds.get('meal_generation')


    def get_generation_template(self, meal_type: str, template_name: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific generation template.
        
        Args:
            meal_type: Meal category (e.g., 'breakfast', 'lunch')
            template_name: Template name (e.g., 'protein_low_carb')
        
        Returns:
            Generation template dict, or None if not found
        """
        if not self.is_valid:
            return None
        
        meal_gen = self._thresholds.get('meal_generation', {})
        if meal_type not in meal_gen:
            return None
        
        return meal_gen[meal_type].get(template_name)


    def expand_pool(self, pool_name: str) -> List[str]:
        """
        Expand a component pool, resolving @references recursively.
        
        Args:
            pool_name: Name of pool to expand
        
        Returns:
            List of food codes (no @references), or empty list if pool not found
        
        Example:
            pools = {
                "eggs": ["EG.1", "EG.B1"],
                "meats": ["MT.4b", "LE.5a"],
                "breakfast_proteins": ["@eggs", "@meats"]
            }
            expand_pool("breakfast_proteins") -> ["EG.1", "EG.B1", "MT.4b", "LE.5a"]
        """
        if not self.is_valid:
            return []
        
        pools = self._thresholds.get('component_pools', {})
        if pool_name not in pools:
            return []
        
        # Track visited pools to prevent infinite recursion
        visited = set()
        
        def expand_recursive(name: str) -> List[str]:
            if name in visited:
                return []  # Circular reference, already validated
            
            if name not in pools:
                return []
            
            visited.add(name)
            result = []
            
            for item in pools[name]:
                if item.startswith('@'):
                    # Recursive expansion
                    ref_name = item[1:]
                    result.extend(expand_recursive(ref_name))
                else:
                    # Direct food code
                    result.append(item)
            
            return result
        
        return expand_recursive(pool_name)
    
    def validate_food_codes(self, master_loader) -> List[str]:
        """
        Validate that all food codes in component pools exist in master.csv.
        
        Call this AFTER load() succeeds with MasterLoader available.
        Uses master_loader.lookup_code() which triggers lazy load.
        
        Args:
            master_loader: MasterLoader instance
        
        Returns:
            List of validation errors (empty if all valid)
        """
        errors = []
        
        if not self.is_valid or 'component_pools' not in self._thresholds:
            return errors
        
        # Check each pool
        pools = self._thresholds['component_pools']
        for pool_name, pool_contents in pools.items():
            if not isinstance(pool_contents, list):
                continue
            
            for item in pool_contents:
                if not isinstance(item, str):
                    continue
                
                # Skip references
                if item.startswith('@'):
                    continue
                
                # Check food code exists (triggers master load if needed)
                code = item.upper()
                if master_loader.lookup_code(code) is None:
                    errors.append(
                        f"component_pools.{pool_name}: food code '{code}' not found in master.csv"
                    )
        
        return errors