"""
Per-food-item nutrient contribution over logged days.

Shared by the `top` command (period totals per item) and `export --top`
(per-day rankings). Values come from ReportBuilder, so they match what
report/chart/export compute for the same log entries.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from meal_planner.parsers.code_parser import CodeParser
from meal_planner.reports.report_builder import ReportBuilder
from meal_planner.utils.time_utils import normalize_meal_name, MEAL_NAMES


# Canonical nutrient keys (DailyTotals.to_dict()) plus friendly aliases.
NUTRIENT_KEYS = [
    "cal", "prot_g", "carbs_g", "fat_g", "sugar_g", "gl",
    "fiber_g", "sodium_mg", "potassium_mg", "vitA_mcg", "vitC_mg", "iron_mg",
]
_NUTRIENT_ALIASES = {
    "calories": "cal", "kcal": "cal",
    "protein": "prot_g", "prot": "prot_g",
    "carbs": "carbs_g", "carb": "carbs_g", "carbohydrates": "carbs_g",
    "fat": "fat_g",
    "sugar": "sugar_g", "sugars": "sugar_g",
    "fiber": "fiber_g", "fibre": "fiber_g",
    "sodium": "sodium_mg", "salt": "sodium_mg",
    "potassium": "potassium_mg",
    "vita": "vitA_mcg", "vitamin_a": "vitA_mcg",
    "vitc": "vitC_mg", "vitamin_c": "vitC_mg",
    "iron": "iron_mg",
}


def resolve_nutrient(name: str) -> Optional[str]:
    """Map user input (e.g. 'carbs', 'prot_g', 'VITC') to a canonical key, or None."""
    key = name.strip().lower()
    for canonical in NUTRIENT_KEYS:
        if canonical.lower() == key:
            return canonical
    return _NUTRIENT_ALIASES.get(key)


def resolve_meal(name: str) -> Optional[str]:
    """Normalize a meal name; None if it isn't a known meal."""
    normalized = normalize_meal_name(name)
    return normalized if normalized in MEAL_NAMES else None


@dataclass
class ItemContribution:
    """One food code's contribution to a nutrient over some span."""
    code: str
    option: str
    section: str
    amount: float = 0.0        # net nutrient amount (subtractions reduce it)
    servings: float = 0.0      # sum of positive multipliers
    days: set = field(default_factory=set)  # dates the item appeared


def day_contributions(
    builder: ReportBuilder,
    codes_str: str,
    nutrient: str,
    meal: Optional[str] = None,
    entry_date: str = "",
) -> Tuple[Dict[str, ItemContribution], float]:
    """
    Per-item contributions for one log entry.

    Args:
        builder:    ReportBuilder over the master database
        codes_str:  Raw log codes string for the day
        nutrient:   Canonical nutrient key (see NUTRIENT_KEYS)
        meal:       Optional canonical meal name; only items in that meal count
        entry_date: Date string recorded in each contribution's `days`

    Returns:
        ({code: ItemContribution}, total) where total is the nutrient total
        across the counted items. Unparseable or empty entries give ({}, 0.0).
    """
    if not codes_str or codes_str == "nan":
        return {}, 0.0
    try:
        report = builder.build_from_items(CodeParser.parse(codes_str), title="")
    except Exception:
        return {}, 0.0

    row_meals = report.get_row_meals() if meal else None
    contributions: Dict[str, ItemContribution] = {}
    total = 0.0

    for idx, row in enumerate(report.rows):
        if meal and row_meals[idx] != meal:
            continue
        value = float(row.totals.to_dict().get(nutrient, 0.0) or 0.0)
        entry = contributions.get(row.code)
        if entry is None:
            entry = contributions[row.code] = ItemContribution(
                code=row.code, option=row.option, section=row.section
            )
        entry.amount += value
        if row.multiplier > 0:
            entry.servings += row.multiplier
            if entry_date:
                entry.days.add(entry_date)
        total += value

    return contributions, total


def period_contributions(
    builder: ReportBuilder,
    log_df,
    date_col: str,
    codes_col: str,
    nutrient: str,
    meal: Optional[str] = None,
) -> Tuple[List[ItemContribution], float, int]:
    """
    Sum per-item contributions across every log row in log_df.

    Returns:
        (items sorted by amount descending, period total, logged day count)
    """
    combined: Dict[str, ItemContribution] = {}
    period_total = 0.0
    logged_days = 0

    for _, row in log_df.iterrows():
        entry_date = str(row[date_col])
        day_items, day_total = day_contributions(
            builder, str(row.get(codes_col, "")), nutrient, meal, entry_date
        )
        if not day_items:
            continue
        logged_days += 1
        period_total += day_total
        for code, item in day_items.items():
            agg = combined.get(code)
            if agg is None:
                combined[code] = item
            else:
                agg.amount += item.amount
                agg.servings += item.servings
                agg.days |= item.days

    ranked = sorted(combined.values(), key=lambda c: c.amount, reverse=True)
    return ranked, period_total, logged_days


def group_by_section(items: List[ItemContribution]) -> List[ItemContribution]:
    """Collapse item contributions into one entry per section, sorted desc."""
    groups: Dict[str, ItemContribution] = {}
    counts: Dict[str, int] = {}
    for item in items:
        key = item.section or "(none)"
        g = groups.get(key)
        if g is None:
            g = groups[key] = ItemContribution(code="", option="", section=key)
        g.amount += item.amount
        g.servings += item.servings
        g.days |= item.days
        counts[key] = counts.get(key, 0) + 1
    for key, g in groups.items():
        g.code = f"{counts[key]} item" + ("" if counts[key] == 1 else "s")
    return sorted(groups.values(), key=lambda c: c.amount, reverse=True)
