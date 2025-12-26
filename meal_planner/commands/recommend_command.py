# meal_planner/commands/recommend_command.py
"""
Recommend command for meal optimization suggestions.

Analyzes meal gaps/excesses and suggests additions, portions, or swaps.
"""
import shlex
from typing import List, Dict, Any, Optional, Tuple
from datetime import date, timedelta
from .base import Command, CommandHistoryMixin, register_command
from meal_planner.analyzers.meal_analyzer import MealAnalyzer
from meal_planner.models.analysis_result import DailyContext
from meal_planner.parsers import parse_selection_to_items
from meal_planner.utils.time_utils import categorize_time, normalize_meal_name, MEAL_NAMES


@register_command
class RecommendCommand(Command, CommandHistoryMixin):
    """Generate recommendations for meal optimization."""
    
    name = "recommend"
    help_text = "Get optimization suggestions (recommend <id|meal_name>)"
    
    def execute(self, args: str) -> None:
        """
        Generate recommendations for a workspace meal or pending meal.
        
        Standard mode:
            recommend 123a
            recommend lunch --template lunch.balanced --meal lunch
            recommend breakfast --template breakfast.protein_focus --meal breakfast
        
        History support:
            recommend --history 5 --meal breakfast
            recommend --use 2 --meal lunch [other flags...]

        Args:
            args: Workspace ID (e.g., "123a") or meal name + --template flag + --meal flag
        
        Examples:
            recommend 123a
            recommend lunch --template lunch.balanced
            recommend breakfast --template breakfast.protein_focus
        """
        # Check dependencies
        if not self._check_thresholds("Recommend"):
            return
        
        if not self.ctx.user_prefs:
            print("\nRecommend unavailable: user preferences not loaded")
            print("Check meal_plan_user_preferences.json\n")
            return
        
        # Parse args
        if not args.strip():
            self._show_help()
            return
        
        # Parse target and template flag
        parts = shlex.split(args)
        if not parts:
            self._show_help()
            return
        
        target = None
        template_override = None
        meal_name = None
        history_limit = None
        use_index = None

        i = 0
        while i < len(parts):
            arg = parts[i]
            
            if arg == "--template":
                if i + 1 < len(parts):
                    template_override = parts[i + 1]
                    i += 2
                else:
                    print("\nError: --template requires a value")
                    print("Example: recommend lunch --template lunch.balanced --meal lunch\n")
                    return
            
            elif arg == "--meal":
                if i + 1 < len(parts):
                    meal_name = parts[i + 1]
                    i += 2
                else:
                    print("Error: --meal requires a meal name")
                    return
            
            elif arg == "--history":
                if i + 1 < len(parts):
                    try:
                        history_limit = int(parts[i + 1])
                        i += 2
                    except ValueError:
                        print("Error: --history requires a number")
                        return
                else:
                    print("Error: --history requires a number")
                    return
            
            elif arg == "--use":
                if i + 1 < len(parts):
                    try:
                        use_index = int(parts[i + 1])
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
            if template_override is not None or target is not None:
                print("Error: --history cannot be combined with recommendation parameters")
                return
            if meal_name is None:
                print("Error: --history requires --meal flag")
                print("Example: recommend --history 5 --meal breakfast")
                return
            
            self._display_command_history("recommend", meal_name, history_limit)
            return
        
        # Handle --use mode
        if use_index is not None:
            if meal_name is None:
                print("Error: --use requires --meal flag")
                print("Example: recommend --use 1 --meal breakfast")
                return
            
            # Load params from history
            params = self._get_params_from_history("recommend", meal_name, use_index)
            if params is None:
                print(f"Error: No history entry #{use_index} for meal '{meal_name}'")
                print(f"Use: recommend --history 10 --meal {meal_name}")
                return
            
            # Re-parse the historical params
            print(f"Using history #{use_index}: {params}")
            
            # Re-execute with historical params
            return self.execute(params)

        # Regular recommendation mode - requires meal
        if meal_name is None:
            print("Error: --meal is required")
            print("Example: recommend lunch --template lunch.balanced --meal lunch")
            return
        
        # Determine if workspace ID or meal name
        is_workspace = False
        if target:
            is_workspace = self._is_workspace_id(target)
        
        # Build parameter string for history recording
        params_for_history = ""
        if target:
            params_for_history = f"{target} "
        if template_override:
            params_for_history += f"--template {template_override} "
        params_for_history += f"--meal {meal_name}"
        
        # Execute recommendation
        success = False
        if is_workspace:
            success = self._recommend_workspace(target, template_override, meal_name)
        else:
            success = self._recommend_pending(target if target else meal_name, 
                                            template_override, meal_name)
        
        # Record in history if successful
        if success:
            self._record_command_history("recommend", params_for_history.strip())
    
    # =========================================================================
    # Main recommendation paths
    # =========================================================================
    
    def _recommend_workspace(self, workspace_id: str, template_override: Optional[str],
                             meal_name: str) -> bool:
        """Generate recommendations for a workspace meal."""
        # Find workspace meal
        ws = self.ctx.planning_workspace
        meal = None
        
        for candidate in ws['candidates']:
            if candidate['id'].upper() == workspace_id.upper():
                meal = candidate
                break
        
        if not meal:
            print(f"\nWorkspace meal '{workspace_id}' not found.")
            print("Use 'plan show' to see available meals.\n")
            return False
        
        # Get items and meal info
        items = meal.get('items', [])
        if not items:
            print(f"\nWorkspace meal '{workspace_id}' has no items.\n")
            return False
        
        meal_name = meal.get('meal_name', 'meal')
        meal_description = meal.get('description', '')
        
        # Determine template
        if template_override:
            # User specified template
            template_path = template_override
        elif meal.get('analyzed_as'):
            # Use locked template from previous analyze
            template_path = meal.get('analyzed_as')
        else:
            # Require explicit template
            print(f"\nNo template specified for workspace meal '{workspace_id}'.")
            print("Either:")
            print(f"  1. Analyze first: analyze {workspace_id} --template <template>")
            print(f"  2. Specify template: recommend {workspace_id} --template <template>")
            print("\nExample: recommend {workspace_id} --template lunch.balanced\n")
            return False
        
        # Run recommendations
        self._generate_recommendations(
            items=items,
            template_path=template_path,
            meal_name=meal_name,
            meal_id=workspace_id,
            meal_description=meal_description
        )
        return True
    
    def _recommend_pending(self, target: str, template_override: Optional[str],
                           meal_name: str) -> bool:
        """Generate recommendations for a pending meal."""
        # Normalize meal name
        try:
            meal_name_norm = normalize_meal_name(meal_name)
        except Exception:
            print(f"\nInvalid meal name: '{meal_name}'")
            print(f"Valid names: {', '.join(MEAL_NAMES)}\n")
            return False
        
        # Load pending
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            pending = None
        
        if not pending or not pending.get('items'):
            print(f"\nNo pending items found for analysis.\n")
            return False
        
        # Extract items for this meal
        items = self._extract_meal_items_from_pending(
            pending.get('items', []),
            meal_name_norm
        )
        
        if not items:
            print(f"\nNo items found for '{meal_name_norm}' in pending.\n")
            return False
        
        # Determine template
        if template_override:
            template_path = template_override
        else:
            # Require explicit template
            print(f"\nNo template specified for '{meal_name_norm}'.")
            print("Specify template: recommend {meal_name_norm} --template <template>")
            print(f"\nExample: recommend {meal_name_norm} --template {meal_name_norm.lower().replace(' ', '_')}.balanced\n")
            return False
        
        # Run recommendations
        self._generate_recommendations(
            items=items,
            template_path=template_path,
            meal_name=meal_name_norm,
            meal_id=None,
            meal_description=None
        )
        return True
    
    def _generate_recommendations(
        self,
        items: List[Dict[str, Any]],
        template_path: str,
        meal_name: str,
        meal_id: Optional[str],
        meal_description: Optional[str]
    ) -> None:
        """Core recommendation generation logic."""
        
        # Run analysis
        analyzer = MealAnalyzer(
            master=self.ctx.master,
            nutrients=self.ctx.nutrients,
            thresholds=self.ctx.thresholds
        )
        
        try:
            result = analyzer.calculate_analysis(
                items=items,
                template_path=template_path,
                meal_name=meal_name,
                meal_id=meal_id,
                meal_description=meal_description
            )
        except Exception as e:
            print(f"\nAnalysis error: {e}\n")
            return
        
        # Display header
        self._display_header(result)
        
        # Display gaps and recommendations
        if result.gaps:
            self._display_gap_recommendations(result)
        else:
            print("\n✓ All nutrient targets met")
        
        # Display excesses
        if result.excesses:
            self._display_excess_recommendations(result)
        else:
            print("\n✓ No nutrient excesses")
        
        # Display leftover suggestions (lunch and dinner)
        if meal_name.upper() in ['LUNCH', 'DINNER']:
            self._display_leftover_suggestions(result)
        
        # Display snack bridge suggestions
        self._display_snack_suggestions(result)
        
        print()
    
    # =========================================================================
    # Gap recommendations
    # =========================================================================
    
    def _display_gap_recommendations(self, result) -> None:
        """Display recommendations for closing nutrient gaps."""
        print("\n=== NUTRIENT GAPS ===")
        
        for gap in result.gaps:

            if hasattr(gap, 'target_max') and gap.target_max is not None:
                target_str = f"{gap.target_min:.1f}{gap.unit} - {gap.target_max:.1f}{gap.unit}"
            else:
                target_str = f"{gap.target_min:.1f}{gap.unit}"
            
            print(f"\n{gap.nutrient}: {gap.current:.1f} / {target_str}")
            print(f"  Deficit: {gap.deficit:.1f}{gap.unit} (priority {gap.priority})")
            
            # Get recommendations
            recs = self._recommend_for_gap(result, gap)
            
            if not recs:
                print("  No suitable additions found")
                continue
            
            # Show top 5
            print("  Suggestions:")
            for i, rec in enumerate(recs[:5], 1):
                impact = rec['impact']
                code = rec['code']
                portion_mult = rec['portion']
                option = rec['option']
                
                # Format portion as multiplier
                if abs(portion_mult - 1.0) < 0.01:
                    portion_str = "x1.0"
                else:
                    portion_str = f"x{portion_mult:.2f}"

                frozen_tag = " [FROZEN]" if rec.get('is_frozen', False) else ""
                
                # Format line
                print(f"    {i}. {code} ({portion_str}){frozen_tag} - {option[:55]}")
                print(f"       +{impact['nutrient_gain']:.1f}{gap.unit}, "
                      f"+{impact['calories']:.0f} cal, "
                      f"+{impact['fat']:.1f}g fat")
    
    def _recommend_for_gap(self, result, gap) -> List[Dict[str, Any]]:
        """Generate recommendations for a specific gap."""
        recommendations = []
        
        # Get nutrient column name
        nutrient_key = gap.nutrient
        
        # Search master for high-nutrient foods
        master_df = self.ctx.master.df.copy()
        cols = self.ctx.master.cols
        
        # Get availability lists
        staples = self.ctx.user_prefs.get_staple_foods()
        unavailable = self.ctx.user_prefs.get_unavailable_items()
        
        # Try recently used (tiered)
        recent_7 = self.ctx.user_prefs.get_recently_used(days=7)
        recent_30 = self.ctx.user_prefs.get_recently_used(days=30)
        
        # Build candidate pool: staples + recent
        candidate_codes = set(staples)
        candidate_codes.update(recent_7)
        
        # Extend with recent_30 if we need more options
        if len(candidate_codes) < 20:
            candidate_codes.update(recent_30)
        
        # Filter master to candidates
        if candidate_codes:
            master_df = master_df[
                master_df[cols.code].str.upper().isin(
                    [c.upper() for c in candidate_codes]
                )
            ]
        
        # Remove unavailable
        if unavailable:
            master_df = master_df[
                ~master_df[cols.code].str.upper().isin(
                    [c.upper() for c in unavailable]
                )
            ]
        
        # Remove items excluded from recommendations (restaurant items, etc.)
        # Filter out codes matching patterns or specific items
        if not master_df.empty:
            codes_to_keep = []
            for idx, row in master_df.iterrows():
                code = row[cols.code]
                if not self.ctx.user_prefs.is_excluded_from_recommendations(code):
                    codes_to_keep.append(idx)
            master_df = master_df.loc[codes_to_keep]
        
        if master_df.empty:
            return []
        
        # Get nutrient column mapping
        nutrient_col = self._map_nutrient_to_column(nutrient_key)
        if nutrient_col not in master_df.columns:
            return []
        
        # Calculate efficiency scores
        for idx, row in master_df.iterrows():
            code = row[cols.code]
            
            # Get nutrient value (per the master.csv portion, whatever that is)
            nutrient_val = row.get(nutrient_col, 0)
            if pd.isna(nutrient_val) or nutrient_val <= 0:
                continue
            
            # Get calories
            cal = row.get(cols.cal, 0)
            if pd.isna(cal) or cal <= 0:
                continue
            
            # Calculate how many portions needed to close gap
            deficit = gap.deficit
            nutrient_per_portion = float(nutrient_val)
            
            # Calculate portions needed
            if nutrient_per_portion > 0:
                portions_needed = deficit / nutrient_per_portion
            else:
                continue
            
            # Check frozen portions - use multiplier
            frozen_mult = self.ctx.user_prefs.get_frozen_multiplier(code)
            is_frozen = False
            if frozen_mult is not None:
                # Use frozen multiplier (e.g., 2 means 2x the master.csv portion)
                portions_needed = frozen_mult
                is_frozen = True
            
            # Don't suggest tiny or huge multipliers
            if portions_needed < 0.1 or portions_needed > 5:
                continue
            
            # Calculate actual impact at this multiplier
            actual_nutrient = nutrient_per_portion * portions_needed
            actual_cal = float(cal) * portions_needed
            actual_fat = float(row.get(cols.fat_g, 0)) * portions_needed
            
            # Efficiency score (nutrient per calorie)
            efficiency = nutrient_per_portion / float(cal) if cal > 0 else 0
            
            # Meal appropriateness bonus
            meal_bonus = self._get_meal_appropriateness(code, result.meal_name)
            
            # Final score
            score = efficiency * meal_bonus
            
            recommendations.append({
                'code': code,
                'option': row[cols.option],
                'section': row[cols.section],
                'portion': portions_needed,  # Store as multiplier, not grams
                'efficiency': efficiency,
                'score': score,
                'is_frozen': is_frozen,
                'impact': {
                    'nutrient_gain': actual_nutrient,
                    'calories': actual_cal,
                    'fat': actual_fat
                }
            })
        
        # Sort by score (descending)
        recommendations.sort(key=lambda x: x['score'], reverse=True)
        
        return recommendations
    
    # =========================================================================
    # Excess recommendations
    # =========================================================================
    
    def _display_excess_recommendations(self, result) -> None:
        """Display recommendations for managing excesses."""
        print("\n=== NUTRIENT EXCESSES ===")
        
        for excess in result.excesses:
            print(f"\n{excess.nutrient}: {excess.current:.1f} / {excess.threshold:.1f}{excess.unit}")
            print(f"  Overage: {excess.overage:.1f}{excess.unit} (priority {excess.priority})")
            
            # Identify contributors
            contributors = self._identify_contributors(result, excess)
            
            if not contributors:
                print("  Unable to identify contributors")
                continue
            
            print("  Top contributors:")
            for i, contrib in enumerate(contributors[:3], 1):
                code = contrib['code']
                option = contrib['option'][:40]
                amount = contrib['amount']
                pct = contrib['percent']
                
                print(f"    {i}. {code} - {option}")
                print(f"       Contributes {amount:.1f}{excess.unit} ({pct:.0f}%)")
            
            # Suggest portion reductions
            print("  Suggestions:")
            print("    • Reduce portions of top contributors")
            print("    • Consider removing lowest-priority items")
    
    def _identify_contributors(self, result, excess) -> List[Dict[str, Any]]:
        """Identify which items contribute most to an excess."""
        contributors = []
        
        nutrient_key = excess.nutrient
        nutrient_col = self._map_nutrient_to_column(nutrient_key)
        
        cols = self.ctx.master.cols
        
        for item in result.meal_items:
            if 'code' not in item:
                continue
            
            code = item['code']
            mult = item.get('mult', 1.0)
            
            # Look up in master
            row = self.ctx.master.lookup_code(code)
            if row is None:
                continue
            
            # Get nutrient value
            nutrient_val = row.get(nutrient_col, 0)
            if pd.isna(nutrient_val):
                nutrient_val = 0
            
            amount = float(nutrient_val) * mult
            
            if amount > 0:
                contributors.append({
                    'code': code,
                    'option': row[cols.option],
                    'amount': amount,
                    'percent': (amount / excess.current) * 100
                })
        
        # Sort by amount (descending)
        contributors.sort(key=lambda x: x['amount'], reverse=True)
        
        return contributors
    
    # =========================================================================
    # Leftover suggestions
    # =========================================================================
    
    def _display_leftover_suggestions(self, result) -> None:
        """Display potential leftover items from recent meals."""
        print("\n=== LEFTOVER OPPORTUNITIES ===")
        
        meal_name = result.meal_name.upper()
        
        # For lunch: show recent dinners
        # For dinner: show recent lunches AND dinners
        if meal_name == 'LUNCH':
            recent_meals = self._get_recent_meals_by_type(days=7, meal_types=['DINNER'])
            source_label = "dinners"
        elif meal_name == 'DINNER':
            recent_meals = self._get_recent_meals_by_type(days=7, meal_types=['LUNCH', 'DINNER'])
            source_label = "lunches and dinners"
        else:
            return  # Only show for lunch and dinner
        
        if not recent_meals:
            print(f"  No recent {source_label} found")
            return
        
        # Collect all unique codes with their first occurrence details
        seen_codes = {}  # code -> (date, meal_type, description)
        
        for meal in recent_meals[:5]:
            date_str = meal['date']
            meal_type = meal['meal_type']
            codes = meal['codes']
            
            for code in codes:
                if code not in seen_codes:
                    # Look up description
                    row = self.ctx.master.lookup_code(code)
                    if row is not None:
                        cols = self.ctx.master.cols
                        description = row[cols.option]
                    else:
                        description = "(description not found)"
                    
                    seen_codes[code] = (date_str, meal_type, description)
        
        if not seen_codes:
            print(f"  No leftover-friendly items in recent {source_label}")
            return
        
        print(f"  Recent {source_label} (leftover-friendly items, deduplicated):")
        
        # Display sorted by date (most recent first)
        for code, (date_str, meal_type, description) in seen_codes.items():
            print(f"    {code} - {description}")
            print(f"      (from {date_str} {meal_type})")
        
        print("  Note: Shows items matching leftover patterns (excluding shelf-stable items)")
        print("  These are suggestions only - may not actually be available")
    
    def _get_recent_meals_by_type(self, days: int, meal_types: List[str]) -> List[Dict[str, Any]]:
        """
        Get specific meal types from recent log entries.
        
        Args:
            days: Number of days to look back
            meal_types: List of meal types to include (e.g., ['LUNCH', 'DINNER'])
        
        Returns:
            List of dicts with date, meal_type, and leftover-friendly codes
        """
        results = []
        
        # Get log entries from last N days
        log_df = self.ctx.log.df
        if log_df.empty:
            return results
        
        # Calculate date range
        today = date.today()
        start_date = today - timedelta(days=days)
        
        # Get date column
        from meal_planner.utils import get_date_column
        date_col = get_date_column(log_df)
        if date_col is None:
            return results
        
        # Filter to date range
        log_df[date_col] = pd.to_datetime(log_df[date_col], errors='coerce')
        mask = (log_df[date_col] >= str(start_date)) & (log_df[date_col] <= str(today))
        recent_df = log_df[mask]
        
        if recent_df.empty:
            return results
        
        # Extract codes from each entry
        from meal_planner.utils import get_codes_column
        codes_col = get_codes_column(recent_df)
        if codes_col is None:
            return results
        
        for idx, row in recent_df.iterrows():
            date_str = str(row[date_col])[:10]
            codes_str = row[codes_col]
            
            if not codes_str or str(codes_str).strip() == '':
                continue
            
            # Parse items
            try:
                items = parse_selection_to_items(str(codes_str))
            except Exception:
                continue
            
            # Extract meals of requested types
            for meal_type in meal_types:
                codes = self._extract_meal_codes_by_type(items, meal_type)
                
                if codes:
                    results.append({
                        'date': date_str,
                        'meal_type': meal_type.title(),
                        'codes': codes
                    })
        
        return results
    
    def _extract_meal_codes_by_type(self, items: List[Dict[str, Any]], meal_type: str) -> List[str]:
        """
        Extract leftover-friendly codes from a specific meal type.
        
        Args:
            items: All items from a log entry
            meal_type: Meal type to extract (e.g., 'LUNCH', 'DINNER')
        
        Returns:
            List of leftover-friendly codes from that meal
        """
        meal_codes = []
        in_target_meal = False
        
        # Get leftover-friendly patterns from user preferences
        leftover_patterns = self.ctx.user_prefs.get_leftover_friendly()
        leftover_excludes = self.ctx.user_prefs.get_leftover_excludes()
        
        # If no patterns defined, use conservative defaults
        if not leftover_patterns:
            leftover_patterns = ['MT.', 'FI.', 'SO.', 'CH.']
        
        for item in items:
            # Time marker
            if 'time' in item:
                time_str = item.get('time', '')
                meal_override = item.get('meal_override', '')
                
                # Detect meal type
                detected_meal = categorize_time(time_str, meal_override)
                in_target_meal = (detected_meal and detected_meal.upper() == meal_type.upper())
                continue
            
            # Code item
            if 'code' in item and in_target_meal:
                code = item['code'].upper()
                
                # Check if excluded (even if matches pattern)
                if code in leftover_excludes:
                    continue
                
                # Only include leftover-friendly items
                if any(code.startswith(pattern) for pattern in leftover_patterns):
                    meal_codes.append(code)
        
        return meal_codes
    
    # =========================================================================
    # Snack bridge suggestions
    # =========================================================================
    
    def _display_snack_suggestions(self, result) -> None:
        """Display snack recommendations to bridge gaps between meals."""
        if not result.gaps:
            return  # No gaps to bridge
        
        print("\n=== SNACK BRIDGE SUGGESTIONS ===")
        print("  Between-meal snacks to address gaps:")
        
        for gap in result.gaps[:3]:  # Show top 3 gaps
            # Get recommendations
            recs = self._recommend_for_gap(result, gap)
            
            if not recs:
                continue
            
            # Show as snack option
            rec = recs[0]  # Top recommendation
            code = rec['code']
            portion_mult = rec['portion']
            option = rec['option'][:40]
            impact = rec['impact']
            
            # Format portion as multiplier
            if abs(portion_mult - 1.0) < 0.01:
                portion_str = "1 portion"
            else:
                portion_str = f"x{portion_mult:.2f}"
            
            print(f"\n  For {gap.nutrient} gap ({gap.deficit:.1f}{gap.unit}):")
            print(f"    Snack idea: {code} ({portion_str}) - {option}")
            print(f"    Impact: +{impact['nutrient_gain']:.1f}{gap.unit}, "
                  f"+{impact['calories']:.0f} cal")
    
    # =========================================================================
    # Helper methods
    # =========================================================================
    
    def _is_workspace_id(self, target: str) -> bool:
        """Check if target looks like a workspace ID."""
        # Workspace IDs are numeric or numeric + letter (e.g., "1", "2a", "123b")
        target = target.strip()
        
        if not target:
            return False
        
        # Must start with digit
        if not target[0].isdigit():
            return False
        
        # Rest must be digits or single letter at end
        if len(target) == 1:
            return True
        
        # Check pattern: digits + optional letter
        import re
        return bool(re.match(r'^\d+[a-zA-Z]?$', target))
    
    def _extract_meal_items_from_pending(
        self,
        items: List[Dict[str, Any]],
        meal_name: str
    ) -> List[Dict[str, Any]]:
        """Extract items for a specific meal from pending."""
        meal_items = []
        current_meal = None
        current_items = []
        
        for item in items:
            # Time marker
            if 'time' in item:
                # Save previous meal if it matches
                if current_meal and current_meal.upper() == meal_name.upper():
                    meal_items.extend(current_items)
                
                # Start new meal
                current_items = []
                time_str = item.get('time', '')
                meal_override = item.get('meal_override', '')
                current_meal = categorize_time(time_str, meal_override)
                continue
            
            # Regular item
            if 'code' in item:
                current_items.append(item)
        
        # Don't forget last meal
        if current_meal and current_meal.upper() == meal_name.upper():
            meal_items.extend(current_items)
        
        return meal_items
    
    def _map_nutrient_to_column(self, nutrient_key: str) -> str:
        """Map nutrient key from template to column name in master."""
        mapping = {
            'cal': 'cal',
            'protein': 'prot_g',
            'carbs': 'carbs_g',
            'fat': 'fat_g',
            'fiber': 'fiber_g',
            'sugar': 'sugar_g',
            'sodium': 'sodium_mg',
            'potassium': 'potassium_mg',
            'gl': 'gl',
            'gi': 'gi'
        }
        
        return mapping.get(nutrient_key, nutrient_key)
    
    def _get_meal_appropriateness(self, code: str, meal_name: str) -> float:
        """
        Get meal appropriateness bonus multiplier.
        
        Higher for items commonly used in this meal type.
        Returns 1.0-1.5 multiplier.
        """
        # Simple heuristic based on code section
        code_upper = code.upper()
        meal_upper = meal_name.upper()
        
        # Breakfast bonuses
        if meal_upper == 'BREAKFAST':
            if code_upper.startswith(('BV', 'EG', 'BF')):
                return 1.3
            if code_upper.startswith(('FR', 'DA')):
                return 1.2
        
        # Lunch bonuses
        elif meal_upper == 'LUNCH':
            if code_upper.startswith(('BR', 'VE', 'SA')):
                return 1.2
        
        # Dinner bonuses
        elif meal_upper == 'DINNER':
            if code_upper.startswith(('MT', 'FI', 'VE')):
                return 1.2
        
        # Snack bonuses
        elif 'SNACK' in meal_upper:
            if code_upper.startswith(('FR', 'NB', 'SN')):
                return 1.3
        
        # Default
        return 1.0
    
    def _display_header(self, result) -> None:
        """Display analysis header."""
        print("\n" + "=" * 70)
        print(f"RECOMMENDATIONS: {result.meal_name}")
        if result.meal_id:
            print(f"Workspace ID: {result.meal_id}")
        if result.meal_description:
            print(f"Description: {result.meal_description}")
        print(f"Template: {result.template_name}")
        print("=" * 70)
        
        # Show current totals
        totals = result.totals
        print(f"\nCurrent totals:")
        print(f"  {totals.calories:.0f} cal | "
              f"{totals.protein_g:.1f}g protein | "
              f"{totals.carbs_g:.1f}g carbs | "
              f"{totals.fat_g:.1f}g fat")
        print(f"  {totals.fiber_g:.1f}g fiber | "
              f"GL {totals.glycemic_load:.0f} | "
              f"{totals.sugar_g:.1f}g sugar")
    
    def _show_help(self) -> None:
        """Show help message."""
        print("\nUsage: recommend <id|meal_name> --template <template>")
        print("\nFor workspace meals:")
        print("  recommend 123a --template lunch.balanced")
        print("  recommend 2a --template breakfast.protein_focus")
        print("  (If already analyzed, template is optional)")
        print("\nFor pending meals:")
        print("  recommend breakfast --template breakfast.balanced")
        print("  recommend lunch --template lunch.low_carb")
        print("  recommend dinner --template dinner.standard")
        print("\nProvides:")
        print("  • Gap closure suggestions (add items/increase portions)")
        print("  • Excess management tips (reduce/remove items)")
        print("  • Leftover ideas (lunch only)")
        print("  • Snack bridge options")
        print()


# Add pandas import
import pandas as pd