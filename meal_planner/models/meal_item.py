"""
Core data models for meal items.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class MealItem:
    """
    Represents a single meal code with optional multiplier.
    
    Attributes:
        code: Meal code (e.g., "B.1", "S2.4")
        multiplier: Portion multiplier (default 1.0)
    
    Example:
        >>> item = MealItem("B.1", 1.5)
        >>> print(item)
        MealItem(code='B.1', multiplier=1.5)
    """
    code: str
    multiplier: float = 1.0
    
    def __post_init__(self):
        """Normalize code to uppercase."""
        self.code = self.code.upper()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary format (for JSON serialization).
        
        Returns:
            Dictionary with 'code' and 'mult' keys
        """
        return {
            "code": self.code,
            "mult": self.multiplier
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MealItem':
        """
        Create from dictionary format.
        
        Args:
            data: Dictionary with 'code' and optional 'mult'/'multiplier'
        
        Returns:
            MealItem instance
        """
        code = data.get("code", "")
        mult = data.get("mult") or data.get("multiplier", 1.0)
        return cls(code, float(mult))
    
    def format_code_string(self) -> str:
        """
        Format as readable code string.
        
        Returns:
            String like "B.1" or "B.1 x1.5"
        
        Example:
            >>> item = MealItem("B.1", 1.5)
            >>> item.format_code_string()
            'B.1 x1.5'
        """
        if abs(self.multiplier - 1.0) < 1e-9:
            return self.code
        elif self.multiplier < 0:
            amag = abs(self.multiplier)
            if abs(amag - 1.0) < 1e-9:
                return f"-{self.code}"
            else:
                return f"-{self.code} x{amag:g}"
        else:
            return f"{self.code} x{self.multiplier:g}"
    
    def __str__(self) -> str:
        """String representation."""
        return self.format_code_string()


@dataclass
class TimeMarker:
    """
    Represents a time marker in a meal log.
    
    Attributes:
        time: Time string in HH:MM format (e.g., "11:30")
    
    Example:
        >>> marker = TimeMarker("11:30")
        >>> print(marker)
        @11:30
    """
    time: str
    
    def __post_init__(self):
        """Validate time format."""
        if ":" not in self.time:
            raise ValueError(f"Invalid time format: {self.time}")
        
        parts = self.time.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid time format: {self.time}")
        
        try:
            hour = int(parts[0])
            minute = int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError(f"Invalid time values: {self.time}")
        except ValueError as e:
            raise ValueError(f"Invalid time format: {self.time}") from e
    
    def to_dict(self) -> Dict[str, str]:
        """
        Convert to dictionary format (for JSON serialization).
        
        Returns:
            Dictionary with 'time' key
        """
        return {"time": self.time}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TimeMarker':
        """
        Create from dictionary format.
        
        Args:
            data: Dictionary with 'time' key
        
        Returns:
            TimeMarker instance
        """
        return cls(data.get("time", "00:00"))
    
    def __str__(self) -> str:
        """String representation."""
        return f"@{self.time}"


# Type alias for items that can be either meal or time
Item = MealItem | TimeMarker


def item_from_dict(data: Dict[str, Any]) -> Optional[Item]:
    """
    Create appropriate item (MealItem or TimeMarker) from dictionary.
    
    Args:
        data: Dictionary with either 'code' or 'time' key
    
    Returns:
        MealItem, TimeMarker, or None if invalid
    
    Example:
        >>> item_from_dict({"code": "B.1", "mult": 1.5})
        MealItem(code='B.1', multiplier=1.5)
        >>> item_from_dict({"time": "11:30"})
        TimeMarker(time='11:30')
    """
    if "code" in data:
        return MealItem.from_dict(data)
    elif "time" in data:
        try:
            return TimeMarker.from_dict(data)
        except ValueError:
            return None
    return None


def items_from_dict_list(data_list: list) -> list[Item]:
    """
    Convert list of dictionaries to list of items.
    
    Args:
        data_list: List of dictionaries
    
    Returns:
        List of MealItem and TimeMarker objects
    """
    items = []
    for data in data_list:
        item = item_from_dict(data)
        if item is not None:
            items.append(item)
    return items


def items_to_dict_list(items: list[Item]) -> list[Dict[str, Any]]:
    """
    Convert list of items to list of dictionaries.
    
    Args:
        items: List of MealItem and TimeMarker objects
    
    Returns:
        List of dictionaries suitable for JSON serialization
    """
    return [item.to_dict() for item in items]