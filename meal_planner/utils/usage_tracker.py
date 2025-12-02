"""
Usage statistics tracker for command usage.
"""
import json
from pathlib import Path
from datetime import date, datetime
from typing import Dict, Any


class UsageTracker:
    """
    Tracks command usage by day, week, and all-time.
    
    Stores statistics in JSON format for analysis.
    """
    
    def __init__(self, filepath: Path, enabled: bool = True):
        """
        Initialize usage tracker.
        
        Args:
            filepath: Path to usage stats JSON file
            enabled: Whether tracking is enabled
        """
        self.filepath = filepath
        self.enabled = enabled
        self._stats = None
    
    def track(self, command: str) -> None:
        """
        Record a command usage.
        
        Args:
            command: Command name that was executed
        """
        if not self.enabled:
            return
        
        # Load current stats
        stats = self.load()
        
        # Get today's date and week
        today = str(date.today())
        week = datetime.now().strftime("%Y-W%U")
        
        # Update daily
        if today not in stats["daily"]:
            stats["daily"][today] = {}
        stats["daily"][today][command] = stats["daily"][today].get(command, 0) + 1
        
        # Update weekly
        if week not in stats["weekly"]:
            stats["weekly"][week] = {}
        stats["weekly"][week][command] = stats["weekly"][week].get(command, 0) + 1
        
        # Update all-time
        stats["all_time"][command] = stats["all_time"].get(command, 0) + 1
        
        # Update first/last seen
        if command not in stats["first_seen"]:
            stats["first_seen"][command] = today
        stats["last_seen"][command] = today
        
        # Save
        self.save(stats)
    
    def load(self) -> Dict[str, Any]:
        """
        Load stats from disk.
        
        Returns:
            Stats dictionary
        """
        if self._stats is not None:
            return self._stats
        
        if not self.filepath.exists():
            self._stats = {
                "daily": {},
                "weekly": {},
                "all_time": {},
                "first_seen": {},
                "last_seen": {}
            }
            return self._stats
        
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                self._stats = json.load(f)
        except Exception:
            self._stats = {
                "daily": {},
                "weekly": {},
                "all_time": {},
                "first_seen": {},
                "last_seen": {}
            }
        
        return self._stats
    
    def save(self, stats: Dict[str, Any]) -> None:
        """
        Save stats to disk.
        
        Args:
            stats: Stats dictionary to save
        """
        if not self.enabled:
            return
        
        self._stats = stats
        
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(stats, f, indent=2, ensure_ascii=False)
        except Exception as e:
            # Silent fail - don't break app if stats can't be saved
            pass
    
    def get_daily_stats(self, target_date: str = None) -> Dict[str, int]:
        """
        Get stats for a specific day.
        
        Args:
            target_date: Date string (YYYY-MM-DD), defaults to today
        
        Returns:
            Dictionary of command: count
        """
        if target_date is None:
            target_date = str(date.today())
        
        stats = self.load()
        return stats["daily"].get(target_date, {})
    
    def get_weekly_stats(self, target_week: str = None) -> Dict[str, int]:
        """
        Get stats for a specific week.
        
        Args:
            target_week: Week string (YYYY-WNN), defaults to current week
        
        Returns:
            Dictionary of command: count
        """
        if target_week is None:
            target_week = datetime.now().strftime("%Y-W%U")
        
        stats = self.load()
        return stats["weekly"].get(target_week, {})
    
    def get_all_time_stats(self) -> Dict[str, int]:
        """
        Get all-time stats.
        
        Returns:
            Dictionary of command: count
        """
        stats = self.load()
        return stats["all_time"]
    
    def get_last_seen(self, command: str) -> str:
        """
        Get last seen date for a command.
        
        Args:
            command: Command name
        
        Returns:
            Date string or "never"
        """
        stats = self.load()
        return stats["last_seen"].get(command, "never")