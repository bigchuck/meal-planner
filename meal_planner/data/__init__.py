"""
Data access layer for meal planner.

Provides managers for master database, daily log, and pending entries.
"""
from .master_loader import MasterLoader, load_master, lookup_code_row
from .log_manager import LogManager, ensure_log, save_log
from .pending_manager import PendingManager, load_pending, save_pending, clear_pending
from .alias_manager import AliasManager
from .thresholds_manager import ThresholdsManager
from .staging_buffer_manager import StagingBufferManager

__all__ = [
    # Classes
    'MasterLoader',
    'LogManager',
    'PendingManager',
    'AliasManager',
    'ThresholdsManager',
    'StagingBufferManager',
    # Backward-compatible functions
    'load_master',
    'lookup_code_row',
    'ensure_log',
    'save_log',
    'load_pending',
    'save_pending',
    'clear_pending',
]