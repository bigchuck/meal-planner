"""
Report command - detailed nutrient breakdown.
"""
from typing import List, Dict, Any, Optional, Tuple
import shlex
from datetime import datetime, date as date_obj

from .base import Command, register_command
from meal_planner.reports.report_builder import ReportBuilder
from meal_planner.parsers import CodeParser
from meal_planner.glucose import GlucoseCalculator
from meal_planner.utils.time_utils import categorize_time, normalize_meal_name


@register_command
class ReportCommand(Command):
    """Show detailed nutrient breakdown."""
    
    name = "report"
    help_text = "Show detailed breakdown (report [date] [--recipes] [--nutrients] [--meals] [--meal \"NAME\"] [--risk] [--verbose])"
    def __init__(self, context):
        super().__init__(context)
        self.glucose_calc = GlucoseCalculator()

    
    def execute(self, args: str) -> None:
        """
        Show detailed report.
        
        Args:
            args: Optional date (YYYY-MM-DD) and/or flags
        """
        # Parse arguments (handles quotes properly)
        try:
            parts = shlex.split(args.strip()) if args.strip() else []
        except ValueError:
            # Fallback to simple split if shlex fails
            parts = args.strip().split() if args.strip() else []
        
        show_recipes = "--recipes" in parts or "--recipe" in parts
        show_nutrients = "--nutrients" in parts or "--nutrient" in parts or "--micro" in parts
        show_meals = "--meals" in parts
        show_risk = "--risk" in parts
        verbose = "--verbose" in parts
        stage = "--stage" in parts

        # --stage auto-enables verbose
        if stage:
            verbose = True 
    
        if show_risk:
            if not self._check_thresholds("Risk analysis"):
                show_risk = False
        
        # Check for --meal <n> (requires quotes for multi-word names)
        meal_name = None
        if "--meal" in parts:
            meal_idx = parts.index("--meal")
            if meal_idx + 1 < len(parts):
                # Take only the next argument (use quotes for multi-word names)
                meal_name = normalize_meal_name(parts[meal_idx + 1])
        
        # Remove flags and their arguments from parts to get date
        date_parts = []
        skip_next = False
        for i, p in enumerate(parts):
            if skip_next:
                skip_next = False
                continue
            if p.startswith("--"):
                if p == "--meal":
                    skip_next = True  # Skip the next argument (meal name)
                continue
            date_parts.append(p)
        
        builder = ReportBuilder(self.ctx.master, self.ctx.nutrients)
        
        # Get items first
        if not date_parts:
            items, date = self._get_pending_items()
        else:
            query_date = date_parts[0]
            items, date = self._get_log_items(query_date)
        
        if items is None:
            return
        
        # Filter to specific meal if requested
        if meal_name:
            items = self._filter_to_meal(items, meal_name)
            if not items:
                print(f"\nNo items found for meal '{meal_name}'\n")
                return
            report = builder.build_from_items(items, title=f"Report for {date} - {meal_name}")
        else:
            report = builder.build_from_items(items, title=f"Report for {date}")
        
        if stage:
            self._stage_report(report, date, meal_name)

            # Show main report (abbreviated if staging, normal otherwise)
        if stage:
            # Show abbreviated format to screen
            lines = report.format_abbreviated()
            for line in lines:
                print(line)
        else:
            # Normal display
            report.print(verbose=verbose)
        
        if not stage:
            # Show meal breakdown if requested (not shown for single meal filter)
            if show_meals and not meal_name:
                if show_risk:
                    self._show_meals(report, True)
                else:
                    self._show_meals(report)
            
            # Show micronutrients if requested
            if show_nutrients and report:
                self._show_nutrients(report)
            
            # Show recipes if requested
            if show_recipes and report:
                self._show_recipes(report)

            if show_risk and not show_meals and not meal_name and report:
                self._show_risk(report)
    
    def _get_pending_items(self) -> Tuple[Optional[List], str]:
        """Get items from pending day."""
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            pending = None
        
        if pending is None or not pending.get("items"):
            print("\n(No active day. Use 'start' and 'add' first.)\n")
            return None, ""
        
        items = pending.get("items", [])
        date = pending.get("date", "unknown")
        return items, date
    
    def _get_log_items(self, query_date: str) -> Tuple[Optional[List], str]:
        """Get items from log date."""
        # Get all entries for this date
        entries = self.ctx.log.get_entries_for_date(query_date)
        
        if entries.empty:
            print(f"\nNo log entries found for {query_date}.\n")
            return None, ""
        
        # Parse codes from all entries for this date
        codes_col = self.ctx.log.cols.codes
        all_codes = ", ".join([
            str(v) for v in entries[codes_col].fillna("") 
            if str(v).strip()
        ])
        
        if not all_codes.strip():
            print(f"\nNo codes found for {query_date}.\n")
            return None, ""
        
        # Parse into items
        items = CodeParser.parse(all_codes)
        return items, query_date
    
    def _filter_to_meal(self, items: List, meal_name: str) -> List:
        """Filter items to only those in the specified meal."""
        filtered = []
        current_meal = None
        
        for item in items:
            # Check if this is a time marker (has 'time' key but no 'code' key)
            if isinstance(item, dict) and 'time' in item and 'code' not in item:
                # Categorize meal name from time
                time_str = item.get('time', '')
                current_meal = categorize_time(time_str)
            elif current_meal == meal_name:
                # Include this item if we're in the target meal
                filtered.append(item)
        
        return filtered
    
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
        print(f"{'Code':<10} {'x':>4} {'Fiber':>8} {'Sodium':>8} {'Potass':>8} {'VitA':>8} {'VitC':>8} {'Iron':>8}")
        print(f"{'':10} {'':>4} {'(g)':>8} {'(mg)':>8} {'(mg)':>8} {'(mcg)':>8} {'(mg)':>8} {'(mg)':>8}")
        print("-" * 78)

        # Data rows - show ALL rows with their multiplied values
        for row in report.rows:
            t = row.totals.rounded()
            mult_str = self._format_mult(row.multiplier)
            
            print(f"{row.code:<10} {mult_str:>4} {int(t.fiber_g):>8} {int(t.sodium_mg):>8} "
                f"{int(t.potassium_mg):>8} {int(t.vitA_mcg):>8} "
                f"{int(t.vitC_mg):>8} {int(t.iron_mg):>8}")
        
        # Separator and total
        print("-" * 78)
        t = report.totals.rounded()
        print(f"{'Total':10} {'':>4} {int(t.fiber_g):>8} {int(t.sodium_mg):>8} "
            f"{int(t.potassium_mg):>8} {int(t.vitA_mcg):>8} "
            f"{int(t.vitC_mg):>8} {int(t.iron_mg):>8}")
        
        print()

    def _format_mult(self, mult: float) -> str:
        """Format multiplier (borrowed from ReportBuilder)."""
        if abs(mult - round(mult)) < 1e-9:
            s = str(int(round(mult)))
            if len(s) <= 4:
                return s
            return s[:4]
        
        for dp in (3, 2, 1, 0):
            s = f"{mult:.{dp}f}"
            if '.' in s:
                s = s.rstrip('0')
                if s.endswith('.'):
                    s = s[:-1]
            if len(s) <= 4:
                return s
        
        if mult < 1:
            for dp in (3, 2, 1):
                s = f"{mult:.{dp}f}"[1:]
                if len(s) <= 4:
                    return s
        
        s = f"{mult:.1f}"
        return s[:4]
    
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

    def _show_risk(self, report) -> None:
        """Show daily risk summary."""
        print("\n=== Nutritional Risk Assessment ===")
        risk_summary = self._get_risk_summary(report.totals, 1)
        print(f"Daily: {risk_summary}")
        print()
    
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
        
        targets = self.ctx.thresholds.get_daily_targets()
        # Calculate per-meal thresholds
        HIGH_SUGAR = int(targets['sugar_g'] / meal_count)
        HIGH_GL = int(targets['glycemic_load'] / meal_count)
        LOW_PROTEIN = int(targets['protein_g'] / meal_count)
        HIGH_FAT = int(targets['fat_pct'])  # Percentage, not divided
        HIGH_CARBS = int(targets['carbs_pct'])  # Percentage, not divided
        VLOW_CALORIES = int(targets['calories_min'] / meal_count)
        VHIGH_CALORIES = int(targets['calories_max'] / meal_count)

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
    Carb Load:           45.2  -> +35 risk
    Sugar Ratio:          0.38 -> +15 risk
    Fiber Offset:        -5.0  -> -8 risk
    Fat Modulation:      -8.5  -> -12 risk
    Protein Balance:      0.82 -> +2 risk
    [other factors...]
                        ---------
    Total Risk Score:           72

    """

    def _stage_report(self, report, date: str, meal_name: Optional[str]) -> None:
        """
        Stage report to buffer for email delivery.
        
        Args:
            report: Report object
            date: Date string
            meal_name: Optional meal name filter
        """
        if not self.ctx.staging_buffer:
            print("\nWarning: Staging buffer not configured, cannot stage.\n")
            return
        
        from meal_planner.data.staging_buffer_manager import StagingBufferManager
        
        # Generate abbreviated output
        content = report.format_abbreviated()
        
        # Generate ID and label based on source
        if meal_name:
            # Specific meal
            item_id = StagingBufferManager.generate_pending_id(meal_name, date)
            label = StagingBufferManager.format_date_label(date, meal_name)
        else:
            # Full day report
            item_id = f"pending:full:{date}"
            # Format label
            try:
                date_dt = datetime.strptime(date, "%Y-%m-%d")
                date_formatted = date_dt.strftime("%A, %B %d, %Y")
                label = f"{date_formatted} - FULL DAY"
            except ValueError:
                label = f"{date} - FULL DAY"
        
        # Add to buffer
        is_new = self.ctx.staging_buffer.add(item_id, label, content)
        
        if is_new:
            print(f"\n✓ Staged: {label}\n")
        else:
            print(f"\n✓ Replaced staged item: {label}\n")