"""
Recipe command - show ingredient list for a code.
"""
from .base import Command, register_command


@register_command
class RecipeCommand(Command):
    """Show recipe/ingredients for a code."""
    
    name = "recipe"
    help_text = "Show recipe for code (recipe SO.11)"
    
    def execute(self, args: str) -> None:
        """
        Show recipe for a code.
        
        Args:
            args: Code to look up
        """
        if not args.strip():
            print("Usage: recipe <code>")
            print("Example: recipe SO.11")
            return
        
        code = args.strip().upper()
        
        # Look up in master
        entry = self.ctx.master.lookup_code(code)
        
        if not entry:
            print(f"\nCode '{code}' not found in master database.")
            print()
            return
        
        # Get recipe
        recipe = entry.get('recipe', '')
        
        if recipe:
            print()
            print(f"Recipe for {code} ({entry.get('option', '')}):")
            print()
            # Format ingredients nicely
            ingredients = recipe.split(',')
            for ingredient in ingredients:
                print(f"  • {ingredient.strip()}")
            print()
        else:
            option = entry.get('option', '')
            print(f"\nCode '{code}' exists: {option}")
            print("But no recipe/ingredients are defined.")
            print()
            """
            Show recipe for a code.
            
            Args:
                args: Code to look up
            """
            if not args.strip():
                print("Usage: recipe <code>")
                print("Example: recipe SO.11")
                return
            
            if not self.ctx.master:
                print("Recipes not available.")
                return
            
            code = args.strip().upper()
            
            # Show the recipe
            formatted = self.ctx.master.format_recipe(code)
            
            if formatted:
                print()
                print(formatted)
            else:
                print(f"\nNo recipe found for code '{code}'.")
                
                # Also show master info if code exists
                master_row = self.ctx.master.lookup_code(code)
                if master_row:
                    cols = self.ctx.master.cols
                    option = master_row.get(cols.option, "")
                    print(f"Code '{code}' exists in master: {option}")
                    print("But no recipe/ingredients are defined.")
                else:
                    print(f"Code '{code}' not found in master database.")
                
                print()