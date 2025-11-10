"""
Commands for managing pending day entries.
"""
from datetime import date
from .base import Command, register_command
from meal_planner.parsers import CodeParser
from meal_planner.models import MealItem, DailyTotals


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
        
        # Parse new codes
        new_items = CodeParser.parse(args.strip())
        
        if not new_items:
            print("No valid codes found.")
            return
        
        # Add items
        pending["items"].extend(new_items)
        self.ctx.pending_mgr.save(pending)
        
        # Check for fish codes (easter egg)
        has_fish = any(
            isinstance(it, dict) and 
            it.get("code", "").upper().startswith("FI.")
            for it in new_items
        )
        
        if has_fish:
            print("THANKS FOR ALL THE FISH!!!")
        
        # Show updated totals
        ShowCommand(self.ctx).execute("")


@register_command
class ShowCommand(Command):
    """Show current pending day totals."""
    
    name = "show"
    help_text = "Show current pending day totals"
    
    def execute(self, args: str) -> None:
        """Display pending day with totals."""
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception as e:
            print(f"\n(No active day. Use 'start' to begin.)\n")
            return
        
        if pending is None or not pending.get("items"):
            print("\n(No active day. Use 'start' to begin.)\n")
            return
        
        items = pending.get("items", [])
        totals, missing, code_strs = self._calculate_totals(items)
        
        print("\n--- Current Day ---")
        print(f"Date: {pending.get('date')}")
        print(f"Codes: {', '.join(code_strs) if code_strs else '(none)'}")
        print(f"Calories: {int(round(totals['cal']))}")
        print(f"Protein: {int(round(totals['prot_g']))} g")
        print(f"Carbs: {int(round(totals['carbs_g']))} g")
        print(f"Fat: {int(round(totals['fat_g']))} g")
        print(f"Sugars: {int(round(totals['sugar_g']))} g")
        print(f"GL: {int(round(totals['gl']))}")
        
        if missing:
            print(f"Missing codes (not included): {', '.join(missing)}")
        
        print("--------------------\n")
    
    def _calculate_totals(self, items: list):
        """
        Calculate totals from items list.
        
        Args:
            items: List of item dicts
        
        Returns:
            Tuple of (totals_dict, missing_codes, code_strings)
        """
        totals = {
            "cal": 0.0, "prot_g": 0.0, "carbs_g": 0.0,
            "fat_g": 0.0, "sugar_g": 0.0, "gl": 0.0
        }
        missing = []
        code_strs = []
        
        for item in items:
            # Time marker
            if "time" in item and item.get("time"):
                code_strs.append(f"@{item['time']}")
                continue
            
            # Code item
            if "code" not in item:
                continue
            
            code = str(item["code"]).upper()
            mult = float(item.get("mult", 1.0))
            
            # Look up in master
            nutrients = self.ctx.master.get_nutrient_totals(code, mult)
            
            if nutrients is None:
                missing.append(code)
                continue
            
            # Accumulate
            for key in totals.keys():
                totals[key] += nutrients.get(key, 0.0)
            
            # Format code string
            if mult < 0:
                amag = abs(mult)
                code_strs.append(
                    f"-{code}" if abs(amag - 1.0) < 1e-9 else f"-{code} x{amag:g}"
                )
            else:
                code_strs.append(
                    f"{code} x{mult:g}" if abs(mult - 1.0) > 1e-9 else code
                )
        
        return totals, missing, code_strs


@register_command
class DiscardCommand(Command):
    """Discard pending day without saving."""
    
    name = "discard"
    help_text = "Discard pending day without saving to log"
    
    def execute(self, args: str) -> None:
        """Clear pending without saving."""
        self.ctx.pending_mgr.clear()
        print("Pending day discarded (not saved to log).")


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
        
        # Calculate totals using ShowCommand's helper
        show_cmd = ShowCommand(self.ctx)
        totals, missing, code_strs = show_cmd._calculate_totals(items)
        
        # Show what we're saving
        show_cmd.execute("")
        
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
        self.ctx.log.append_entry(entry)
        self.ctx.log.save()
        
        # Clear pending
        self.ctx.pending_mgr.clear()
        
        print(f"Closed and saved to log. Pending cleared.")