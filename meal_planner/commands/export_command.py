# meal_planner/commands/export_command.py
"""
Export command - extract nutrient data to CSV for external analysis.

All nutrient values (macros and micros) are derived exclusively from
ReportBuilder, which resolves each code through master.json. This means
the exported values reflect the same computation used in report/chart
rather than the pre-summed columns stored in the log.

Modes:
  export --daily    One row per calendar date, all macros + micros summed.
  export --meals    Six CSVs (one per meal type), same columns, zero-filled
                    for dates where the meal was absent.
  export --top <nutrient> [N]
                    One row per day per top-N contributing food item
                    (long format), optionally limited with --meal NAME.

Date range arguments mirror the chart command:
  export --daily                        last 90 days
  export --daily --history 60           last 60 days
  export --daily 2025-01-01             from date to today
  export --daily 2025-01-01 2025-03-31  explicit range
"""
import re
import shlex
from datetime import date as date_type, timedelta
from pathlib import Path

from .base import Command, register_command
from meal_planner.reports.report_builder import ReportBuilder
from meal_planner.parsers.code_parser import CodeParser
from meal_planner.utils.time_utils import MEAL_NAMES
from meal_planner.reports.contributors import (
    NUTRIENT_KEYS, resolve_nutrient, resolve_meal, day_contributions,
)
from config import CHART_OUTPUT_FILE  # output directory matches chart command


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
    category = "Output"
    help_text = (
        "Export nutrient data to CSV "
        "(export --daily|--meals|--top <nutrient> [N] [--history N] [start] [end])"
    )
    overview_help = (
        "export  —  Export nutrient data to CSV for spreadsheet analysis\n"
        "\n"
        "Usage:\n"
        "  export --daily                        One row per date, all macros + micros summed\n"
        "  export --meals                         Six CSVs, one per meal type, zero-filled where absent\n"
        "  export --daily --history 60            Last 60 days instead of the default 90\n"
        "  export --daily 2025-01-01 2025-03-31    Explicit date range\n"
        "  export --top carbs 5                    Top 5 carb contributors per day\n"
        "  export --top prot_g 3 --meal lunch      Top 3 protein items per day, lunch only\n"
        "\n"
        "--top writes export_top_<nutrient>[_<meal>].csv, one row per day per\n"
        "ranked item: date, rank, code, option, section, amount, servings,\n"
        "pct_of_day, day_total. Days with no log entry are omitted. N defaults\n"
        "to 5. Nutrient: " + ", ".join(NUTRIENT_KEYS) + " (or carbs, protein, ...).\n"
        "\n"
        "All values are recomputed via the same code path as report/chart, not\n"
        "the pre-summed log columns. Files are written next to the chart output."
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
        try:
            tokens = shlex.split(args) if args.strip() else []
        except ValueError:
            tokens = args.split()

        do_daily = False
        do_meals = False
        top_nutrient = None
        top_n = 5
        top_meal = None
        history_days = None
        date_tokens = []

        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token.lower() == "--daily":
                do_daily = True
            elif token.lower() == "--meals":
                do_meals = True
            elif token.lower() == "--top":
                if i + 1 >= len(tokens):
                    print("Error: --top requires a nutrient, e.g. export --top carbs 5")
                    return
                top_nutrient = resolve_nutrient(tokens[i + 1])
                if top_nutrient is None:
                    print(f"Error: Unknown nutrient '{tokens[i + 1]}'. Valid: {', '.join(NUTRIENT_KEYS)}")
                    return
                i += 1
                if i + 1 < len(tokens) and tokens[i + 1].isdigit():
                    top_n = max(1, int(tokens[i + 1]))
                    i += 1
            elif token.lower() == "--meal":
                if i + 1 >= len(tokens):
                    print("Error: --meal requires a meal name")
                    return
                top_meal = resolve_meal(tokens[i + 1])
                if top_meal is None:
                    print(f"Error: Invalid meal name '{tokens[i + 1]}'. Valid: {', '.join(MEAL_NAMES)}")
                    return
                i += 1
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

        if not do_daily and not do_meals and top_nutrient is None:
            print("\nUsage: export --daily|--meals|--top <nutrient> [N] [--meal NAME] [--history N] [start] [end]\n")
            return

        if top_meal is not None and top_nutrient is None:
            print("Error: --meal only applies to --top (use --meals for per-meal totals)")
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

        if top_nutrient is not None:
            self._export_top(log_df, builder, date_col, codes_col,
                             top_nutrient, top_n, top_meal)

        print()

    # ------------------------------------------------------------------
    # Top-contributor export
    # ------------------------------------------------------------------

    def _export_top(self, log_df, builder, date_col, codes_col, nutrient, top_n, meal):
        """
        Write export_top_<nutrient>[_<meal>].csv in long format.

        For each logged date, items are ranked by their contribution to the
        nutrient (via the shared contributors helper, same values as `top`)
        and the top N are written one row each.
        """
        import pandas as pd

        columns = ["date", "rank", "code", "option", "section", nutrient,
                   "servings", "pct_of_day", "day_total"]
        records = []
        days_written = 0

        for _, row in log_df.sort_values(date_col).iterrows():
            entry_date = str(row[date_col])
            day_items, day_total = day_contributions(
                builder, str(row.get(codes_col, "")), nutrient, meal, entry_date
            )
            if not day_items:
                continue
            days_written += 1
            ranked = sorted(day_items.values(), key=lambda c: c.amount, reverse=True)
            for rank, item in enumerate(ranked[:top_n], 1):
                pct = round(item.amount / day_total * 100, 1) if day_total > 0 else ""
                records.append({
                    "date": entry_date,
                    "rank": rank,
                    "code": item.code,
                    "option": item.option,
                    "section": item.section,
                    nutrient: round(item.amount, 1),
                    "servings": round(item.servings, 2),
                    "pct_of_day": pct,
                    "day_total": round(day_total, 1),
                })

        suffix = f"_{_meal_filename(meal)}" if meal else ""
        filename = f"export_top_{nutrient}{suffix}.csv"
        pd.DataFrame(records, columns=columns).to_csv(
            CHART_OUTPUT_FILE.parent / filename, index=False
        )
        print(f"  {filename}  {len(records)} rows "
              f"(top {top_n} per day over {days_written} logged days)")

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
        out_path = CHART_OUTPUT_FILE.parent / "export_daily.csv"
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
            df_out.to_csv(CHART_OUTPUT_FILE.parent / filename, index=False)

            present = sum(1 for ds in full_date_strs if ds in date_map)
            print(
                f"  {filename:<40}  "
                f"{len(full_date_strs)} rows "
                f"({present} with data, {len(full_date_strs) - present} zero-filled)"
            )