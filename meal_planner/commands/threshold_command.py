# meal_planner/commands/threshold_command.py
"""
Threshold command for displaying meal planning configuration.

Provides dot-notation navigation through the thresholds JSON structure,
supporting both glucose monitoring and meal template configuration.
"""
import shlex
from .base import Command, register_command


@register_command
class ThresholdCommand(Command):
    """Display meal planning threshold configuration."""
    
    name = "threshold"
    help_text = "Display configuration (threshold --display <keys>)"
    
    def execute(self, args: str) -> None:
        """
        Display threshold configuration using dot-notation key paths.
        
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
            elif arg == "--all":
                show_all = True
                i += 1
            else:
                print(f"Unknown argument: {arg}")
                print("Usage: threshold [--display <keys>] [--all]")
                return
        
        # Get thresholds data
        data = self.ctx.thresholds.thresholds
        if not data:
            print("Error: Thresholds not loaded")
            return
        
        # Display
        self._display_threshold(data, key_path, show_all)
    
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