"""
Base command classes and registry.
"""
from abc import ABC, abstractmethod
from typing import Dict, Type, Optional, List
from pathlib import Path

from meal_planner.data import MasterLoader, LogManager, PendingManager


class CommandContext:
    """
    Shared context for all commands.
    
    Provides access to data managers and configuration.
    """
    
    def __init__(self, master_file: Path, log_file: Path, pending_file: Path):
        """
        Initialize command context.
        
        Args:
            master_file: Path to master CSV
            log_file: Path to log CSV
            pending_file: Path to pending JSON
        """
        self.master = MasterLoader(master_file)
        self.log = LogManager(log_file)
        self.pending_mgr = PendingManager(pending_file)
        
        # Session-only stash for undo/redo operations
        self.pending_stack: List = []
        self.editing_date: Optional[str] = None
    
    def reload_master(self):
        """Reload master file from disk."""
        self.master.reload()
    
    def reload_log(self):
        """Reload log file from disk."""
        self.log.reload()


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