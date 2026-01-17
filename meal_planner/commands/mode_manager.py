"""
Mode state manager for REPL command context modes.
"""
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class ModeState:
    """
    Represents active mode state.
    
    Attributes:
        mode_type: Type of mode ("plan", "date", etc.)
        mode_target: Target ID/parameter (workspace ID, date, etc.) - can be None
        prompt_display: String to show in prompt
    """
    mode_type: str
    mode_target: Optional[str]
    prompt_display: str


class ModeManager:
    """
    Manages REPL mode state.
    
    Tracks active mode and provides mode entry/exit/validation.
    """
    
    def __init__(self, ctx):
        """
        Initialize mode manager.
        
        Args:
            ctx: CommandContext instance
        """
        self.ctx = ctx
        self._active_mode: Optional[ModeState] = None
    
    @property
    def active_mode(self) -> Optional[ModeState]:
        """Get current active mode."""
        return self._active_mode
    
    @property
    def is_active(self) -> bool:
        """Check if any mode is active."""
        return self._active_mode is not None
    
    def enter_plan_mode(self, workspace_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Enter plan mode for a workspace or general planning.
        
        Args:
            workspace_id: Optional workspace/candidate ID for meal-specific mode
        
        Returns:
            Tuple of (success, message)
        """
        if workspace_id:
            # Meal-specific mode - validate workspace exists
            ws = self.ctx.planning_workspace
            found = False
            
            for candidate in ws.get('candidates', []):
                if candidate['id'].upper() == workspace_id.upper():
                    found = True
                    workspace_id = candidate['id']  # Use canonical case
                    break
            
            if not found:
                return False, f"Workspace '{workspace_id}' not found. Use 'plan show' to see available workspaces."
            
            # Set mode with workspace target
            self._active_mode = ModeState(
                mode_type="plan",
                mode_target=workspace_id,
                prompt_display=f"plan:{workspace_id}"
            )
            
            return True, f"Entered plan mode for workspace '{workspace_id}'"
        else:
            # General planning mode - no specific workspace
            self._active_mode = ModeState(
                mode_type="plan",
                mode_target=None,
                prompt_display="plan"
            )
            
            return True, "Entered general planning mode"
            
    def exit_mode(self) -> str:
        """
        Exit current mode.
        
        Returns:
            Message describing exit
        """
        if not self._active_mode:
            return "Not in any mode"
        
        mode_display = self._active_mode.prompt_display
        self._active_mode = None
        return f"Exited {mode_display} mode"
    
    def validate_mode(self) -> Tuple[bool, Optional[str]]:
        """
        Validate current mode is still valid.
        
        Checks that mode target still exists (workspace not deleted, etc.)
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self._active_mode:
            return True, None
        
        if self._active_mode.mode_type == "plan":
            # General planning mode (no target) is always valid
            if self._active_mode.mode_target is None:
                return True, None
            
            # Meal-specific mode - check workspace still exists
            ws = self.ctx.planning_workspace
            for candidate in ws.get('candidates', []):
                if candidate['id'].upper() == self._active_mode.mode_target.upper():
                    return True, None
            
            # Workspace was deleted
            return False, f"Workspace '{self._active_mode.mode_target}' no longer exists"
        
        # Add validation for other mode types here
        return True, None
    
    def auto_exit_if_invalid(self) -> Optional[str]:
        """
        Check mode validity and auto-exit if invalid.
        
        Returns:
            Warning message if auto-exited, None otherwise
        """
        is_valid, error = self.validate_mode()
        
        if not is_valid:
            old_mode = self._active_mode.prompt_display
            self._active_mode = None
            return f"Auto-exited {old_mode} mode: {error}"
        
        return None
    
    def apply_mode_prefix(self, user_input: str) -> str:
        """
        Apply mode prefix to user input if in mode.
        
        Args:
            user_input: Raw user input
        
        Returns:
            Prefixed command string
        """
        if not self._active_mode:
            return user_input
        
        # Apply mode-specific prefix
        if self._active_mode.mode_type == "plan":
            # Only apply prefix if we have a target (meal-specific mode)
            if self._active_mode.mode_target:
                # Plan command syntax: plan <subcommand> <id> <rest>
                # User input: "report" or "add BF.1" or "setmult 1 *1.5"
                # Output: "plan report 1a" or "plan add 1a BF.1" or "plan setmult 1a 1 *1.5"
                
                parts = user_input.split(maxsplit=1)
                subcommand = parts[0]
                rest = parts[1] if len(parts) > 1 else ""
                
                if rest:
                    return f"plan {subcommand} {self._active_mode.mode_target} {rest}"
                else:
                    return f"plan {subcommand} {self._active_mode.mode_target}"
            else:
                # General planning mode - no prefix needed
                return user_input
        
        return user_input