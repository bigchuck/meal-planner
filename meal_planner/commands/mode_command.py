"""
Mode command - enter/exit command modes.
"""
from .base import Command, register_command


@register_command
class ModeCommand(Command):
    """Enter or exit command modes."""
    
    name = "mode"
    help_text = "Enter/exit command modes (mode plan <id>, mode exit)"
    
    def execute(self, args: str) -> None:
        """
        Execute mode command.
        
        Syntax:
            mode plan <id>     - Enter plan mode for workspace
            mode exit          - Exit current mode
            mode               - Show current mode status
        
        Args:
            args: Mode subcommand and parameters
        """
        if not args.strip():
            self._show_status()
            return
        
        parts = args.split(maxsplit=1)
        subcommand = parts[0].lower()
        
        if subcommand == "exit":
            self._exit_mode()
        elif subcommand == "plan":
            if len(parts) < 2:
                print("Usage: mode plan <workspace_id>")
                print("Example: mode plan 2a")
                return
            workspace_id = parts[1].strip()
            self._enter_plan_mode(workspace_id)
        else:
            print(f"Unknown mode type: {subcommand}")
            print("Available modes: plan")
            print("Use 'mode exit' to leave current mode")
    
    def _show_status(self) -> None:
        """Show current mode status."""
        if self.ctx.mode_mgr.is_active:
            mode = self.ctx.mode_mgr.active_mode
            print(f"Current mode: {mode.prompt_display}")
            print(f"  Type: {mode.mode_type}")
            print(f"  Target: {mode.mode_target}")
            print()
            print("Type 'mode exit' or 'exit' to leave mode")
        else:
            print("No active mode")
            print()
            print("Available modes:")
            print("  mode plan <id>  - Enter plan mode for workspace")
    
    def _enter_plan_mode(self, workspace_id: str) -> None:
        """Enter plan mode."""
        success, message = self.ctx.mode_mgr.enter_plan_mode(workspace_id)
        
        print()
        print(message)
        
        if success:
            print()
            print("Plan mode commands (no 'plan <id>' prefix needed):")
            print("  add <codes>          - Add items")
            print("  rm <indices>         - Remove items")
            print("  setmult <idx> <mult> - Set multiplier")
            print("  report               - Show report")
            print("  promote <time>       - Promote to pending")
            print("  analyze              - Analyze meal")
            print("  recommend            - Get recommendations")
            print()
            print("Prefix commands with '.' for global commands (e.g., '.status')")
            print("Type 'exit' to leave mode, 'quit' to exit application")
        
        print()
    
    def _exit_mode(self) -> None:
        """Exit current mode."""
        message = self.ctx.mode_mgr.exit_mode()
        print()
        print(message)
        print()