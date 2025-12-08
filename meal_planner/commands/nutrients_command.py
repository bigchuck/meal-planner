"""
Nutrients command - show micronutrients for a code.
"""
import shlex

from .base import Command, register_command
from meal_planner.reports.report_builder import ReportBuilder
from meal_planner.parsers import CodeParser
from meal_planner.utils.time_utils import normalize_meal_name


@register_command
class NutrientsCommand(Command):
    """Show micronutrients for a code."""
    
    name = ("nutrients", "nutrient")
    help_text = "Show micronutrients (nutrients SO.11 or [date] --meals or [date] --meal \"MEAL NAME\")"
    
    def execute(self, args: str) -> None:
        """
        Show micronutrients for a code, all meals, or specific meal.
        
        Args:
            args: Code to look up, [date] --meals, or [date] --meal MEALNAME
        """
        if not args.strip():
            print("Usage: nutrients <code>")
            print("   or: nutrients [date] --meals")
            print("   or: nutrients [date] --meal <MEALNAME>")
            print("\nExamples:")
            print("  nutrients SO.11")
            print("  nutrients --meals")
            print("  nutrients 2025-01-15 --meals")
            print("  nutrients --meal BREAKFAST")
            print("  nutrients --meal \"MORNING SNACK\"")
            print("  nutrients 2025-01-15 --meal LUNCH")
            return
        
        if not self.ctx.nutrients:
            print("Micronutrients not available.")
            return
        
        # Parse arguments (handles quotes properly)
        try:
            parts = shlex.split(args.strip())
        except ValueError:
            # Fallback to simple split if shlex fails
            parts = args.strip().split()
        
        # Check if first part is a date (YYYY-MM-DD format)
        date_arg = None
        start_idx = 0
        if len(parts) > 0 and len(parts[0]) == 10 and parts[0][4] == '-' and parts[0][7] == '-':
            date_arg = parts[0]
            start_idx = 1
        
        # Check for --meals flag (all meals)
        if start_idx < len(parts) and parts[start_idx] == "--meals":
            # Validate no extra tokens
            if len(parts) > start_idx + 1:
                print("Error: Incorrect number of arguments")
                return
            self._show_all_meals_nutrients(date_arg)
            return
        
        # Check for --meal flag (specific meal)
        if start_idx < len(parts) and parts[start_idx] == "--meal":
            if start_idx + 1 >= len(parts):
                print("Error: --meal requires a meal name")
                print("Example: nutrients --meal BREAKFAST")
                print("   or: nutrients --meal \"MORNING SNACK\"")
                return
            
            # Validate no extra tokens after meal name
            if len(parts) > start_idx + 2:
                print("Error: Incorrect number of arguments")
                return
            
            # Take only the next argument (use quotes for multi-word names)
            meal_name = normalize_meal_name(parts[start_idx + 1])
            self._show_meal_nutrients(meal_name, date_arg)
            return
        
        # If we have a date and no flag, that's an error
        if date_arg:
            print("Error: Date must be followed by --meals or --meal")
            print("Examples:")
            print("  nutrients 2025-01-15 --meals")
            print("  nutrients 2025-01-15 --meal BREAKFAST")
            return
        
        # Single code lookup
        code = args.strip().upper()
        
        # Get nutrients
        nutrients = self.ctx.nutrients.get_nutrients_for_code(code)
        
        if nutrients:
            print()
            print(f"[{code}] Micronutrients:")
            print("-" * 60)
            
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
    
    def _show_all_meals_nutrients(self, date_arg: str = None) -> None:
        """
        Show micronutrient totals for all meals.
        
        Args:
            date_arg: Optional date (YYYY-MM-DD) for log lookup
        """
        builder = ReportBuilder(self.ctx.master, self.ctx.nutrients)
        
        if date_arg:
            # Get from log
            report = self._get_log_report(builder, date_arg)
            date_label = date_arg
        else:
            # Get from pending
            report = self._get_pending_report(builder)
            date_label = "pending"
        
        if report is None:
            return
        
        # Get meal breakdown
        breakdown = report.get_meal_breakdown()
        
        if breakdown is None:
            print("\n(No time markers present - meal breakdown not available)\n")
            print("Add time markers to your meals using '@HH:MM' format:")
            print("  Example: add @08:00, B.1, S2.4")
            return
        
        # Display micronutrients for all meals
        print(f"\n=== Micronutrients by Meal [{date_label}] ===\n")
        
        # Header aligned with report --meals format
        print(f"{'':30} {'Fiber':>6} {'Sodium':>7} {'Potass':>7} {'VitA':>7} {'VitC':>6} {'Iron':>6}")
        print(f"{'':30} {'(g)':>6} {'(mg)':>7} {'(mg)':>7} {'(mcg)':>7} {'(mg)':>6} {'(mg)':>6}")
        print("-" * 78)
        
        # Meal rows
        for meal_name, first_time, meal_totals in breakdown:
            label = f"{meal_name} ({first_time})"
            print(f"{label:30} {int(meal_totals.fiber_g):>6} {int(meal_totals.sodium_mg):>7} "
                  f"{int(meal_totals.potassium_mg):>7} {int(meal_totals.vitA_mcg):>7} "
                  f"{int(meal_totals.vitC_mg):>6} {int(meal_totals.iron_mg):>6}")
        
        # Separator
        print("-" * 78)
        
        # Daily total
        t = report.totals
        print(f"{'Daily Total':30} {int(t.fiber_g):>6} {int(t.sodium_mg):>7} "
              f"{int(t.potassium_mg):>7} {int(t.vitA_mcg):>7} "
              f"{int(t.vitC_mg):>6} {int(t.iron_mg):>6}")
        
        print()
    
    def _show_meal_nutrients(self, meal_name: str, date_arg: str = None) -> None:
        """
        Show micronutrient totals for a specific meal.
        
        Args:
            meal_name: Meal name (BREAKFAST, LUNCH, etc.)
            date_arg: Optional date (YYYY-MM-DD) for log lookup
        """
        builder = ReportBuilder(self.ctx.master, self.ctx.nutrients)
        
        if date_arg:
            # Get from log
            report = self._get_log_report(builder, date_arg)
            date_label = date_arg
        else:
            # Get from pending
            report = self._get_pending_report(builder)
            date_label = "pending"
        
        if report is None:
            return
        
        # Get meal breakdown
        breakdown = report.get_meal_breakdown()
        
        if breakdown is None:
            print("\n(No time markers present - meal breakdown not available)\n")
            print("Add time markers to your meals using '@HH:MM' format:")
            print("  Example: add @08:00, B.1, S2.4")
            return
        
        # Find the requested meal
        meal_data = None
        for m_name, m_time, m_totals in breakdown:
            if m_name == meal_name:
                meal_data = (m_name, m_time, m_totals)
                break
        
        if meal_data is None:
            print(f"\n(No meal found matching '{meal_name}')\n")
            available = [m[0] for m in breakdown]
            print(f"Available meals: {', '.join(available)}")
            return
        
        m_name, m_time, m_totals = meal_data
        
        # Display micronutrients
        print(f"\n=== Micronutrients for {m_name} ({m_time}) [{date_label}] ===\n")
        
        # Header aligned with report --meals format
        print(f"{'':30} {'Fiber':>6} {'Sodium':>7} {'Potass':>7} {'VitA':>7} {'VitC':>6} {'Iron':>6}")
        print(f"{'':30} {'(g)':>6} {'(mg)':>7} {'(mg)':>7} {'(mcg)':>7} {'(mg)':>6} {'(mg)':>6}")
        print("-" * 78)
        
        # Data row
        label = f"{m_name} ({m_time})"
        print(f"{label:30} {int(m_totals.fiber_g):>6} {int(m_totals.sodium_mg):>7} "
              f"{int(m_totals.potassium_mg):>7} {int(m_totals.vitA_mcg):>7} "
              f"{int(m_totals.vitC_mg):>6} {int(m_totals.iron_mg):>6}")
        
        print()
    
    def _get_pending_report(self, builder):
        """Get report from pending."""
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            pending = None
        
        if pending is None or not pending.get("items"):
            print("\n(No active day. Use 'start' and 'add' first.)\n")
            return None
        
        items = pending.get("items", [])
        return builder.build_from_items(items, title="Nutrient Analysis")
    
    def _get_log_report(self, builder, query_date):
        """Get report from log date."""
        entries = self.ctx.log.get_entries_for_date(query_date)
        
        if entries.empty:
            print(f"\nNo log entries found for {query_date}.\n")
            return None
        
        codes_col = self.ctx.log.cols.codes
        all_codes = ", ".join([
            str(v) for v in entries[codes_col].fillna("") 
            if str(v).strip()
        ])
        
        if not all_codes.strip():
            print(f"\nNo codes found for {query_date}.\n")
            return None
        
        items = CodeParser.parse(all_codes)
        return builder.build_from_items(items, title="Nutrient Analysis")