"""
Report command - detailed nutrient breakdown.
"""
from typing import List, Dict, Any, Optional, Tuple

from .base import Command, register_command
from meal_planner.reports.report_builder import ReportBuilder
from meal_planner.parsers import CodeParser
from meal_planner.glucose import GlucoseCalculator


@register_command
class ReportCommand(Command):
    """Show detailed nutrient breakdown."""
    
    name = "report"
    help_text = "Show detailed breakdown (report [date] [--recipes] [--nutrients] [--meals] [--risk])"

    def __init__(self, context):
        super().__init__(context)
        self.glucose_calc = GlucoseCalculator()

    
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
        if show_meals and show_risk and report:
            self._show_meals(report, True)        
        elif show_meals and report:
            self._show_meals(report)
        
        # Show micronutrients if requested
        if show_nutrients and report:
            self._show_nutrients(report)
        
        # Show recipes if requested
        if show_recipes and report:
            self._show_recipes(report)

        if show_risk and not show_meals and report:
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
    
    def _show_meals(self, report, show_risk=False):
        """Show meal breakdown with subtotals."""
        breakdown = report.get_meal_breakdown()
        
        if breakdown is None:
            print("\n(No time markers present - meal breakdown not available)\n")
            return
        
        print("=== Meal Breakdown ===")
        
        # Header
        if not show_risk:
            print(f"{'':30} {'Cal':>6} {'P':>5} {'C':>5} {'F':>5} {'Sug':>6} {'GL':>4}")
        else:
            print(f"{'':30} {'Cal':>6} {'P':>5} {'C':>5} {'F':>5} {'Sug':>6} {'GL':>4} {'Issues':>40}")
        
        # Meal rows
        meal_count = sum(1 for name, time, totals in breakdown if "SNACK" not in name)
        for meal_name, first_time, meal_totals in breakdown:
            t = meal_totals.rounded()
            label = f"{meal_name} ({first_time})"
            if not show_risk or "SNACK" in meal_name:
                print(f"{label:30} {int(t.calories):>6} {int(t.protein_g):>5} "
                      f"{int(t.carbs_g):>5} {int(t.fat_g):>5} "
                      f"{int(t.sugar_g):>6} {int(t.glycemic_load):>4}")
            else:
                risk_summary = self._get_risk_summary(meal_totals, meal_count)
                print(f"{label:30} {int(t.calories):>6} {int(t.protein_g):>5} "
                      f"{int(t.carbs_g):>5} {int(t.fat_g):>5} "
                      f"{int(t.sugar_g):>6} {int(t.glycemic_load):>4}    "
                      f"{risk_summary}")
        
        # Separator
        print("-" * 78)
        
        # Daily total
        t = report.totals.rounded()
        if not show_risk:
            print(f"{'Daily Total':30} {int(t.calories):>6} {int(t.protein_g):>5} "
                f"{int(t.carbs_g):>5} {int(t.fat_g):>5} "
                f"{int(t.sugar_g):>6} {int(t.glycemic_load):>4}")
        else:
            risk_summary = self._get_risk_summary(t, 1)
            print(f"{'Daily Total':30} {int(t.calories):>6} {int(t.protein_g):>5} "
                f"{int(t.carbs_g):>5} {int(t.fat_g):>5} "
                f"{int(t.sugar_g):>6} {int(t.glycemic_load):>4}    "
                f"{risk_summary}")
        print()

    def _show_nutrients(self, report):
        """Show micronutrients for codes in report."""
        if not self.ctx.nutrients:
            print("n(Micronutrients not available)n")
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
    
    """
        -----------------------------------------------------------------
        From Claude discussion 2025-11-20
        -----------------------------------------------------------------

    For each meal from "report --meals --risk"

    Each Meal Totals:
                                      Cal     P     C     F    Sug   GL   Issues
    BREAKFAST (08:00)                 500    31    22    33      2   11   High sugar (58g/50g), High fat (47%/35%)

    """

    def _get_risk_summary(self, totals, meal_count) -> str:
        """Show nutritional risk assessment."""
        risks = ""
        if meal_count == 0:
            return risks
        
        HIGH_SUGAR = int(50/meal_count)
        HIGH_GL = int(100/meal_count)
        LOW_PROTEIN = int(100/meal_count)
        HIGH_FAT = int(35/meal_count)
        HIGH_CARBS = int(60/meal_count)
        VLOW_CALORIES = int(1200/meal_count)
        VHIGH_CALORIES = int(3000/meal_count)

        # High sugar (>50g)
        if totals.sugar_g > HIGH_SUGAR:
            risks += f"High sugar ({int(totals.sugar_g)}g/{HIGH_SUGAR}g), "
        
        # High glycemic load (>100)
        if totals.glycemic_load > HIGH_GL:
            risks += f"High GL ({int(totals.glycemic_load)}/{HIGH_GL}), "
        
        # Low protein (<100g)
        if totals.protein_g < LOW_PROTEIN:
            risks += f"Low protein ({int(totals.protein_g)}g/{LOW_PROTEIN}g), "
        
        # High fat percentage (>35% of calories)
        fat_cal = totals.fat_g * 9
        fat_pct = (fat_cal / totals.calories * 100) if totals.calories > 0 else 0
        if fat_pct > HIGH_FAT:
            risks += f"High fat ({fat_pct:.0f}%/{HIGH_FAT}%), "
        
        # High carb percentage (>60% of calories)
        carb_cal = totals.carbs_g * 4
        carb_pct = (carb_cal / totals.calories * 100) if totals.calories > 0 else 0
        if carb_pct > HIGH_CARBS:
            risks += f"High carbs ({carb_pct:.0f}%/{HIGH_CARBS}%), "
        
        # Very low calories (<1200)
        if totals.calories < VLOW_CALORIES:
            risks += f"VLow calories ({int(totals.calories)}/{VLOW_CALORIES}), "
        
        # Very high calories (>3000)
        if totals.calories > VHIGH_CALORIES:
            risks += f"VHigh calories ({int(totals.calories)}/{VHIGH_CALORIES}), "

        if len(risks) == 0:
            risks += f"No significant nutritional risks detected, "
    
        return risks[:-2]

    """
    For each meal from "glucose"

    For the day total:
    === Glucose Analysis for 2025-01-15 ===

    Summary:
    Risk Score:      72 / 100
    Glycemic Index:  58
    Curve Type:      Moderate Spike
    Confidence:      High (0.89)

    Components:
    Carb Load:           45.2  → +35 risk
    Sugar Ratio:          0.38 → +15 risk
    Fiber Offset:        -5.0  → -8 risk
    Fat Modulation:      -8.5  → -12 risk
    Protein Balance:      0.82 → +2 risk
    [other factors...]
                        ─────────
    Total Risk Score:           72



    """
