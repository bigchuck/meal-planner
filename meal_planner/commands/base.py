"""
Base command classes and registry.
"""
from abc import ABC, abstractmethod
from typing import Dict, Type, Optional, List, Set
from pathlib import Path

from meal_planner.data import MasterLoader, LogManager, PendingManager, ThresholdsManager
from datetime import datetime


class CommandContext:
    """
    Shared context for all commands.
    
    Provides access to data managers and configuration.
    """
    
    def __init__(self, master_file: Path, log_file: Path, pending_file: Path,
                 nutrients_file: Path = None, recipes_file: Path = None,
                 aliases_file: Path = None, thresholds_file: Path = None,
                 user_prefs_file: Path = None, workspace_file: Path = None,
                 staging_buffer_file: Path = None):
        """
        Initialize command context.
        
        Args:
            master_file: Path to master CSV
            log_file: Path to log CSV
            pending_file: Path to pending JSON
            nutrients_file: Path to nutrients CSV (optional)
            recipes_file: Path to recipes CSV (optional)
            aliases_file: Path to aliases JSON (optional)
            thresholds_file: Path to thresholds JSON (optional)
        """
        from meal_planner.data.nutrients_manager import NutrientsManager
        from meal_planner.data.recipes_manager import RecipesManager
        from meal_planner.data.alias_manager import AliasManager
        from meal_planner.data.workspace_manager import WorkspaceManager
        from meal_planner.data.user_preferences_manager import UserPreferencesManager
        from meal_planner.data.staging_buffer_manager import StagingBufferManager
        
        self.master = MasterLoader(master_file, nutrients_file, recipes_file)
        self.log = LogManager(log_file)
        self.pending_mgr = PendingManager(pending_file)
        self.nutrients = NutrientsManager(nutrients_file) if nutrients_file else None
        self.recipes = RecipesManager(recipes_file) if recipes_file else None
        self.aliases = AliasManager(aliases_file) if aliases_file else None

        self.thresholds = None
        self.thresholds_error = None
        if thresholds_file:
            self.thresholds = ThresholdsManager(thresholds_file)
            if not self.thresholds.load():
                # Store error message for commands to display
                self.thresholds_error = self.thresholds.get_error_message()
                # Set thresholds to None to disable dependent features
                self.thresholds = None

        self.user_prefs = None
        self.user_prefs_error = None
        if user_prefs_file:
            self.user_prefs = UserPreferencesManager(user_prefs_file)
            if not self.user_prefs.load():
                self.user_prefs_error = self.user_prefs.get_error_message()
                # Don't fail - user prefs are optional

        # Session-only stash for undo/redo operations
        # Each entry: {"pending": {...}, "timestamp": datetime, "auto": bool}
        self.pending_stack: List[Dict] = []
        self.editing_date: Optional[str] = None

        # Track provenance of current pending to enable smart confirmations
        # Possible values: "empty", "normal", "stash_pop", "editing"
        self.pending_source: str = self._determine_initial_pending_source()

        # Usage tracking
        from config import TRACK_USAGE, USAGE_STATS_FILE
        from meal_planner.utils import UsageTracker
        self.usage = UsageTracker(USAGE_STATS_FILE, enabled=TRACK_USAGE)

       # Session state for backups
        self.session_start = datetime.now()
        self.backed_up_files: Set[Path] = set()  # Track which files backed up this session
    
        if workspace_file:
            self.workspace_mgr = WorkspaceManager(workspace_file)
            # Load workspace and convert to planning_workspace format
            workspace_data = self.workspace_mgr.load()
            self.planning_workspace = self.workspace_mgr.convert_to_planning_workspace(workspace_data)
        else:
            self.workspace_mgr = None
            self.planning_workspace = {
                "candidates": [],
                "next_numeric_id": 1,
                "next_invented_id": 1
            }

        self.staging_buffer = None
        if staging_buffer_file:
            self.staging_buffer = StagingBufferManager(staging_buffer_file)

    def _determine_initial_pending_source(self) -> str:
        """
        Determine initial pending source state on startup.
        
        Any existing pending from previous session is treated as "normal"
        user work and should be protected.
        
        Returns:
            "empty" if no pending exists, "normal" if pending has items
        """
        try:
            pending = self.pending_mgr.load()
            if pending and pending.get("items"):
                return "normal"
            else:
                return "empty"
        except Exception:
            return "empty"

    def reload_master(self):
        """Reload master file from disk."""
        self.master.reload()
    
    def reload_log(self):
        """Reload log file from disk."""
        self.log.reload()

    def save_workspace(self):
        """Save planning workspace to disk (auto-save)."""
        if self.workspace_mgr:
            workspace_data = self.workspace_mgr.convert_from_planning_workspace(self.planning_workspace)
            self.workspace_mgr.save(workspace_data)

class CommandHistoryMixin:
    """
    Mixin for commands that support command history (threshold, analyze, recommend).
    
    Provides --history and --use flag support with meal-specific filtering.
    """
    
    def _extract_meal_from_params(self, params: str) -> str:
        """
        Extract meal name from parameter string containing --meal flag.
        
        Args:
            params: Parameter string (e.g., "--template breakfast --meal breakfast")
        
        Returns:
            Meal name if found, otherwise "default"
        """
        import shlex
        
        try:
            parts = shlex.split(params)
        except:
            parts = params.split()
        
        # Look for --meal flag
        for i, part in enumerate(parts):
            if part == "--meal" and i + 1 < len(parts):
                return parts[i + 1]
        
        return "default"
    
    def _record_command_history(self, command_name: str, params: str) -> None:
        """
        Record successful command execution in workspace history.
        
        Args:
            command_name: "threshold", "analyze", or "recommend"
            params: Full parameter string
        """
        if not self.ctx.workspace_mgr:
            return
        
        # Determine meal bucket
        meal = self._extract_meal_from_params(params)
        
        # Get max history size from user preferences
        max_size = 10  # default
        if self.ctx.user_prefs:
            max_size = self.ctx.user_prefs.get_command_history_size()
        
        # Record in workspace
        workspace_data = self.ctx.workspace_mgr.load()
        self.ctx.workspace_mgr.record_command_history(
            workspace_data, command_name, params, meal, max_size
        )
        self.ctx.workspace_mgr.save(workspace_data)
    
    def _display_command_history(self, command_name: str, meal: str, limit: int) -> bool:
        """
        Display command history for a specific command/meal.
        
        Args:
            command_name: "threshold", "analyze", or "recommend"
            meal: Meal name to filter by
            limit: Maximum entries to display
        
        Returns:
            True if history was displayed, False if none available
        """
        if not self.ctx.workspace_mgr:
            print("\nCommand history unavailable (no workspace)\n")
            return False
        
        workspace_data = self.ctx.workspace_mgr.load()
        history = self.ctx.workspace_mgr.get_command_history(
            workspace_data, command_name, meal, limit
        )
        
        if not history:
            print(f"\nNo {command_name} command history for meal '{meal}'\n")
            return False
        
        print(f"\nRecent {command_name} commands for meal '{meal}':")
        for i, params in enumerate(history, 1):
            print(f"  {i}: {params}")
        print()
        
        return True
    
    def _get_params_from_history(self, command_name: str, meal: str, index: int) -> Optional[str]:
        """
        Get parameter string from history at specified index.
        
        Args:
            command_name: "threshold", "analyze", or "recommend"
            meal: Meal name to filter by
            index: 1-based index into history
        
        Returns:
            Parameter string if found, None otherwise
        """
        if not self.ctx.workspace_mgr:
            return None
        
        workspace_data = self.ctx.workspace_mgr.load()
        history = self.ctx.workspace_mgr.get_command_history(
            workspace_data, command_name, meal
        )
        
        if not history or index < 1 or index > len(history):
            return None
        
        return history[index - 1]

class Command(ABC):
    """
    Base class for all commands.
    
    Each command should override:
    - name: Command name(s) that trigger it
    - help_text: Short description
    - execute(): Command logic
    """
    
    # Command name(s) - can be string or tuple of strings
    name: str | tuple = ""
    
    # Help text shown in help command
    help_text: str = ""
    
    def __init__(self, context: CommandContext):
        """
        Initialize command with context.
        
        Args:
            context: Shared command context
        """
        self.ctx = context
    
    @abstractmethod
    def execute(self, args: str) -> None:
        """
        Execute the command.
        
        Args:
            args: Command arguments (everything after the command name)
        """
        pass
    
    def matches(self, cmd: str) -> bool:
        """
        Check if command matches this handler.
        
        Args:
            cmd: Command string to check
        
        Returns:
            True if this command handles it
        """
        if isinstance(self.name, str):
            return cmd.lower() == self.name.lower()
        else:
            return cmd.lower() in [n.lower() for n in self.name]

    def _check_thresholds(self, feature_name: str) -> bool:
        """
        Check if thresholds are available for a feature.
        
        Args:
            feature_name: Name of feature requiring thresholds
        
        Returns:
            True if available, False if disabled (prints error message)
        """
        if self.ctx.thresholds is None:
            if self.ctx.thresholds_error:
                print(f"\n{feature_name} unavailable: {self.ctx.thresholds_error}\n")
            else:
                print(f"\n{feature_name} unavailable: thresholds file not configured\n")
            return False
        return True


class CommandRegistry:
    """
    Registry for all available commands.
    
    Commands register themselves and can be looked up by name.
    """
    
    def __init__(self):
        """Initialize empty registry."""
        self._commands: Dict[str, Type[Command]] = {}
    
    def register(self, command_class: Type[Command]) -> None:
        """
        Register a command class.
        
        Args:
            command_class: Command class to register
        """
        if isinstance(command_class.name, str):
            names = [command_class.name]
        else:
            names = list(command_class.name)
        
        for name in names:
            self._commands[name.lower()] = command_class
    
    def get(self, cmd: str) -> Optional[Type[Command]]:
        """
        Get command class for a command name.
        
        Args:
            cmd: Command name
        
        Returns:
            Command class or None if not found
        """
        return self._commands.get(cmd.lower())
    
    def list_commands(self) -> List[str]:
        """
        Get list of all registered command names.
        
        Returns:
            Sorted list of command names
        """
        return sorted(set(self._commands.keys()))
    
    def get_all_commands(self) -> List[Type[Command]]:
        """
        Get list of all unique command classes.
        
        Returns:
            List of command classes
        """
        seen = set()
        commands = []
        for cmd_class in self._commands.values():
            if cmd_class not in seen:
                seen.add(cmd_class)
                commands.append(cmd_class)
        return commands


# Global registry
_registry = CommandRegistry()


def register_command(command_class: Type[Command]) -> Type[Command]:
    """
    Decorator to register a command.
    
    Usage:
        @register_command
        class MyCommand(Command):
            name = "mycommand"
            ...
    """
    _registry.register(command_class)
    return command_class


def get_registry() -> CommandRegistry:
    """Get the global command registry."""
    return _registry
