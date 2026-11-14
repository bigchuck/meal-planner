# meal_planner/commands/top_command.py
"""
Top command - which logged food items contributed most to a nutrient.
"""
import re
import shlex
from datetime import date as date_type, timedelta

from .base import Command, register_command
from meal_planner.reports.report_builder import ReportBuilder
from meal_planner.reports.contributors import (
    NUTRIENT_KEYS, resolve_nutrient, resolve_meal,
    period_contributions, group_by_section,
)
from meal_planner.utils.time_utils import MEAL_NAMES


_USAGE = ("Usage: top <nutrient> [N] [--history DAYS | start [end]] "
          "[--meal NAME] [--by section]")


@register_command
class TopCommand(Command):
    """Rank logged food items by total contribution to a nutrient."""

    name = "top"
    category = "Analysis"
    help_text = "Top food items contributing to a nutrient over logged days"
    overview_help = (
        "top  —  Which food items contributed most to a nutrient over a period\n"
        "\n"
        f"{_USAGE}\n"
        "\n"
        "Sums each food code's actual logged amount (portion multipliers\n"
        "applied) across the period. Default: top 10 over the last 90 days.\n"
        "\n"
        "Examples:\n"
        "  top carbs              Top 10 carb contributors, last 90 days\n"
        "  top prot_g 15 --history 30\n"
        "  top cal --meal lunch\n"
        "  top sugar --by section\n"
        "\n"
        "For per-day rankings as a CSV, see 'export --top'."
    )
    detailed_help = (
        "top  —  Which food items contributed most to a nutrient over a period\n"
        "\n"
        f"{_USAGE}\n"
        "\n"
        "  nutrient       " + ", ".join(NUTRIENT_KEYS) + "\n"
        "                 (aliases: calories, protein, carbs, fat, sugar, fiber,\n"
        "                 sodium, potassium, vita, vitc, iron)\n"
        "  N              How many items to show (default 10)\n"
        "  --history D    Last D days (default 90)\n"
        "  start [end]    Explicit YYYY-MM-DD range (end defaults to today)\n"
        "  --meal NAME    Only count items eaten in that meal\n"
        "  --by section   Group items by master section instead of per code\n"
        "\n"
        "Columns: amount = total over the period; % = share of the period\n"
        "total; /day = amount averaged over logged days; days = days the item\n"
        "was eaten; servings = sum of portion multipliers. Subtractions\n"
        "(e.g. D.10-VE.T1) reduce the subtracted item's amount.\n"
        "\n"
        "Examples:\n"
        "  top carbs\n"
        "  top prot_g 15 --history 30\n"
        "  top cal 20 2025-01-01 2025-03-31\n"
        "  top sugar --meal \"afternoon snack\"\n"
        "  top carbs --by section"
    )

    def execute(self, args: str) -> None:
        try:
            tokens = shlex.split(args) if args.strip() else []
        except ValueError:
            tokens = args.split()

        if not tokens:
            print(f"\n{_USAGE}\n")
            return

        nutrient = resolve_nutrient(tokens[0])
        if nutrient is None:
            print(f"\nError: Unknown nutrient '{tokens[0]}'")
            print(f"Valid: {', '.join(NUTRIENT_KEYS)}\n")
            return

        limit = 10
        history_days = None
        date_tokens = []
        meal = None
        by_section = False

        i = 1
        while i < len(tokens):
            tok = tokens[i]
            low = tok.lower()
            if low == "--history":
                if i + 1 >= len(tokens):
                    print("\nError: --history requires a number of days\n")
                    return
                try:
                    history_days = max(1, int(tokens[i + 1]))
                except ValueError:
                    print(f"\nError: --history requires an integer, got '{tokens[i + 1]}'\n")
                    return
                i += 2
                continue
            if low == "--meal":
                if i + 1 >= len(tokens):
                    print("\nError: --meal requires a meal name\n")
                    return
                meal = resolve_meal(tokens[i + 1])
                if meal is None:
                    print(f"\nError: Invalid meal name '{tokens[i + 1]}'")
                    print(f"Valid meal names: {', '.join(MEAL_NAMES)}\n")
                    return
                i += 2
                continue
            if low == "--by":
                if i + 1 >= len(tokens) or tokens[i + 1].lower() != "section":
                    print("\nError: --by currently supports only 'section'\n")
                    return
                by_section = True
                i += 2
                continue
            if re.match(r"^\d{4}-\d{2}-\d{2}$", tok):
                date_tokens.append(tok)
            elif tok.isdigit():
                limit = max(1, int(tok))
            else:
                print(f"\nError: Unrecognized argument '{tok}'")
                print(f"{_USAGE}\n")
                return
            i += 1

        if history_days is not None and date_tokens:
            print("\nError: --history cannot be combined with explicit dates\n")
            return

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

        builder = ReportBuilder(self.ctx.master, self.ctx.report_columns)
        items, period_total, logged_days = period_contributions(
            builder, log_df, self.ctx.log.cols.date, self.ctx.log.cols.codes,
            nutrient, meal,
        )

        if not items:
            scope = f" in {meal}" if meal else ""
            print(f"\nNo food items found{scope} between {start_date} and {end_date}.\n")
            return

        if by_section:
            items = group_by_section(items)

        shown = items[:limit]
        scope = f", {meal}" if meal else ""
        unit_label = "sections" if by_section else "items"
        print(f"\n=== Top {len(shown)} {unit_label} by {nutrient} "
              f"({start_date} to {end_date}{scope}) ===")
        # items is non-empty, so logged_days >= 1
        print(f"Period total: {period_total:,.1f}  over {logged_days} logged days  "
              f"(avg {period_total / logged_days:,.1f}/day)\n")

        if by_section:
            print(f"{'Rank':>4}  {'Section':<12} {'Amount':>10} {'%':>6} {'/day':>8} "
                  f"{'Days':>5} {'Servings':>9}  Items")
        else:
            print(f"{'Rank':>4}  {'Code':<10} {'Amount':>10} {'%':>6} {'/day':>8} "
                  f"{'Days':>5} {'Servings':>9}  Item")

        for rank, item in enumerate(shown, 1):
            pct = (item.amount / period_total * 100) if period_total else 0.0
            per_day = item.amount / logged_days if logged_days else 0.0
            if by_section:
                lead, tail = item.section[:12], item.code
                print(f"{rank:>4}  {lead:<12} {item.amount:>10,.1f} {pct:>5.1f}% {per_day:>8,.1f} "
                      f"{len(item.days):>5} {item.servings:>9.1f}  {tail}")
            else:
                print(f"{rank:>4}  {item.code:<10} {item.amount:>10,.1f} {pct:>5.1f}% {per_day:>8,.1f} "
                      f"{len(item.days):>5} {item.servings:>9.1f}  {item.option}")

        shown_total = sum(item.amount for item in shown)
        shown_pct = (shown_total / period_total * 100) if period_total else 0.0
        print(f"\nTop {len(shown)} account for {shown_pct:.1f}% of {nutrient} "
              f"({len(items)} {unit_label} contributed in total).\n")
