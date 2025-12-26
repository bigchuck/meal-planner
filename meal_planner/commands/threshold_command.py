# meal_planner/commands/threshold_command.py
"""
Threshold command for displaying meal planning configuration.

Provides dot-notation navigation through the thresholds JSON structure,
supporting both glucose monitoring and meal template configuration.
"""
import shlex
from .base import Command, CommandHistoryMixin, register_command


@register_command
class ThresholdCommand(Command, CommandHistoryMixin):
    """Display meal planning threshold configuration."""
    
    name = "threshold"
    help_text = "Display configuration (threshold --display <keys>)"
    
    def execute(self, args: str) -> None:
        """
        Display threshold configuration using dot-notation key paths.
        
        Standard mode:
            threshold                                     -> List top-level sections
            threshold --display glucose_scoring           -> Show glucose scoring keys
            threshold --display meal_templates.breakfast --meal breakfast
        
        History support:
            threshold --history 5 --meal breakfast
            threshold --use 2 --meal lunch [other flags...]

        Args:
            args: Command arguments
        
        Examples:
            threshold                                     -> List top-level sections
            threshold --display glucose_scoring           -> Show glucose scoring keys
            threshold --display meal_templates.breakfast  -> Show breakfast templates
            threshold --display meal_templates.breakfast.protein_low_carb --all
        """
        if not self._check_thresholds("threshold"):
            return
        
        # Parse args
        args_list = shlex.split(args) if args else []
        
        key_path = ""
        show_all = False
        meal_name = None
        history_limit = None
        use_index = None
        
        i = 0
        while i < len(args_list):
            arg = args_list[i]
            
            if arg == "--display":
                if i + 1 < len(args_list):
                    key_path = args_list[i + 1]
                    i += 2
                else:
                    print("Error: --display requires a key path")
                    return
            elif arg == "--meal":
                if i + 1 < len(args_list):
                    meal_name = args_list[i + 1]
                    i += 2
                else:
                    print("Error: --meal requires a meal name")
                    return
            elif arg == "--all":
                show_all = True
                i += 1

            elif arg == "--history":
                if i + 1 < len(args_list):
                    try:
                        history_limit = int(args_list[i + 1])
                        i += 2
                    except ValueError:
                        print("Error: --history requires a number")
                        return
                else:
                    print("Error: --history requires a number")
                    return
            
            elif arg == "--use":
                if i + 1 < len(args_list):
                    try:
                        use_index = int(args_list[i + 1])
                        i += 2
                    except ValueError:
                        print("Error: --use requires a number")
                        return
                else:
                    print("Error: --use requires a number")
                    return

            else:
                print(f"Unknown argument: {arg}")
                print("Usage: threshold [--display <keys>] [--all] [--meal <meal>]")
                print("   or: threshold --history <n> --meal <meal>")
                print("   or: threshold --use <n> --meal <meal> [other options...]")
                return

        # Handle --history mode
        if history_limit is not None:
            if use_index is not None:
                print("Error: --history and --use are mutually exclusive")
                return
            if key_path or show_all:
                print("Error: --history cannot be combined with display parameters")
                return
            if meal_name is None:
                print("Error: --history requires --meal flag")
                print("Example: threshold --history 5 --meal breakfast")
                return
            
            self._display_command_history("threshold", meal_name, history_limit)
            return
    
        # Handle --use mode
        if use_index is not None:
            if meal_name is None:
                print("Error: --use requires --meal flag")
                print("Example: threshold --use 1 --meal breakfast")
                return
            
            # Load params from history
            params = self._get_params_from_history("threshold", meal_name, use_index)
            if params is None:
                print(f"Error: No history entry #{use_index} for meal '{meal_name}'")
                print(f"Use: threshold --history 10 --meal {meal_name}")
                return
        
            # Re-parse the historical params
            print(f"Using history #{use_index}: {params}")
        
            # Re-execute with historical params
            return self.execute(params)


        # Get thresholds data
        data = self.ctx.thresholds.thresholds
        if not data:
            print("Error: Thresholds not loaded")
            return
        
        # Display
        self._display_threshold(data, key_path, show_all)

        # Record in history if we used --display and --meal
        if key_path and meal_name:
            params_for_history = f"--display {key_path} --meal {meal_name}"
            if show_all:
                params_for_history += " --all"
            self._record_command_history("threshold", params_for_history)

    
    def _display_threshold(self, data: dict, key_path: str = "", show_all: bool = False):
        """
        Display threshold configuration at the specified key path.
        
        Args:
            data: Full thresholds dictionary
            key_path: Dot-separated key path (empty = top level)
            show_all: Show all details recursively
        """
        if not key_path:
            # Naked command - show only top-level keys
            print("Configuration sections:")
            for key in sorted(data.keys()):
                print(f"  {key}")
            return
        
        # Navigate to specified path
        value, remaining = self._navigate_keys(data, key_path)
        
        if value is None:
            print(f"Error: Key path not found: {key_path}")
            if remaining:
                print(f"  Could not find: {remaining}")
            return
        
        # Display based on type and depth
        if isinstance(value, dict):
            if show_all:
                # Recursive display of entire subtree
                print(f"{key_path}:")
                for line in self._format_value(value, indent=1):
                    print(line)
            else:
                # Just show next level keys
                print(f"{key_path}:")
                for key in sorted(value.keys()):
                    print(f"  {key}")
        
        elif isinstance(value, list):
            # Lists always show full content
            print(f"{key_path}:")
            for line in self._format_value(value, indent=1):
                print(line)
        
        else:
            # Scalar value - just display it
            print(f"{key_path}: {value}")
    
    def _navigate_keys(self, data: dict, key_path: str) -> tuple:
        """
        Navigate through nested dictionary using dot-separated key path.
        
        Args:
            data: Root dictionary
            key_path: Dot-separated keys
        
        Returns:
            (value, remaining_path) where remaining_path is empty if exact match found
        """
        if not key_path:
            return data, ""
        
        keys = key_path.split('.')
        current = data
        
        for i, key in enumerate(keys):
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                # Key not found - return None and remaining path
                remaining = '.'.join(keys[i:])
                return None, remaining
        
        return current, ""
    
    def _format_value(self, value, indent: int = 0):
        """
        Format a value for display with ASCII-only output.
        
        Args:
            value: Value to format (dict, list, or scalar)
            indent: Current indentation level
        
        Returns:
            List of formatted lines
        """
        prefix = "  " * indent
        lines = []
        
        if isinstance(value, dict):
            for key, val in value.items():
                if isinstance(val, dict):
                    # Check if this is a simple dict (all values are scalars)
                    if all(isinstance(v, (str, int, float, type(None))) for v in val.values()):
                        # Compact single-line format for simple dicts
                        parts = [f"{k}: {v}" for k, v in val.items()]
                        lines.append(f"{prefix}{key}: {', '.join(parts)}")
                    else:
                        # Nested dict - show key and recurse
                        lines.append(f"{prefix}{key}:")
                        lines.extend(self._format_value(val, indent + 1))
                elif isinstance(val, list):
                    lines.append(f"{prefix}{key}:")
                    lines.extend(self._format_value(val, indent + 1))
                else:
                    lines.append(f"{prefix}{key}: {val}")
        
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                if isinstance(item, (dict, list)):
                    lines.append(f"{prefix}[{idx}]")
                    lines.extend(self._format_value(item, indent + 1))
                else:
                    lines.append(f"{prefix}[{idx}] {item}")
        
        else:
            # Scalar value
            lines.append(f"{prefix}{value}")
        
        return lines