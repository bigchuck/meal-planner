# meal_planner/generators/__init__.py
"""
Meal candidate generation for recommendation engine.
"""
from .history_meal_generator import HistoryMealGenerator
from .exhaustive_meal_generator import ExhaustiveMealGenerator

__all__ = ['HistoryMealGenerator', 'ExhaustiveMealGenerator']