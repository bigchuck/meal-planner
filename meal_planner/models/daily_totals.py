"""
Models for nutrient totals and daily summaries.
"""
from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class DailyTotals:
    """
    Represents daily nutrient totals.
    
    Attributes:

        # Macronutrients
        calories: Total calories
        protein_g: Total protein in grams
        carbs_g: Total carbohydrates in grams
        fat_g: Total fat in grams
        sugar_g: Total sugar in grams
        glycemic_load: Total glycemic load
    
        # Micronutrients
        fiber_g: Total fiber in grams
        sodium_mg: Total sodium in milligrams
        potassium_mg: Total potassium in milligrams
        vitA_mcg: Total vitamin A in micrograms
        vitC_mg: Total vitamin C in milligrams
        iron_mg: Total iron in milligrams

    Example:
        >>> totals = DailyTotals(calories=2000, protein_g=150, carbs_g=200, fat_g=70)
        >>> print(totals.calories)
        2000
    """
    calories: float = 0.0
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0
    sugar_g: float = 0.0
    glycemic_load: float = 0.0

    fiber_g: float = 0.0
    sodium_mg: float = 0.0
    potassium_mg: float = 0.0
    vitA_mcg: float = 0.0
    vitC_mg: float = 0.0
    iron_mg: float = 0.0
    
    def to_dict(self) -> Dict[str, float]:
        """
        Convert to dictionary format.
        
        Returns:
            Dictionary with keys: cal, prot_g, carbs_g, fat_g, sugar_g, gl
        """
        return {
            "cal": self.calories,
            "prot_g": self.protein_g,
            "carbs_g": self.carbs_g,
            "fat_g": self.fat_g,
            "sugar_g": self.sugar_g,
            "gl": self.glycemic_load,
            "fiber_g": self.fiber_g,
            "sodium_mg": self.sodium_mg,
            "potassium_mg": self.potassium_mg,
            "vitA_mcg": self.vitA_mcg,
            "vitC_mg": self.vitC_mg,
            "iron_mg": self.iron_mg
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DailyTotals':
        """
        Create from dictionary format.
        
        Args:
            data: Dictionary with nutrient values (various key formats supported)
        
        Returns:
            DailyTotals instance
        """
        def get_float(key_variants: tuple, default: float = 0.0) -> float:
            """Try multiple key variants and return first found."""
            for key in key_variants:
                if key in data:
                    try:
                        return float(data[key])
                    except (ValueError, TypeError):
                        pass
            return default
        
        return cls(
            calories=get_float(("cal", "calories")),
            protein_g=get_float(("prot_g", "protein_g", "protein")),
            carbs_g=get_float(("carbs_g", "carbohydrates_g", "carbs")),
            fat_g=get_float(("fat_g", "fat")),
            sugar_g=get_float(("sugar_g", "sugar")),
            glycemic_load=get_float(("gl", "glycemic_load", "GL")),
            fiber_g=get_float(("fiber_g", "fiber")),
            sodium_mg=get_float(("sodium_mg", "sodium")),
            potassium_mg=get_float(("potassium_mg", "potassium")),
            vitA_mcg=get_float(("vitA_mcg", "vita_mcg", "vitamin_a_mcg", "vitamin_a")),
            vitC_mg=get_float(("vitC_mg", "vitc_mg", "vitamin_c_mg", "vitamin_c")),
            iron_mg=get_float(("iron_mg", "iron"))
        )
    
    def add(self, other: 'DailyTotals') -> 'DailyTotals':
        """
        Add another DailyTotals to this one (returns new instance).
        
        Args:
            other: Another DailyTotals instance
        
        Returns:
            New DailyTotals with summed values
        
        Example:
            >>> t1 = DailyTotals(calories=500, protein_g=30)
            >>> t2 = DailyTotals(calories=300, protein_g=20)
            >>> t3 = t1.add(t2)
            >>> print(t3.calories)
            800
        """
        return DailyTotals(
            calories=self.calories + other.calories,
            protein_g=self.protein_g + other.protein_g,
            carbs_g=self.carbs_g + other.carbs_g,
            fat_g=self.fat_g + other.fat_g,
            sugar_g=self.sugar_g + other.sugar_g,
            glycemic_load=self.glycemic_load + other.glycemic_load,
            fiber_g=self.fiber_g + other.fiber_g,
            sodium_mg=self.sodium_mg + other.sodium_mg,
            potassium_mg=self.potassium_mg + other.potassium_mg,
            vitA_mcg=self.vitA_mcg + other.vitA_mcg,
            vitC_mg=self.vitC_mg + other.vitC_mg,
            iron_mg=self.iron_mg + other.iron_mg
        )
    
    def __add__(self, other: 'DailyTotals') -> 'DailyTotals':
        """Support + operator."""
        return self.add(other)
    
    def scale(self, multiplier: float) -> 'DailyTotals':
        """
        Scale all values by a multiplier (returns new instance).
        
        Args:
            multiplier: Scaling factor
        
        Returns:
            New DailyTotals with scaled values
        
        Example:
            >>> totals = DailyTotals(calories=1000, protein_g=50)
            >>> doubled = totals.scale(2.0)
            >>> print(doubled.calories)
            2000
        """
        return DailyTotals(
            calories=self.calories * multiplier,
            protein_g=self.protein_g * multiplier,
            carbs_g=self.carbs_g * multiplier,
            fat_g=self.fat_g * multiplier,
            sugar_g=self.sugar_g * multiplier,
            glycemic_load=self.glycemic_load * multiplier,
            fiber_g=self.fiber_g * multiplier,
            sodium_mg=self.sodium_mg * multiplier,
            potassium_mg=self.potassium_mg * multiplier,
            vitA_mcg=self.vitA_mcg * multiplier,
            vitC_mg=self.vitC_mg * multiplier,
            iron_mg=self.iron_mg * multiplier,
        )
    
    def __mul__(self, multiplier: float) -> 'DailyTotals':
        """Support * operator."""
        return self.scale(multiplier)
    
    def rounded(self) -> 'DailyTotals':
        """
        Return new instance with all values rounded to integers.
        
        Returns:
            New DailyTotals with rounded values
        """
        return DailyTotals(
            calories=round(self.calories),
            protein_g=round(self.protein_g),
            carbs_g=round(self.carbs_g),
            fat_g=round(self.fat_g),
            sugar_g=round(self.sugar_g),
            glycemic_load=round(self.glycemic_load),
            fiber_g=round(self.fiber_g),
            sodium_mg=round(self.sodium_mg),
            potassium_mg=round(self.potassium_mg),
            vitA_mcg=round(self.vitA_mcg),
            vitC_mg=round(self.vitC_mg),
            iron_mg=round(self.iron_mg),
        )
    
    def format_summary(self) -> str:
        """
        Format as human-readable summary string.
        
        Returns:
            Formatted string with all nutrients
        
        Example:
            >>> totals = DailyTotals(calories=2000, protein_g=150)
            >>> print(totals.format_summary())
            Cal: 2000 | P: 150g | C: 0g | F: 0g | Sugars: 0g | GL: 0
        """
        rounded = self.rounded()
        return (
            f"Cal: {int(rounded.calories)} | "
            f"P: {int(rounded.protein_g)}g | "
            f"C: {int(rounded.carbs_g)}g | "
            f"F: {int(rounded.fat_g)}g | "
            f"Sugars: {int(rounded.sugar_g)}g | "
            f"GL: {int(rounded.glycemic_load)}"
        )
    
    def format_detailed_summary(self) -> str:
        """
        Format with micronutrients included.
        
        Returns:
            Formatted string with macros and micros
        """
        rounded = self.rounded()
        lines = []
        lines.append(self.format_summary())
        lines.append(
            f"Fiber: {int(rounded.fiber_g)}g | "
            f"Sodium: {int(rounded.sodium_mg)}mg | "
            f"Potassium: {int(rounded.potassium_mg)}mg"
        )
        lines.append(
            f"Vit A: {int(rounded.vitA_mcg)}mcg | "
            f"Vit C: {int(rounded.vitC_mg)}mg | "
            f"Iron: {int(rounded.iron_mg)}mg"
        )
        return "\n".join(lines)
    
    def __str__(self) -> str:
        """String representation."""
        return self.format_summary()


@dataclass
class NutrientRow:
    """
    Represents a single row in a nutrient breakdown (for reports).
    
    Used when showing detailed breakdown of each code in a meal.
    
    Attributes:
        code: Meal code
        option: Meal description
        section: Meal section/category
        multiplier: Portion multiplier
        totals: Nutrient totals for this item
    """
    code: str
    option: str
    section: str
    multiplier: float
    totals: DailyTotals
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        result = {
            "code": self.code,
            "option": self.option,
            "section": self.section,
            "mult": self.multiplier
        }
        result.update(self.totals.to_dict())
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NutrientRow':
        """Create from dictionary format."""
        totals = DailyTotals.from_dict(data)
        return cls(
            code=data.get("code", ""),
            option=data.get("option", ""),
            section=data.get("section", ""),
            multiplier=float(data.get("mult", 1.0)),
            totals=totals
        )