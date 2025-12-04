"""
What-if command - preview removal of items.
"""
import re
from .base import Command, register_command
from meal_planner.reports.report_builder import ReportBuilder
from meal_planner.parsers import CodeParser


@register_command
class WhatIfCommand(Command):
    """Preview totals with items removed."""
    
    name = "whatif"
    help_text = "Preview removing items (whatif 3,5 or whatif 2025-01-15 3-5)"
    
    def execute(self, args: str) -> None:
        """
        Show what-if scenario removing items.
        
        Args:
            args: Indices to remove, or date + indices
                  Examples: "3,5", "2-4", "2025-01-15 3,5"
        """
        if not args.strip():
            print("Usage: whatif <indices> or whatif <YYYY-MM-DD> <indices>")
            print("Examples:")
            print("  whatif 3,5       - Remove items 3 and 5 from pending")
            print("  whatif 2-4       - Remove items 2, 3, 4 from pending")
            print("  whatif 2025-01-15 3,5  - Remove items from that log date")
            return
        
        # Parse arguments
        tokens = args.strip().split()
        
        # Check if first token is a date
        if len(tokens) >= 2 and re.match(r"\d{4}-\d{2}-\d{2}", tokens[0]):
            # whatif <date> <indices>
            query_date = tokens[0]
            indices_str = " ".join(tokens[1:])
            self._whatif_log_date(query_date, indices_str)
        else:
            # whatif <indices>
            indices_str = args.strip()
            self._whatif_pending(indices_str)
    
    def _whatif_pending(self, indices_str: str) -> None:
        """What-if for pending day."""
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            pending = None
        
        if pending is None or not pending.get("items"):
            print("\nNo pending items to preview.\n")
            return
        
        base_items = pending.get("items", [])
        label = f"pending ({pending.get('date', 'unknown')})"
        
        self._show_whatif_preview(base_items, indices_str, label)
    
    def _whatif_log_date(self, query_date: str, indices_str: str) -> None:
        """What-if for log date."""
        # Get entries for date
        entries = self.ctx.log.get_entries_for_date(query_date)
        
        if entries.empty:
            print(f"\nNo log entries found for {query_date}.\n")
            return
        
        # Parse codes
        codes_col = self.ctx.log.cols.codes
        all_codes = ", ".join([
            str(v) for v in entries[codes_col].fillna("")
            if str(v).strip()
        ])
        
        if not all_codes.strip():
            print(f"\nNo codes for {query_date}.\n")
            return
        
        base_items = CodeParser.parse(all_codes)
        
        self._show_whatif_preview(base_items, indices_str, query_date)
    
    def _show_whatif_preview(self, base_items: list, indices_str: str, label: str) -> None:
        """
        Show what-if preview.
        
        Args:
            base_items: Original items list
            indices_str: Indices to remove (e.g., "3,5" or "2-4")
            label: Label for output
        """
        n = len(base_items)
        
        if n == 0:
            print(f"\nWHAT-IF PREVIEW ({label}) - no items to remove.\n")
            return
        
        # Parse indices (convert 1-based to 0-based)
        drop_indices = self._parse_indices(indices_str, n)
        
        if not drop_indices:
            print(f"\nNo valid indices to remove.\n")
            return
        
        drop_1based = {i + 1 for i in drop_indices}
        
        # Build reports
        builder = ReportBuilder(self.ctx.master, self.ctx.nutrients)
        
        # Original report
        original_report = builder.build_from_items(
            base_items, 
            title=f"Original ({label})"
        )
        
        # Excluded items
        excluded_items = [base_items[i] for i in drop_indices]
        
        # Kept items
        kept_items = [
            item for i, item in enumerate(base_items)
            if i not in drop_indices
        ]
        
        # Print header
        print(f"\nWHAT-IF PREVIEW (no changes saved) - {label}")
        print("-" * 78)
        
        # Show what's being excluded
        if excluded_items:
            print("Excluded:")
            for i in sorted(drop_1based):
                item = base_items[i - 1]
                if "time" in item:
                    print(f"  - #{i} @{item['time']}")
                elif "code" in item:
                    code = item["code"]
                    mult = item.get("mult", 1.0)
                    mult_str = f" x{mult}" if abs(mult - 1.0) > 1e-9 else ""
                    print(f"  - #{i} {code}{mult_str}")
        
        # Build and show adjusted report
        print()
        adjusted_report = builder.build_from_items(
            kept_items,
            title=f"Adjusted ({len(kept_items)} items remaining)"
        )
        adjusted_report.print()
        
        # Show delta
        delta = adjusted_report.totals + (original_report.totals * -1)
        delta_rounded = delta.rounded()
        
        print("Change from original:")
        print(f"  Cal: {self._format_delta(delta_rounded.calories)} | "
              f"P: {self._format_delta(delta_rounded.protein_g)} g | "
              f"C: {self._format_delta(delta_rounded.carbs_g)} g | "
              f"F: {self._format_delta(delta_rounded.fat_g)} g | "
              f"Sugars: {self._format_delta(delta_rounded.sugar_g)} g | "
              f"GL: {self._format_delta(delta_rounded.glycemic_load)}")
        print()
    
    def _parse_indices(self, indices_str: str, max_idx: int) -> list:
        """
        Parse indices string into 0-based list.
        
        Args:
            indices_str: String like "3,5" or "2-4"
            max_idx: Maximum valid index (length of list)
        
        Returns:
            List of 0-based indices
        """
        indices = set()
        
        for part in indices_str.split(","):
            part = part.strip()
            if not part:
                continue
            
            if "-" in part:
                # Range: "2-4"
                try:
                    a, b = part.split("-", 1)
                    start = int(a.strip())
                    end = int(b.strip())
                    for i in range(min(start, end), max(start, end) + 1):
                        if 1 <= i <= max_idx:
                            indices.add(i - 1)  # Convert to 0-based
                except ValueError:
                    pass
            else:
                # Single index
                try:
                    i = int(part)
                    if 1 <= i <= max_idx:
                        indices.add(i - 1)  # Convert to 0-based
                except ValueError:
                    pass
        
        return sorted(indices)
    
    def _format_delta(self, value: float) -> str:
        """Format delta with +/- sign."""
        v = int(value)
        if v >= 0:
            return f"+{v}"
        else:
            return str(v)