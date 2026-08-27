"""
Mode command - enter/exit command modes.
"""
from .base import Command, register_command


@register_command
class ModeCommand(Command):
    """Enter or exit command modes."""
    
    name = "mode"
    category = "Plan"
    help_text = "Enter/exit command modes (mode plan [id], mode exit)"
    overview_help = (
        "mode  —  Enter a REPL mode that auto-prefixes your input with a command\n"
        "\n"
        "Usage:\n"
        "  mode              Show current mode status\n"
        "  mode plan [id]    Enter plan mode (optionally scoped to one workspace candidate)\n"
        "  mode exit          Exit the current mode (or type 'exit')\n"
        "\n"
        "While in plan mode, bare input like 'show' or 'add 2 B.1' is run as\n"
        "'plan show'/'plan add 2 B.1' automatically. Prefix a line with '.' to\n"
        "run a global command instead for that one line."
    )


    def execute(self, args: str) -> None:
        """
        Execute mode command.
        
        Syntax:
            mode plan [id]     - Enter plan mode (optional workspace ID)
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
            workspace_id = parts[1].strip() if len(parts) > 1 else None
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
            if mode.mode_target:  # NEW: Only show target if present
                print(f"  Target: {mode.mode_target}")
            print()
            print("Type 'mode exit' or 'exit' to leave mode")
        else:
            print("No active mode")
            print()
            print("Available modes:")
            print("  mode plan       - Enter general planning mode")  # NEW
            print("  mode plan <id>  - Enter plan mode for workspace meal")  # UPDATED
    
    def _enter_plan_mode(self, workspace_id: str = None) -> None:
        """
        Enter plan mode.
        
        Args:
            workspace_id: Optional workspace ID for meal-specific mode
        """
        success, message = self.ctx.mode_mgr.enter_plan_mode(workspace_id)
        
        print()
        print(message)
        
        if success:
            print()
            if workspace_id:
                # Meal-specific mode
                print("Plan mode commands (no 'plan <id>' prefix needed):")
                print("  add <codes>          - Add items")
                print("  rm <indices>         - Remove items")
                print("  setmult <idx> <mult> - Set multiplier")
                print("  report               - Show report")
                print("  promote <@HH:MM>     - Promote to pending")
                print("  analyze              - Analyze meal")
                print("  recommend            - Get recommendations")
                print()
            else:
                # General planning mode
                print("General planning mode commands:")
                print("  inventory add/remove/depleted/restore/list")
                print("  plan <subcommands>   - Access plan commands")
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