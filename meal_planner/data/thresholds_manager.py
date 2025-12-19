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
            'explain_messages'
        ]
        
        for section in required_sections:
            if section not in self._thresholds:
                self._validation_errors.append(
                    f"Missing required section: '{section}'"
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