# meal_planner/commands/stage_command.py
"""
Stage command - manage staging buffer for email delivery.

Provides subcommands for viewing, editing, and clearing staged meal plans.
"""
import shlex
from .base import Command, register_command
from typing import List, Tuple

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
        elif subcommand == "send":     
            self._send(subargs)
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
  send                  - Email buffer to your phone  

EXAMPLES:
  stage show
  stage edit 2 --desc "Tuesday Lunch - client meeting"
  stage remove 3
  stage clear
  stage send
  
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

    def _send(self, args: list) -> None:
        """
        Send staged content via email.
        
        Usage: stage send
        """
        buffer_mgr = self.ctx.staging_buffer
        email_mgr = self.ctx.email_mgr
        
        # Check if email is configured
        if not email_mgr:
            print("\nEmail not configured.")
            print("Create data/email_config.json with your Gmail settings.")
            print("See documentation for setup instructions.\n")
            return
        
        # Load email config
        if not email_mgr.load_config():
            print(f"\n{email_mgr.get_error_message()}\n")
            return
        
        # Check if buffer has content
        if buffer_mgr.is_empty():
            print("\nStaging buffer is empty. Nothing to send.\n")
            return
        
        # Get buffer contents
        items = buffer_mgr.get_all()
        total_lines = buffer_mgr.get_total_lines()
        
        # Show what will be sent
        print("\nBuffer contains:")
        for pos, label, content, timestamp in items:
            line_count = len(content)
            print(f"  {pos}. {label} ({line_count} lines)")
        
        print(f"\nTotal: {len(items)} items, {total_lines} lines")
        
        # Show recipient and rate limit status
        recipient = email_mgr.get_configured_address()
        sent_count, limit = email_mgr.get_rate_limit_status()
        
        print(f"\nSend to: {recipient}")
        print(f"Rate limit: {sent_count}/{limit} sent in last hour")
        
        # Generate subject
        subject = self._generate_subject(items)
        print(f"Subject: {subject}")
        
        # Confirmation
        print()
        response = input("Send email? (y/n): ").strip().lower()
        
        if response not in ("y", "yes"):
            print("\nCancelled.\n")
            return
        
        # Build email body
        body_lines = self._build_email_body(items)
        
        # Send
        success, message = email_mgr.send(subject, body_lines)
        
        if success:
            print(f"\n✓ {message}\n")
            
            # Ask if user wants to clear buffer
            print("Clear staging buffer?")
            response = input("(y/n): ").strip().lower()
            
            if response in ("y", "yes"):
                count = buffer_mgr.clear_all()
                print(f"\n✓ Cleared {count} item(s) from buffer.\n")
            else:
                print("\nBuffer preserved.\n")
        else:
            print(f"\n✗ Failed to send: {message}\n")

    def _generate_subject(self, items: List[Tuple]) -> str:
        """
        Generate email subject from staged items.
        
        Args:
            items: List of (pos, label, content, timestamp) tuples
        
        Returns:
            Email subject string
        """
        from datetime import datetime
        
        # Extract meal names from labels
        meal_names = []
        for pos, label, content, timestamp in items:
            # Skip analysis items
            if label.startswith("Analysis:"):
                continue
            
            # Extract meal name from label
            # Format: "Thursday, December 26, 2024 - BREAKFAST"
            # or: "Tuesday Dinner - client meeting"
            if " - " in label:
                parts = label.split(" - ")
                meal_part = parts[-1]  # Last part is usually the meal
                
                # Clean up meal name (remove "(workspace)", etc.)
                meal_part = meal_part.replace("(workspace)", "").strip()
                
                if meal_part and meal_part not in meal_names:
                    meal_names.append(meal_part)
        
        # Generate subject
        today = datetime.now().strftime("%b %d")
        
        if len(meal_names) == 0:
            return f"Meal Plans - {today}"
        elif len(meal_names) == 1:
            return f"Meal Plan: {meal_names[0]} - {today}"
        elif len(meal_names) <= 3:
            return f"Meal Plans: {', '.join(meal_names)} - {today}"
        else:
            return f"Meal Plans ({len(meal_names)} meals) - {today}"

    def _build_email_body(self, items: List[Tuple]) -> List[str]:
        """
        Build email body from staged items.
        
        Args:
            items: List of (pos, label, content, timestamp) tuples
        
        Returns:
            List of body lines
        """
        body = []
        
        for i, (pos, label, content, timestamp) in enumerate(items):
            # Add separator between items (except before first)
            if i > 0:
                body.append("")
                body.append("=" * 70)
                body.append("")
            
            # Add item label as header
            body.append(label)
            body.append("=" * 70)
            
            # Add content (skip first line if it's a duplicate header)
            for line in content:
                # Skip empty === headers that duplicate our label
                if line.strip().startswith("===") and label in line:
                    continue
                body.append(line)
        
        return body