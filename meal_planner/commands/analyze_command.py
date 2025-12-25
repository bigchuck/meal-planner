# meal_planner/commands/analyze_command.py
"""
Analyze command for template-based meal nutrition analysis.

Compares meals against nutritional targets defined in templates.
Supports workspace meals, pending meals, and log dates.
"""
import shlex
import re
from datetime import date as date_type
from typing import Optional, Dict, Any, List, Tuple
from .base import Command, register_command
from meal_planner.parsers import parse_selection_to_items, CodeParser
from meal_planner.utils.time_utils import categorize_time, normalize_meal_name
from meal_planner.analyzers.meal_analyzer import MealAnalyzer
from meal_planner.models.analysis_result import AnalysisResult, DailyContext


@register_command
class AnalyzeCommand(Command):
    """Analyze meals against nutritional templates."""
    
    name = "analyze"
    help_text = "Analyze meals against template (analyze [date|id] --template <key>)"
    
    def execute(self, args: str) -> None:
        """
        Analyze meals against a nutritional template.
        
        Supports three modes:
        1. Workspace meal: analyze <id> --template <template>
        2. Pending meal: analyze --template <template>
        3. Log date: analyze <date> --template <template>
        
        Args:
            args: Command arguments
        
        Examples:
            analyze 123a --template breakfast.protein_low_carb
            analyze --template breakfast.protein_low_carb
            analyze 2024-12-20 --template lunch.balanced
        """
        if not self._check_thresholds("analyze"):
            return
        
        # Parse arguments
        args_list = shlex.split(args) if args else []
        
        if not args_list:
            print("Usage: analyze [date|workspace_id] --template <template_key>")
            print("\nExamples:")
            print("  analyze 123a --template breakfast.protein_low_carb")
            print("  analyze --template breakfast.protein_low_carb")
            print("  analyze 2024-12-20 --template lunch.balanced")
            return
        
        # Extract target and template
        target = None
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
                # First non-flag arg is the target
                if target is None:
                    target = arg
                    i += 1
                else:
                    print(f"Error: Unexpected argument '{arg}'")
                    return
        
        if not template_key:
            print("Error: --template is required")
            print("Example: analyze --template breakfast.protein_low_carb")
            return
        
        # Auto-prepend "meal_templates." if not present
        if not template_key.startswith("meal_templates."):
            template_key = f"meal_templates.{template_key}"
        
        # Determine analysis mode based on target
        if target is None:
            # Mode: Pending (today)
            self._analyze_pending(template_key)
        elif self._is_date(target):
            # Mode: Log date
            self._analyze_log_date(target, template_key)
        elif self._is_workspace_id(target):
            # Mode: Workspace meal
            self._analyze_workspace(target, template_key)
        else:
            print(f"Error: Could not determine target type: {target}")
            print("Expected: workspace ID (e.g., 123a, N1), date (YYYY-MM-DD), or nothing for pending")
            return
    
    def _is_date(self, arg: str) -> bool:
        """Check if argument is a date (YYYY-MM-DD)."""
        return bool(re.match(r'^\d{4}-\d{2}-\d{2}$', arg))
    
    def _is_workspace_id(self, arg: str) -> bool:
        """Check if argument looks like a workspace ID."""
        # Numeric (1, 2, 123) or numeric with letter (123a, 2b)
        # or N-prefix (N1, N2, N1a)
        return bool(re.match(r'^(\d+[a-z]?|N\d+[a-z]?)$', arg, re.IGNORECASE))
    
    def _analyze_workspace(self, workspace_id: str, template_path: str) -> None:
        """Analyze workspace meal against template."""
        # Find candidate in workspace
        candidate = self._find_workspace_candidate(workspace_id)
        if not candidate:
            print(f"Workspace meal '{workspace_id}' not found.")
            print("Use 'plan show' to see available meals.")
            return
        
        # Check template locking
        analyzed_as = candidate.get("analyzed_as")
        meal_type = self._extract_meal_type_from_template(template_path)
        
        if analyzed_as:
            # Meal already analyzed - check if template matches
            if analyzed_as != meal_type:
                print(f"Error: Meal {workspace_id} already analyzed as '{analyzed_as}'")
                print(f"Cannot analyze with '{meal_type}' template")
                print(f"Use 'plan copy {workspace_id}' to create unlocked variant")
                return
        else:
            # First analysis - lock it
            candidate["analyzed_as"] = meal_type
            self.ctx.save_workspace()
        
        # Get meal data
        items = candidate.get("items", [])
        meal_name = candidate.get("meal_name", "meal")
        meal_id = candidate.get("id")
        meal_description = candidate.get("description")
        
        if not items:
            print(f"Workspace meal {workspace_id} has no items.")
            return
        
        # Create analyzer
        analyzer = MealAnalyzer(self.ctx.master, 
                                self.ctx.nutrients, 
                                self.ctx.thresholds, 
                                self.ctx.user_prefs)
        
        # Run analysis (no daily context for workspace meals)
        try:
            result = analyzer.calculate_analysis(
                items=items,
                template_path=template_path,
                meal_name=meal_name,
                meal_id=meal_id,
                meal_description=meal_description,
                daily_context=None
            )
        except ValueError as e:
            print(f"Error: {e}")
            return
        
        # Display result
        self._display_analysis(result)
    
    def _analyze_pending(self, template_path: str) -> None:
        """Analyze pending meal against template."""
        # Get meal type from template
        meal_type = self._extract_meal_type_from_template(template_path)
        if not meal_type:
            print(f"Error: Could not extract meal type from template: {template_path}")
            return
        
        # Get items from pending for this meal
        items = self._get_pending_meal_items(meal_type)
        
        if not items:
            print(f"\nNo {meal_type} items found in pending.")
            print("Use 'add' to add items with time markers.")
            return
        
        # Calculate daily context
        daily_context = self._calculate_daily_context(meal_type)
        
        # Create analyzer
        analyzer = MealAnalyzer(self.ctx.master, self.ctx.nutrients, self.ctx.thresholds)
        
        # Run analysis
        try:
            result = analyzer.calculate_analysis(
                items=items,
                template_path=template_path,
                meal_name=meal_type,
                meal_id=None,
                meal_description=None,
                daily_context=daily_context
            )
        except ValueError as e:
            print(f"Error: {e}")
            return
        
        # Display result
        self._display_analysis(result)
    
    def _analyze_log_date(self, query_date: str, template_path: str) -> None:
        """Analyze log date meal against template."""
        # Get meal type from template
        meal_type = self._extract_meal_type_from_template(template_path)
        if not meal_type:
            print(f"Error: Could not extract meal type from template: {template_path}")
            return
        
        # Get items from log for this meal
        items = self._get_log_meal_items(query_date, meal_type)
        
        if not items:
            print(f"\nNo {meal_type} items found for {query_date}.")
            return
        
        # Create analyzer
        analyzer = MealAnalyzer(self.ctx.master, self.ctx.nutrients, self.ctx.thresholds)
        
        # Run analysis (no daily context for historical dates)
        try:
            result = analyzer.calculate_analysis(
                items=items,
                template_path=template_path,
                meal_name=meal_type,
                meal_id=None,
                meal_description=None,
                daily_context=None
            )
        except ValueError as e:
            print(f"Error: {e}")
            return
        
        # Display result
        self._display_analysis(result)
    
    def _find_workspace_candidate(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        """Find candidate in workspace by ID (case-insensitive)."""
        ws = self.ctx.planning_workspace
        workspace_id_upper = workspace_id.upper()
        
        for candidate in ws.get("candidates", []):
            if candidate.get("id", "").upper() == workspace_id_upper:
                return candidate
        
        return None
    
    def _extract_meal_type_from_template(self, template_path: str) -> Optional[str]:
        """
        Extract meal type from template path.
        
        Expected: meal_templates.<meal_type>.<template_name>
        Returns: <meal_type>
        """
        parts = template_path.split(".")
        
        if len(parts) >= 3 and parts[0] == "meal_templates":
            return parts[1]
        
        return None
    
    def _get_pending_meal_items(self, meal_type: str) -> List[Dict[str, Any]]:
        """Get items for specific meal from pending."""
        from meal_planner.reports.report_builder import ReportBuilder
        
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            pending = None
        
        if not pending or not pending.get("items"):
            return []
        
        items = pending["items"]
        
        # Extract items for target meal using time markers
        return self._extract_meal_items(items, meal_type)
    
    def _get_log_meal_items(self, query_date: str, meal_type: str) -> List[Dict[str, Any]]:
        """Get items for specific meal from log date."""
        # Get log entries
        entries = self.ctx.log.get_entries_for_date(query_date)
        
        if entries.empty:
            return []
        
        # Parse codes
        codes_col = self.ctx.log.cols.codes
        all_codes = ", ".join([
            str(v) for v in entries[codes_col].fillna("")
            if str(v).strip()
        ])
        
        if not all_codes.strip():
            return []
        
        items = CodeParser.parse(all_codes)
        
        # Extract items for target meal
        return self._extract_meal_items(items, meal_type)
    
    def _extract_meal_items(self, items: List[Dict[str, Any]], meal_type: str) -> List[Dict[str, Any]]:
        """Extract items belonging to a specific meal from item list."""
        meal_items = []
        current_meal = []
        current_time = None
        current_meal_override = None
        in_target_meal = False
        
        for item in items:
            # Time marker
            if 'time' in item and 'code' not in item:
                # Save previous meal if it was our target
                if in_target_meal and current_meal:
                    meal_items.extend(current_meal)
                
                # Start new meal
                current_meal = []
                current_time = item.get('time')
                current_meal_override = item.get('meal_override')
                
                # Check if this is our target meal
                detected_meal = categorize_time(current_time, current_meal_override)
                in_target_meal = (detected_meal and detected_meal.upper() == meal_type.upper())
                continue
            
            # Regular item
            if 'code' in item and in_target_meal:
                current_meal.append(item)
        
        # Add last meal if it was our target
        if in_target_meal and current_meal:
            meal_items.extend(current_meal)
        
        return meal_items
    
    def _calculate_daily_context(self, current_meal_type: str) -> Optional[DailyContext]:
        """
        Calculate daily context from earlier pending meals.
        
        For now returns None - will be implemented in phase 3.
        """
        # TODO: Implement daily context calculation
        return None
    
    def _display_analysis(self, result: AnalysisResult) -> None:
        """Display analysis result in terminal."""
        
        # Header
        print(f"\n{'=' * 70}")
        print(f"Analysis: {result.meal_name.title()}")
        if result.meal_id:
            print(f"Workspace: {result.meal_id}")
        if result.meal_description:
            print(f"Description: {result.meal_description}")
        print(f"Template: {result.template_name}")
        print(f"{'=' * 70}\n")
        
        # Daily context (if present)
        if result.daily_context and (result.daily_context.has_deficits() or 
                                     result.daily_context.has_excesses()):
            print("Daily Context (from earlier meals):")
            
            if result.daily_context.protein_deficit > 0:
                print(f"  Protein deficit: {result.daily_context.protein_deficit:.1f}g")
            if result.daily_context.fiber_deficit > 0:
                print(f"  Fiber deficit: {result.daily_context.fiber_deficit:.1f}g")
            if result.daily_context.sugar_excess > 0:
                print(f"  Sugar excess: {result.daily_context.sugar_excess:.1f}g")
            
            if result.daily_context.sugar_budget_remaining > 0:
                print(f"  Sugar budget remaining: {result.daily_context.sugar_budget_remaining:.1f}g")
            
            print()
        
        # Template targets
        print("Template Targets:")
        targets = result.template.get("targets", {})
        for nutrient, target_def in targets.items():
            # Special case for GL (glycemic load) - display as all caps
            display_name = "GL" if nutrient.lower() == "gl" else nutrient.capitalize()
            
            unit = target_def.get("unit", "")
            if "min" in target_def and "max" in target_def:
                print(f"  {display_name:12} {target_def['min']:.1f}-{target_def['max']:.1f}{unit}")
            elif "min" in target_def:
                print(f"  {display_name:12} ≥ {target_def['min']:.1f}{unit}")
            elif "max" in target_def:
                print(f"  {display_name:12} ≤ {target_def['max']:.1f}{unit}")        
        print()
        
        # Current totals
        print("Current Meal:")
        totals = result.totals
        print(f"  Calories:    {totals.calories:.1f}")
        print(f"  Protein:     {totals.protein_g:.1f}g")
        print(f"  Carbs:       {totals.carbs_g:.1f}g")
        print(f"  Fat:         {totals.fat_g:.1f}g")
        print(f"  Fiber:       {totals.fiber_g:.1f}g")
        print(f"  GL:          {totals.glycemic_load:.1f}")
        print()
        
        # Gaps (deficits)
        if result.gaps:
            print("Gaps (Below Target):")
            for gap in result.gaps:
                priority_mark = "***" if gap.priority == 1 else "**" if gap.priority == 2 else "*"
                print(f"  {priority_mark} {gap}")
            print()
        
        # Excesses (surpluses)
        if result.excesses:
            print("Excesses (Above Threshold):")
            for excess in result.excesses:
                priority_mark = "***" if excess.priority == 1 else "**" if excess.priority == 2 else "*"
                print(f"  {priority_mark} {excess}")
            print()
        
        # Overall status
        if not result.has_issues():
            print("✓ All targets met")
        else:
            gap_count = result.get_gap_count()
            excess_count = result.get_excess_count()
            
            issues = []
            if gap_count > 0:
                issues.append(f"{gap_count} gap{'s' if gap_count > 1 else ''}")
            if excess_count > 0:
                issues.append(f"{excess_count} excess{'es' if excess_count > 1 else ''}")
            
            print(f"Status: Found {' and '.join(issues)}")
            print(f"Use 'recommend {result.meal_id or result.meal_name}' for suggestions")
        
        print()