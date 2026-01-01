"""
Command classes for the meal planner REPL.
"""
from .base import Command, CommandContext, CommandHistoryMixin, CommandRegistry, register_command, get_registry

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
from . import glucose_command
from . import data_management
from . import stats_command
from . import explain_command
from . import order_command
from . import plan_command
from . import threshold_command
from . import analyze_command
from . import recommend_command
from . import stage_command
from . import mode_command

__all__ = [
    'Command',
    'CommandContext',
    'CommandRegistry',
    'CommandHistoryMixin',
    'register_command',
    'get_registry',
]