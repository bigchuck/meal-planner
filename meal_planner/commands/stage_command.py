# meal_planner/commands/stage_command.py
"""
Stage command - manage staging buffer for email delivery.

Provides subcommands for viewing, editing, and clearing staged meal plans.
"""
import shlex
from .base import Command, register_command


@register_command
class StageCommand(Command):
    """Manage staging buffer for email delivery."""
    
    name = "stage"
    help_text = "Manage staging buffer (stage show|edit|remove|clear)"
    
    def execute(self, args: str) -> None:
        """
        Route to staging buffer subcommands.
        
        Args:
            args: Subcommand and arguments
        """
        # Check if staging buffer is available
        if not self.ctx.staging_buffer:
            print("\nStaging buffer not configured.\n")
            return
        
        # Parse arguments
        try:
            parts = shlex.split(args) if args.strip() else []
        except ValueError:
            parts = args.strip().split() if args.strip() else []
        
        # No args or help request
        if not parts or parts[0] == "help":
            self._show_help()
            return
        
        subcommand = parts[0].lower()
        subargs = parts[1:]
        
        # Route to subcommand handlers
        if subcommand == "show":
            self._show(subargs)
        elif subcommand == "edit":
            self._edit(subargs)
        elif subcommand == "remove":
            self._remove(subargs)
        elif subcommand == "clear":
            self._clear(subargs)
        else:
            print(f"\nUnknown subcommand: {subcommand}")
            print("Use 'stage help' to see available subcommands\n")
    
    def _show_help(self) -> None:
        """Display help for all subcommands."""
        print("""
=== Staging Buffer Management ===

The staging buffer holds meals and analysis to be emailed to your phone.

SUBCOMMANDS:
  show                  - Display buffer contents
  edit <pos> --desc "text" - Edit description at position
  remove <pos>          - Remove item at position
  clear                 - Clear entire buffer

EXAMPLES:
  stage show
  stage edit 2 --desc "Tuesday Lunch - client meeting"
  stage remove 3
  stage clear
  
NOTE: Use --stage flag on report/analyze/plan commands to add to buffer.
""")
    
    def _show(self, args: list) -> None:
        """Display staging buffer contents."""
        buffer_mgr = self.ctx.staging_buffer
        
        if buffer_mgr.is_empty():
            print("\nStaging buffer is empty.\n")
            return
        
        items = buffer_mgr.get_all()
        total_lines = buffer_mgr.get_total_lines()
        
        print("\nStaging Buffer:")
        for pos, label, content, timestamp in items:
            line_count = len(content)
            print(f"  {pos}. {label} ({line_count} lines)")
        
        print(f"\nTotal: {len(items)} items, {total_lines} lines")
        print(f"Last modified: {buffer_mgr.load()['last_modified']}\n")
    
    def _edit(self, args: list) -> None:
        """
        Edit description for an item.
        
        Usage: stage edit <position> --desc "new description"
        """
        if len(args) < 3 or "--desc" not in args:
            print("\nUsage: stage edit <position> --desc \"new description\"")
            print("Example: stage edit 2 --desc \"Tuesday Lunch\"\n")
            return
        
        # Parse position
        try:
            position = int(args[0])
        except ValueError:
            print(f"\nError: Invalid position: {args[0]}\n")
            return
        
        # Find --desc flag
        try:
            desc_index = args.index("--desc")
            if desc_index + 1 >= len(args):
                print("\nError: --desc requires a description\n")
                return
            new_desc = " ".join(args[desc_index + 1:])
        except ValueError:
            print("\nError: Missing --desc flag\n")
            return
        
        # Update description
        buffer_mgr = self.ctx.staging_buffer
        success, old_label = buffer_mgr.update_label(position, new_desc)
        
        if success:
            print(f"\n✓ Updated description for position {position}")
            print(f"  Old: {old_label}")
            print(f"  New: {new_desc}\n")
        else:
            count = buffer_mgr.get_count()
            print(f"\nError: Invalid position {position}. Buffer has {count} items.\n")
    
    def _remove(self, args: list) -> None:
        """
        Remove an item by position.
        
        Usage: stage remove <position>
        """
        if not args:
            print("\nUsage: stage remove <position>")
            print("Example: stage remove 2\n")
            return
        
        # Parse position
        try:
            position = int(args[0])
        except ValueError:
            print(f"\nError: Invalid position: {args[0]}\n")
            return
        
        # Remove item
        buffer_mgr = self.ctx.staging_buffer
        success, label = buffer_mgr.remove(position)
        
        if success:
            print(f"\n✓ Removed: {label}\n")
        else:
            count = buffer_mgr.get_count()
            print(f"\nError: Invalid position {position}. Buffer has {count} items.\n")
    
    def _clear(self, args: list) -> None:
        """Clear the entire buffer with confirmation."""
        buffer_mgr = self.ctx.staging_buffer
        
        if buffer_mgr.is_empty():
            print("\nStaging buffer is already empty.\n")
            return
        
        count = buffer_mgr.get_count()
        
        # Confirmation
        print(f"\nClear {count} item(s) from staging buffer?")
        response = input("Confirm (y/n): ").strip().lower()
        
        if response in ("y", "yes"):
            cleared = buffer_mgr.clear_all()
            print(f"\n✓ Cleared {cleared} item(s) from staging buffer.\n")
        else:
            print("\nCancelled.\n")