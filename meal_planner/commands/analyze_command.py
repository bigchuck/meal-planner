# meal_planner/commands/analyze_command.py
"""
Analyze command for template-based meal nutrition analysis.

Compares meals against nutritional targets defined in templates.
Supports workspace meals, pending meals, and log dates.
"""
import shlex
import re
from datetime import date as date_type
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from .base import Command, CommandHistoryMixin, register_command
from meal_planner.parsers import parse_selection_to_items, CodeParser
from meal_planner.utils.time_utils import categorize_time, normalize_meal_name
from meal_planner.analyzers.meal_analyzer import MealAnalyzer
from meal_planner.models.analysis_result import AnalysisResult, DailyContext


@register_command
class AnalyzeCommand(Command, CommandHistoryMixin):
    """Analyze meals against nutritional templates."""
    
    name = "analyze"
    help_text = "Analyze meals against template (analyze [date|id] --template <key> --meal <meal> [--stage])"
    
    def execute(self, args: str) -> None:
        """
        Analyze meals against a nutritional template.
        
        Supports three modes: 
            1. Workspace meal: analyze <id> --template <template> --meal <meal> [--stage]
            2. Pending meal: analyze --template <template> --meal <meal> [--stage]
            3. Log date: analyze <date> --template <template> --meal <meal> [--stage]
        Args:
            args: Command arguments
        
        History support:
        - analyze --history 5 --meal breakfast
        - analyze --use 2 --meal lunch [other flags...]
 
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
            print("Usage: analyze [date|workspace_id] --template <template_key> --meal <meal>")
            print("   or: analyze --history <n> --meal <meal>")
            print("   or: analyze --use <n> --meal <meal> [other options...]")
            print("\nExamples:")
            print("  analyze 123a --template breakfast.protein_low_carb --meal breakfast")
            print("  analyze --template breakfast.protein_low_carb --meal breakfast")
            print("  analyze --history 5 --meal breakfast")
            print("  analyze --use 1 --meal breakfast")
            return
        
        # Extract target and template
        target = None
        template_key = None
        meal_name = None
        history_limit = None
        use_index = None
        stage = False
        
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
            elif arg == "--meal":
                if i + 1 < len(args_list):
                    meal_name = args_list[i + 1]
                    i += 2
                else:
                    print("Error: --meal requires a meal name")
                    return
        
            elif arg == "--history":
                if i + 1 < len(args_list):
                    try:
                        history_limit = int(args_list[i + 1])
                        i += 2
                    except ValueError:
                        print("Error: --history requires a number")
                        return
                else:
                    print("Error: --history requires a number")
                    return
            
            elif arg == "--stage":
                stage = True
                i += 1

            elif arg == "--use":
                if i + 1 < len(args_list):
                    try:
                        use_index = int(args_list[i + 1])
                        i += 2
                    except ValueError:
                        print("Error: --use requires a number")
                        return
                else:
                    print("Error: --use requires a number")
                    return

            else:
                # First non-flag arg is the target
                if target is None:
                    target = arg
                    i += 1
                else:
                    print(f"Error: Unexpected argument '{arg}'")
                    return
   
        # Handle --history mode
        if history_limit is not None:
            if use_index is not None:
                print("Error: --history and --use are mutually exclusive")
                return
            if template_key is not None or target is not None:
                print("Error: --history cannot be combined with analysis parameters")
                return
            if meal_name is None:
                print("Error: --history requires --meal flag")
                print("Example: analyze --history 5 --meal breakfast")
                return
            
            self._display_command_history("analyze", meal_name, history_limit)
            return
        
        # Handle --use mode
        if use_index is not None:
            if meal_name is None:
                print("Error: --use requires --meal flag")
                print("Example: analyze --use 1 --meal breakfast")
                return
            # Load params from history
            params = self._get_params_from_history("analyze", meal_name, use_index)
            if params is None:
                print(f"Error: No history entry #{use_index} for meal '{meal_name}'")
                print(f"Use: analyze --history 10 --meal {meal_name}")
                return        
            print(f"Using history #{use_index}: {params}")

            # Prepend target if provided in current command
            if target:
                params = f"{target} {params}"
            if stage:
                params = f"{params} --stage"
            return self.execute(params)
   
        if not template_key:
            print("Error: --template is required")
            print("Example: analyze --template breakfast.protein_low_carb")
            return
        if not meal_name:
            print("Error: --meal is required")
            print("Example: analyze --template breakfast.protein_low_carb --meal breakfast")
            return        

        # Auto-prepend "meal_templates." if not present
        if not template_key.startswith("meal_templates."):
            template_key = f"meal_templates.{template_key}"
        
        # Build parameter string for history recording
        params_for_history = f"--template {template_key} --meal {meal_name}"

        # Determine analysis mode based on target
        if target is None:
            # Mode: Pending (today)
            success, lines, date_label = self._analyze_pending(template_key, meal_name, stage)
        elif self._is_date(target):
            # Mode: Log date
            success, lines, date_label = self._analyze_log_date(target, template_key, meal_name, stage)
        elif self._is_workspace_id(target):
            # Mode: Workspace meal
            success, lines, date_label = self._analyze_workspace(target, template_key, meal_name, stage)
        else:
            print(f"Error: Could not determine target type: {target}")
            print("Expected: workspace ID (e.g., 123a, N1), date (YYYY-MM-DD), or nothing for pending")
            return
            # Handle staging if requested
        if success and stage and lines:
            self._stage_analysis(lines, date_label, meal_name, target)

        # Record in history if successful
        if success:
            self._record_command_history("analyze", params_for_history)
    
    def _is_date(self, arg: str) -> bool:
        """Check if argument is a date (YYYY-MM-DD)."""
        return bool(re.match(r'^\d{4}-\d{2}-\d{2}$', arg))
    
    def _is_workspace_id(self, arg: str) -> bool:
        """Check if argument exists as a workspace ID."""
        # Actually look it up in the workspace
        ws = self.ctx.planning_workspace
        for candidate in ws['candidates']:
            if candidate['id'].upper() == arg.upper():
                return True
    
    def _analyze_workspace(self, workspace_id: str, template_path: str, meal_name: str, 
                           stage: bool = False) -> Tuple[bool, Optional[List[str]], Optional[str]]: 
        """Analyze workspace meal against template."""
        # Find candidate in workspace
        candidate = self._find_workspace_candidate(workspace_id)
        if not candidate:
            print(f"Workspace meal '{workspace_id}' not found.")
            print("Use 'plan show' to see available meals.")
            return False, None, None
        
        # Check template locking
        analyzed_as = candidate.get("analyzed_as")
        meal_type = self._extract_meal_type_from_template(template_path)
        
        if analyzed_as:
            # Meal already analyzed - check if template matches
            if analyzed_as != meal_type:
                print(f"Error: Meal {workspace_id} already analyzed as '{analyzed_as}'")
                print(f"Cannot analyze with '{meal_type}' template")
                print(f"Use 'plan copy {workspace_id}' to create unlocked variant")
                return False, None, None
        else:
            # First analysis - lock it
            candidate["analyzed_as"] = meal_type
            self.ctx.save_workspace()
        
        # Get meal data
        items = candidate.get("meal", {}).get("items", [])
        meal_name = candidate.get("meal_name", "meal")
        meal_id = candidate.get("id")
        meal_description = candidate.get("description")
        
        if not items:
            print(f"Workspace meal {workspace_id} has no items.")
            return False, None, None
        
        # Create analyzer
        analyzer = MealAnalyzer(self.ctx.master, 
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
            return False, None, None
        
        lines = self._display_analysis(result)

        if stage:
            # Return lines for staging (caller will handle staging and display)
            return True, lines, "workspace"
        else:
            # Normal mode: print immediately
            self._print_lines(lines)
            return True, None, None
    
    def _analyze_pending(self, template_path: str, meal_name: str, 
                         stage: bool = False) -> Tuple[bool, Optional[List[str]], Optional[str]]:
        """Analyze pending meal against template."""
        # Get items from pending for this meal
        items = self._get_pending_meal_items(meal_name)
        
        if not items:
            print(f"\nNo {meal_name} items found in pending.")
            print("Use 'add' to add items with time markers.")
            return False, None, None
        
        # Get items from pending for this meal
        items = self._get_pending_meal_items(meal_name)
        
        if not items:
            print(f"\nNo {meal_name} items found in pending.")
            print("Use 'add' to add items with time markers.")
            return False, None, None
        
        # Calculate daily context
        daily_context = self._calculate_daily_context(meal_name)
        
        # Create analyzer
        analyzer = MealAnalyzer(self.ctx.master, self.ctx.thresholds)
        
        # Run analysis
        try:
            result = analyzer.calculate_analysis(
                items=items,
                template_path=template_path,
                meal_name=meal_name,
                meal_id=None,
                meal_description=None,
                daily_context=daily_context
            )
        except ValueError as e:
            print(f"Error: {e}")
            return False, None, None
        
        # Display result
        lines = self._display_analysis(result)
        if stage:
            # Return lines for staging (caller will handle staging and display)
            return True, lines, "pending"
        else:
            # Normal mode: print immediately
            self._print_lines(lines)
            return True, None, None
    
    def _analyze_log_date(self, query_date: str, template_path: str, meal_name: str, 
                          stage: bool = False) -> Tuple[bool, Optional[List[str]], Optional[str]]:
        """Analyze log date meal against template."""
        # Get items from log for this meal
        items = self._get_log_meal_items(query_date, meal_name)
        
        if not items:
            print(f"\nNo {meal_name} items found for {query_date}.")
            return False, None, None
        
        # Create analyzer
        analyzer = MealAnalyzer(self.ctx.master, self.ctx.thresholds)
        
        # Run analysis (no daily context for historical dates)
        try:
            result = analyzer.calculate_analysis(
                items=items,
                template_path=template_path,
                meal_name=meal_name,
                meal_id=None,
                meal_description=None,
                daily_context=None
            )
        except ValueError as e:
            print(f"Error: {e}")
            return False, None, None
        
        # Display result
        lines = self._display_analysis(result)
        if stage:
            # Return lines for staging (caller will handle staging and display)
            return True, lines, query_date
        else:
            # Normal mode: print immediately
            self._print_lines(lines)
            return True, None, None
    
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
    
    def _display_analysis(self, result: AnalysisResult) -> List[str]:
        """Display analysis result in terminal."""
        
        lines = []
        # Header
        lines.append(f"\n{'=' * 70}")
        lines.append(f"Analysis: {result.meal_name.title()}")
        if result.meal_id:
            lines.append(f"Workspace: {result.meal_id}")
        if result.meal_description:
            lines.append(f"Description: {result.meal_description}")
        lines.append(f"Template: {result.template_name}")
        lines.append(f"{'=' * 70}\n")
        
        # Daily context (if present)
        if result.daily_context and (result.daily_context.has_deficits() or 
                                     result.daily_context.has_excesses()):
            lines.append("Daily Context (from earlier meals):")
            
            if result.daily_context.protein_deficit > 0:
                lines.append(f"  Protein deficit: {result.daily_context.protein_deficit:.1f}g")
            if result.daily_context.fiber_deficit > 0:
                lines.append(f"  Fiber deficit: {result.daily_context.fiber_deficit:.1f}g")
            if result.daily_context.sugar_excess > 0:
                lines.append(f"  Sugar excess: {result.daily_context.sugar_excess:.1f}g")
            
            if result.daily_context.sugar_budget_remaining > 0:
                lines.append(f"  Sugar budget remaining: {result.daily_context.sugar_budget_remaining:.1f}g")
            
            lines.append("")
        
        # Template targets
        lines.append("Template Targets:")
        targets = result.template.get("targets", {})
        for nutrient, target_def in targets.items():
            # Special case for GL (glycemic load) - display as all caps
            display_name = "GL" if nutrient.lower() == "gl" else nutrient.capitalize()
            
            unit = target_def.get("unit", "")
            if "min" in target_def and "max" in target_def:
                lines.append(f"  {display_name:12} {target_def['min']:.1f}-{target_def['max']:.1f}{unit}")
            elif "min" in target_def:
                lines.append(f"  {display_name:12} ≥ {target_def['min']:.1f}{unit}")
            elif "max" in target_def:
                lines.append(f"  {display_name:12} ≤ {target_def['max']:.1f}{unit}")        
        lines.append("")
        
        # Current totals
        lines.append("Current Meal:")
        totals = result.totals
        lines.append(f"  Calories:    {totals.calories:.1f}")
        lines.append(f"  Protein:     {totals.protein_g:.1f}g")
        lines.append(f"  Carbs:       {totals.carbs_g:.1f}g")
        lines.append(f"  Fat:         {totals.fat_g:.1f}g")
        lines.append(f"  Fiber:       {totals.fiber_g:.1f}g")
        lines.append(f"  GL:          {totals.glycemic_load:.1f}")
        lines.append("")

        # Gaps (deficits)
        if result.gaps:
            lines.append("Gaps (Below Target):")
            for gap in result.gaps:
                priority_mark = "***" if gap.priority == 1 else "**" if gap.priority == 2 else "*"
                lines.append(f"  {priority_mark} {gap}")
            lines.append("")
        
        # Excesses (surpluses)
        if result.excesses:
            lines.append("Excesses (Above Threshold):")
            for excess in result.excesses:
                priority_mark = "***" if excess.priority == 1 else "**" if excess.priority == 2 else "*"
                lines.append(f"  {priority_mark} {excess}")
            lines.append("")
        
        # Overall status
        if not result.has_issues():
            lines.append("✓ All targets met")
        else:
            gap_count = result.get_gap_count()
            excess_count = result.get_excess_count()
            
            issues = []
            if gap_count > 0:
                issues.append(f"{gap_count} gap{'s' if gap_count > 1 else ''}")
            if excess_count > 0:
                issues.append(f"{excess_count} excess{'es' if excess_count > 1 else ''}")
            
            lines.append(f"Status: Found {' and '.join(issues)}")
            lines.append(f"Use 'recommend {result.meal_id or result.meal_name}' for suggestions")
        
        lines.append("")

        return lines
    
    def _print_lines(self, lines: List[str]) -> None:
        """
        Print list of lines to console.
        
        Args:
            lines: List of strings to print
        """
        for line in lines:
            print(line)

    def _stage_analysis(self, lines: List[str], date_label: str, meal_name: str, 
                        target: Optional[str]) -> None:
        """
        Stage analysis output to buffer and display to screen.
        
        Args:
            lines: Formatted output lines
            date_label: Date label ("pending", "workspace", or "YYYY-MM-DD")
            meal_name: Meal name
            target: Original target (workspace ID or date, or None for pending)
        """
        if not self.ctx.staging_buffer:
            print("\nWarning: Staging buffer not configured, cannot stage.\n")
            # Still print to screen
            self._print_lines(lines)
            return
        
        from meal_planner.data.staging_buffer_manager import StagingBufferManager
        from datetime import datetime
        
        # Print to screen
        self._print_lines(lines)
        
        # Generate ID and label based on source
        if date_label == "workspace":
            # Workspace analysis
            base_id = StagingBufferManager.generate_workspace_id(target, meal_name)
            item_id = StagingBufferManager.generate_analysis_id(base_id)
            label = f"Analysis: {meal_name} (workspace {target})"
        elif date_label == "pending":
            # Pending analysis
            today = str(datetime.now().date())
            base_id = StagingBufferManager.generate_pending_id(meal_name, today)
            item_id = StagingBufferManager.generate_analysis_id(base_id)
            label = f"Analysis: " + StagingBufferManager.format_date_label(today, meal_name)
        else:
            # Log date analysis
            base_id = StagingBufferManager.generate_pending_id(meal_name, date_label)
            item_id = StagingBufferManager.generate_analysis_id(base_id)
            label = f"Analysis: " + StagingBufferManager.format_date_label(date_label, meal_name)
        
        # Add to buffer
        is_new = self.ctx.staging_buffer.add(item_id, label, lines)
        
        if is_new:
            print(f"\n✓ Staged: {label}\n")
        else:
            print(f"\n✓ Replaced staged item: {label}\n")