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