# meal_planner/commands/analyze_command.py
"""
Analyze command for template-based meal nutrition analysis.

Compares consumed meals against nutritional targets defined in templates.
"""
import shlex
from datetime import date as date_type
from typing import Optional, Dict, Any, List, Tuple
from .base import Command, register_command
from meal_planner.parsers import parse_selection_to_items
from meal_planner.utils.time_utils import categorize_time


@register_command
class AnalyzeCommand(Command):
    """Analyze meals against nutritional templates."""
    
    name = "analyze"
    help_text = "Analyze meals against template (analyze [date] --template <key>)"
    
    def execute(self, args: str) -> None:
        """
        Analyze meals against a nutritional template.
        
        Args:
            args: Command arguments
        
        Examples:
            analyze --template meal_templates.breakfast.protein_low_carb
            analyze 2024-12-20 --template meal_templates.breakfast.protein_low_carb
            analyze 2024-12-20 --template "meal_templates.morning snack.low_cal"
        """
        if not self._check_thresholds("analyze"):
            return
        
        # Parse arguments
        args_list = shlex.split(args) if args else []
        
        if not args_list:
            print("Usage: analyze [date] --template <template_key>")
            print("\nExamples:")
            print("  analyze --template meal_templates.breakfast.protein_low_carb")
            print("  analyze 2024-12-20 --template meal_templates.lunch.balanced")
            print('  analyze 2024-12-20 --template "meal_templates.morning snack.low_cal"')
            return
        
        # Extract date and template
        target_date = None
        template_key = None
        
        i = 0
        while i < len(args_list):
            arg = args_list[i]
            
            if arg == "--template":
                if i + 1 < len(args_list):
                    template_key = args_list[i + 1]
                    i += 2
                else:
                    print("Error: --template requires a key path")
                    return
            else:
                # Assume it's a date
                if target_date is None:
                    target_date = arg
                    i += 1
                else:
                    print(f"Error: Unexpected argument '{arg}'")
                    return
        
        if not template_key:
            print("Error: --template is required")
            print("Example: analyze --template meal_templates.breakfast.protein_low_carb")
            return
        
        # Load template
        template = self._load_template(template_key)
        if not template:
            return  # Error already printed
        
        # Extract meal category from template key
        meal_category = self._extract_meal_category(template_key)
        if not meal_category:
            print(f"Error: Could not extract meal category from template key: {template_key}")
            print("Expected format: meal_templates.<meal_name>.<template_name>")
            return
        
        # Determine date and source
        if target_date:
            # Validate date format (YYYY-MM-DD)
            if len(target_date) != 10 or target_date[4] != '-' or target_date[7] != '-':
                print(f"Error: Invalid date format '{target_date}'. Use YYYY-MM-DD")
                return
            use_pending = False
            analysis_date = target_date
        else:
            # No date specified - use pending
            use_pending = True
            analysis_date = str(date_type.today())
        
        # Get meals
        if use_pending:
            items, meal_totals = self._get_totals_from_pending(meal_category)
            date_str = "today (pending)"
        else:
            items, meal_totals = self._get_totals_from_log(analysis_date, meal_category)
            date_str = analysis_date
        
        if meal_totals is None:
            print(f"\n=== {meal_category.title()} Analysis ({date_str}) ===")
            print(f"Template: {template.get('display_name', template_key)}")
            print(f"\nNo {meal_category} meals found for {date_str}\n")
            return
        
        # Compare against template
        self._display_analysis(template, template_key, meal_category, date_str, 
                              items, meal_totals)
    
    def _load_template(self, template_key: str) -> Optional[Dict[str, Any]]:
        """Load template from thresholds using dot-notation key path."""
        data = self.ctx.thresholds.thresholds
        
        if not template_key:
            print("Error: Template key is required")
            return None
        
        # Navigate to template
        keys = template_key.split('.')
        current = data
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                print(f"Error: Template not found: {template_key}")
                return None
        
        # Verify it has targets
        if not isinstance(current, dict) or 'targets' not in current:
            print(f"Error: Template missing 'targets' section: {template_key}")
            return None
        
        return current
    
    def _extract_meal_category(self, template_key: str) -> Optional[str]:
        """
        Extract meal category from template key.
        
        Expected format: meal_templates.<meal_name>.<template_name>
        Returns: <meal_name>
        """
        parts = template_key.split('.')
        
        if len(parts) < 3 or parts[0] != 'meal_templates':
            return None
        
        return parts[1]
    
    def _get_totals_from_pending(self, meal_category: str) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, float]]]:
        """Get nutrient totals for matching meal category from pending."""
        from meal_planner.reports.report_builder import ReportBuilder
        
        pending = self.ctx.pending_mgr.load()
        if not pending or not pending.get('items'):
            return [], None
        
        items = pending['items']
        
        # Build report to get meal breakdown
        builder = ReportBuilder(self.ctx.master, self.ctx.nutrients)
        report = builder.build_from_items(items, title="Analysis")
        
        breakdown = report.get_meal_breakdown()
        if not breakdown:
            return [], None
        
        # Sum totals for all meals matching the category
        matching_totals = None
        matching_items = []
        
        for m_name, first_time, meal_totals in breakdown:
            if m_name.upper() == meal_category.upper():
                if matching_totals is None:
                    matching_totals = meal_totals
                else:
                    matching_totals = matching_totals + meal_totals
                
                # Extract items for this meal
                meal_items = self._extract_meal_items(items, m_name)
                matching_items.extend(meal_items)
        
        if matching_totals is None:
            return [], None
        
        # Convert DailyTotals to dict
        nutrient_dict = self._totals_to_dict(matching_totals)
        
        return matching_items, nutrient_dict
    
    def _get_totals_from_log(self, target_date: str, meal_category: str) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, float]]]:
        """Get nutrient totals for matching meal category from log."""
        from meal_planner.reports.report_builder import ReportBuilder
        from meal_planner.utils.columns import get_codes_column
        
        # Get log entries for date
        entries = self.ctx.log.get_entries_for_date(target_date)
        if entries.empty:
            return [], None
        
        codes_col = get_codes_column(entries)
        
        # Get codes string
        codes_str = entries.iloc[0][codes_col]
        if not codes_str or str(codes_str).strip() == '':
            return [], None
        
        # Parse into items
        items = parse_selection_to_items(str(codes_str))
        if not items:
            return [], None
        
        # Build report to get meal breakdown
        builder = ReportBuilder(self.ctx.master, self.ctx.nutrients)
        report = builder.build_from_items(items, title="Analysis")
        
        breakdown = report.get_meal_breakdown()
        if not breakdown:
            return [], None
        
        # Sum totals for all meals matching the category
        matching_totals = None
        matching_items = []
        
        for m_name, first_time, meal_totals in breakdown:
            if m_name.upper() == meal_category.upper():
                if matching_totals is None:
                    matching_totals = meal_totals
                else:
                    matching_totals = matching_totals + meal_totals
                
                # Extract items for this meal
                meal_items = self._extract_meal_items(items, m_name)
                matching_items.extend(meal_items)
        
        if matching_totals is None:
            return [], None
        
        # Convert DailyTotals to dict
        nutrient_dict = self._totals_to_dict(matching_totals)
        
        return matching_items, nutrient_dict
    
    def _extract_meal_items(self, items: List[Dict[str, Any]], meal_name: str) -> List[Dict[str, Any]]:
        """Extract items belonging to a specific meal."""
        meal_items = []
        current_meal = []
        current_time = None
        current_meal_override = None
        in_target_meal = False
        
        for item in items:
            # Time marker
            if 'time' in item:
                # Save previous meal if it was our target
                if in_target_meal and current_meal:
                    meal_items.extend(current_meal)
                
                # Start new meal
                current_meal = []
                current_time = item.get('time')
                current_meal_override = item.get('meal_override')
                
                # Check if this is our target meal
                detected_meal = categorize_time(current_time, current_meal_override)
                in_target_meal = (detected_meal and detected_meal.upper() == meal_name.upper())
                continue
            
            # Regular item
            if 'code' in item and in_target_meal:
                current_meal.append(item)
        
        # Add last meal if it was our target
        if in_target_meal and current_meal:
            meal_items.extend(current_meal)
        
        return meal_items
    
    def _totals_to_dict(self, totals) -> Dict[str, float]:
        """Convert DailyTotals object to dict for template comparison."""
        return {
            'cal': totals.calories,
            'protein': totals.protein_g,
            'carbs': totals.carbs_g,
            'fat': totals.fat_g,
            'fiber': totals.fiber_g,
            'sugar': totals.sugar_g,
            'gl': totals.glycemic_load,
            'sodium': totals.sodium_mg,
            'potassium': totals.potassium_mg,
        }
    
    def _display_analysis(self, template: Dict[str, Any], template_key: str,
                         meal_category: str, date_str: str,
                         items: List[Dict[str, Any]], 
                         nutrient_totals: Dict[str, float]) -> None:
        """Display analysis results in ASCII format."""
        display_name = template.get('display_name', template_key)
        
        print(f"\n=== {meal_category.title()} Analysis ({date_str}) ===")
        print(f"Template: {display_name}")
        print()
        
        # Show consumed meals summary
        print("Consumed meals:")
        codes = []
        for item in items:
            if 'code' not in item:
                continue
            code = item.get('code', '').upper()
            mult = item.get('mult', 1.0)
            if mult == 1.0:
                codes.append(code)
            else:
                codes.append(f"{code} x{mult:g}")
        
        if codes:
            print(f"  {meal_category}: {', '.join(codes)}")
        print()
        
        # Analyze nutrients
        targets = template.get('targets', {})
        
        print("Nutrient Analysis:")
        
        status_summary = []
        gaps = []
        
        for nutrient_name, target in targets.items():
            # Get actual value
            actual = nutrient_totals.get(nutrient_name)
            
            if actual is None:
                # Nutrient not available
                unit = target.get('unit', '')
                print(f"  {nutrient_name.capitalize():12} N/A        (target data not available)")
                continue
            
            # Compare against target
            status, gap = self._compare_to_target(actual, target)
            
            # Format output
            unit = target.get('unit', '')
            target_str = self._format_target(target)
            
            if status == "OK":
                status_mark = "[OK]     "
            elif status in ["LOW", "HIGH", "EXCEEDED"]:
                status_mark = f"[{status:8}]"
                status_summary.append(status)
                if gap != 0:
                    gaps.append((nutrient_name, status, gap, unit))
            
            print(f"  {nutrient_name.capitalize():12} {actual:6.1f}{unit:2} {status_mark} (target: {target_str})")
        
        print()
        
        # Overall status
        if not status_summary:
            print("Status: All targets met")
        else:
            print(f"Status: {len(status_summary)} target(s) missed")
            print()
            print("Suggestions:")
            for nutrient_name, status, gap, unit in gaps:
                if status == "LOW":
                    print(f"  To meet {nutrient_name} target: add {abs(gap):.1f}{unit}")
                elif status in ["HIGH", "EXCEEDED"]:
                    print(f"  To meet {nutrient_name} target: reduce by {abs(gap):.1f}{unit}")
        
        # Show guidelines and rationale
        guidelines = template.get('guidelines', [])
        if guidelines:
            print()
            print("Guidelines (from template):")
            for guideline in guidelines:
                print(f"  - {guideline}")
        
        rationale = template.get('rationale', [])
        if rationale:
            print()
            print("Rationale:")
            for reason in rationale:
                print(f"  - {reason}")
        
        print()
    
    def _compare_to_target(self, actual: float, target: Dict[str, Any]) -> Tuple[str, float]:
        """
        Compare actual value to target.
        
        Returns:
            (status, gap) where status is "OK"/"LOW"/"HIGH"/"EXCEEDED" and gap is difference
        """
        min_val = target.get('min')
        max_val = target.get('max')
        
        # Range target (min and max)
        if min_val is not None and max_val is not None:
            if actual < min_val:
                return ("LOW", min_val - actual)
            elif actual > max_val:
                return ("HIGH", actual - max_val)
            else:
                return ("OK", 0.0)
        
        # Upper bound only (max, no min)
        elif max_val is not None:
            if actual > max_val:
                return ("EXCEEDED", actual - max_val)
            else:
                return ("OK", 0.0)
        
        # Lower bound only (min, no max)
        elif min_val is not None:
            if actual < min_val:
                return ("LOW", min_val - actual)
            else:
                return ("OK", 0.0)
        
        # No bounds defined
        return ("OK", 0.0)
    
    def _format_target(self, target: Dict[str, Any]) -> str:
        """Format target range for display."""
        min_val = target.get('min')
        max_val = target.get('max')
        unit = target.get('unit', '')
        
        if min_val is not None and max_val is not None:
            return f"{min_val}-{max_val}{unit}"
        elif max_val is not None:
            return f"<={max_val}{unit}"
        elif min_val is not None:
            return f">={min_val}{unit}"
        else:
            return "no target"