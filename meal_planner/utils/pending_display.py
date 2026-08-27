"""
Shared helpers for calculating and printing pending-day totals.

Used by commands that need to report the current pending day's nutrient
totals (add, close, chart, log-editing stash/apply flows) without each
duplicating the calculation or print formatting.
"""


def calculate_totals(master, items: list):
    """
    Calculate nutrient totals from a list of pending/log items.

    Args:
        master: MasterLoader instance used to look up nutrient values
        items: List of item dicts (code items or time markers)

    Returns:
        Tuple of (totals_dict, missing_codes, code_strings)
    """
    totals = {
        "cal": 0.0, "prot_g": 0.0, "carbs_g": 0.0,
        "fat_g": 0.0, "sugar_g": 0.0, "gl": 0.0
    }
    missing = []
    code_strs = []

    for item in items:
        # Time marker
        if "time" in item and item.get("time"):
            time_str = f"@{item['time']}"
            meal_override = item.get("meal_override")
            if meal_override:
                time_str += f" ({meal_override})"
            code_strs.append(time_str)
            continue

        # Code item
        if "code" not in item:
            continue

        code = str(item["code"]).upper()
        mult = float(item.get("mult", 1.0))

        # Look up in master
        nutrients = master.get_nutrient_totals(code, mult)

        if nutrients is None:
            missing.append(code)
            continue

        # Accumulate
        for key in totals.keys():
            totals[key] += nutrients.get(key, 0.0)

        # Format code string
        if mult < 0:
            amag = abs(mult)
            code_strs.append(
                f"-{code}" if abs(amag - 1.0) < 1e-9 else f"-{code} x{amag:g}"
            )
        else:
            code_strs.append(
                f"{code} x{mult:g}" if abs(mult - 1.0) > 1e-9 else code
            )

    return totals, missing, code_strs


def print_day_summary(ctx) -> None:
    """
    Print the "Current Day" totals block for the active pending day.

    Args:
        ctx: CommandContext (used for ctx.pending_mgr and ctx.master)
    """
    try:
        pending = ctx.pending_mgr.load()
    except Exception:
        print("\n(No active day. Use 'start' to begin.)\n")
        return

    if pending is None or not pending.get("items"):
        print("\n(No active day. Use 'start' to begin.)\n")
        return

    items = pending.get("items", [])
    totals, missing, code_strs = calculate_totals(ctx.master, items)

    print("\n--- Current Day ---")
    print(f"Date: {pending.get('date')}")
    print(f"Codes: {', '.join(code_strs) if code_strs else '(none)'}")
    print(f"Calories: {int(round(totals['cal']))}")
    print(f"Protein: {int(round(totals['prot_g']))} g")
    print(f"Carbs: {int(round(totals['carbs_g']))} g")
    print(f"Fat: {int(round(totals['fat_g']))} g")
    print(f"Sugars: {int(round(totals['sugar_g']))} g")
    print(f"GL: {int(round(totals['gl']))}")

    if missing:
        print(f"Missing codes (not included): {', '.join(missing)}")

    print("--------------------\n")
