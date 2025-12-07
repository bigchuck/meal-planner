"""
Nutrients command - show micronutrients for a code.
"""
from .base import Command, register_command


@register_command
class NutrientsCommand(Command):
    """Show micronutrients for a code."""
    
    name = ("nutrients", "nutrient")
    help_text = "Show micronutrients for code (nutrients SO.11 [--format])"
    
    def execute(self, args: str) -> None:
        """
        Show micronutrients for a code.
        
        Args:
            args: Code to look up, optional --format flag
        """
        # Parse arguments
        parts = args.strip().split()
        if not parts:
            print("Usage: nutrients <code> [--format]")
            print("Example: nutrients SO.11")
            print("         nutrients SO.11 --format")
            return
        
        code = parts[0].upper()
        show_format = "--format" in parts
        
        if not self.ctx.nutrients:
            print("Micronutrients not available.")
            return
        
        # Get nutrients
        nutrients = self.ctx.nutrients.get_nutrients_for_code(code)
        
        if nutrients:
            if show_format:
                # Detailed table format
                self._show_detailed_format(code, nutrients)
            else:
                # Compact single-line format (aligned with find)
                self._show_compact_format(code, nutrients)
        else:
            print(f"\nNo micronutrient data for code '{code}'.")
            
            # Also show master info if code exists
            master_row = self.ctx.master.lookup_code(code)
            if master_row:
                cols = self.ctx.master.cols
                option = master_row.get(cols.option, "")
                print(f"Code '{code}' exists in master: {option}")
                print("But no micronutrient data is defined.")
            else:
                print(f"Code '{code}' not found in master database.")
            
            print()
    
    def _show_compact_format(self, code: str, nutrients: dict) -> None:
        """Show single-line format aligned with find command."""
        # Look up master info for section and option
        master_row = self.ctx.master.lookup_code(code)
        
        if master_row:
            cols = self.ctx.master.cols
            section = str(master_row.get(cols.section, ""))[:7]
            option = str(master_row.get(cols.option, ""))
        else:
            section = "???"
            option = "(not in master)"
        
        # Build micronutrient bracket string with 3-char abbreviations
        micro_parts = []
        
        # Map nutrients to abbreviated format
        abbrev_map = {
            'fiber_g': ('Fib', 'g'),
            'sodium_mg': ('Na', 'mg'),
            'potassium_mg': ('K', 'mg'),
            'vitA_mcg': ('A', 'mcg'),
            'vitC_mg': ('C', 'mg'),
            'iron_mg': ('Fe', 'mg'),
        }
        
        for nutrient_key, (abbrev, unit) in abbrev_map.items():
            if nutrient_key in nutrients:
                value = nutrients[nutrient_key]
                try:
                    # Format with 1 decimal if needed, otherwise integer
                    num = float(value)
                    if num == int(num):
                        micro_parts.append(f"{abbrev}={int(num)}{unit}")
                    else:
                        micro_parts.append(f"{abbrev}={num:.1f}{unit}")
                except (ValueError, TypeError):
                    micro_parts.append(f"{abbrev}=?{unit}")
        
        micro_str = " ".join(micro_parts)
        
        # Print in aligned format
        print()
        print(f"  {code:>8} | {section:<7} | {option} [{micro_str}]")
        print()
    
    def _show_detailed_format(self, code: str, nutrients: dict) -> None:
        """Show detailed table format."""
        print()
        print(f"[{code}] Micronutrients:")
        print("─" * 60)
        
        # Format as table
        for nutrient, value in nutrients.items():
            # Extract unit from nutrient name
            # fiber_g -> Fiber (g)
            # sodium_mg -> Sodium (mg)
            parts = nutrient.split("_")
            if len(parts) >= 2:
                name = parts[0].capitalize()
                unit = parts[1]
                label = f"{name} ({unit})"
            else:
                label = nutrient.capitalize()
            
            try:
                print(f"  {label:<20} {float(value):>8.1f}")
            except:
                print(f"  {label:<20} {str(value):>8}")
        
        print()