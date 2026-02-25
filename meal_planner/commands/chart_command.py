"""
Chart command - trend visualization with moving averages.
"""
import re
from datetime import date as date_type
from .base import Command, register_command
from meal_planner.reports.chart_builder import ChartBuilder
from config import CHART_OUTPUT_FILE
from pathlib import Path

@register_command
class ChartCommand(Command):
    """Generate trend chart with moving averages."""
    
    name = "chart"
    help_text = "Generate trend chart (chart [window] [start] [end] [today] [--micros])"
    
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
        include_micro = False
        include_dots = False        
        
        # Extract tokens
        date_tokens = []
        for token in tokens:
            if re.match(r"^\d{4}-\d{2}-\d{2}$", token):
                date_tokens.append(token)
            elif token.lower() in ("today", "--today"):
                include_today = True
            elif token.lower() in ("--micro", "--micros"):
                include_micro = True
            elif token.lower() in ("--dots", "--dot"):
                include_dots = True
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
        if include_micro:
            chart_df = self._build_micro_dataframe(log_df)
        else:
            required = ["date", "cal", "prot_g", "carbs_g", "fat_g", "sugar_g", "gl"]
            for col in required:
                if col not in log_df.columns:
                    log_df[col] = 0
            chart_df = log_df[required]

            if chart_df.empty:
                print("\nNo data to chart.\n")
                return
            
        # Build chart
        if include_micro:
            output_file = Path(str(CHART_OUTPUT_FILE).replace(".jpg", "_micro.jpg"))
        else:
            output_file = CHART_OUTPUT_FILE
        builder = ChartBuilder(output_file)
        
        # Build title
        label = "Micro Trends" if include_micro else "Nutrient Trends"
        title_parts = [f"{label} (MA={window} days)"]
        if start_date and end_date:
            title_parts.append(f"{start_date} to {end_date}")
        elif start_date:
            title_parts.append(f"from {start_date}")
        elif end_date:
            title_parts.append(f"to {end_date}")
        
        if include_today:
            title_parts.append("+ pending")
        
        title = " - ".join(title_parts)
        
        builder.build_from_dataframe(chart_df, window=window, title=title,
                                     mode="micro" if include_micro else "macro",
                                     dots=include_dots)
    
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
    
    def _build_micro_dataframe(self, log_df):
        """Build per-date micro totals by running codes through ReportBuilder."""
        import pandas as pd
        from meal_planner.reports.report_builder import ReportBuilder
        from meal_planner.parsers.code_parser import CodeParser

        builder = ReportBuilder(self.ctx.master, self.ctx.report_columns)
        codes_col = self.ctx.log.cols.codes
        date_col = self.ctx.log.cols.date

        rows = []
        for _, row in log_df.iterrows():
            entry_date = str(row[date_col])
            codes_str = str(row.get(codes_col, ""))
            if not codes_str or codes_str == "nan":
                continue
            try:
                items = CodeParser.parse(codes_str)
                report = builder.build_from_items(items, title="")
                t = report.totals
                rows.append({
                    "date": entry_date,
                    "fiber_g":       t.fiber_g,
                    "sodium_mg":     t.sodium_mg,
                    "potassium_mg":  t.potassium_mg,
                    "vitA_mcg":      t.vitA_mcg,
                    "vitC_mg":       t.vitC_mg,
                    "iron_mg":       t.iron_mg,
                })
            except Exception:
                continue

        return pd.DataFrame(rows) if rows else pd.DataFrame()