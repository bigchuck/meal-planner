# meal_planner/reports/report_columns.py
"""
Config-driven report column definitions.

Controls which nutrient columns appear in report grids (a)/(c)
and totals/micros summary lines (b). Adding or removing a column
from the report grid is a config-only change.

Supports two column types via the 'aggregation' field:
- "sum":  Values accumulate across items (Cal, P, C, F, Sug, GL, micros).
          Sourced from DailyTotals via totals_attr.
          Shown in per-item rows, meal summaries, and totals lines.
- "none": Per-item values only (e.g., GI). Not summable.
          Sourced from master data via master_col at build time.
          Shown in per-item rows only; blank in meal summaries and totals.

Reads the 'report_columns' block from meal_plan_config.json.
"""
from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass
class ReportColumnSpec:
    """
    Specification for a single report column.

    Attributes:
        name:         Logical key (e.g., "protein", "fiber", "gi")
        totals_attr:  DailyTotals attribute name (e.g., "protein_g"); None for non-aggregated
        master_col:   ColumnResolver property name for non-aggregated cols (e.g., "gi"); None for sum cols
        aggregation:  "sum" (accumulates across items) or "none" (per-item only)
        header:       Short header for grid display (e.g., "P")
        width:        Column width for right-justified grid formatting
        unit:         Display unit (e.g., "g", "mg", "mcg", "")
        rounding:     Rounding rule: "int" or "1f"
        totals_label: Label used in Totals/Micros summary line
        totals_group: "macro", "micro", or "none" (non-aggregated)
        show_in_grid: Whether this column appears in (a)/(c) grids
        grid_order:   Position in grid columns (None if not in grid)
        totals_order: Position within its totals_group line (0 if not in totals)
    """
    name: str
    totals_attr: Optional[str]
    master_col: Optional[str]
    aggregation: str
    header: str
    width: int
    unit: str
    rounding: str
    totals_label: str
    totals_group: str
    show_in_grid: bool
    grid_order: Optional[int]
    totals_order: int


class ReportColumnConfig:
    """
    Loaded report column configuration.

    Provides sorted column lists and formatting helpers consumed
    by Report.print(), Report.format_abbreviated(), _show_meals(),
    and format_nutrient_totals().
    """

    def __init__(self, columns: List[ReportColumnSpec]):
        self._columns = columns

    # =========================================================================
    # Construction
    # =========================================================================

    @classmethod
    def from_config(cls, config_dict: Dict[str, Any]) -> 'ReportColumnConfig':
        """
        Build from the 'report_columns' block in config.

        Args:
            config_dict: Full config dict (looks for 'report_columns' key)

        Returns:
            ReportColumnConfig instance (falls back to default if key absent)
        """
        rc_block = config_dict.get('report_columns')
        if not rc_block:
            return cls.default()

        columns = []
        errors = []

        for name, spec in rc_block.items():
            aggregation = spec.get('aggregation', 'sum')

            # Validate required fields based on aggregation type
            if aggregation == 'sum':
                required = ['totals_attr', 'header', 'width', 'totals_label',
                            'totals_group', 'totals_order']
            else:
                required = ['master_col', 'header', 'width']

            missing = [f for f in required if f not in spec]
            if missing:
                errors.append(f"report_columns.{name}: missing {', '.join(missing)}")
                continue

            show_in_grid = spec.get('show_in_grid', False)
            grid_order = spec.get('grid_order')

            if show_in_grid and grid_order is None:
                errors.append(
                    f"report_columns.{name}: show_in_grid=true requires grid_order"
                )
                continue

            columns.append(ReportColumnSpec(
                name=name,
                totals_attr=spec.get('totals_attr'),
                master_col=spec.get('master_col'),
                aggregation=aggregation,
                header=spec['header'],
                width=spec['width'],
                unit=spec.get('unit', ''),
                rounding=spec.get('rounding', 'int'),
                totals_label=spec.get('totals_label', ''),
                totals_group=spec.get('totals_group', 'none'),
                show_in_grid=show_in_grid,
                grid_order=grid_order,
                totals_order=spec.get('totals_order', 0),
            ))

        if errors:
            print("\nWarning: report_columns config issues:")
            for e in errors:
                print(f"  - {e}")
            if not columns:
                print("  Falling back to defaults.")
                return cls.default()

        return cls(columns)

    @classmethod
    def default(cls) -> 'ReportColumnConfig':
        """
        Hardcoded default matching the original report layout.

        Used as fallback when config block is absent.
        """
        # (name, totals_attr, master_col, aggregation, header, width, unit,
        #  rounding, totals_label, totals_group, show_in_grid, grid_order, totals_order)
        specs = [
            ("calories",  "calories",      None, "sum",  "Cal",   6, "",    "int", "Cal",    "macro", True,  1,  1),
            ("protein",   "protein_g",     None, "sum",  "P",     5, "g",   "int", "P",      "macro", True,  2,  2),
            ("carbs",     "carbs_g",       None, "sum",  "C",     5, "g",   "int", "C",      "macro", True,  3,  3),
            ("fat",       "fat_g",         None, "sum",  "F",     5, "g",   "int", "F",      "macro", True,  4,  4),
            ("sugar",     "sugar_g",       None, "sum",  "Sug",   6, "g",   "int", "Sugars", "macro", True,  5,  5),
            ("gl",        "glycemic_load", None, "sum",  "GL",    4, "",    "int", "GL",     "macro", True,  6,  6),
            ("fiber",     "fiber_g",       None, "sum",  "Fiber", 6, "g",   "int", "Fiber",  "micro", False, None, 1),
            ("sodium",    "sodium_mg",     None, "sum",  "Na",    7, "mg",  "int", "Na",     "micro", False, None, 2),
            ("potassium", "potassium_mg",  None, "sum",  "K",     7, "mg",  "int", "K",      "micro", False, None, 3),
            ("vitA",      "vitA_mcg",      None, "sum",  "VitA",  7, "mcg", "int", "VitA",   "micro", False, None, 4),
            ("vitC",      "vitC_mg",       None, "sum",  "VitC",  6, "mg",  "int", "VitC",   "micro", False, None, 5),
            ("iron",      "iron_mg",       None, "sum",  "Fe",    6, "mg",  "int", "Fe",     "micro", False, None, 6),
            ("gi",        None,            "gi", "none", "GI",    4, "",    "int", "GI",     "none",  False, None, 0),
        ]

        columns = [
            ReportColumnSpec(
                name=s[0], totals_attr=s[1], master_col=s[2], aggregation=s[3],
                header=s[4], width=s[5], unit=s[6], rounding=s[7],
                totals_label=s[8], totals_group=s[9], show_in_grid=s[10],
                grid_order=s[11], totals_order=s[12],
            )
            for s in specs
        ]
        return cls(columns)

    # =========================================================================
    # Column accessors
    # =========================================================================

    def grid_columns(self) -> List[ReportColumnSpec]:
        """Columns shown in (a)/(c) grids, sorted by grid_order."""
        return sorted(
            [c for c in self._columns if c.show_in_grid],
            key=lambda c: c.grid_order or 0
        )

    def macro_columns(self) -> List[ReportColumnSpec]:
        """Macro columns for Totals line, sorted by totals_order."""
        return sorted(
            [c for c in self._columns
             if c.totals_group == 'macro' and c.aggregation == 'sum'],
            key=lambda c: c.totals_order
        )

    def micro_columns(self) -> List[ReportColumnSpec]:
        """Micro columns for Micros line, sorted by totals_order."""
        return sorted(
            [c for c in self._columns
             if c.totals_group == 'micro' and c.aggregation == 'sum'],
            key=lambda c: c.totals_order
        )

    def non_aggregated_columns(self) -> List[ReportColumnSpec]:
        """All columns with aggregation='none'."""
        return [c for c in self._columns if c.aggregation == 'none']

    # =========================================================================
    # Value extraction
    # =========================================================================

    def _format_value(self, spec: ReportColumnSpec, totals) -> str:
        """Extract and format a single value from a DailyTotals instance."""
        val = getattr(totals, spec.totals_attr, 0)
        if spec.rounding == '1f':
            return f"{val:.1f}"
        return str(int(round(val)))

    def _format_item_value(self, spec: ReportColumnSpec, item_values: dict) -> str:
        """Format a non-aggregated value from item_values dict."""
        val = item_values.get(spec.name)
        if val is None:
            return ""
        if spec.rounding == '1f':
            return f"{val:.1f}"
        return str(int(round(val)))

    # =========================================================================
    # Grid formatting (sections a and c)
    # =========================================================================

    def grid_width(self) -> int:
        """Total character width of all grid columns including spacing."""
        cols = self.grid_columns()
        if not cols:
            return 0
        return sum(c.width for c in cols) + len(cols) - 1

    def build_grid_header(self) -> str:
        """Build header string for grid columns (e.g., '   Cal     P     C ...')."""
        parts = [f"{c.header:>{c.width}}" for c in self.grid_columns()]
        return " ".join(parts)

    def build_grid_blanks(self) -> str:
        """Build blank-filled string matching grid column widths."""
        parts = [f"{'':>{c.width}}" for c in self.grid_columns()]
        return " ".join(parts)

    def format_grid_values(self, totals, item_values: dict = None) -> str:
        """
        Format nutrient values for one row of the grid.

        For per-item rows (item_values provided):
          - sum columns read from totals
          - none columns read from item_values
        For summary rows (item_values=None):
          - sum columns read from totals
          - none columns render as blank
        """
        rounded = totals.rounded()
        parts = []
        for c in self.grid_columns():
            if c.aggregation == 'none':
                if item_values is not None:
                    val_str = self._format_item_value(c, item_values)
                    parts.append(f"{val_str:>{c.width}}")
                else:
                    parts.append(f"{'':>{c.width}}")
            else:
                parts.append(f"{self._format_value(c, rounded):>{c.width}}")
        return " ".join(parts)

    # =========================================================================
    # Totals / Micros line formatting (section b)
    # =========================================================================

    def format_totals_line(self, totals) -> str:
        """
        Format the 'Totals = ...' line from macro columns.

        Non-aggregated columns are excluded.
        """
        rounded = totals.rounded()
        parts = []
        for col in self.macro_columns():
            val = self._format_value(col, rounded)
            if col.unit:
                parts.append(f"{col.totals_label}: {val} {col.unit}")
            else:
                parts.append(f"{col.totals_label}: {val}")
        return "Totals = " + " | ".join(parts)

    def format_micros_line(self, totals) -> str:
        """
        Format the 'Micros = ...' line from micro columns.

        Only includes non-zero values. Non-aggregated columns excluded.
        Returns empty string if all zero.
        """
        rounded = totals.rounded()
        parts = []
        for col in self.micro_columns():
            val = getattr(rounded, col.totals_attr, 0)
            int_val = int(round(val))
            if int_val > 0:
                parts.append(f"{col.totals_label}: {int_val}{col.unit}")
        if not parts:
            return ""
        return "Micros = " + " | ".join(parts)

    def format_abbreviated_totals(self, totals) -> str:
        """
        Format abbreviated totals for staging/email.

        Non-aggregated columns excluded.
        """
        rounded = totals.rounded()
        parts = []
        for col in self.macro_columns():
            val = self._format_value(col, rounded)
            if col.unit:
                parts.append(f"{val}{col.unit} {col.totals_label}")
            else:
                parts.append(f"{col.totals_label}: {val}")
        return " | ".join(parts)