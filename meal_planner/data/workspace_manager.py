# meal_planner/data/workspace_manager.py
"""
Workspace manager for planning workspace persistence.

Handles auto-save/load of meal planning workspace to JSON.
"""
import json
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime


class WorkspaceManager:
    """
    Manages the planning workspace JSON file.
    
    Provides auto-save/load functionality for session continuity.
    """
    
    def __init__(self, filepath: Path):
        """
        Initialize workspace manager.
        
        Args:
            filepath: Path to workspace JSON file
        """
        self.filepath = filepath
    
    def load(self) -> Dict[str, Any]:
        """
        Load workspace from disk.
        
        Returns:
            Workspace dictionary, or empty workspace if file doesn't exist
            
        """
        if not self.filepath.exists():
            return self._create_empty_workspace()
        
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Validate structure
            if not isinstance(data, dict):
                return self._create_empty_workspace()
            
            # Ensure required fields
            if "last_modified" not in data:
                data["last_modified"] = datetime.now().isoformat()
            
            if "meals" not in data or not isinstance(data["meals"], dict):
                data["meals"] = {}

            # Initialize command_history if missing (backward compatibility)
            if "command_history" not in data:
                data["command_history"] = {
                    "threshold": {},
                    "analyze": {},
                    "recommend": {}
                }
            else:
                # Ensure all three command types exist
                for cmd in ["threshold", "analyze", "recommend"]:
                    if cmd not in data["command_history"]:
                        data["command_history"][cmd] = {}
        
            # Initialize inventory if missing (NEW for Phase 1)
            if "inventory" not in data:
                data["inventory"] = {
                    "leftovers": {},
                    "batch": {},
                    "rotating": {}
                }
            else:
                # Ensure all three inventory types exist
                for inv_type in ["leftovers", "batch", "rotating"]:
                    if inv_type not in data["inventory"]:
                        data["inventory"][inv_type] = {}

            if "locks" not in data:
                data["locks"] = {
                    "include": {},
                    "exclude": []
                }
            else:
                # Ensure both lock types exist
                if "include" not in data["locks"]:
                    data["locks"]["include"] = {}
                if "exclude" not in data["locks"]:
                    data["locks"]["exclude"] = []

            return data
            
        except (json.JSONDecodeError, Exception):
            # Corrupted file - return empty workspace
            return self._create_empty_workspace()
    
    def save(self, workspace: Dict[str, Any]) -> None:
        """
        Save workspace to disk.
        
        Args:
            workspace: Workspace dictionary
        """
        # Update timestamp
        workspace["last_modified"] = datetime.now().isoformat()
        
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(workspace, f, indent=2, ensure_ascii=False)
        except Exception as e:
            # Log error but don't crash - workspace is session-only
            print(f"Warning: Failed to save workspace: {e}")
    
    def clear(self) -> None:
        """Delete the workspace file."""
        if self.filepath.exists():
            try:
                self.filepath.unlink()
            except Exception as e:
                print(f"Warning: Failed to delete workspace: {e}")
    
    def _create_empty_workspace(self) -> Dict[str, Any]:
        """Create empty workspace structure."""
        return {
            "last_modified": datetime.now().isoformat(),
            "meals": {}
        }
    
    def convert_from_planning_workspace(self, planning_ws: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert old planning_workspace format to new workspace format.
        
        Args:
            planning_ws: Old format workspace from context
        
        Returns:
            New format workspace
        """
        # Load existing workspace to preserve command_history and inventory
        workspace = self.load()
        
        # Clear meals but keep command_history and inventory
        workspace["meals"] = {}
        
        # Convert candidates list to meals dict
        for candidate in planning_ws.get("candidates", []):
            meal_id = candidate.get("id")
            if not meal_id:
                continue
            
            # Map candidate to meal structure
            workspace["meals"][meal_id] = {
                "description": candidate.get("description"),
                "analyzed_as": candidate.get("analyzed_as"),
                "created": candidate.get("created"),
                "meal_name": candidate.get("meal_name"),
                "type": candidate.get("type"),
                "items": candidate.get("items", []),
                "totals": candidate.get("totals", {}),
                "source_date": candidate.get("source_date"),
                "source_time": candidate.get("source_time"),
                "parent_id": candidate.get("parent_id"),
                "ancestor_id": candidate.get("ancestor_id"),
                "modification_log": candidate.get("modification_log", []),
                "meets_constraints": candidate.get("meets_constraints", True),
                "history": candidate.get("history", []),  # NEW
                "immutable": candidate.get("immutable", False)  # NEW
            }

        
        return workspace
    
    def convert_to_planning_workspace(self, workspace: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert new workspace format back to planning_workspace format.
        
        Args:
            workspace: New format workspace
        
        Returns:
            Planning workspace format for context
        """
        planning_ws = {
            "candidates": [],
            "next_numeric_id": 1,
            "next_invented_id": 1
        }
        
        # Convert meals dict to candidates list
        for meal_id, meal_data in workspace.get("meals", {}).items():
            candidate = {
                "id": meal_id,
                "description": meal_data.get("description"),
                "analyzed_as": meal_data.get("analyzed_as"),
                "created": meal_data.get("created"),
                "meal_name": meal_data.get("meal_name"),
                "type": meal_data.get("type"),
                "items": meal_data.get("items", []),
                "totals": meal_data.get("totals", {}),
                "source_date": meal_data.get("source_date"),
                "source_time": meal_data.get("source_time"),
                "parent_id": meal_data.get("parent_id"),
                "ancestor_id": meal_data.get("ancestor_id"),
                "modification_log": meal_data.get("modification_log", []),
                "meets_constraints": meal_data.get("meets_constraints", True),
                "history": meal_data.get("history", []),
                "immutable": meal_data.get("immutable", False)
            }
            planning_ws["candidates"].append(candidate)
        
        # Calculate next IDs
        numeric_ids = []
        invented_ids = []
        
        for meal_id in workspace.get("meals", {}).keys():
            if meal_id.startswith("N"):
                # Extract number from N1, N2, etc.
                try:
                    base = meal_id.lstrip("N").rstrip("abcdefghijklmnopqrstuvwxyz")
                    if base:
                        invented_ids.append(int(base))
                except ValueError:
                    pass
            else:
                # Extract number from 1, 2, 123a, etc.
                try:
                    base = meal_id.rstrip("abcdefghijklmnopqrstuvwxyz")
                    if base:
                        numeric_ids.append(int(base))
                except ValueError:
                    pass
        
        if numeric_ids:
            planning_ws["next_numeric_id"] = max(numeric_ids) + 1
        if invented_ids:
            planning_ws["next_invented_id"] = max(invented_ids) + 1
        
        return planning_ws
    
    def _create_empty_workspace(self) -> Dict[str, Any]:
        """Create empty workspace structure."""
        return {
            "last_modified": datetime.now().isoformat(),
            "meals": {},
            "command_history": {
                "threshold": {},
                "analyze": {},
                "recommend": {}
            },
            "inventory": {
                "leftovers": {},
                "batch": {},
                "rotating": {}
            },
            "locks": {
                "include": {},
                "exclude": []
            }

        }  
    
    # Method to record command in history
    def record_command_history(self, workspace: Dict[str, Any], 
                            command: str, params: str, meal: str,
                            max_size: int = 10) -> None:
        """
        Record a command execution in history.
        
        Args:
            workspace: Workspace dictionary
            command: Command name ("threshold", "analyze", or "recommend")
            params: Parameter string (everything after command name)
            meal: Meal name for categorization (or "default" for no-meal commands)
            max_size: Maximum entries to keep per meal
        """
        if "command_history" not in workspace:
            workspace["command_history"] = {
                "threshold": {},
                "analyze": {},
                "recommend": {}
            }
        
        if command not in workspace["command_history"]:
            workspace["command_history"][command] = {}
        
        meal_history = workspace["command_history"][command].get(meal, [])
        
        # Remove duplicate if exists (move to front)
        if params in meal_history:
            meal_history.remove(params)
        
        # Add to front
        meal_history.insert(0, params)
        
        # Trim to max size
        if len(meal_history) > max_size:
            meal_history = meal_history[:max_size]
        
        # Save back
        workspace["command_history"][command][meal] = meal_history

    # Method to get command history
    def get_command_history(self, workspace: Dict[str, Any],
                        command: str, meal: str,
                        limit: Optional[int] = None) -> List[str]:
        """
        Get command history for a specific command/meal.
        
        Args:
            workspace: Workspace dictionary
            command: Command name ("threshold", "analyze", or "recommend")
            meal: Meal name (or "default")
            limit: Optional limit on number of entries to return
        
        Returns:
            List of parameter strings, most recent first
        """
        if "command_history" not in workspace:
            return []
        
        if command not in workspace["command_history"]:
            return []
        
        meal_history = workspace["command_history"][command].get(meal, [])
        
        if limit and limit < len(meal_history):
            return meal_history[:limit]
        
        return meal_history.copy()

    def append_plan_history(self, workspace: Dict[str, Any], plan_id: str, 
                        command: str, note: str) -> None:
        """
        Append a history entry to a plan's history.
        
        Args:
            workspace: Workspace dictionary (new format)
            plan_id: Plan ID
            command: Command string
            note: Description of what happened
        """
        if "meals" not in workspace or plan_id not in workspace["meals"]:
            return
        
        meal = workspace["meals"][plan_id]
        
        if "history" not in meal:
            meal["history"] = []
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        meal["history"].append({
            'timestamp': timestamp,
            'command': command,
            'note': note
        })

    def get_plan_history(self, workspace: Dict[str, Any], plan_id: str) -> List[Dict[str, str]]:
        """
        Get history for a plan.
        
        Args:
            workspace: Workspace dictionary (new format)
            plan_id: Plan ID
        
        Returns:
            List of history entries
        """
        if "meals" not in workspace or plan_id not in workspace["meals"]:
            return []
        
        meal = workspace["meals"][plan_id]
        return meal.get("history", [])