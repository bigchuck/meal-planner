# meal_planner/data/staging_buffer_manager.py
"""
Staging buffer manager for email meal plan staging.

Manages staging_buffer.json with meals and analysis to be emailed.
"""
import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime


class StagingBufferManager:
    """
    Manages the meal plan staging buffer for email delivery.
    
    Provides persistent storage of meals and analysis that will be
    emailed to the user's phone. Uses positional access for user
    commands while maintaining semantic IDs internally.
    """
    
    def __init__(self, filepath: Path):
        """
        Initialize staging buffer manager.
        
        Args:
            filepath: Path to staging buffer JSON file
        """
        self.filepath = filepath
        self._buffer: Optional[Dict[str, Any]] = None
    
    def load(self) -> Dict[str, Any]:
        """
        Load buffer from disk.
        
        Returns:
            Buffer dictionary, or empty buffer if file doesn't exist
        """
        if not self.filepath.exists():
            return self._create_empty_buffer()
        
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Validate structure
            if not isinstance(data, dict):
                return self._create_empty_buffer()
            
            # Ensure required fields
            if "items" not in data or not isinstance(data["items"], dict):
                data["items"] = {}
            
            if "last_modified" not in data:
                data["last_modified"] = datetime.now().isoformat()
            
            self._buffer = data
            return data
            
        except (json.JSONDecodeError, Exception):
            # Corrupted file - return empty buffer
            return self._create_empty_buffer()
    
    def save(self, buffer: Dict[str, Any]) -> None:
        """
        Save buffer to disk.
        
        Args:
            buffer: Buffer dictionary
        """
        # Update timestamp
        buffer["last_modified"] = datetime.now().isoformat()
        
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(buffer, f, indent=2, ensure_ascii=False)
            self._buffer = buffer
        except Exception as e:
            # Log error but don't crash - buffer is session-persistent
            print(f"Warning: Failed to save staging buffer: {e}")
    
    def clear(self) -> None:
        """Delete the staging buffer file."""
        if self.filepath.exists():
            try:
                self.filepath.unlink()
                self._buffer = None
            except Exception as e:
                print(f"Warning: Failed to delete staging buffer: {e}")
    
    def _create_empty_buffer(self) -> Dict[str, Any]:
        """Create empty buffer structure."""
        buffer = {
            "last_modified": datetime.now().isoformat(),
            "items": {}
        }
        self._buffer = buffer
        return buffer
    
    # =========================================================================
    # Buffer operations
    # =========================================================================
    
    def add(self, item_id: str, label: str, content: List[str]) -> bool:
        """
        Add or update an item in the buffer.
        
        If item_id already exists, it will be overwritten with a warning.
        
        Args:
            item_id: Unique identifier (e.g., "pending:Breakfast:2024-12-26")
            label: Human-readable label (e.g., "Thursday, December 26, 2024 - BREAKFAST")
            content: List of formatted output lines
        
        Returns:
            True if item was added, False if it replaced an existing item
        """
        buffer = self.load()
        
        # Check if replacing
        replacing = item_id in buffer["items"]
        
        # Store item
        buffer["items"][item_id] = {
            "label": label,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        
        self.save(buffer)
        return not replacing
    
    def remove(self, position: int) -> Tuple[bool, Optional[str]]:
        """
        Remove an item by its position (1-based).
        
        Args:
            position: Position number (1-based)
        
        Returns:
            (success, label) where label is the removed item's label or None
        """
        buffer = self.load()
        
        # Get ordered items
        ordered_items = self._get_ordered_items(buffer)
        
        # Validate position
        if position < 1 or position > len(ordered_items):
            return False, None
        
        # Get item ID at position (convert to 0-based)
        item_id = ordered_items[position - 1][0]
        label = buffer["items"][item_id]["label"]
        
        # Remove item
        del buffer["items"][item_id]
        
        self.save(buffer)
        return True, label
    
    def clear_all(self) -> int:
        """
        Clear all items from buffer.
        
        Returns:
            Number of items that were cleared
        """
        buffer = self.load()
        count = len(buffer["items"])
        
        buffer["items"] = {}
        self.save(buffer)
        
        return count
    
    def update_label(self, position: int, new_label: str) -> Tuple[bool, Optional[str]]:
        """
        Update the label for an item at a given position.
        
        Args:
            position: Position number (1-based)
            new_label: New label text
        
        Returns:
            (success, old_label) where old_label is the previous label or None
        """
        buffer = self.load()
        
        # Get ordered items
        ordered_items = self._get_ordered_items(buffer)
        
        # Validate position
        if position < 1 or position > len(ordered_items):
            return False, None
        
        # Get item ID at position
        item_id = ordered_items[position - 1][0]
        old_label = buffer["items"][item_id]["label"]
        
        # Update label
        buffer["items"][item_id]["label"] = new_label
        
        self.save(buffer)
        return True, old_label
    
    def get_all(self) -> List[Tuple[int, str, List[str], str]]:
        """
        Get all items with their positions.
        
        Returns:
            List of (position, label, content, timestamp) tuples, ordered by timestamp
        """
        buffer = self.load()
        ordered_items = self._get_ordered_items(buffer)
        
        result = []
        for i, (item_id, item_data) in enumerate(ordered_items, start=1):
            result.append((
                i,  # position
                item_data["label"],
                item_data["content"],
                item_data["timestamp"]
            ))
        
        return result
    
    def get_by_position(self, position: int) -> Optional[Tuple[str, List[str]]]:
        """
        Get a specific item by position.
        
        Args:
            position: Position number (1-based)
        
        Returns:
            (label, content) tuple or None if position invalid
        """
        buffer = self.load()
        ordered_items = self._get_ordered_items(buffer)
        
        if position < 1 or position > len(ordered_items):
            return None
        
        item_id = ordered_items[position - 1][0]
        item_data = buffer["items"][item_id]
        
        return (item_data["label"], item_data["content"])
    
    def is_empty(self) -> bool:
        """
        Check if buffer is empty.
        
        Returns:
            True if buffer has no items
        """
        buffer = self.load()
        return len(buffer["items"]) == 0
    
    def get_count(self) -> int:
        """
        Get count of items in buffer.
        
        Returns:
            Number of items
        """
        buffer = self.load()
        return len(buffer["items"])
    
    def get_total_lines(self) -> int:
        """
        Get total line count across all items.
        
        Returns:
            Total number of content lines
        """
        buffer = self.load()
        total = 0
        for item_data in buffer["items"].values():
            total += len(item_data["content"])
        return total
    
    # =========================================================================
    # Helper methods
    # =========================================================================
    
    def _get_ordered_items(self, buffer: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Get items ordered by timestamp (oldest first).
        
        Args:
            buffer: Buffer dictionary
        
        Returns:
            List of (item_id, item_data) tuples ordered by timestamp
        """
        items = buffer.get("items", {})
        
        # Sort by timestamp
        ordered = sorted(
            items.items(),
            key=lambda x: x[1].get("timestamp", "")
        )
        
        return ordered
    
    # =========================================================================
    # ID generation helpers
    # =========================================================================
    
    @staticmethod
    def generate_pending_id(meal_name: str, date_str: str) -> str:
        """
        Generate ID for a pending meal.
        
        Args:
            meal_name: Meal name (e.g., "Breakfast")
            date_str: Date string (YYYY-MM-DD format)
        
        Returns:
            Item ID (e.g., "pending:Breakfast:2024-12-26")
        """
        return f"pending:{meal_name}:{date_str}"
    
    @staticmethod
    def generate_workspace_id(ws_id: str, meal_name: str = None) -> str:
        """
        Generate ID for a workspace meal.
        
        Args:
            ws_id: Workspace ID (e.g., "ws_1234" or "N1")
            meal_name: Optional meal name
        
        Returns:
            Item ID (e.g., "ws:N1" or "ws:N1:Dinner")
        """
        if meal_name:
            return f"ws:{ws_id}:{meal_name}"
        else:
            return f"ws:{ws_id}"
    
    @staticmethod
    def generate_analysis_id(base_id: str) -> str:
        """
        Generate ID for analysis of a meal.
        
        Args:
            base_id: Base meal ID (pending or workspace)
        
        Returns:
            Analysis ID (e.g., "analysis:pending:Breakfast:2024-12-26")
        """
        return f"analysis:{base_id}"
    
    @staticmethod
    def format_date_label(date_str: str, meal_name: str) -> str:
        """
        Format a date and meal name into a display label.
        
        Args:
            date_str: Date string (YYYY-MM-DD)
            meal_name: Meal name (e.g., "Breakfast")
        
        Returns:
            Formatted label (e.g., "Thursday, December 26, 2024 - BREAKFAST")
        """
        from datetime import datetime
        
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            # Format: "Thursday, December 26, 2024"
            date_formatted = date_obj.strftime("%A, %B %d, %Y")
            return f"{date_formatted} - {meal_name.upper()}"
        except ValueError:
            # Fallback if date parsing fails
            return f"{date_str} - {meal_name.upper()}"