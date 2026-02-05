# meal_planner/filters/base_filter.py
"""
Base class for meal candidate filters.

Defines the standard interface and common behaviors for all filters
in the recommendation pipeline.
"""
from typing import List, Dict, Any, Tuple
from abc import ABC, abstractmethod


class BaseFilter(ABC):
    """
    Abstract base class for meal candidate filters.
    
    All filters follow a common contract:
    - Accept a list of candidates with 'rejection_reasons' field initialized
    - Return (passed, rejected) tuple based on filter criteria
    - Support collect_all mode for accumulating violations across filters
    
    Subclasses must implement:
    - filter_candidates(): Core filtering logic
    """
    
    def __init__(self):
        """Initialize base filter."""
        self.collect_all = False
    
    @abstractmethod
    def filter_candidates(
        self,
        candidates: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Apply filter logic to candidates.
        
        Subclasses implement specific filtering criteria.
        
        Expected behavior:
        - Candidates have 'rejection_reasons' list initialized
        - Add reasons to rejection_reasons for violations
        - If collect_all=True: accumulate reasons but still pass candidates
        - If collect_all=False: reject candidates immediately on violation
        
        Args:
            candidates: List of candidates with 'rejection_reasons' field
        
        Returns:
            Tuple of (passed_candidates, rejected_candidates)
        """
        pass
    
    def get_filter_stats(
        self,
        original_count: int,
        filtered_count: int
    ) -> str:
        """
        Get human-readable filter statistics.
        
        Default implementation shows pass/reject counts and percentage.
        Subclasses can override for more detailed statistics.
        
        Args:
            original_count: Number of candidates before filtering
            filtered_count: Number of candidates after filtering
        
        Returns:
            Formatted statistics string
        """
        rejected_count = original_count - filtered_count
        pass_rate = (filtered_count / original_count * 100) if original_count > 0 else 0
        
        return f"passed {filtered_count}/{original_count} ({pass_rate:.1f}%)"