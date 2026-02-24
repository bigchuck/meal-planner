"""
Recipe command - show ingredient list for a code.
"""
import shlex
from typing import List
from .base import Command, register_command


@register_command
class RecipeCommand(Command):
    """Show recipe/ingredients for a code."""
    
    name = "recipe"
    help_text = "Show recipe for code (recipe SO.11 [--stage])"
    
    def execute(self, args: str) -> None:
        """
        Show recipe for a code.
        
        Args:
            args: Code to look up, with optional --stage flag
        """
        if not args.strip():
            print("Usage: recipe <code> [--stage]")
            print("Example: recipe SO.11")
            return

        # Parse --stage flag
        try:
            parts = shlex.split(args)
        except ValueError:
            parts = args.strip().split()

        stage = "--stage" in parts
        tokens = [p for p in parts if p != "--stage"]

        if not tokens:
            print("Usage: recipe <code> [--stage]")
            return

        code = tokens[0].upper()

        # Look up in master
        entry = self.ctx.master.lookup_code(code)

        if not entry:
            print(f"\nCode '{code}' not found in master database.")
            print()
            return

        # Build lines list
        lines: List[str] = []
        recipe = entry.get('recipe', '')

        if recipe:
            lines.append("")
            lines.append(f"Recipe for {code} ({entry.get('option', '')}):")
            lines.append("")
            for ingredient in recipe.split(','):
                lines.append(f"  • {ingredient.strip()}")
            lines.append("")
        else:
            option = entry.get('option', '')
            lines.append(f"\nCode '{code}' exists: {option}")
            lines.append("But no recipe/ingredients are defined.")
            lines.append("")

        # Print to screen
        for line in lines:
            print(line)

        # Stage if requested
        if stage:
            self._stage_recipe(code, entry, lines)

    def _stage_recipe(self, code: str, entry: dict, lines: List[str]) -> None:
        """
        Add recipe to staging buffer.

        Args:
            code: Food code
            entry: Master entry dict
            lines: Formatted output lines already printed to screen
        """
        if not self.ctx.staging_buffer:
            print("\nWarning: Staging buffer not configured, cannot stage.\n")
            return

        item_id = f"recipe:{code}"
        option = entry.get('option', '')
        label = f"Recipe: {code} ({option})" if option else f"Recipe: {code}"

        is_new = self.ctx.staging_buffer.add(item_id, label, lines)

        if is_new:
            print(f"✓ Staged: {label}\n")
        else:
            print(f"✓ Replaced staged item: {label}\n")