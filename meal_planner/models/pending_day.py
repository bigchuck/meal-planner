"""
Model for pending day with meal items.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import List, Dict, Any

from .meal_item import MealItem, TimeMarker, Item, items_from_dict_list, items_to_dict_list


@dataclass
class PendingDay:
    """
    Represents a day's pending meal entries.
    
    Attributes:
        date: Date string (YYYY-MM-DD)
        items: List of MealItem and TimeMarker objects
    
    Example:
        >>> day = PendingDay("2025-01-15", [
        ...     MealItem("B.1", 1.5),
        ...     TimeMarker("11:00"),
        ...     MealItem("S2.4", 1.0)
        ... ])
        >>> print(len(day.items))
        3
    """
    date: str
    items: List[Item] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate date format."""
        # Basic validation - just check it looks like YYYY-MM-DD
        if not self.date or len(self.date) != 10 or self.date.count("-") != 2:
            # Try to fix common issues
            try:
                # If it's a date object, convert
                if hasattr(self.date, 'isoformat'):
                    self.date = self.date.isoformat()
                else:
                    self.date = str(date.today())
            except:
                self.date = str(date.today())
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary format (for JSON serialization).
        
        Returns:
            Dictionary with 'date' and 'items' keys
        """
        return {
            "date": self.date,
            "items": items_to_dict_list(self.items)
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PendingDay':
        """
        Create from dictionary format.
        
        Args:
            data: Dictionary with 'date' and 'items' keys
        
        Returns:
            PendingDay instance
        """
        date_str = data.get("date", str(date.today()))
        items_data = data.get("items", [])
        items = items_from_dict_list(items_data)
        return cls(date_str, items)
    
    def add_item(self, item: Item) -> None:
        """
        Add an item to the pending list.
        
        Args:
            item: MealItem or TimeMarker to add
        """
        self.items.append(item)
    
    def remove_item(self, index: int) -> None:
        """
        Remove an item by index.
        
        Args:
            index: 0-based index to remove
        
        Raises:
            IndexError: If index is out of range
        """
        del self.items[index]
    
    def get_meal_items(self) -> List[MealItem]:
        """
        Get only the meal items (exclude time markers).
        
        Returns:
            List of MealItem objects
        """
        return [item for item in self.items if isinstance(item, MealItem)]
    
    def get_time_markers(self) -> List[TimeMarker]:
        """
        Get only the time markers.
        
        Returns:
            List of TimeMarker objects
        """
        return [item for item in self.items if isinstance(item, TimeMarker)]
    
    def format_codes_string(self) -> str:
        """
        Format items as a readable codes string.
        
        Returns:
            String like "B.1 x1.5, @11:00, S2.4"
        
        Example:
            >>> day = PendingDay("2025-01-15", [
            ...     MealItem("B.1", 1.5),
            ...     TimeMarker("11:00")
            ... ])
            >>> day.format_codes_string()
            'B.1 x1.5, @11:00'
        """
        parts = []
        for item in self.items:
            if isinstance(item, TimeMarker):
                parts.append(str(item))
            elif isinstance(item, MealItem):
                parts.append(item.format_code_string())
        return ", ".join(parts)
    
    def is_empty(self) -> bool:
        """
        Check if there are no items.
        
        Returns:
            True if items list is empty
        """
        return len(self.items) == 0
    
    def clear(self) -> None:
        """Remove all items."""
        self.items.clear()
    
    def __len__(self) -> int:
        """Return number of items."""
        return len(self.items)
    
    def __str__(self) -> str:
        """String representation."""
        return f"PendingDay({self.date}, {len(self.items)} items)"