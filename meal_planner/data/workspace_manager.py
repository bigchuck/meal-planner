# meal_planner/data/workspace_manager.py
"""
Workspace manager for planning workspace persistence.

Handles auto-save/load of meal planning workspace to JSON.
Phase 1: Splits reco data into separate reco_workspace.json file.
"""
import json
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime


class WorkspaceManager:
    """
    Manages the planning workspace JSON files.
    
    Provides auto-save/load functionality for session continuity.
    Reco data is stored separately in reco_workspace.json.
    """
    
    def __init__(self, filepath: Path):
        """
        Initialize workspace manager.
        
        Args:
            filepath: Path to workspace JSON file
        """
        self.filepath = filepath
        # Reco workspace is same directory, base name + _reco suffix
        self.reco_filepath = filepath.parent / f"{filepath.stem}_reco.json"
    
    def load(self) -> Dict[str, Any]:
        """
        Load workspace from disk (WITHOUT reco data).
        
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
        
            # Initialize inventory if missing
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

            # MIGRATION: If old reco data exists in main workspace, migrate it
            if "generated_candidates" in data or "generation_state" in data:
                self._migrate_reco_data(data)

            return data
            
        except (json.JSONDecodeError, Exception):
            # Corrupted file - return empty workspace
            return self._create_empty_workspace()
    
    def save(self, workspace: Dict[str, Any]) -> None:
        """
        Save workspace to disk (WITHOUT reco data).
        
        Reco data should never be in the workspace dict passed here.
        If it is, it's silently dropped.
        
        Args:
            workspace: Workspace dictionary
        """
        # Safety: Remove reco data if present (shouldn't be, but be defensive)
        workspace_clean = {k: v for k, v in workspace.items() 
                          if k not in ("generated_candidates", "generation_state")}
        
        # Update timestamp
        workspace_clean["last_modified"] = datetime.now().isoformat()
        
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(workspace_clean, f, indent=2, ensure_ascii=False)
        except Exception as e:
            # Log error but don't crash - workspace is session-only
            print(f"Warning: Failed to save workspace: {e}")
    
    def load_reco(self) -> Dict[str, Any]:
        """
        Load reco workspace from disk.
        
        Returns:
            Reco workspace dictionary, or empty reco workspace if file doesn't exist
        """
        if not self.reco_filepath.exists():
            return self._create_empty_reco_workspace()
        
        try:
            with open(self.reco_filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Validate structure
            if not isinstance(data, dict):
                return self._create_empty_reco_workspace()
            
            # Ensure required fields
            if "last_modified" not in data:
                data["last_modified"] = datetime.now().isoformat()
            
            # Ensure generated_candidates structure
            if "generated_candidates" not in data:
                data["generated_candidates"] = {}
            
            # Ensure generation_state structure  
            if "generation_state" not in data:
                data["generation_state"] = {}
            
            return data
            
        except (json.JSONDecodeError, Exception):
            # Corrupted file - return empty reco workspace
            return self._create_empty_reco_workspace()
    
    def save_reco(self, reco_workspace: Dict[str, Any]) -> None:
        """
        Save reco workspace to disk.
        
        Args:
            reco_workspace: Reco workspace dictionary
        """
        # Update timestamp
        reco_workspace["last_modified"] = datetime.now().isoformat()
        
        try:
            with open(self.reco_filepath, 'w', encoding='utf-8') as f:
                json.dump(reco_workspace, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Failed to save reco workspace: {e}")
    
    def clear(self) -> None:
        """Delete the workspace file."""
        if self.filepath.exists():
            try:
                self.filepath.unlink()
            except Exception as e:
                print(f"Warning: Failed to delete workspace: {e}")
    
    def clear_reco(self) -> None:
        """Delete the reco workspace file."""
        if self.reco_filepath.exists():
            try:
                self.reco_filepath.unlink()
            except Exception as e:
                print(f"Warning: Failed to delete reco workspace: {e}")
    
    def _create_empty_workspace(self) -> Dict[str, Any]:
        """Create empty workspace structure (WITHOUT reco data)."""
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
    
    def _create_empty_reco_workspace(self) -> Dict[str, Any]:
        """Create empty reco workspace structure."""
        return {
            "last_modified": datetime.now().isoformat(),
            "generated_candidates": {},
            "generation_state": {}
        }
    
    def _migrate_reco_data(self, workspace: Dict[str, Any]) -> None:
        """
        Migrate reco data from main workspace to separate reco workspace.
        
        This is a one-time migration for existing workspaces.
        
        Args:
            workspace: Main workspace dict (will be modified to remove reco data)
        """
        print("\n[MIGRATION] Moving reco data to separate file...")
        
        # Extract reco data
        reco_workspace = self._create_empty_reco_workspace()
        
        if "generated_candidates" in workspace:
            reco_workspace["generated_candidates"] = workspace.pop("generated_candidates")
        
        if "generation_state" in workspace:
            reco_workspace["generation_state"] = workspace.pop("generation_state")
        
        # Save both files
        self.save(workspace)  # Save cleaned main workspace
        self.save_reco(reco_workspace)  # Save new reco workspace
        
        print(f"[MIGRATION] Reco data moved to: {self.reco_filepath}")
        print()
    
    # ... (rest of the methods remain unchanged)
    
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
                "items": candidate.get("meal", {}).get("items", []),
                "totals": candidate.get("totals", {}),
                "source_date": candidate.get("source_date"),
                "source_time": candidate.get("source_time"),
                "parent_id": candidate.get("parent_id"),
                "ancestor_id": candidate.get("ancestor_id"),
                "modification_log": candidate.get("modification_log", []),
                "meets_constraints": candidate.get("meets_constraints", True),
                "history": candidate.get("history", []),
                "immutable": candidate.get("immutable", False)
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
    
        
    # =========================================================================
    # Generated Candidates Management - NOW USES RECO WORKSPACE
    # =========================================================================

    def get_generated_candidates(self) -> Optional[Dict[str, Any]]:
        """
        Get generated candidates section from reco workspace.
        
        Returns:
            Dict with meal_type, generated_at, candidates list
            None if no generated candidates exist
        """
        reco_workspace = self.load_reco()
        gen_cands = reco_workspace.get("generated_candidates")
        return gen_cands if gen_cands else None

    def set_generated_candidates(
            self,
            meal_type: str,
            raw_candidates: List[Dict[str, Any]],
            cursor: int = 0,
            append: bool = False
        ) -> None:
        """
        Set or append generated candidates in reco workspace.
        Assigns G-IDs and creates unified structure with subordinate dicts.
        
        Args:
            meal_type: Meal category (breakfast, lunch, etc.)
            raw_candidates: List of raw generated candidate dicts (without IDs)
            cursor: Starting ID number (0 = start at G1, 5 = start at G6)
            append: If True, append to existing candidates; if False, replace
        """
        reco_workspace = self.load_reco()
        
        # Get existing candidates if appending
        existing_candidates = []
        if append and "generated_candidates" in reco_workspace:
            existing_candidates = reco_workspace["generated_candidates"].get("candidates", [])
        
        # Transform to unified structure
        unified_candidates = []
        for i, raw_cand in enumerate(raw_candidates, 1):
            # Extract meal data
            meal_data = {
                "items": raw_cand.get("items", []),
                "totals": raw_cand.get("totals", {}),
                "meal_type": raw_cand.get("meal_type", meal_type),
                "source_date": raw_cand.get("source_date"),
                "description": raw_cand.get("description", "")
            }
            
            # Extract generation metadata
            gen_metadata = {
                "method": raw_cand.get("generation_method", "unknown"),
                "timestamp": datetime.now().isoformat()
            }
            
            # Add template info if present
            if "template_info" in raw_cand:
                gen_metadata["template_info"] = raw_cand["template_info"]
            
            # Create unified candidate with cursor-based ID
            unified = {
                "id": f"G{cursor + i}",  # Use cursor for ID offset
                "meal": meal_data,
                "generation_metadata": gen_metadata,
                "filter_result": None,  # Until filtered
                "score_result": None    # Until scored
            }
            
            unified_candidates.append(unified)
        
        # Combine with existing if appending
        all_candidates = existing_candidates + unified_candidates if append else unified_candidates
        
        # Ensure generated_candidates exists
        if "generated_candidates" not in reco_workspace:
            reco_workspace["generated_candidates"] = {}
        
        # Set just the candidates array
        reco_workspace["generated_candidates"]["candidates"] = all_candidates
        reco_workspace["generated_candidates"]["meal_type"] = meal_type
        
        self.save_reco(reco_workspace)

    def clear_generated_candidates(self) -> None:
        """Clear generated candidates from reco workspace."""
        reco_workspace = self.load_reco()
        
        if "generated_candidates" in reco_workspace:
            del reco_workspace["generated_candidates"]
            self.save_reco(reco_workspace)

    def has_generated_candidates(self) -> bool:
        """
        Check if reco workspace has generated candidates.
        
        Returns:
            True if generated candidates exist
        """
        reco_workspace = self.load_reco()
        return "generated_candidates" in reco_workspace

    def get_raw_candidates_count(self) -> int:
        """Get count of all candidates."""
        gen_cands = self.get_generated_candidates()
        if not gen_cands:
            return 0
        return len(gen_cands.get("candidates", []))

    def get_filtered_candidates_count(self) -> int:
        """Get count of filtered (passed) candidates."""
        gen_cands = self.get_generated_candidates()
        if not gen_cands:
            return 0
        candidates = gen_cands.get("candidates", [])
        return sum(1 for c in candidates 
                if c.get("filter_result", {}).get("passed", False))

    def get_scored_candidates_count(self) -> int:
        """Get count of scored candidates."""
        gen_cands = self.get_generated_candidates()
        if not gen_cands:
            return 0
        candidates = gen_cands.get("candidates", [])
        return sum(1 for c in candidates if c.get("score_result") is not None)
    
