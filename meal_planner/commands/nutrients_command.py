"""
Nutrients command - show micronutrients for a code.
"""
from .base import Command, register_command


@register_command
class NutrientsCommand(Command):
    """Show micronutrients for a code."""
    
    name = ("nutrients", "nutrient")
    help_text = "Show micronutrients for code (nutrients SO.11)"
    
    def execute(self, args: str) -> None:
        """
        Show micronutrients for a code.
        
        Args:
            args: Code to look up
        """
        if not args.strip():
            print("Usage: nutrients <code>")
            print("Example: nutrients SO.11")
            return
        
        if not self.ctx.nutrients:
            print("Micronutrients not available.")
            return
        
        code = args.strip().upper()
        
        # Get nutrients
        nutrients = self.ctx.nutrients.get_nutrients_for_code(code)
        
        if nutrients:
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