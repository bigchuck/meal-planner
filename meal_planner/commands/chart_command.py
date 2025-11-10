"""
Chart command - trend visualization with moving averages.
"""
import re
from datetime import date as date_type
from .base import Command, register_command
from meal_planner.reports.chart_builder import ChartBuilder
from config import CHART_OUTPUT_FILE


@register_command
class ChartCommand(Command):
    """Generate trend chart with moving averages."""
    
    name = "chart"
    help_text = "Generate trend chart (chart [window] [start] [end] [today])"
    
    def execute(self, args: str) -> None:
        """
        Generate trend chart.
        
        Args:
            args: Optional: window size, date range, 'today' flag
                  Examples:
                    chart
                    chart 14
                    chart 7 2025-01-01
                    chart 7 2025-01-01 2025-01-31
                    chart 7 2025-01-01 2025-01-31 today
        """
        # Parse arguments
        tokens = args.strip().split() if args.strip() else []
        
        window = 7  # default
        start_date = None
        end_date = None
        include_today = False
        
        # Extract tokens
        date_tokens = []
        for token in tokens:
            if re.match(r"^\d{4}-\d{2}-\d{2}$", token):
                date_tokens.append(token)
            elif token.lower() in ("today", "--today"):
                include_today = True
            else:
                # Try to parse as window
                try:
                    window = max(1, int(token))
                except ValueError:
                    pass
        
        # Assign dates
        if len(date_tokens) >= 1:
            start_date = date_tokens[0]
        if len(date_tokens) >= 2:
            end_date = date_tokens[1]
        
        # Get log data
        log_df = self.ctx.log.get_date_range(start_date, end_date)
        
        # Optionally include today's pending
        if include_today:
            today_df = self._build_today_dataframe()
            if today_df is not None and not today_df.empty:
                import pandas as pd
                log_df = pd.concat([log_df, today_df], ignore_index=True)
        
        if log_df.empty:
            print("\nNo data to chart.\n")
            return
        
        # Ensure required columns
        required = ["date", "cal", "prot_g", "carbs_g", "fat_g", "sugar_g", "gl"]
        for col in required:
            if col not in log_df.columns:
                log_df[col] = 0
        
        # Build chart
        builder = ChartBuilder(CHART_OUTPUT_FILE)
        
        # Build title
        title_parts = [f"Nutrient Trends (MA={window} days)"]
        if start_date and end_date:
            title_parts.append(f"{start_date} to {end_date}")
        elif start_date:
            title_parts.append(f"from {start_date}")
        elif end_date:
            title_parts.append(f"to {end_date}")
        
        if include_today:
            title_parts.append("+ pending")
        
        title = " - ".join(title_parts)
        
        builder.build_from_dataframe(log_df[required], window=window, title=title)
    
    def _build_today_dataframe(self):
        """Build DataFrame row from pending data."""
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            return None
        
        if pending is None or not pending.get("items"):
            return None
        
        # Calculate totals
        from .pending_commands import ShowCommand
        show_cmd = ShowCommand(self.ctx)
        totals, _, code_strs = show_cmd._calculate_totals(pending["items"])
        
        # Build DataFrame
        import pandas as pd
        return pd.DataFrame([{
            "date": pending.get("date", str(date_type.today())),
            "codes": ", ".join(code_strs),
            "cal": int(round(totals["cal"])),
            "prot_g": int(round(totals["prot_g"])),
            "carbs_g": int(round(totals["carbs_g"])),
            "fat_g": int(round(totals["fat_g"])),
            "sugar_g": int(round(totals["sugar_g"])),
            "gl": int(round(totals["gl"])),
        }])