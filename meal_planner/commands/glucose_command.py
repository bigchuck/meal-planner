"""
Glucose command to provide detail information about a meal's predictive effect on CGM data
"""
"""
Glucose command - glycemic load analysis.
"""
from typing import List, Dict, Any, Optional, Tuple

from .base import Command, register_command
from meal_planner.reports.report_builder import ReportBuilder
from meal_planner.parsers import CodeParser
from meal_planner.glucose import GlucoseCalculator


@register_command
class GlucoseCommand(Command):
    """Show glycemic load analysis."""
    
    name = "glucose"
    help_text = "Show glycemic analysis (glucose or glucose YYYY-MM-DD)"
    
    def execute(self, args: str) -> None:
        """
        Show glucose/glycemic load analysis.
        
        Args:
            args: Optional date (YYYY-MM-DD)
        """
        parts = args.strip().split() if args.strip() else []
        
        self.show_all_meals = "--all" in parts

        builder = ReportBuilder(self.ctx.master, self.ctx.nutrients)

        date_parts = [p for p in parts if not p.startswith("--")]

        if not date_parts:
            # Use pending
            report = self._get_pending_report(builder)
            date_label = "pending"
        else:
            # Use log date
            query_date = date_parts[0]
            report = self._get_log_report(builder, query_date)
            date_label = query_date
        
        if report is None:
            return
        
        # Show glucose analysis
        self.glucose_calculator = GlucoseCalculator()
        self._show_glucose_analysis(report, date_label)
    
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
        return builder.build_from_items(items, title="Glucose Analysis")
    
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
        return builder.build_from_items(items, title="Glucose Analysis")
    """
    --------------------------------------------------------------------
    """    
    def _show_glucose_analysis(self, report, date_label):
        """Display glucose analysis."""
        print(f"\n=== Detailed Glycemic Analysis ({date_label}) ===\n")
        
        # Get meal breakdown if time markers present
        breakdown = report.get_meal_breakdown()

        for meal_name, first_time, totals in breakdown:
            if self.show_all_meals or "SNACK" not in meal_name: 
                # Format meal header
                print(f"\n{'=' * 70}")
                print(f"{meal_name} @ {first_time}")
                print(f"{'=' * 70}")

                meal_dict = totals.to_dict()
                meal_dict['calories'] = meal_dict.pop('cal')
                meal_dict['protein_g'] = meal_dict.pop('prot_g')
                meal_dict['gi'] = 100 * meal_dict['gl'] / meal_dict['carbs_g'] if meal_dict['carbs_g'] > 0 else 0

                # Meal composition table
                print(f"\nMeal Composition:")
                print(f"  {'Calories:':<20} {meal_dict['calories']:>6.0f}")
                print(f"  {'Carbohydrates:':<20} {meal_dict['carbs_g']:>6.1f} g")
                print(f"  {'  - Sugars:':<20} {meal_dict['sugar_g']:>6.1f} g ({100 * meal_dict['sugar_g'] / meal_dict['carbs_g'] if meal_dict['carbs_g'] > 0 else 0:.0f}%)")
                print(f"  {'Protein:':<20} {meal_dict['protein_g']:>6.1f} g")
                print(f"  {'Fat:':<20} {meal_dict['fat_g']:>6.1f} g")
                print(f"  {'Glycemic Index:':<20} {meal_dict['gi']:>6.0f}")
                print(f"  {'Glycemic Load:':<20} {meal_dict['gl']:>6.1f}")

                risks = self.glucose_calculator.compute_risk_scores(meal_dict)

                comps = risks['components']
                # Risk analysis
                print(f"\nGlucose Risk Analysis:")
                print(f"  {'Overall Risk Score:':<22} {risks['risk_score']:>5.1f} / 10.0  [{risks['risk_rating'].upper()}]")

                print(f"\n  Risk Components:")
                print(f"    {'Carb Risk:':<24} {comps['carb_risk']:>5.1f}")
                print(f"    {'GI Speed Factor:':<24} {comps['gi_speed_factor']:>5.2f}x")
                print(f"    {'Base Carb Risk:':<24} {comps['base_carb_risk']:>5.1f}")
                print(f"    {'Fat Delay Risk:':<24} +{comps['fat_delay_risk']:>4.1f}")
                print(f"    {'Protein Tail Risk:':<24} +{comps['protein_tail_risk']:>4.1f}")
                print(f"    {'Fiber Buffer:':<24} -{comps['fiber_buffer']:>4.1f}")
                print(f"    {'-' * 32}")
                print(f"    {'Raw Total:':<24} {comps['raw_score_before_clamp']:>5.1f}")


            
