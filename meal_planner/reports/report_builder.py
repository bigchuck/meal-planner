"""
Report builder for nutrient breakdowns.

Generates detailed reports showing each item's contribution to daily totals.
"""
from typing import List, Dict, Any, Tuple
import pandas as pd

from meal_planner.models import DailyTotals, NutrientRow
from meal_planner.data import MasterLoader
from meal_planner.utils import ColumnResolver
from meal_planner.utils.time_utils import categorize_time, normalize_meal_name, MEAL_NAMES

class ReportBuilder:
    """
    Builds detailed nutrient reports from item lists.
    
    Shows breakdown of each code with its multiplier and nutrient contributions.
    """
    
    def __init__(self, master: MasterLoader):
        """
        Initialize report builder.
        
        Args:
            master: MasterLoader instance for lookups
        """
        self.master = master
    
    def build_from_items(self, items: List[Dict[str, Any]], 
                        title: str = "Report") -> 'Report':
        """
        Build report from items list.
        
        Args:
            items: List of item dicts (codes and time markers)
            title: Report title
        
        Returns:
            Report object with rows, totals, and display order
        """
        rows = []
        totals = DailyTotals()
        missing = []
        display = []  # Preserves order: ("row", idx) or ("time", item_dict)
        
        cols = self.master.cols
        
        for item in items:
            # Time marker - store the full item dict
            if "time" in item and item.get("time"):
                display.append(("time", item))
                continue
            
            # Skip non-code items
            if "code" not in item:
                continue
            
            code = str(item["code"]).upper()
            mult = float(item.get("mult", 1.0))
            
            # Look up in master
            row_data = self.master.lookup_code(code)
            
            if row_data is None:
                missing.append(code)
                continue
            
            # Calculate nutrient totals for this item
            item_totals = DailyTotals(
                calories=self._safe_float(row_data.get(cols.cal, 0)) * mult,
                protein_g=self._safe_float(row_data.get(cols.prot_g, 0)) * mult,
                carbs_g=self._safe_float(row_data.get(cols.carbs_g, 0)) * mult,
                fat_g=self._safe_float(row_data.get(cols.fat_g, 0)) * mult,
                sugar_g=self._safe_float(row_data.get(cols.sugar_g, 0)) * mult if cols.sugar_g else 0.0,
                glycemic_load=self._safe_float(row_data.get(cols.gl, 0)) * mult if cols.gl else 0.0,
            )

            # Add micronutrients from nutrients manager if available
            micro_data = self.master.get_nutrients(code)
            if micro_data:
                item_totals.fiber_g = self._safe_float(micro_data.get('fiber_g', 0)) * mult
                item_totals.sodium_mg = self._safe_float(micro_data.get('sodium_mg', 0)) * mult
                item_totals.potassium_mg = self._safe_float(micro_data.get('potassium_mg', 0)) * mult
                item_totals.vitA_mcg = self._safe_float(micro_data.get('vitA_mcg', 0)) * mult
                item_totals.vitC_mg = self._safe_float(micro_data.get('vitC_mg', 0)) * mult
                item_totals.iron_mg = self._safe_float(micro_data.get('iron_mg', 0)) * mult
        
            
            # Create row
            row = NutrientRow(
                code=code,
                option=str(row_data.get(cols.option, "")),
                section=str(row_data.get(cols.section, "")),
                multiplier=mult,
                totals=item_totals
            )
            
            # Track in display order
            row_idx = len(rows)
            rows.append(row)
            display.append(("row", row_idx))
            
            # Accumulate totals
            totals = totals + item_totals
        
        return Report(rows, totals, missing, display, title)
    
    def _safe_float(self, value, default: float = 0.0) -> float:
        """Safely convert to float."""
        try:
            if value is None or (isinstance(value, float) and pd.isna(value)):
                return default
            return float(value)
        except (ValueError, TypeError):
            return default


class Report:
    """
    Container for a nutrient report.
    
    Attributes:
        rows: List of NutrientRow objects
        totals: DailyTotals for entire report
        missing: List of codes not found in master
        display: Display order (preserves time markers)
        title: Report title
    """
    
    def __init__(self, rows: List[NutrientRow], totals: DailyTotals,
                 missing: List[str], display: List[Tuple[str, Any]], 
                 title: str = "Report"):
        """Initialize report."""
        self.rows = rows
        self.totals = totals
        self.missing = missing
        self.display = display
        self.title = title
    
    def print(self, verbose: bool = False) -> None:
        """Print formatted report to console."""
        print(f"\n=== {self.title} ===")
        
        if not self.rows and not self.display:
            print("(no items)")
            print()
            return
    
        opt_width = 41 if verbose else 21
        line_width = 98 if verbose else 78

        # Header
        print(f"{'CODE':>8} {'Section':<8} {'x':>4} {'Option':<{opt_width}} "
            f"{'Cal':>6} {'P':>5} {'C':>5} {'F':>5} {'Sug':>6} {'GL':>4}")
        print("-" * line_width)
        
        # Display rows in order (with time markers)
        for kind, val in self.display:
            if kind == "time":
                # Time marker row - val is the full item dict
                time_str = val.get("time", "")
                meal_override = val.get("meal_override")
                display_str = f"@{time_str}"
                if meal_override:
                    display_str += f" ({meal_override})"
                print(f"{'':>8} {'':<8} {'':>4} {'time: '+display_str:<{opt_width}} "
                    f"{'':>6} {'':>5} {'':>5} {'':>5} {'':>6} {'':>4}")
            else:
                # Nutrient row
                row = self.rows[val]
                self._print_row(row, verbose=verbose)
        
        # Totals
        print("-" * line_width)
        rounded = self.totals.rounded()
        print(f"Totals = Cal: {int(rounded.calories)} | "
              f"P: {int(rounded.protein_g)} g | "
              f"C: {int(rounded.carbs_g)} g | "
              f"F: {int(rounded.fat_g)} g | "
              f"Sugars: {int(rounded.sugar_g)} g | "
              f"GL: {int(rounded.glycemic_load)}")
        # Add nutrient totals if available
        nutrient_line = self.format_nutrient_totals()
        if nutrient_line:
            print(f"Micros = {nutrient_line}")
        
        if self.missing:
            print(f"Missing (not counted): {', '.join(self.missing)}")
        
        print()
    
    def _print_row(self, row: NutrientRow, verbose: bool = False) -> None:
        """Print a single nutrient row."""
        # Format multiplier (right-aligned, max 4 chars)
        mult_str = self._format_mult(row.multiplier)
        
        # Truncate option if too long
        opt = row.option
        if verbose:
            # Verbose: 40 chars + "+" if longer
            opt_display = (opt[:40] + "+") if len(opt) > 40 else opt
            opt_width = 41
        else:
            # Normal: 20 chars + "+" if longer
            opt_display = (opt[:20] + "+") if len(opt) > 20 else opt
            opt_width = 21
        
        # Section truncated to 8 chars
        sect = row.section[:8]
        
        # Rounded totals
        t = row.totals.rounded()
        
        print(f"{row.code:>8} {sect:<8} {mult_str:>4} {opt_display:<{opt_width}} "
              f"{int(t.calories):>6} {int(t.protein_g):>5} "
              f"{int(t.carbs_g):>5} {int(t.fat_g):>5} "
              f"{int(t.sugar_g):>6} {int(t.glycemic_load):>4}")
    
    def _format_mult(self, mult: float) -> str:
        """
        Format multiplier to max 4 chars, right-aligned.
        
        Rules:
        - Always show value (including 1)
        - Integers without decimal: "1", "4", "10"
        - With decimals, fit in 4 chars: "1.5", "0.58", ".125"
        - Max 4 characters total
        """
        # Check if it's effectively an integer
        if abs(mult - round(mult)) < 1e-9:
            s = str(int(round(mult)))
            if len(s) <= 4:
                return s
            return s[:4]  # Truncate if too long
        
        # Has decimal component - try to fit with max precision
        # Try different decimal places: 3, 2, 1, 0
        for dp in (3, 2, 1, 0):
            s = f"{mult:.{dp}f}"
            
            # Strip trailing zeros but keep at least one decimal place
            if '.' in s:
                s = s.rstrip('0')
                # If we stripped all decimals, this becomes integer case
                if s.endswith('.'):
                    s = s[:-1]
            
            if len(s) <= 4:
                return s
        
        # Still too long - round to fit
        # For values < 1, try ".XXX" format (drop leading 0)
        if mult < 1:
            for dp in (3, 2, 1):
                s = f"{mult:.{dp}f}"[1:]  # Drop leading "0"
                if len(s) <= 4:
                    return s
        
        # Fallback: just round and truncate
        s = f"{mult:.1f}"
        return s[:4]
    
    def get_meal_breakdown(self):
        """
        Analyze meal breakdown from time markers.
        
        Returns:
            List of tuples: (meal_name, first_time, DailyTotals)
            Returns None if no time markers present
        """
        if not self.display:
            return None
        
        # Check if any time markers exist
        has_time_markers = any(kind == "time" for kind, _ in self.display)
        if not has_time_markers:
            return None
        
        # Group items by time segments
        segments = []  # List of (time_item_dict, [row_indices])
        current_time_item = None
        current_rows = []
        
        for kind, val in self.display:
            if kind == "time":
                # Save previous segment if exists
                if current_time_item is not None or current_rows:
                    segments.append((current_time_item, current_rows))
                # Start new segment - val is full item dict
                current_time_item = val
                current_rows = []
            elif kind == "row":
                current_rows.append(val)
        
        # Don't forget last segment
        if current_time_item is not None or current_rows:
            segments.append((current_time_item, current_rows))
        
        # If first segment has no time, assign to breakfast
        if segments and segments[0][0] is None:
            segments[0] = ({"time": "05:00"}, segments[0][1])
        
        # Categorize segments into meals
        meal_categories = {meal: [] for meal in MEAL_NAMES}

        for time_item, row_indices in segments:
            if not row_indices:
                continue
            
            time_str = time_item.get("time", "05:00")
            meal_override = time_item.get("meal_override")
            
            meal_name = categorize_time(time_str, meal_override)
            if meal_name:
                meal_categories[meal_name].append((time_str, row_indices))
        
        # Build result with subtotals
        result = []
        canonical_order = MEAL_NAMES
        
        for meal_name in canonical_order:
            segments_for_meal = meal_categories[meal_name]
            if not segments_for_meal:
                continue
            
            # Get first time for this meal
            first_time = segments_for_meal[0][0]
            
            # Calculate subtotals for all segments in this meal
            meal_totals = DailyTotals()
            for _, row_indices in segments_for_meal:
                for row_idx in row_indices:
                    meal_totals = meal_totals + self.rows[row_idx].totals
            
            result.append((meal_name, first_time, meal_totals))
        
        return result if result else None
    
    def format_abbreviated(self) -> List[str]:
        """
        Format report in abbreviated style for phone/email viewing.
        
        Abbreviated format:
        - Title
        - Code xMult - Description (no macro columns)
        - Time markers preserved
        - Totals line without "TOTAL" prefix
        - Missing codes if any
        
        Returns:
            List of formatted output lines
        """
        lines = []
        
        # Title
        lines.append(f"\n=== {self.title} ===")
        
        if not self.rows and not self.display:
            lines.append("(no items)")
            lines.append("")
            return lines
        
        # Items (no header row for abbreviated format)
        for kind, val in self.display:
            if kind == "time":
                # Time marker
                time_str = val.get("time", "")
                meal_override = val.get("meal_override")
                display_str = f"@{time_str}"
                if meal_override:
                    display_str += f" ({meal_override})"
                lines.append(f"  {display_str}")
            else:
                # Nutrient row - abbreviated format
                row = self.rows[val]
                lines.append(self._format_abbreviated_row(row))
        
        # Totals (without "TOTAL" prefix)
        rounded = self.totals.rounded()
        totals_line = (f"{int(rounded.calories)} cal | "
                    f"{int(rounded.protein_g)}g P | "
                    f"{int(rounded.carbs_g)}g C | "
                    f"{int(rounded.fat_g)}g F | "
                    f"{int(rounded.sugar_g)}g Sugars | "
                    f"GL: {int(rounded.glycemic_load)}")
        lines.append("")
        lines.append(totals_line)
        
        if self.missing:
            lines.append(f"Missing (not counted): {', '.join(self.missing)}")
        
        lines.append("")
        return lines

    def _format_abbreviated_row(self, row: NutrientRow) -> str:
        """
        Format a single row in abbreviated style.
        
        Format: CODE xMULT - Description
        Always shows multiplier.
        
        Args:
            row: NutrientRow to format
        
        Returns:
            Formatted string
        """
        # Format multiplier - always show
        mult_str = self._format_mult(row.multiplier)
        
        # Build line: CODE xMULT - Description
        return f"  {row.code} x{mult_str} - {row.option}"
    
    def format_nutrient_totals(self) -> str:
        """
        Format nutrient totals line similar to macros.
        
        Returns:
            Formatted string like: "Fiber: 25g | Na: 2300mg | K: 3500mg | VitA: 900mcg | VitC: 90mg | Fe: 18mg"
        """
        t = self.totals.rounded()
        
        parts = []
        
        # Only include non-zero values
        if t.fiber_g > 0:
            parts.append(f"Fiber: {int(t.fiber_g)}g")
        if t.sodium_mg > 0:
            parts.append(f"Na: {int(t.sodium_mg)}mg")
        if t.potassium_mg > 0:
            parts.append(f"K: {int(t.potassium_mg)}mg")
        if t.vitA_mcg > 0:
            parts.append(f"VitA: {int(t.vitA_mcg)}mcg")
        if t.vitC_mg > 0:
            parts.append(f"VitC: {int(t.vitC_mg)}mg")
        if t.iron_mg > 0:
            parts.append(f"Fe: {int(t.iron_mg)}mg")
        
        if not parts:
            return ""
        
        return " | ".join(parts)