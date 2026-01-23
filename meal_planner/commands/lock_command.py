# meal_planner/commands/lock_command.py
"""
Lock command - manage include/exclude locks for recommendation engine.
"""
from .base import Command, register_command
from meal_planner.parsers.code_parser import eval_multiplier_expression, parse_one_code_mult
import re


@register_command
class LockCommand(Command):
    """Manage recommendation locks (include/exclude specific foods)."""
    
    name = "lock"
    help_text = "Manage recommendation locks (lock include/exclude/remove/list/clear)"
    
    def execute(self, args: str) -> None:
        """
        Execute lock command.
        
        Syntax:
            lock include <code> [<multiplier>]
            lock exclude <code>
            lock remove <code>
            lock list
            lock clear
        
        Args:
            args: Subcommand and parameters
        """
        # Check if in planning mode
        if not self.ctx.mode_mgr.is_active or self.ctx.mode_mgr.active_mode.mode_type != "plan":
            print("\nError: Lock commands only available in planning mode")
            print("Use: mode plan")
            print()
            return
        
        if not args.strip():
            self._show_help()
            return
        
        parts = args.split(maxsplit=1)
        subcommand = parts[0].lower()
        subargs = parts[1] if len(parts) > 1 else ""
        
        if subcommand == "include":
            self._include(subargs)
        elif subcommand == "exclude":
            self._exclude(subargs)
        elif subcommand == "remove":
            self._remove(subargs)
        elif subcommand == "list":
            self._list()
        elif subcommand == "clear":
            self._clear()
        else:
            print(f"\nUnknown lock subcommand: {subcommand}")
            self._show_help()
    
    def _show_help(self) -> None:
        """Show lock command help."""
        print("""
Lock Management Commands:

  lock include <code> [<multiplier>]
      Signal that this food MUST be used in next meal recommendation
      Multiplier represents fraction of master.csv portion
      - If code is in leftovers: defaults to leftover quantity
      - Otherwise: defaults to 1.0
      Multiplier supports arithmetic: 1.5, .9/4, 5.7/4, etc.
      Cannot exceed leftover quantity if in inventory
      
      Examples:
        lock include FI.8            # uses leftover quantity if available
        lock include FI.8 0.225      # use 0.225x portion of fish
        lock include FI.8 .9/4       # use (0.9/4)x portion
        lock include FI.8 x1/7       # use x1/7 portion (like add command)
        lock include FI.8 *1/7       # use *1/7 portion (like add command)
        lock include SO.13d 0.5      # use 0.5x portion of soup
        lock include GR.H1           # use 1.0x portion of granola
  
  lock exclude <code|pattern>
      Signal that this food MUST NOT appear in meal recommendations
      Supports wildcards for patterns (exclude only)
      
      Examples:
        lock exclude 11124           # exclude specific code
        lock exclude SO.*            # exclude all soups (pattern)
  
  lock remove <code|pattern>
      Remove lock (from either include or exclude list)
      
      Examples:
        lock remove FI.8
        lock remove SO.*
  
  lock list
      Show all current locks
      Displays [leftover: X.XXx] tag for items from inventory
  
  lock clear
      Remove all locks (requires confirmation)

Notes:
  - Locks persist across planning sessions
  - Include = MUST use (hard requirement for recommendation engine)
  - Exclude = MUST NOT use (absolute block)
  - A code can only be in include OR exclude, not both
  - Wildcards (e.g. SO.*) only allowed in exclude list
  - Codes are case-insensitive: fi.8 and FI.8 are identical
  - Smart defaulting: leftover items default to their inventory quantity
  - Locks auto-save after each change
""")
    
    def _include(self, args: str) -> None:
        """
        Add food to include list.
        
        Args:
            args: "<code> [<multiplier>]"
        """
        if not args.strip():
            print("\nUsage: lock include <code> [<multiplier>]")
            print("Example: lock include FI.8 0.225")
            print("         lock include FI.8 .9/4")
            print()
            return
        
        parts = args.split()
        code = parts[0].upper()  # Case-insensitive input, stored as uppercase
        
        # Check for wildcard (not allowed in include)
        if '*' in code:
            print("\nError: Wildcards not allowed in include list")
            print("Wildcards are only supported for exclude")
            print()
            return
        
        # Validate code exists in master
        if not self._validate_code(code):
            print(f"\nError: Food code '{code}' not found in master.csv")
            print()
            return
        
        # Get workspace
        workspace = self._load_workspace()
        
        # Check if in exclude list
        if code in workspace["locks"]["exclude"]:
            print(f"\nError: {code} is currently in exclude list")
            print(f"Use 'lock remove {code}' first, then 'lock include {code}'")
            print()
            return
        
        # Check inventory for leftovers and determine default multiplier
        inventory = workspace.get("inventory", {})
        leftovers = inventory.get("leftovers", {})
        
        # Smart default: use leftover quantity if available, else 1.0
        default_multiplier = leftovers[code]["multiplier"] if code in leftovers else 1.0
        user_provided_multiplier = len(parts) > 1
        
        # Parse optional multiplier (supports x1/7, *1/7, 1/7, .9/4, etc.)
        if user_provided_multiplier:
            # Try parsing with code prefix first (handles x1/7, *1/7)
            test_snippet = f"DUMMY {parts[1]}"
            parsed = parse_one_code_mult(test_snippet)
            
            if parsed and 'mult' in parsed:
                multiplier = parsed['mult']
                if multiplier <= 0:
                    print(f"\nError: Multiplier must be positive, got {multiplier}")
                    print()
                    return
            else:
                print(f"\nError: Invalid multiplier '{parts[1]}'")
                print()
                return
        else:
            multiplier = default_multiplier
        
        # Validate against leftover constraints
        if code in leftovers:
            leftover_mult = leftovers[code]["multiplier"]
            if abs(multiplier-leftover_mult) > 0.001 and "--force" not in args:
                print(f"\nError: Multiplier {multiplier} exceeds leftover quantity {leftover_mult}")
                print(f"Available in inventory: {leftover_mult}x")
                print(f"Note: If using more than leftover quantity, this is not coming from leftovers")
                print()
                return

        # Add to include list
        workspace["locks"]["include"][code] = multiplier
        
        # Save workspace
        self._save_workspace(workspace)
        
        # Get food name for display
        food_name = self._get_food_name(code)
        
        print(f"\nLocked {code} ({food_name}) for inclusion")
        print(f"  Multiplier: {multiplier:g}x")
        if code in leftovers and not user_provided_multiplier:
            print(f"  Note: Defaulted to leftover quantity")
        print()
    
    def _exclude(self, args: str) -> None:
        """
        Add food or pattern to exclude list.
        
        Args:
            args: "<code|pattern>"
        """
        if not args.strip():
            print("\nUsage: lock exclude <code|pattern>")
            print("Example: lock exclude 11124")
            print("         lock exclude SO.*")
            print()
            return
        
        code_or_pattern = args.strip().upper()
        
        # Check if pattern (contains wildcard)
        is_pattern = '*' in code_or_pattern
        
        if is_pattern:
            # Validate pattern syntax
            if not self._validate_pattern(code_or_pattern):
                print(f"\nError: Invalid pattern syntax '{code_or_pattern}'")
                print("Patterns should be like: SO.*, FI.*, etc.")
                print()
                return
        else:
            # Validate code exists in master
            if not self._validate_code(code_or_pattern):
                print(f"\nError: Food code '{code_or_pattern}' not found in master.csv")
                print()
                return
        
        # Get workspace
        workspace = self._load_workspace()
        
        # Check if in include list
        if code_or_pattern in workspace["locks"]["include"]:
            print(f"\nError: {code_or_pattern} is currently in include list")
            print(f"Use 'lock remove {code_or_pattern}' first, then 'lock exclude {code_or_pattern}'")
            print()
            return
        
        # Add to exclude list (avoid duplicates)
        if code_or_pattern not in workspace["locks"]["exclude"]:
            workspace["locks"]["exclude"].append(code_or_pattern)
        
        # Save workspace
        self._save_workspace(workspace)
        
        if is_pattern:
            print(f"\nLocked pattern '{code_or_pattern}' for exclusion")
            print(f"  This will exclude all matching food codes")
        else:
            food_name = self._get_food_name(code_or_pattern)
            print(f"\nLocked {code_or_pattern} ({food_name}) for exclusion")
        print()
    
    def _remove(self, args: str) -> None:
        """
        Remove lock from either include or exclude list.
        
        Args:
            args: "<code|pattern>"
        """
        if not args.strip():
            print("\nUsage: lock remove <code|pattern>")
            print("Example: lock remove FI.8")
            print("         lock remove SO.*")
            print()
            return
        
        code_or_pattern = args.strip().upper()
        
        # Get workspace
        workspace = self._load_workspace()
        
        # Try to remove from include
        removed_from = None
        if code_or_pattern in workspace["locks"]["include"]:
            del workspace["locks"]["include"][code_or_pattern]
            removed_from = "include"
        
        # Try to remove from exclude
        elif code_or_pattern in workspace["locks"]["exclude"]:
            workspace["locks"]["exclude"].remove(code_or_pattern)
            removed_from = "exclude"
        
        if removed_from is None:
            print(f"\nError: {code_or_pattern} not found in locks")
            print("Use 'lock list' to see current locks")
            print()
            return
        
        # Save workspace
        self._save_workspace(workspace)
        
        # Check if pattern
        is_pattern = '*' in code_or_pattern
        
        if is_pattern:
            print(f"\nRemoved pattern '{code_or_pattern}' from {removed_from} list")
        else:
            food_name = self._get_food_name(code_or_pattern)
            print(f"\nRemoved {code_or_pattern} ({food_name}) from {removed_from} list")
        print()
    
    def _list(self) -> None:
        """Show all current locks."""
        workspace = self._load_workspace()
        
        # Check if any locks exist
        has_locks = (
            len(workspace["locks"]["include"]) > 0 or
            len(workspace["locks"]["exclude"]) > 0
        )
        
        if not has_locks:
            print("\nNo locks currently set")
            print()
            return
        
        print("\n=== RECOMMENDATION LOCKS ===")
        print()
        
        # Show include list
        if workspace["locks"]["include"]:
            print("Include (MUST use):")
            
            # Get leftover inventory for reference
            leftovers = workspace.get("inventory", {}).get("leftovers", {})
            
            for code, multiplier in sorted(workspace["locks"]["include"].items()):
                food_name = self._get_food_name(code)
                
                # Check if from leftovers
                leftover_tag = ""
                if code in leftovers:
                    leftover_mult = leftovers[code]["multiplier"]
                    leftover_tag = f" [leftover: {leftover_mult:g}x]"
                
                print(f"  {code} ({food_name}): {multiplier:g}x{leftover_tag}")
            print()
        
        # Show exclude list
        if workspace["locks"]["exclude"]:
            print("Exclude (MUST NOT use):")
            for item in sorted(workspace["locks"]["exclude"]):
                # Check if pattern
                if '*' in item:
                    print(f"  {item} (pattern - matches multiple codes)")
                else:
                    food_name = self._get_food_name(item)
                    print(f"  {item} ({food_name})")
            print()
    
    def _clear(self) -> None:
        """Clear all locks with confirmation."""
        workspace = self._load_workspace()
        
        # Check if any locks exist
        has_locks = (
            len(workspace["locks"]["include"]) > 0 or
            len(workspace["locks"]["exclude"]) > 0
        )
        
        if not has_locks:
            print("\nNo locks to clear")
            print()
            return
        
        # Count locks for confirmation message
        include_count = len(workspace["locks"]["include"])
        exclude_count = len(workspace["locks"]["exclude"])
        
        print(f"\nAbout to clear ALL locks:")
        print(f"  Include: {include_count} items")
        print(f"  Exclude: {exclude_count} items")
        print()
        
        # Confirmation prompt
        response = input("Are you sure? (yes/no): ").strip().lower()
        
        if response != "yes":
            print("\nClear cancelled")
            print()
            return
        
        # Clear all locks
        workspace["locks"]["include"] = {}
        workspace["locks"]["exclude"] = []
        
        # Save workspace
        self._save_workspace(workspace)
        
        print("\nAll locks cleared")
        print()
    
    # Helper methods
    
    def _validate_pattern(self, pattern: str) -> bool:
        """
        Validate pattern syntax.
        
        Args:
            pattern: Pattern string (e.g., "SO.*")
        
        Returns:
            True if valid pattern
        """
        # Basic validation: should have format PREFIX.*
        # where PREFIX is 2-4 uppercase letters
        pattern_regex = r'^[A-Z]{2,4}\.\*$'
        return bool(re.match(pattern_regex, pattern))
    
    def _load_workspace(self):
        """Load workspace data from disk."""
        workspace = self.ctx.workspace_mgr.load()
        
        # Initialize locks if missing (backward compatibility)
        if "locks" not in workspace:
            workspace["locks"] = {
                "include": {},
                "exclude": []
            }
        else:
            # Ensure both lists exist
            if "include" not in workspace["locks"]:
                workspace["locks"]["include"] = {}
            if "exclude" not in workspace["locks"]:
                workspace["locks"]["exclude"] = []
        
        return workspace
    
    def _save_workspace(self, workspace):
        """Save workspace data to disk."""
        self.ctx.workspace_mgr.save(workspace)
    
    def _validate_code(self, code: str) -> bool:
        """
        Validate that code exists in master.csv.
        
        Args:
            code: Food code
        
        Returns:
            True if code exists
        """
        row = self.ctx.master.lookup_code(code)
        return row is not None
    
    def _get_food_name(self, code: str) -> str:
        """
        Get food name for a code.
        
        Args:
            code: Food code
        
        Returns:
            Food description or "Unknown"
        """
        row = self.ctx.master.lookup_code(code)
        if row is not None:
            return row[self.ctx.master.cols.option]
        return "Unknown"
