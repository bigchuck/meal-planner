# meal_planner/commands/lock_command.py
"""
Lock command - manage include/exclude locks for recommendation engine.
"""
from typing import Optional, Tuple, List
from .base import Command, register_command
from meal_planner.parsers.code_parser import eval_multiplier_expression, parse_one_code_mult
from meal_planner.utils.time_utils import MEAL_NAMES, normalize_meal_name
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
            self._list(subargs)
        elif subcommand == "clear":
            self._clear(subargs)
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
        Add food to include list for specific meal or all meals.
        
        Args:
            args: "[meal_type|all] <code> [<multiplier>]"
        """
        # Parse meal type
        meal_type, remaining_args = self._parse_meal_and_args(args)
        
        if not meal_type:
            print("\nUsage: lock include [meal_type|all] <code> [<multiplier>]")
            print("Example: lock include lunch FI.8 0.5")
            print("         lock include all EG.1")
            print("         lock include dinner SO.13d 0.225")
            print(f"\nValid meal types: {', '.join([m.lower() for m in MEAL_NAMES])}, all")
            print()
            return
        
        # Parse code and optional multiplier
        parts = remaining_args.strip().split()
        
        if not parts:
            print("\nError: Missing food code")
            print("Usage: lock include [meal_type|all] <code> [<multiplier>]")
            print()
            return
        
        code = parts[0].upper()
        
        # Validate code exists
        if not self._validate_code(code):
            print(f"\nError: Food code '{code}' not found in master.csv")
            print()
            return
        
        # Parse multiplier (default to 1.0 or leftover quantity)
        workspace = self._load_workspace()
        leftovers = workspace.get("inventory", {}).get("leftovers", {})
        
        if len(parts) > 1:
            multiplier = self._parse_multiplier(parts[1], code, leftovers)
            if multiplier is None:
                return  # Error already printed
        else:
            # Smart default: use leftover quantity if available, else 1.0
            if code in leftovers:
                multiplier = leftovers[code]["multiplier"]
            else:
                multiplier = 1.0
        
        # Validate multiplier doesn't exceed leftover
        if code in leftovers:
            leftover_mult = leftovers[code]["multiplier"]
            if multiplier > leftover_mult + 0.001:  # Small tolerance
                print(f"\nError: Multiplier {multiplier:g}x exceeds leftover quantity {leftover_mult:g}x")
                print(f"Maximum allowed: {leftover_mult:g}x")
                print()
                return
        
        # Determine target meals
        if meal_type == "all":
            target_meals = self._get_meal_keys()
            meal_desc = "all meals"
        else:
            target_meals = [meal_type]
            meal_desc = meal_type.lower()
        
        # Apply to target meals
        for meal in target_meals:
            # Check if in exclude list for this meal
            if code in workspace["locks"][meal]["exclude"]:
                print(f"\nError: {code} is in exclude list for {meal.lower()}")
                print(f"Use 'lock remove {meal.lower()} {code}' first")
                print()
                return
            
            # Add to include list
            workspace["locks"][meal]["include"][code] = multiplier
        
        # Save workspace
        self._save_workspace(workspace)
        
        # Show confirmation
        food_name = self._get_food_name(code)
        leftover_tag = f" [from leftover: {leftovers[code]['multiplier']:g}x]" if code in leftovers else ""
        
        print(f"\nLocked {code} ({food_name}): {multiplier:g}x for {meal_desc}{leftover_tag}")
        print()    

    def _exclude(self, args: str) -> None:
        """
        Add food/pattern to exclude list for specific meal or all meals.
        
        Args:
            args: "[meal_type|all] <code|pattern>"
        """
        # Parse meal type
        meal_type, remaining_args = self._parse_meal_and_args(args)
        
        if not meal_type:
            print("\nUsage: lock exclude [meal_type|all] <code|pattern>")
            print("Example: lock exclude lunch VE.14")
            print("         lock exclude all SO.*")
            print("         lock exclude dinner DN.*")
            print(f"\nValid meal types: {', '.join([m.lower() for m in MEAL_NAMES])}, all")
            print()
            return
        
        if not remaining_args.strip():
            print("\nError: Missing food code or pattern")
            print("Usage: lock exclude [meal_type|all] <code|pattern>")
            print()
            return
        
        code_or_pattern = remaining_args.strip().upper()
        
        # Check if pattern
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
        
        # Determine target meals
        if meal_type == "all":
            target_meals = self._get_meal_keys()
            meal_desc = "all meals"
        else:
            target_meals = [meal_type]
            meal_desc = meal_type.lower()
        
        # Apply to target meals
        for meal in target_meals:
            # Check if in include list for this meal
            if code_or_pattern in workspace["locks"][meal]["include"]:
                print(f"\nError: {code_or_pattern} is in include list for {meal.lower()}")
                print(f"Use 'lock remove {meal.lower()} {code_or_pattern}' first")
                print()
                return
            
            # Add to exclude list (avoid duplicates)
            if code_or_pattern not in workspace["locks"][meal]["exclude"]:
                workspace["locks"][meal]["exclude"].append(code_or_pattern)
        
        # Save workspace
        self._save_workspace(workspace)
        
        if is_pattern:
            print(f"\nLocked pattern '{code_or_pattern}' for exclusion from {meal_desc}")
        else:
            food_name = self._get_food_name(code_or_pattern)
            print(f"\nLocked {code_or_pattern} ({food_name}) for exclusion from {meal_desc}")
        print()

    def _remove(self, args: str) -> None:
        """
        Remove lock from specific meal or all meals.
        
        Args:
            args: "[meal_type|all] <code|pattern>"
        """
        # Parse meal type
        meal_type, remaining_args = self._parse_meal_and_args(args)
        
        if not meal_type:
            print("\nUsage: lock remove [meal_type|all] <code|pattern>")
            print("Example: lock remove lunch FI.8")
            print("         lock remove all SO.*")
            print(f"\nValid meal types: {', '.join([m.lower() for m in MEAL_NAMES])}, all")
            print()
            return
        
        if not remaining_args.strip():
            print("\nError: Missing food code or pattern")
            print("Usage: lock remove [meal_type|all] <code|pattern>")
            print()
            return
        
        code_or_pattern = remaining_args.strip().upper()
        
        # Get workspace
        workspace = self._load_workspace()
        
        # Determine target meals
        if meal_type == "all":
            target_meals = self._get_meal_keys()
        else:
            target_meals = [meal_type]
        
        # Track removals
        removed_from = []
        
        for meal in target_meals:
            removed_type = None
            
            # Try to remove from include
            if code_or_pattern in workspace["locks"][meal]["include"]:
                del workspace["locks"][meal]["include"][code_or_pattern]
                removed_type = "include"
            
            # Try to remove from exclude
            elif code_or_pattern in workspace["locks"][meal]["exclude"]:
                workspace["locks"][meal]["exclude"].remove(code_or_pattern)
                removed_type = "exclude"
            
            if removed_type:
                removed_from.append((meal, removed_type))
        
        if not removed_from:
            meal_desc = "any meal" if meal_type == "all" else meal_type.lower()
            print(f"\nError: {code_or_pattern} not found in locks for {meal_desc}")
            print("Use 'lock list' to see current locks")
            print()
            return
        
        # Save workspace
        self._save_workspace(workspace)
        
        # Show confirmation
        is_pattern = '*' in code_or_pattern
        food_name = "pattern" if is_pattern else self._get_food_name(code_or_pattern)
        
        if len(removed_from) == 1:
            meal, lock_type = removed_from[0]
            print(f"\nRemoved {code_or_pattern} ({food_name}) from {lock_type} list for {meal.lower()}")
        else:
            print(f"\nRemoved {code_or_pattern} ({food_name}) from {len(removed_from)} meals:")
            for meal, lock_type in removed_from:
                print(f"  {meal.lower()}: {lock_type}")
        print()

    def _list(self, args: str = "") -> None:
        """
        Show locks for specific meal or all meals.
        
        Args:
            args: Optional "[meal_type]" to filter display
        """
        workspace = self._load_workspace()
        
        # Parse optional meal type filter
        filter_meal = None
        if args.strip():
            filter_meal = normalize_meal_name(args.strip()).lower()
            if filter_meal not in self._get_meal_keys():
                print(f"\nError: Invalid meal type '{args.strip()}'")
                print(f"Valid types: {', '.join(self._get_meal_keys())}")
                print()
                return
        
        # Determine which meals to show
        meals_to_show = [filter_meal] if filter_meal else self._get_meal_keys()
        print(f"{self._get_meal_keys()}")
        
        # Check if any locks exist in target meals
        has_any_locks = False
        for meal in meals_to_show:
            if (len(workspace["locks"][meal]["include"]) > 0 or
                len(workspace["locks"][meal]["exclude"]) > 0):
                has_any_locks = True
                break
        
        if not has_any_locks:
            if filter_meal:
                print(f"\nNo locks set for {filter_meal}")
            else:
                print("\nNo locks currently set for any meal")
            print()
            return
        
        print("\n=== RECOMMENDATION LOCKS ===")
        print()
        
        # Get leftover inventory for reference
        leftovers = workspace.get("inventory", {}).get("leftovers", {})
        
        # Show locks by meal type
        for meal in meals_to_show:
            meal_locks = workspace["locks"][meal]
            
            # Skip meals with no locks
            if (len(meal_locks["include"]) == 0 and
                len(meal_locks["exclude"]) == 0):
                continue
            
            print(f"{meal.upper()}:")  # Display uppercase
            
            # Show include list
            if meal_locks["include"]:
                print("  Include (MUST use):")
                for code, multiplier in sorted(meal_locks["include"].items()):
                    food_name = self._get_food_name(code)
                    
                    # Check if from leftovers
                    leftover_tag = ""
                    if code in leftovers:
                        leftover_mult = leftovers[code]["multiplier"]
                        leftover_tag = f" [leftover: {leftover_mult:g}x]"
                    
                    print(f"    {code} ({food_name}): {multiplier:g}x{leftover_tag}")
            
            # Show exclude list
            if meal_locks["exclude"]:
                print("  Exclude (MUST NOT use):")
                for item in sorted(meal_locks["exclude"]):
                    # Check if pattern
                    if '*' in item:
                        print(f"    {item} (pattern)")
                    else:
                        food_name = self._get_food_name(item)
                        print(f"    {item} ({food_name})")
            
            print()
    
    def _clear(self, args: str = "") -> None:
        """
        Clear locks for specific meal or all meals.
        
        Args:
            args: Optional "[meal_type|all]" to target specific meal(s)
        """
        workspace = self._load_workspace()
        
        # Parse optional meal type
        if args.strip():
            if args.strip().lower() == "all":
                meal_type = "all"
            else:
                normalized = normalize_meal_name(args.strip())
                if normalized not in MEAL_NAMES:
                    print(f"\nError: Invalid meal type '{args.strip()}'")
                    print(f"Valid types: {', '.join(self._get_meal_keys())}, all")
                    print()
                    return
                meal_type = normalized.lower()  # Use lowercase
        else:
            meal_type = "all"
        
        # Determine target meals
        if meal_type == "all":
            target_meals = self._get_meal_keys()
            meal_desc = "all meals"
        else:
            target_meals = [meal_type]
            meal_desc = meal_type

        # Check if any locks exist in target meals
        has_locks = False
        total_include = 0
        total_exclude = 0
        
        for meal in target_meals:
            include_count = len(workspace["locks"][meal]["include"])
            exclude_count = len(workspace["locks"][meal]["exclude"])
            
            if include_count > 0 or exclude_count > 0:
                has_locks = True
                total_include += include_count
                total_exclude += exclude_count
        
        if not has_locks:
            print(f"\nNo locks to clear for {meal_desc}")
            print()
            return
        
        # Show what will be cleared
        print(f"\nAbout to clear locks for {meal_desc}:")
        print(f"  Include: {total_include} items")
        print(f"  Exclude: {total_exclude} items")
        print()
        
        # Confirmation prompt
        response = input("Are you sure? (yes/no): ").strip().lower()
        
        if response != "yes":
            print("\nClear cancelled")
            print()
            return
        
        # Clear locks for target meals
        for meal in target_meals:
            workspace["locks"][meal]["include"] = {}
            workspace["locks"][meal]["exclude"] = []
        
        # Save workspace
        self._save_workspace(workspace)
        
        print(f"\nCleared all locks for {meal_desc}")
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
        
        # Initialize locks with meal-oriented structure if missing
        if "locks" not in workspace:
            workspace["locks"] = {}
        
        # Ensure all meal types exist
        for meal_type in MEAL_NAMES:
            if meal_type not in workspace["locks"]:
                workspace["locks"][meal_type] = {
                    "include": {},
                    "exclude": []
                }
            else:
                # Ensure both include/exclude exist
                if "include" not in workspace["locks"][meal_type]:
                    workspace["locks"][meal_type]["include"] = {}
                if "exclude" not in workspace["locks"][meal_type]:
                    workspace["locks"][meal_type]["exclude"] = []
        
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

    def _parse_meal_and_args(self, args: str) -> Tuple[Optional[str], str]:
        """
        Parse meal type from args string.
        
        Args:
            args: Full argument string
        
        Returns:
            Tuple of (meal_type_lowercase, remaining_args)
            Returns (None, args) if no valid meal type found
        """
        parts = args.strip().split(maxsplit=1)
        
        if not parts:
            return None, ""
        
        potential_meal = parts[0]
        
        # Check for "all"
        if potential_meal.lower() == "all":
            remaining = parts[1] if len(parts) > 1 else ""
            return "all", remaining
        
        # Try to normalize to canonical meal name
        normalized = normalize_meal_name(potential_meal)
        
        # Check if it's a valid meal type
        if normalized in MEAL_NAMES:
            remaining = parts[1] if len(parts) > 1 else ""
            return normalized.lower(), remaining  # Return lowercase for workspace keys
        
        # No meal type found - treat entire args as code/pattern
        return None, args
    
    def _get_meal_keys(self) -> List[str]:
        """
        Get lowercase meal type keys for workspace storage.
        
        Returns:
            List of lowercase meal type strings matching workspace format
        """
        return [m.lower() for m in MEAL_NAMES]