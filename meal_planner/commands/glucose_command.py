"""
Glucose command to provide detail information about a meal's predictive effect on CGM data
"""
"""
Glucose command - glycemic load analysis.
"""
from .base import Command, register_command
from meal_planner.reports.report_builder import ReportBuilder
from meal_planner.parsers import CodeParser


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
        
        builder = ReportBuilder(self.ctx.master)
        
        if not parts:
            # Use pending
            report = self._get_pending_report(builder)
            date_label = "pending"
        else:
            # Use log date
            query_date = parts[0]
            report = self._get_log_report(builder, query_date)
            date_label = query_date
        
        if report is None:
            return
        
        # Show glucose analysis
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
    
    def _show_glucose_analysis(self, report, date_label):
        """Display glucose analysis."""
        print(f"\n=== Glycemic Analysis ({date_label}) ===\n")
        
        # Get meal breakdown if time markers present
        breakdown = report.get_meal_breakdown()
        
        if breakdown:
            print(f"{'Meal':<20} {'Time':>8} {'GL':>6} {'Carbs':>8} {'Sugar':>8}")
            print("-" * 56)
            
            for meal_name, first_time, totals in breakdown:
                t = totals.rounded()
                print(f"{meal_name:<20} {first_time:>8} {int(t.glycemic_load):>6} "
                      f"{int(t.carbs_g):>8}g {int(t.sugar_g):>8}g")
            
            print("-" * 56)
        
        # Daily total
        t = report.totals.rounded()
        print(f"{'Daily Total':<20} {'':>8} {int(t.glycemic_load):>6} "
              f"{int(t.carbs_g):>8}g {int(t.sugar_g):>8}g")
        
        # GL categories
        total_gl = int(t.glycemic_load)
        if total_gl <= 80:
            category = "LOW"
        elif total_gl <= 120:
            category = "MODERATE"
        else:
            category = "HIGH"
        
        print(f"\nDaily GL Category: {category}")
        print(f"  (Low: ≤80, Moderate: 81-120, High: >120)")
        print()