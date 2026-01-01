"""
Basic commands: help, quit, reload, status.
"""
from .base import Command, register_command, get_registry


@register_command
class HelpCommand(Command):
    """Show help information."""
    
    name = ("help", "h", "?")
    help_text = "Show this help message"
    
    def execute(self, args: str) -> None:
        """Display help for all commands."""
        registry = get_registry()
        
        # Show mode status if active
        if self.ctx.mode_mgr.is_active:
            mode = self.ctx.mode_mgr.active_mode
            print(f"\n*** Currently in {mode.prompt_display} mode ***")
            print("Commands shown below can be used WITHOUT the mode prefix")
            print("Prefix with '.' to use global commands")
            print()

        print("\nAvailable Commands:")
        print("=" * 70)
        
        # Get unique commands and sort by name
        commands = registry.get_all_commands()
        commands.sort(key=lambda c: c.name if isinstance(c.name, str) else c.name[0])
        
        for cmd_class in commands:
            # Show all aliases
            if isinstance(cmd_class.name, str):
                names = cmd_class.name
            else:
                names = ", ".join(cmd_class.name)
            
            print(f"  {names:20} {cmd_class.help_text}")
        
        print("=" * 70)
        print()


@register_command
class QuitCommand(Command):
    """Exit the application."""
    
    name = ("quit", "q")
    help_text = "Exit the application"
    
    def execute(self, args: str) -> None:
        """Exit with message."""
        print("SO LONG, CRABBY!")
        raise SystemExit(0)

# @register_command
# class ReloadCommand(Command):
#     """Reload master file from disk."""
    
#     name = "reload"
#     help_text = "Reload master file from disk"
    
#     def execute(self, args: str) -> None:
#         """Reload master file."""
#         self.ctx.reload_master()
#         print(f"Master reloaded from disk ({len(self.ctx.master.df)} entries).")

@register_command
class StatusCommand(Command):
    """Show current pending status."""
    
    name = "status"
    help_text = "Show current pending day status"
    
    def execute(self, args: str) -> None:
        """Display pending status."""
        pending = self.ctx.pending_mgr.load()
        
        if pending is None:
            print("No pending day.")
        else:
            date = pending.get("date", "unknown")
            items = pending.get("items", [])
            print(f"Pending day: {date} with {len(items)} item(s).")