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
    help_text = "Show detailed breakdown (report [date] [--recipes] [--nutrients] [--meals] [--risk])"
    
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
        show_meals = "--meals" in parts or "--meal" in parts
        show_risk = "--risk" in parts        
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
        
        # Show meal breakdown if requested
        if show_meals and report:
            self._show_meals(report)
        
        # Show micronutrients if requested
        if show_nutrients and report:
            self._show_nutrients(report)
        
        # Show recipes if requested
        if show_recipes and report:
            self._show_recipes(report)

        if show_meals and show_risk and report:
            self._show_risk(report)
    
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
    
    def _show_meals(self, report):
        """Show meal breakdown with subtotals."""
        breakdown = report.get_meal_breakdown()
        
        if breakdown is None:
            print("\n(No time markers present - meal breakdown not available)\n")
            return
        
        print("=== Meal Breakdown ===")
        
        # Header
        print(f"{'':30} {'Cal':>6} {'P':>5} {'C':>5} {'F':>5} {'Sug':>6} {'GL':>4}")
        
        # Meal rows
        for meal_name, first_time, totals in breakdown:
            t = totals.rounded()
            label = f"{meal_name} ({first_time})"
            print(f"{label:30} {int(t.calories):>6} {int(t.protein_g):>5} "
                  f"{int(t.carbs_g):>5} {int(t.fat_g):>5} "
                  f"{int(t.sugar_g):>6} {int(t.glycemic_load):>4}")
        
        # Separator
        print("-" * 78)
        
        # Daily total
        t = report.totals.rounded()
        print(f"{'Daily Total':30} {int(t.calories):>6} {int(t.protein_g):>5} "
              f"{int(t.carbs_g):>5} {int(t.fat_g):>5} "
              f"{int(t.sugar_g):>6} {int(t.glycemic_load):>4}")
        
        print()
    
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
    
    def _show_risk(self, report):
        """Show nutritional risk assessment."""
        print("=== Risk Assessment ===")
        print()
        
        t = report.totals.rounded()
        risks = []
        
        # High sugar (>50g)
        if t.sugar_g > 50:
            risks.append(f"⚠ High sugar: {int(t.sugar_g)}g (>50g)")
        
        # High glycemic load (>100)
        if t.glycemic_load > 100:
            risks.append(f"⚠ High glycemic load: {int(t.glycemic_load)} (>100)")
        
        # Low protein (<100g)
        if t.protein_g < 100:
            risks.append(f"⚠ Low protein: {int(t.protein_g)}g (<100g)")
        
        # High fat percentage (>35% of calories)
        fat_cal = t.fat_g * 9
        fat_pct = (fat_cal / t.calories * 100) if t.calories > 0 else 0
        if fat_pct > 35:
            risks.append(f"⚠ High fat: {fat_pct:.0f}% of calories (>35%)")
        
        # High carb percentage (>60% of calories)
        carb_cal = t.carbs_g * 4
        carb_pct = (carb_cal / t.calories * 100) if t.calories > 0 else 0
        if carb_pct > 60:
            risks.append(f"⚠ High carbs: {carb_pct:.0f}% of calories (>60%)")
        
        # Very low calories (<1200)
        if t.calories < 1200:
            risks.append(f"⚠ Very low calories: {int(t.calories)} (<1200)")
        
        # Very high calories (>3000)
        if t.calories > 3000:
            risks.append(f"⚠ Very high calories: {int(t.calories)} (>3000)")
        
        if risks:
            for risk in risks:
                print(risk)
        else:
            print("✓ No significant nutritional risks detected")
        
        print()