# meal_planner/commands/export_command.py
"""
Export command - extract nutrient data to CSV for external analysis.

All nutrient values (macros and micros) are derived exclusively from
ReportBuilder, which resolves each code through master.json. This means
the exported values reflect the same computation used in report/chart
rather than the pre-summed columns stored in the log.

Two modes:
  export --daily    One row per calendar date, all macros + micros summed.
  export --meals    Six CSVs (one per meal type), same columns, zero-filled
                    for dates where the meal was absent.

Date range arguments mirror the chart command:
  export --daily                        last 90 days
  export --daily --history 60           last 60 days
  export --daily 2025-01-01             from date to today
  export --daily 2025-01-01 2025-03-31  explicit range
"""
import re
from datetime import date as date_type, timedelta
from pathlib import Path

from .base import Command, register_command
from meal_planner.reports.report_builder import ReportBuilder
from meal_planner.parsers.code_parser import CodeParser
from meal_planner.utils.time_utils import MEAL_NAMES


# Ordered column list for all output CSVs
_NUTRIENT_COLS = [
    "cal", "prot_g", "carbs_g", "fat_g", "sugar_g", "gl",
    "fiber_g", "sodium_mg", "potassium_mg", "vitA_mcg", "vitC_mg", "iron_mg",
]


def _meal_filename(meal_name: str) -> str:
    """Convert MEAL_NAME to a safe filename suffix."""
    return meal_name.lower().replace(" ", "_")


def _zero_row() -> dict:
    """Return a dict of zeros for all nutrient columns."""
    return {col: 0 for col in _NUTRIENT_COLS}


def _round_row(nutrient_dict: dict) -> dict:
    """Round all nutrient values to integers for clean CSV output."""
    result = {}
    for col in _NUTRIENT_COLS:
        val = nutrient_dict.get(col, 0) or 0
        result[col] = int(round(float(val)))
    return result


def _build_report(builder: ReportBuilder, codes_str: str):
    """
    Parse a codes string and return a ReportBuilder Report, or None on failure.

    Both macros and micros are read from report.totals (a DailyTotals instance)
    via its to_dict() method. No log column values are used for nutrients.
    """
    if not codes_str or codes_str == "nan":
        return None
    try:
        items = CodeParser.parse(codes_str)
        return builder.build_from_items(items, title="")
    except Exception:
        return None


@register_command
class ExportCommand(Command):
    """Export nutrient data to CSV for spreadsheet analysis."""

    name = "export"
    help_text = (
        "Export nutrient data to CSV "
        "(export --daily|--meals [--history N] [start] [end])"
    )

    def execute(self, args: str) -> None:
        """
        Export nutrient data to CSV files.

        Args:
            args: Flags and optional date range.
                  --daily       Export one CSV with per-day totals.
                  --meals       Export six CSVs, one per meal type.
                  --history N   Last N days (default 90).
                  YYYY-MM-DD    Explicit start (and optional end) date.

        Examples:
            export --daily
            export --meals
            export --daily --meals --history 120
            export --daily 2025-01-01
            export --daily 2025-01-01 2025-06-30
        """
        tokens = args.strip().split() if args.strip() else []

        do_daily = False
        do_meals = False
        history_days = None
        date_tokens = []

        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token.lower() == "--daily":
                do_daily = True
            elif token.lower() == "--meals":
                do_meals = True
            elif token.lower() == "--history":
                if i + 1 < len(tokens):
                    try:
                        history_days = max(1, int(tokens[i + 1]))
                        i += 1
                    except ValueError:
                        print(f"Error: --history requires an integer, got '{tokens[i+1]}'")
                        return
                else:
                    print("Error: --history requires a number of days")
                    return
            elif re.match(r"^\d{4}-\d{2}-\d{2}$", token):
                date_tokens.append(token)
            i += 1

        if not do_daily and not do_meals:
            print("\nUsage: export --daily|--meals [--history N] [start] [end]\n")
            return

        if history_days is not None and date_tokens:
            print("Error: --history cannot be combined with explicit dates")
            return

        # Resolve date range
        if date_tokens:
            start_date = date_tokens[0]
            end_date = date_tokens[1] if len(date_tokens) >= 2 else str(date_type.today())
        else:
            lookback = history_days if history_days is not None else 90
            start_date = str(date_type.today() - timedelta(days=lookback))
            end_date = str(date_type.today())

        log_df = self.ctx.log.get_date_range(start_date, end_date)

        if log_df.empty:
            print(f"\nNo log data found between {start_date} and {end_date}.\n")
            return

        # Full calendar index — every date in the range regardless of logging
        import pandas as pd
        full_date_strs = [
            str(d.date())
            for d in pd.date_range(start=start_date, end=end_date, freq="D")
        ]

        # Single ReportBuilder instance shared across both modes
        builder = ReportBuilder(self.ctx.master, self.ctx.report_columns)
        codes_col = self.ctx.log.cols.codes
        date_col = self.ctx.log.cols.date

        print()

        if do_daily:
            self._export_daily(log_df, full_date_strs, builder, date_col, codes_col)

        if do_meals:
            self._export_meals(log_df, full_date_strs, builder, date_col, codes_col)

        print()

    # ------------------------------------------------------------------
    # Daily export
    # ------------------------------------------------------------------

    def _export_daily(self, log_df, full_date_strs, builder, date_col, codes_col):
        """
        Write export_daily.csv.

        Each logged date is processed through ReportBuilder; report.totals
        provides all 12 nutrient values via DailyTotals.to_dict(). Dates
        with no log entry or unparseable codes receive a zero row.
        """
        import pandas as pd

        date_rows = {}
        for _, row in log_df.iterrows():
            entry_date = str(row[date_col])
            codes_str = str(row.get(codes_col, ""))
            report = _build_report(builder, codes_str)
            if report is not None:
                # report.totals is a DailyTotals; to_dict() covers all macros + micros
                date_rows[entry_date] = report.totals.to_dict()
            else:
                date_rows[entry_date] = _zero_row()

        records = []
        for ds in full_date_strs:
            nutrient_vals = date_rows.get(ds, _zero_row())
            records.append({"date": ds, **_round_row(nutrient_vals)})

        df_out = pd.DataFrame(records, columns=["date"] + _NUTRIENT_COLS)
        out_path = Path("export_daily.csv")
        df_out.to_csv(out_path, index=False)

        logged = sum(1 for ds in full_date_strs if ds in date_rows)
        print(
            f"  export_daily.csv  "
            f"{len(full_date_strs)} rows "
            f"({logged} logged, {len(full_date_strs) - logged} zero-filled)"
        )

    # ------------------------------------------------------------------
    # Meal export
    # ------------------------------------------------------------------

    def _export_meals(self, log_df, full_date_strs, builder, date_col, codes_col):
        """
        Write one CSV per meal type.

        For each logged date, ReportBuilder produces a breakdown via
        get_meal_breakdown(), which returns (meal_name, first_time, DailyTotals)
        per slot. meal_totals.to_dict() provides all 12 nutrient values.
        Dates where a meal slot is absent (or where the day has no time
        markers) receive a zero row in that meal's CSV.
        """
        import pandas as pd

        # meal_data[meal_name][date_str] = nutrient dict from DailyTotals.to_dict()
        meal_data = {meal: {} for meal in MEAL_NAMES}

        for _, row in log_df.iterrows():
            entry_date = str(row[date_col])
            codes_str = str(row.get(codes_col, ""))
            report = _build_report(builder, codes_str)
            if report is None:
                continue
            breakdown = report.get_meal_breakdown()
            if not breakdown:
                continue
            for meal_name, _first_time, meal_totals in breakdown:
                if meal_name in meal_data:
                    # meal_totals is a DailyTotals; to_dict() covers all macros + micros
                    meal_data[meal_name][entry_date] = meal_totals.to_dict()

        for meal_name in MEAL_NAMES:
            date_map = meal_data[meal_name]
            records = []
            for ds in full_date_strs:
                nutrient_vals = date_map.get(ds, _zero_row())
                records.append({"date": ds, **_round_row(nutrient_vals)})

            df_out = pd.DataFrame(records, columns=["date"] + _NUTRIENT_COLS)
            filename = f"export_meal_{_meal_filename(meal_name)}.csv"
            df_out.to_csv(Path(filename), index=False)

            present = sum(1 for ds in full_date_strs if ds in date_map)
            print(
                f"  {filename:<40}  "
                f"{len(full_date_strs)} rows "
                f"({present} with data, {len(full_date_strs) - present} zero-filled)"
            )