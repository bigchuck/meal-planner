"""
Commands for managing pending day entries.
"""
from datetime import date
from .base import Command, register_command
from meal_planner.parsers import CodeParser
from meal_planner.models import MealItem, DailyTotals
from meal_planner.utils.pending_display import calculate_totals, print_day_summary


@register_command
class StartCommand(Command):
    """Start a new pending day."""
    
    name = "start"
    help_text = "Start new pending day (e.g., start 2025-01-15)"
    
    def execute(self, args: str) -> None:
        """
        Start a new pending day.
        
        Args:
            args: Optional date (YYYY-MM-DD), defaults to today
        """
        # Check if there's already active pending
        try:
            existing = self.ctx.pending_mgr.load()
        except Exception:
            existing = None
        
        if existing and existing.get("items"):
            print("Active pending day already exists.")
            print("Use 'close' to save it or 'discard' to clear it before starting a new day.")
            return
        
        target_date = args.strip() if args.strip() else str(date.today())
        
        pending = {
            "date": target_date,
            "items": []
        }
        
        self.ctx.pending_mgr.save(pending)
        self.ctx.pending_source = "normal"
        print(f"Pending day started for {target_date}.")


@register_command
class AddCommand(Command):
    """Add items to pending day."""
    
    name = "add"
    help_text = "Add codes to pending day (e.g., add B.1 *1.5, S2.4)"
    
    def execute(self, args: str) -> None:
        """
        Add codes to pending day.
        
        Args:
            args: Codes string to parse and add
        """
        if not args.strip():
            print("Usage: add <codes>")
            return
        
        was_empty = (self.ctx.pending_source == "empty")

        # Load or create pending
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            pending = None
        
        if pending is None:
            pending = {
                "date": str(date.today()),
                "items": []
            }
            was_empty = True
        
        # Resolve items: search mode, direct lookup, or fallback to code parser
        from meal_planner.commands.add_resolver import resolve_add_args
        from meal_planner.parsers.alias_expander import expand_aliases
        resolved = resolve_add_args(args.strip(), self.ctx)
        if resolved is None:
            return
        if resolved == 'fallback':
            new_items = expand_aliases(args.strip(), self.ctx.aliases)
        else:
            new_items = resolved

        if not new_items:
            print("No valid codes found.")
            return
        
        # Reject CM. codes (combo codes must be added via alias)
        combo_codes = [
            item['code'] for item in new_items 
            if 'code' in item and item['code'].upper().startswith('CM.')
        ]
        if combo_codes:
            print("\nError: Cannot add combo codes (CM.) directly.")
            print("Combo codes must be added via their alias name.")
            print(f"Rejected: {', '.join(combo_codes)}")
            return

        # Add items
        pending["items"].extend(new_items)
        self.ctx.pending_mgr.save(pending)
        
        if was_empty:
            self.ctx.pending_source = "normal"
        # Otherwise preserve current state (editing, stash_pop, normal)

        # Check for fish codes (easter egg)
        has_fish = any(
            isinstance(it, dict) and 
            it.get("code", "").upper().startswith("FI.")
            for it in new_items
        )
        
        if has_fish:
            print("THANKS FOR ALL THE FISH!!!")
        
        # Show updated totals
        print_day_summary(self.ctx)


@register_command
class CloseCommand(Command):
    """Finalize pending day and save to log."""
    
    name = "close"
    help_text = "Finalize pending day and save to log"
    
    def execute(self, args: str) -> None:
        """Save pending to log and clear."""
        # Prevent closing during log edit
        if self.ctx.editing_date:
            print("Cannot close while editing a log entry.")
            print("Use 'applylog' to save changes, or 'discard' to cancel.")
            return
        
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            pending = None
        
        if pending is None or not pending.get("items"):
            print("Nothing to close. Start and add items first.")
            return
        
        items = pending.get("items", [])
        
        # Calculate totals
        totals, missing, code_strs = calculate_totals(self.ctx.master, items)

        # Show what we're saving
        print_day_summary(self.ctx)
        
        # Create log entry
        entry = {
            "date": pending.get("date", str(date.today())),
            "codes": ", ".join(code_strs),
            "cal": int(round(totals["cal"])),
            "prot_g": int(round(totals["prot_g"])),
            "carbs_g": int(round(totals["carbs_g"])),
            "fat_g": int(round(totals["fat_g"])),
            "sugar_g": int(round(totals["sugar_g"])),
            "gl": int(round(totals["gl"]))
        }
        
        # Append to log
        self.ctx.log.load()
        self.ctx.log.append_entry(entry)
        self.ctx.log.save()
        
        # Clear pending
        self.ctx.pending_mgr.clear()

        self.ctx.pending_source = "empty"
        
        print(f"Closed and saved to log. Pending cleared.")