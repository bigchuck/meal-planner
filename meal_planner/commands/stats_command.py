"""
Stats command - show usage statistics.
"""
import re
from datetime import date, datetime, timedelta
from .base import Command, register_command


@register_command
class StatsCommand(Command):
    """Show command usage statistics."""
    
    name = "stats"
    help_text = "Show usage statistics (stats [YYYY-MM-DD|daily|weekly|alltime])"
    
    def execute(self, args: str) -> None:
        """
        Show usage statistics.
        
        Args:
            args: Optional: YYYY-MM-DD (specific date), "daily", "weekly", "alltime"
                  Default with no args: show all three sections
        """
        if not self.ctx.usage.enabled:
            print("\nUsage tracking is disabled.")
            print("Set TRACK_USAGE = True in config.py to enable.\n")
            return
        
        arg = args.strip().lower()
        
        # Check if it's a date (YYYY-MM-DD)
        if re.match(r"^\d{4}-\d{2}-\d{2}$", arg):
            self._show_daily(arg)
            return
        
        # Handle mode keywords
        if not arg:
            # No args: show all three sections
            self._show_daily()
            self._show_weekly()
            self._show_all_time()
        elif arg == "daily":
            self._show_daily()
        elif arg == "weekly":
            self._show_weekly()
        elif arg in ("alltime", "all"):
            self._show_all_time()
        else:
            print(f"Unknown option: {arg}")
            print("Usage: stats [YYYY-MM-DD|daily|weekly|alltime]")
    
    def _show_daily(self, target_date: str = None) -> None:
        """
        Show daily usage.
        
        Args:
            target_date: Optional date string (YYYY-MM-DD), defaults to today
        """
        if target_date is None:
            target_date = str(date.today())
        
        stats = self.ctx.usage.get_daily_stats(target_date)
        
        print(f"\n=== Daily Usage: {target_date} ===")
        
        if not stats:
            print("No commands used on this date.\n")
            return
        
        # Get canonical command names only
        canonical_commands = self._get_canonical_commands()
        
        # Show in alpha order
        print(f"{'Command':<15} {'Count':>6}")
        print("-" * 22)
        
        for cmd in sorted(canonical_commands):
            count = stats.get(cmd, 0)
            if count > 0:
                print(f"{cmd:<15} {count:>6}")
        
        # Show total
        total = sum(stats.values())
        print("-" * 22)
        print(f"{'TOTAL':<15} {total:>6}")
        print()
    
    def _show_weekly(self) -> None:
        """Show this week's usage."""
        week = datetime.now().strftime("%Y-W%U")
        stats = self.ctx.usage.get_weekly_stats(week)
        
        # Calculate week start/end for display
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        
        print(f"\n=== Weekly Usage: {week} ({week_start} to {week_end}) ===")
        
        if not stats:
            print("No commands used this week.\n")
            return
        
        # Get canonical command names only
        canonical_commands = self._get_canonical_commands()
        
        # Show in alpha order
        print(f"{'Command':<15} {'Count':>6}")
        print("-" * 22)
        
        for cmd in sorted(canonical_commands):
            count = stats.get(cmd, 0)
            if count > 0:
                print(f"{cmd:<15} {count:>6}")
        
        # Show total
        total = sum(stats.values())
        print("-" * 22)
        print(f"{'TOTAL':<15} {total:>6}")
        print()
    
    def _show_all_time(self) -> None:
        """Show all-time usage."""
        stats = self.ctx.usage.get_all_time_stats()
        
        print("\n=== All-Time Usage ===")
        
        if not stats:
            print("No commands tracked yet.\n")
            return
        
        # Get canonical command names only
        canonical_commands = self._get_canonical_commands()
        
        # Show in alpha order with last used
        print(f"{'Command':<15} {'Count':>6}  {'Last Used':<12}")
        print("-" * 36)
        
        for cmd in sorted(canonical_commands):
            count = stats.get(cmd, 0)
            if count > 0:
                last_used = self.ctx.usage.get_last_seen(cmd)
                print(f"{cmd:<15} {count:>6}  {last_used:<12}")
        
        # Show never-used commands
        never_used = [cmd for cmd in sorted(canonical_commands) if stats.get(cmd, 0) == 0]
        if never_used:
            print("\nNever used:")
            self._print_wrapped_list(never_used, indent=2, width=70)
        
        # Show total
        total = sum(stats.values())
        print("-" * 36)
        print(f"{'TOTAL':<15} {total:>6}")
        print()
    
    def _get_canonical_commands(self) -> list:
        """
        Get list of canonical command names (no aliases).
        
        Returns:
            List of command names (first name from each command class)
        """
        from .base import get_registry
        registry = get_registry()
        
        # Get all unique command classes
        commands = registry.get_all_commands()
        
        # Get canonical name (first name) from each
        canonical = []
        for cmd_class in commands:
            if isinstance(cmd_class.name, str):
                canonical.append(cmd_class.name)
            else:
                canonical.append(cmd_class.name[0])
        
        return canonical
    
    def _print_wrapped_list(self, items: list, indent: int = 0, width: int = 70) -> None:
        """
        Print a list of items wrapped to specified width.
        
        Args:
            items: List of strings to print
            indent: Number of spaces to indent
            width: Maximum line width
        """
        prefix = " " * indent
        current_line = prefix
        
        for i, item in enumerate(items):
            # Add comma except for first item
            separator = ", " if i > 0 else ""
            test_line = current_line + separator + item
            
            if len(test_line) <= width:
                current_line = test_line
            else:
                # Print current line and start new one
                print(current_line)
                current_line = prefix + item
        
        # Print remaining
        if current_line.strip():
            print(current_line)
        
        print()  # Blank line after
