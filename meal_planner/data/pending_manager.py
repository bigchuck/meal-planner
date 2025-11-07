"""
Pending day manager for in-progress meal entries.

Handles persistence of the current day's pending items to JSON,
with validation and normalization of the data structure.
"""
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import date

from meal_planner.parsers import parse_selection_to_items


class PendingManager:
    """
    Manages the pending meal entries JSON file.
    
    The pending file stores the current day's meal selections
    before they are finalized and saved to the log.
    """
    
    def __init__(self, filepath: Path):
        """
        Initialize pending manager.
        
        Args:
            filepath: Path to pending JSON file
        """
        self.filepath = filepath
    
    def load(self) -> Optional[Dict[str, Any]]:
        """
        Load pending data from disk.
        
        Returns:
            Normalized pending dictionary, or None if file doesn't exist
            Format: {"date": "YYYY-MM-DD", "items": [{"code": "...", "mult": ...}, ...]}
        """
        if not self.filepath.exists():
            return None
        
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            return self._normalize(raw)
        except Exception:
            # Corrupted file - return None
            return None
    
    def save(self, pending: Dict[str, Any]) -> None:
        """
        Save pending data to disk.
        
        Args:
            pending: Pending dictionary with 'date' and 'items'
        """
        normalized = self._normalize(pending) or {
            "date": str(date.today()),
            "items": []
        }
        
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(normalized, f, indent=2, ensure_ascii=False)
    
    def clear(self) -> None:
        """Delete the pending file."""
        if self.filepath.exists():
            os.remove(self.filepath)
    
    def _normalize(self, data: Any) -> Optional[Dict[str, Any]]:
        """
        Normalize pending data to consistent structure.
        
        Handles various legacy formats and ensures consistent output.
        
        Args:
            data: Raw pending data (dict, list, or other)
        
        Returns:
            Normalized dict with 'date' and 'items', or None if invalid
        """
        if data is None:
            return None
        
        # Unwrap {"pending": {...}} legacy format
        if isinstance(data, dict) and "pending" in data and isinstance(data["pending"], dict):
            data = data["pending"]
        
        # List input: treat as items list
        if isinstance(data, list):
            items = self._normalize_items(data)
            return {
                "date": str(date.today()),
                "items": items
            }
        
        # Must be dict at this point
        if not isinstance(data, dict):
            return None
        
        # Extract date
        result_date = str(
            data.get("date") or 
            data.get("day") or 
            data.get("when") or 
            date.today()
        )
        
        # Extract items
        if "items" in data and isinstance(data["items"], list):
            items = self._normalize_items(data["items"])
        else:
            # Check legacy keys
            for key in ("codes", "selection", "entries"):
                if key in data and data[key]:
                    items = parse_selection_to_items(data[key])
                    break
            else:
                items = []
        
        return {
            "date": result_date,
            "items": items
        }
    
    def _normalize_items(self, items: List[Any]) -> List[Dict[str, Any]]:
        """
        Normalize a list of items (codes and time markers).
        
        Args:
            items: List of various item formats
        
        Returns:
            List of normalized item dicts
        """
        result = []
        
        for item in items:
            # Already a valid code dict
            if isinstance(item, dict) and "code" in item:
                code = str(item["code"]).upper()
                mult = float(item.get("mult", 1.0))
                result.append({"code": code, "mult": mult})
                continue
            
            # Already a valid time dict
            if isinstance(item, dict) and "time" in item:
                time_str = str(item["time"]).strip()
                if time_str:
                    result.append({"time": time_str})
                continue
            
            # String or list: parse it
            if isinstance(item, (str, list)):
                parsed = parse_selection_to_items(item)
                result.extend(parsed)
                continue
        
        return result
    
    def get_items(self) -> List[Dict[str, Any]]:
        """
        Get the items list from pending data.
        
        Returns:
            List of items, or empty list if no pending data
        """
        pending = self.load()
        if pending is None:
            return []
        return pending.get("items", [])
    
    def get_date(self) -> Optional[str]:
        """
        Get the date from pending data.
        
        Returns:
            Date string (YYYY-MM-DD) or None if no pending data
        """
        pending = self.load()
        if pending is None:
            return None
        return pending.get("date")
    
    def add_items(self, new_items: List[Dict[str, Any]]) -> None:
        """
        Add items to the pending list.
        
        Args:
            new_items: List of items to add (codes and/or time markers)
        """
        pending = self.load()
        if pending is None:
            pending = {
                "date": str(date.today()),
                "items": []
            }
        
        pending["items"].extend(new_items)
        self.save(pending)
    
    def remove_items(self, indices: List[int]) -> None:
        """
        Remove items by index (0-based).
        
        Args:
            indices: List of 0-based indices to remove
        """
        pending = self.load()
        if pending is None:
            return
        
        items = pending.get("items", [])
        
        # Remove in reverse order to maintain indices
        for idx in sorted(indices, reverse=True):
            if 0 <= idx < len(items):
                del items[idx]
        
        pending["items"] = items
        self.save(pending)
    
    def set_date(self, new_date: str) -> None:
        """
        Change the date of pending data.
        
        Args:
            new_date: New date string (YYYY-MM-DD)
        """
        pending = self.load()
        if pending is None:
            pending = {
                "date": new_date,
                "items": []
            }
        else:
            pending["date"] = new_date
        
        self.save(pending)
    
    def replace_items(self, new_items: List[Dict[str, Any]]) -> None:
        """
        Replace all items with a new list.
        
        Args:
            new_items: New items list
        """
        pending = self.load()
        if pending is None:
            pending = {
                "date": str(date.today()),
                "items": new_items
            }
        else:
            pending["items"] = new_items
        
        self.save(pending)


# Convenience functions for backward compatibility
def load_pending(filepath: Path) -> Optional[Dict[str, Any]]:
    """Load pending file (backward compatible)."""
    manager = PendingManager(filepath)
    return manager.load()


def save_pending(pending: Dict[str, Any], filepath: Path) -> None:
    """Save pending file (backward compatible)."""
    manager = PendingManager(filepath)
    manager.save(pending)


def clear_pending(filepath: Path) -> None:
    """Clear pending file (backward compatible)."""
    manager = PendingManager(filepath)
    manager.clear()