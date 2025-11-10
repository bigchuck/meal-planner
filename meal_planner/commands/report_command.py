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
    help_text = "Show detailed breakdown (report or report YYYY-MM-DD)"
    
    def execute(self, args: str) -> None:
        """
        Show detailed report.
        
        Args:
            args: Optional date (YYYY-MM-DD) to report from log
        """
        builder = ReportBuilder(self.ctx.master)
        
        if not args.strip():
            # Report from pending
            self._report_pending(builder)
        else:
            # Report from log date
            query_date = args.strip()
            self._report_log_date(builder, query_date)
    
    def _report_pending(self, builder: ReportBuilder) -> None:
        """Report from pending day."""
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            pending = None
        
        if pending is None or not pending.get("items"):
            print("\n(No active day. Use 'start' and 'add' first.)\n")
            return
        
        items = pending.get("items", [])
        date = pending.get("date", "unknown")
        
        report = builder.build_from_items(items, title=f"Report for {date}")
        report.print()
    
    def _report_log_date(self, builder: ReportBuilder, query_date: str) -> None:
        """Report from log date."""
        # Get all entries for this date
        entries = self.ctx.log.get_entries_for_date(query_date)
        
        if entries.empty:
            print(f"\nNo log entries found for {query_date}.\n")
            return
        
        # Parse codes from all entries for this date
        codes_col = self.ctx.log.cols.codes
        all_codes = ", ".join([
            str(v) for v in entries[codes_col].fillna("") 
            if str(v).strip()
        ])
        
        if not all_codes.strip():
            print(f"\nNo codes found for {query_date}.\n")
            return
        
        # Parse into items
        items = CodeParser.parse(all_codes)
        
        report = builder.build_from_items(items, title=f"Report for {query_date}")
        report.print()