"""
Report builder for nutrient breakdowns.

Generates detailed reports showing each item's contribution to daily totals.
"""
from typing import List, Dict, Any, Tuple
import pandas as pd

from meal_planner.models import DailyTotals, NutrientRow
from meal_planner.data import MasterLoader
from meal_planner.utils import ColumnResolver


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
        display = []  # Preserves order: ("row", idx) or ("time", "HH:MM")
        
        cols = self.master.cols
        
        for item in items:
            # Time marker
            if "time" in item and item.get("time"):
                display.append(("time", str(item["time"])))
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
    
    def print(self) -> None:
        """Print formatted report to console."""
        print(f"\n=== {self.title} ===")
        
        if not self.rows and not self.display:
            print("(no items)")
            print()
            return
        
        # Header
        print(f"{'CODE':>8} {'Section':<8} {'x':>4} {'Option':<21} "
              f"{'Cal':>6} {'P':>5} {'C':>5} {'F':>5} {'Sug':>6} {'GL':>4}")
        print("-" * 78)
        
        # Display rows in order (with time markers)
        for kind, val in self.display:
            if kind == "time":
                # Time marker row
                print(f"{'':>8} {'':<8} {'':>4} {'time: '+str(val):<21} "
                      f"{'':>6} {'':>5} {'':>5} {'':>5} {'':>6} {'':>4}")
            else:
                # Nutrient row
                row = self.rows[val]
                self._print_row(row)
        
        # Totals
        print("-" * 78)
        rounded = self.totals.rounded()
        print(f"Totals = Cal: {int(rounded.calories)} | "
              f"P: {int(rounded.protein_g)} g | "
              f"C: {int(rounded.carbs_g)} g | "
              f"F: {int(rounded.fat_g)} g | "
              f"Sugars: {int(rounded.sugar_g)} g | "
              f"GL: {int(rounded.glycemic_load)}")
        
        if self.missing:
            print(f"Missing (not counted): {', '.join(self.missing)}")
        
        print()
    
    def _print_row(self, row: NutrientRow) -> None:
        """Print a single nutrient row."""
        # Format multiplier (right-aligned, max 4 chars)
        mult_str = self._format_mult(row.multiplier)
        
        # Truncate option if too long
        opt = row.option
        opt_display = (opt[:20] + "+") if len(opt) > 20 else opt
        
        # Section truncated to 8 chars
        sect = row.section[:8]
        
        # Rounded totals
        t = row.totals.rounded()
        
        print(f"{row.code:>8} {sect:<8} {mult_str:>4} {opt_display:<21} "
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
        segments = []  # List of (time_str, [row_indices])
        current_time = None
        current_rows = []
        
        for kind, val in self.display:
            if kind == "time":
                # Save previous segment if exists
                if current_time is not None or current_rows:
                    segments.append((current_time, current_rows))
                # Start new segment
                current_time = val
                current_rows = []
            elif kind == "row":
                current_rows.append(val)
        
        # Don't forget last segment
        if current_time is not None or current_rows:
            segments.append((current_time, current_rows))
        
        # If first segment has no time, assign to breakfast
        if segments and segments[0][0] is None:
            segments[0] = ("05:00", segments[0][1])  # Arbitrary breakfast time
        
        # Categorize segments into meals
        meal_categories = {
            "BREAKFAST": [],
            "MORNING SNACK": [],
            "LUNCH": [],
            "AFTERNOON SNACK": [],
            "DINNER": [],
            "EVENING": []
        }
        
        for time_str, row_indices in segments:
            if not row_indices:
                continue
            
            meal_name = self._categorize_time(time_str)
            if meal_name:
                meal_categories[meal_name].append((time_str, row_indices))
        
        # Build result with subtotals
        result = []
        canonical_order = [
            "BREAKFAST", "MORNING SNACK", "LUNCH", 
            "AFTERNOON SNACK", "DINNER", "EVENING"
        ]
        
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
    
    def _categorize_time(self, time_str: str) -> str:
        """
        Categorize time string into meal name.
        
        Args:
            time_str: Time in HH:MM format
        
        Returns:
            Meal name or None
        """
        if not time_str:
            return None
        
        try:
            # Parse HH:MM
            parts = time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            
            # Convert to minutes since midnight for easier comparison
            total_minutes = hour * 60 + minute
            
            # Time ranges (in minutes)
            # Breakfast: 05:00 - 10:29 (300 - 629)
            # Morning Snack: 10:30 - 11:59 (630 - 719)
            # Lunch: 12:00 - 14:29 (720 - 869)
            # Afternoon Snack: 14:30 - 16:59 (870 - 1019)
            # Dinner: 17:00 - 19:59 (1020 - 1199)
            # Evening: 20:00 - 04:59 (1200+ or 0-299)
            
            if 300 <= total_minutes <= 629:
                return "BREAKFAST"
            elif 630 <= total_minutes <= 719:
                return "MORNING SNACK"
            elif 720 <= total_minutes <= 869:
                return "LUNCH"
            elif 870 <= total_minutes <= 1019:
                return "AFTERNOON SNACK"
            elif 1020 <= total_minutes <= 1199:
                return "DINNER"
            else:  # 1200+ or 0-299
                return "EVENING"
        except:
            return None
