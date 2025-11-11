"""
Command classes for the meal planner REPL.
"""
from .base import Command, CommandContext, CommandRegistry, register_command, get_registry

# Import all command modules to trigger registration
from . import basic_commands
from . import search_command
from . import pending_commands
from . import report_command
from . import whatif_command
from . import item_management
from . import log_editing
from . import chart_command
from . import recipe_command
from . import nutrients_command

__all__ = [
    'Command',
    'CommandContext',
    'CommandRegistry',
    'register_command',
    'get_registry',
]