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
    category = "Pending"
    help_text = "Start new pending day (e.g., start 2025-01-15)"
    overview_help = (
        "start  —  Begin a new pending day\n"
        "\n"
        "Usage:\n"
        "  start              Start pending for today\n"
        "  start YYYY-MM-DD   Start pending for a specific date\n"
        "\n"
        "Fails if a pending day with items is already active — 'close' or\n"
        "'discard' it first."
    )


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
    category = "Pending"
    help_text = "Add codes to pending day (e.g., add B.1 *1.5, S2.4)"
    overview_help = (
        "add  —  Add food codes to the pending day\n"
        "\n"
        "Usage: add <codes>\n"
        "  add B.1                     One item\n"
        "  add B.1 *1.5, S2.4          Multiplier, then a second item\n"
        "  add chicken                 No comma / no known code -> fuzzy name search\n"
        "\n"
        "Starts a pending day automatically if none is active. Rejects CM. combo\n"
        "codes (add those via their alias name instead). See 'help add --detail'\n"
        "for the full code syntax (groups, subtraction, time markers, search mode)."
    )
    detailed_help = (
        "add  —  Add food codes to the pending day\n"
        "\n"
        "Usage: add <codes>\n"
        "\n"
        "Code syntax (comma-separated list of codes/expressions):\n"
        "  B.1                        Simple code, multiplier defaults to 1\n"
        "  L.3x2, FI.9 x5.7/4         Multiplier (x or *, integer/decimal/fraction)\n"
        "  (FR.1, FR.2) *.5           Group: apply one multiplier to several codes\n"
        "  D.10-VE.T1                 Subtraction: remove VE.T1's nutrition from D.10\n"
        "  @11:30 (DINNER)            Time marker, with optional meal-name override\n"
        "\n"
        "Fuzzy search mode (when args aren't a comma-separated code list):\n"
        "  add chicken                Search by name; a single unambiguous hit is\n"
        "                              added directly, multiple hits print a\n"
        "                              numbered list\n"
        "  add chicken #2              Add the #2 result from a prior conflict list\n"
        "  add chicken x1.5            Trailing multiplier applies to the match\n"
        "  add chicken --last           Add the most recently logged matching item\n"
        "                              (scans pending, then the last 3 days of log)\n"
        "\n"
        "Notes:\n"
        "  - CM. combo codes cannot be added directly — add them via their alias.\n"
        "  - Prints the updated day totals after adding.\n"
        "\n"
        "See also: ins (insert at a position), rm/move/setmult (edit existing items)."
    )


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
    category = "Pending"
    help_text = "Finalize pending day and save to log"
    overview_help = (
        "close  —  Finalize the pending day and save it to the log\n"
        "\n"
        "Usage: close\n"
        "\n"
        "Calculates totals, appends an entry to the daily log CSV, then clears\n"
        "the pending day. Blocked while a log entry is being edited (applylog first)."
    )


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