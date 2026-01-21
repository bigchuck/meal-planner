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
    
    def get_error_message(self) -> str:
        """
        Get formatted error message for display.
        
        Returns:
            Single-line error summary
        """
        if not self._validation_errors:
            return "Thresholds not loaded"
        
        if len(self._validation_errors) == 1:
            return self._validation_errors[0]
        
        print(self._validation_errors)

        return f"Multiple errors in thresholds file ({len(self._validation_errors)} issues)"
    
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
    
        # Validate daily_planning
        if 'daily_planning' in self._thresholds:
            self._validate_daily_planning()

    
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