"""
Calculate glucose prediction
"""
"""
Glucose impact calculator for meal planning.

Calculates glucose-related metrics from meal data including glycemic load,
meal timing, and estimated glucose response patterns.
"""
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class GlucoseMetrics:
    """Container for glucose-related calculations."""
    total_gl: float
    peak_gl: float  # Highest single-meal GL
    meal_count: int
    avg_gl_per_meal: float
    time_weighted_gl: float  # GL adjusted for meal spacing
    estimated_peak_time: Optional[str]  # When glucose likely peaks
    meal_distribution_score: float  # How well-distributed meals are (0-1)
    

class GlucoseCalculator:
    """
    Calculates glucose impact metrics from meal data.
    
    Uses glycemic load values and meal timing to estimate glucose response.
    """
    
    # Time constants (minutes)
    GLUCOSE_PEAK_TIME = 45  # Minutes to peak after eating
    GLUCOSE_CLEAR_TIME = 180  # Minutes to return to baseline
    IDEAL_MEAL_GAP = 240  # Ideal gap between meals (4 hours)
    
    def __init__(self):
        """Initialize calculator."""
        pass
    
    def calculate_from_meals(self, meals: List[Dict[str, Any]]) -> GlucoseMetrics:
        """
        Calculate glucose metrics from meal breakdown.
        
        Args:
            meals: List of meal dicts with keys:
                   - 'time': Time string (HH:MM)
                   - 'gl': Glycemic load value
                   - 'name': Meal name (optional)
        
        Returns:
            GlucoseMetrics object
        """
        if not meals:
            return GlucoseMetrics(
                total_gl=0, peak_gl=0, meal_count=0,
                avg_gl_per_meal=0, time_weighted_gl=0,
                estimated_peak_time=None, meal_distribution_score=1.0
            )
        
        # Basic metrics
        total_gl = sum(m['gl'] for m in meals)
        peak_gl = max(m['gl'] for m in meals)
        meal_count = len(meals)
        avg_gl = total_gl / meal_count if meal_count > 0 else 0
        
        # Time-weighted GL (accounts for overlapping glucose responses)
        time_weighted = self._calculate_time_weighted_gl(meals)
        
        # Find estimated peak time
        peak_time = self._estimate_peak_time(meals)
        
        # Calculate distribution score
        distribution = self._calculate_distribution_score(meals)
        
        return GlucoseMetrics(
            total_gl=total_gl,
            peak_gl=peak_gl,
            meal_count=meal_count,
            avg_gl_per_meal=avg_gl,
            time_weighted_gl=time_weighted,
            estimated_peak_time=peak_time,
            meal_distribution_score=distribution
        )
    
    def _calculate_time_weighted_gl(self, meals: List[Dict[str, Any]]) -> float:
        """
        Calculate time-weighted GL considering meal spacing.
        
        When meals are close together, glucose responses overlap,
        potentially creating higher peaks than isolated meals.
        """
        if not meals:
            return 0.0
        
        # Sort meals by time
        sorted_meals = sorted(meals, key=lambda m: self._time_to_minutes(m['time']))
        
        # Simulate glucose curve throughout day
        max_response = 0.0
        
        for i, meal in enumerate(sorted_meals):
            meal_time = self._time_to_minutes(meal['time'])
            meal_gl = meal['gl']
            
            # Peak response for this meal
            peak_time = meal_time + self.GLUCOSE_PEAK_TIME
            
            # Check for overlaps with other meals
            overlap_factor = 1.0
            
            for j, other_meal in enumerate(sorted_meals):
                if i == j:
                    continue
                    
                other_time = self._time_to_minutes(other_meal['time'])
                time_diff = abs(peak_time - other_time)
                
                # If meals are close, increase impact
                if time_diff < self.GLUCOSE_CLEAR_TIME:
                    overlap_boost = 1.0 - (time_diff / self.GLUCOSE_CLEAR_TIME)
                    overlap_factor += overlap_boost * 0.3  # 30% additional impact
            
            meal_response = meal_gl * overlap_factor
            max_response = max(max_response, meal_response)
        
        return max_response
    
    def _estimate_peak_time(self, meals: List[Dict[str, Any]]) -> Optional[str]:
        """
        Estimate when glucose levels will be highest.
        
        Returns time string (HH:MM) of estimated peak.
        """
        if not meals:
            return None
        
        # Find meal with highest GL
        peak_meal = max(meals, key=lambda m: m['gl'])
        
        # Add peak time offset
        peak_minutes = (self._time_to_minutes(peak_meal['time']) + 
                       self.GLUCOSE_PEAK_TIME)
        
        return self._minutes_to_time(peak_minutes)
    
    def _calculate_distribution_score(self, meals: List[Dict[str, Any]]) -> float:
        """
        Calculate how well-distributed meals are throughout the day.
        
        Returns score from 0-1, where 1 is optimal spacing.
        """
        if len(meals) <= 1:
            return 1.0
        
        # Sort by time
        sorted_meals = sorted(meals, key=lambda m: self._time_to_minutes(m['time']))
        
        # Calculate gaps between meals
        gaps = []
        for i in range(len(sorted_meals) - 1):
            time1 = self._time_to_minutes(sorted_meals[i]['time'])
            time2 = self._time_to_minutes(sorted_meals[i + 1]['time'])
            gap = time2 - time1
            gaps.append(gap)
        
        if not gaps:
            return 1.0
        
        # Score based on how close gaps are to ideal
        scores = []
        for gap in gaps:
            # Perfect score at ideal gap, decreases as gap differs
            deviation = abs(gap - self.IDEAL_MEAL_GAP) / self.IDEAL_MEAL_GAP
            score = max(0, 1.0 - deviation * 0.5)
            scores.append(score)
        
        return sum(scores) / len(scores)
    
    def _time_to_minutes(self, time_str: str) -> int:
        """Convert HH:MM to minutes since midnight."""
        parts = time_str.split(':')
        return int(parts[0]) * 60 + int(parts[1])
    
    def _minutes_to_time(self, minutes: int) -> str:
        """Convert minutes since midnight to HH:MM."""
        minutes = minutes % (24 * 60)  # Wrap at midnight
        h = minutes // 60
        m = minutes % 60
        return f"{h:02d}:{m:02d}"
    
    def analyze_meal_spacing(self, meals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyze gaps between meals and flag potential issues.
        
        Returns list of analysis items with recommendations.
        """
        if len(meals) <= 1:
            return []
        
        sorted_meals = sorted(meals, key=lambda m: self._time_to_minutes(m['time']))
        
        issues = []
        
        for i in range(len(sorted_meals) - 1):
            meal1 = sorted_meals[i]
            meal2 = sorted_meals[i + 1]
            
            time1 = self._time_to_minutes(meal1['time'])
            time2 = self._time_to_minutes(meal2['time'])
            gap = time2 - time1
            
            # Too close together
            if gap < 120:  # Less than 2 hours
                issues.append({
                    'type': 'close_spacing',
                    'severity': 'warning',
                    'meals': (meal1.get('name', meal1['time']), 
                             meal2.get('name', meal2['time'])),
                    'gap_hours': gap / 60,
                    'message': f"Meals only {gap} min apart - glucose responses may overlap"
                })
            
            # Too far apart
            elif gap > 360:  # More than 6 hours
                issues.append({
                    'type': 'long_gap',
                    'severity': 'info',
                    'meals': (meal1.get('name', meal1['time']), 
                             meal2.get('name', meal2['time'])),
                    'gap_hours': gap / 60,
                    'message': f"Large gap ({gap // 60}h {gap % 60}m) - consider snack"
                })
        
        return issues