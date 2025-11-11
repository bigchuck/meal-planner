"""
Report command - detailed nutrient breakdown.
"""
from .base import Command, register_command
from meal_planner.reports.report_builder import ReportBuilder
from meal_planner.parsers import CodeParser


@register_command
class ReportCommand(Command):
    """Show detailed nutrient breakdown."""
    
    name = "report"
    help_text = "Show detailed breakdown (report [date] [--recipes] [--nutrients])"
    
    def execute(self, args: str) -> None:
        """
        Show detailed report.
        
        Args:
            args: Optional date (YYYY-MM-DD) and/or flags
        """
        # Parse arguments
        parts = args.strip().split() if args.strip() else []
        
        show_recipes = "--recipes" in parts or "--recipe" in parts
        show_nutrients = "--nutrients" in parts or "--nutrient" in parts or "--micro" in parts
        
        # Remove flags from parts
        date_parts = [p for p in parts if not p.startswith("--")]
        
        builder = ReportBuilder(self.ctx.master)
        
        if not date_parts:
            # Report from pending
            report = self._report_pending(builder)
        else:
            # Report from log date
            query_date = date_parts[0]
            report = self._report_log_date(builder, query_date)
        
        # Show micronutrients if requested
        if show_nutrients and report:
            self._show_nutrients(report)
        
        # Show recipes if requested
        if show_recipes and report:
            self._show_recipes(report)
    
    def _report_pending(self, builder: ReportBuilder):
        """Report from pending day."""
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            pending = None
        
        if pending is None or not pending.get("items"):
            print("\n(No active day. Use 'start' and 'add' first.)\n")
            return None
        
        items = pending.get("items", [])
        date = pending.get("date", "unknown")
        
        report = builder.build_from_items(items, title=f"Report for {date}")
        report.print()
        return report
    
    def _report_log_date(self, builder: ReportBuilder, query_date: str):
        """Report from log date."""
        # Get all entries for this date
        entries = self.ctx.log.get_entries_for_date(query_date)
        
        if entries.empty:
            print(f"\nNo log entries found for {query_date}.\n")
            return None
        
        # Parse codes from all entries for this date
        codes_col = self.ctx.log.cols.codes
        all_codes = ", ".join([
            str(v) for v in entries[codes_col].fillna("") 
            if str(v).strip()
        ])
        
        if not all_codes.strip():
            print(f"\nNo codes found for {query_date}.\n")
            return None
        
        # Parse into items
        items = CodeParser.parse(all_codes)
        
        report = builder.build_from_items(items, title=f"Report for {query_date}")
        report.print()
        return report
    
    def _show_nutrients(self, report):
        """Show micronutrients for codes in report."""
        if not self.ctx.nutrients:
            print("\n(Micronutrients not available)\n")
            return
        
        # Track codes we've seen (to show each only once)
        seen_codes = set()
        codes_in_order = []
        
        # Get codes in order they appear
        for row in report.rows:
            code = row.code
            if code not in seen_codes:
                if self.ctx.nutrients.has_nutrients(code):
                    codes_in_order.append(code)
                    seen_codes.add(code)
        
        if not codes_in_order:
            print("\n(No micronutrient data for these items)\n")
            return
        
        # Get available nutrient columns
        available = self.ctx.nutrients.get_available_nutrients()
        if not available:
            print("\n(No micronutrient data available)\n")
            return
        
        # Show micronutrients
        print("=== Micronutrients ===")
        print()
        
        # Header
        print(f"{'Code':<10} {' '.join(f'{n[:6]:>8}' for n in available)}")
        print("-" * (10 + len(available) * 9))
        
        # Data rows
        for code in codes_in_order:
            nutrients = self.ctx.nutrients.get_nutrients_for_code(code)
            if nutrients:
                values = []
                for nutrient in available:
                    val = nutrients.get(nutrient, 0)
                    try:
                        # Format as number
                        values.append(f"{float(val):>8.1f}")
                    except:
                        values.append(f"{'':>8}")
                
                print(f"{code:<10} {' '.join(values)}")
        
        print()
    
    def _show_recipes(self, report):
        """Show recipes for codes in report (once per code, in order)."""
        if not self.ctx.recipes:
            print("(Recipes not available)")
            return
        
        # Track codes we've seen (to show each recipe only once)
        seen_codes = set()
        codes_in_order = []
        
        # Get codes in order they appear
        for row in report.rows:
            code = row.code
            if code not in seen_codes:
                if self.ctx.recipes.has_recipe(code):
                    codes_in_order.append(code)
                    seen_codes.add(code)
        
        if not codes_in_order:
            print("\n(No recipes available for these items)\n")
            return
        
        # Show recipes
        print("=== Recipes ===")
        print()
        
        for code in codes_in_order:
            formatted = self.ctx.recipes.format_recipe(code)
            if formatted:
                print(formatted)