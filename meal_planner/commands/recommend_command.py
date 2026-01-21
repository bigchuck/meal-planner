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
from meal_planner.models.scoring_context import MealLocation, ScoringContext
from meal_planner.analyzers.meal_analyzer import MealAnalyzer
from meal_planner.generators import MealGenerator

import pandas as pd        

@register_command
class RecommendCommand(Command, CommandHistoryMixin):
    """Generate recommendations for meal optimization."""
    
    name = "recommend"
    help_text = "Get optimization suggestions (recommend <id|meal_name>)"
    
    def execute(self, args: str) -> None:
        """
        Execute recommend command with subcommands.
        
        Args:
            args: Full argument string (everything after "recommend")
        """
        # Check dependencies
        if not self._check_thresholds("Recommend"):
            return
        
        if not self.ctx.user_prefs:
            print("\nRecommend unavailable: user preferences not loaded")
            print("Check meal_plan_user_preferences.json\n")
            return
        
        # Parse args
        try:
            parts = shlex.split(args) if args.strip() else []
        except ValueError:
            parts = args.strip().split() if args.strip() else []
        
        # No args or help request
        if not parts or parts[0] == "help":
            self._help()
            return
        
        # Extract subcommand and remaining arguments
        subcommand = parts[0].lower()
        subargs = parts[1:]  # THIS IS THE FIX - use parts[1:] not parts[1].split()
        
        # Route to subcommand handlers
        if subcommand == "generate":
            self._generate_candidates(subargs)
        elif subcommand == "show":
            self._show(subargs)
        elif subcommand == "filter":
            self._filter(subargs)
        elif subcommand == "score":
            self._score(subargs)
        elif subcommand == "discard":
            self._discard(subargs)
        elif subcommand == "help":
            self._help()
        else:
            print(f"\nUnknown subcommand: {subcommand}")
            self._help()

    # =========================================================================
    # Helper methods
    # =========================================================================
    
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
        

    def _help(self) -> None:
        """Display help for recommend command."""
        print("\nRECOMMEND - Meal recommendation pipeline")
        print()
        print("Subcommands:")
        print()
        
        print("  recommend generate <meal_type> [count]")
        print("    Generate meal candidates from history")
        print("    Examples:")
        print("      recommend generate lunch")
        print("      recommend generate breakfast 20")
        print()
        
        print("  recommend show [id]")
        print("    Show generated candidates")
        print("    Examples:")
        print("      recommend show          # All candidates (one-line summaries)")
        print("      recommend show G3       # Detailed view of G3")
        print()
        
        print("  recommend filter [--verbose]")
        print("    Apply pre-score filters (locks, availability)")
        print("    Filters raw candidates before scoring")
        print("    Examples:")
        print("      recommend filter")
        print("      recommend filter --verbose")
        print()
        
        print("  recommend score <meal_id>")
        print("    Debug scorer output for a specific meal")
        print("    Examples:")
        print("      recommend score 123a")
        print("      recommend score pending --meal breakfast")
        print()
        
        print("  recommend discard [array]")
        print("    Discard generated candidates (requires confirmation)")
        print("    Arrays: raw, filtered, scored (omit to discard all)")
        print("    Examples:")
        print("      recommend discard       # Discard all")
        print("      recommend discard raw   # Discard only raw")
        print()
        
        print("Pipeline flow:")
        print("  1. recommend generate lunch      # Generate raw candidates")
        print("  2. recommend show                # Preview candidates")
        print("  3. recommend filter              # Apply pre-score filters")
        print("  4. recommend show                # View filtered candidates")
        print("  5. recommend score               # Score filtered candidates (future)")
        print("  6. recommend accept G3           # Accept a recommendation (future)")
        print("  7. recommend discard             # Clean up when done")
        print()

    def _score(self, args: List[str]) -> None:
        """
        Debug scorer output for a meal.
        
        Args:
            args: [meal_id, optional --meal flag]
        
        Examples:
            recommend score 123a
            recommend score N1
            recommend score pending --meal breakfast
        """
        if not args:
            print("\nUsage: recommend score <meal_id>")
            print("\nExamples:")
            print("  recommend score 123a")
            print("  recommend score N1")
            print("  recommend score pending --meal breakfast")
            print()
            return
        
        # Check dependencies
        if not self.ctx.scorers:
            print("\nScorer system not initialized")
            print("Check meal_plan_config.json and user preferences")
            print()
            return
        
        # Parse meal_id
        meal_id = args[0]
        meal_category = None
        
        # Check for --meal flag (for pending)
        if len(args) >= 3 and args[1] == "--meal":
            meal_category = args[2]
        
        # Build scoring context
        context = self._build_scoring_context(meal_id, meal_category)
        if not context:
            return
        
        # Score the meal
        self._score_meal(context)

    def _build_scoring_context(self, meal_id: str, meal_category: Optional[str]) -> Optional[ScoringContext]:
        """Build scoring context from meal ID."""

        # Determine location and get items
        if meal_id.lower() == "pending":
            location = MealLocation.PENDING
            
            # Get pending items for meal_category
            if not meal_category:
                print("\nError: --meal required for pending")
                print("Example: recommend score pending --meal breakfast")
                print()
                return None
            
            # Extract items for this meal from pending
            pending = self.ctx.pending.load()
            if not pending or not pending.get('items'):
                print(f"\nNo pending items for {meal_category}")
                print()
                return None
            
            # Extract items for target meal
            items = self._extract_pending_meal_items(pending['items'], meal_category)
            
            if not items:
                print(f"\nNo items found for pending {meal_category}")
                print()
                return None
            
            meal_id_str = None  # Pending doesn't have persistent ID
            
        else:
            location = MealLocation.WORKSPACE
            
            # Get workspace meal by ID
            ws = self.ctx.planning_workspace
            meal = None
            
            for candidate in ws['candidates']:
                if candidate['id'].upper() == meal_id.upper():
                    meal = candidate
                    break
            
            if not meal:
                print(f"\nMeal '{meal_id}' not found in workspace")
                print("Use 'plan show' to see available meals")
                print()
                return None
            
            items = meal.get('items', [])
            meal_category = meal.get('meal_name', 'unknown')
            meal_id_str = meal['id']
        
        # Get template path
        template_path = self._get_template_for_meal(meal_category)
        
        # Run analysis to get gaps/excesses
        analyzer = MealAnalyzer(
            self.ctx.master,
            self.ctx.nutrients,
            self.ctx.thresholds
        )
        
        try:
            analysis_result = analyzer.calculate_analysis(
                items=items,
                template_path=template_path,
                meal_name=meal_category,
                meal_id=meal_id_str
            )
        except Exception as e:
            print(f"\nAnalysis error: {e}")
            print()
            return None
        
        # Build context
        context = ScoringContext(
            location=location,
            meal_id=meal_id_str,
            meal_category=meal_category,
            template_path=template_path,
            items=items,
            totals=analysis_result.totals.to_dict() if hasattr(analysis_result.totals, 'to_dict') else {},
            analysis_result=analysis_result
        )
        
        return context

    def _score_meal(self, context: ScoringContext) -> None:
        """Score and display results for a meal."""
        
        # Display header
        meal_display = context.meal_id if context.meal_id else "pending"
        print(f"\nScoring meal: {meal_display} ({context.meal_category})")
        print(f"Items: {context.item_count()}")
        
        if context.totals:
            cal = context.totals.get('cal', 0)
            prot = context.totals.get('prot_g', 0)
            carbs = context.totals.get('carbs_g', 0)
            fat = context.totals.get('fat_g', 0)
            print(f"Total: {cal:.0f} cal, {prot:.0f}g prot, {carbs:.0f}g carbs, {fat:.0f}g fat")
        print()
        
        # Run each scorer
        scorer_results = []
        weights = self.ctx.thresholds.get_recommendation_weights()
        
        for scorer_name, scorer in self.ctx.scorers.items():
            result = scorer.calculate_score(context)
            scorer_results.append(result)
            
            weight = weights.get(scorer_name, 0.0)
            weighted = result.get_weighted_score(weight)
            
            print(f"=== {scorer_name.upper()} ===")
            print(f"Raw Score: {result.raw_score:.3f}")
            print(f"Weight: {weight:.1f}")
            print(f"Weighted Score: {weighted:.3f}")
            print()
            
            # Display details
            if result.details:
                self._display_scorer_details(scorer_name, result.details)
            print()
        
        # Calculate aggregate
        final_score = sum(
            r.get_weighted_score(weights.get(r.scorer_name, 0.0))
            for r in scorer_results
        )
        
        print(f"=== AGGREGATE SCORE ===")
        print(f"Final Score: {final_score:.3f}")
        print()

    def _display_scorer_details(self, scorer_name: str, details: Dict[str, Any]) -> None:
        """Display scorer-specific details."""
        if scorer_name == "nutrient_gap":
            self._display_nutrient_gap_details(details)

    def _display_nutrient_gap_details(self, details: Dict[str, Any]) -> None:
        """Display nutrient gap scorer details."""
        print("Gap Analysis:")
        
        gap_count = details.get("gap_count", 0)
        excess_count = details.get("excess_count", 0)
        
        print(f"  Gaps: {gap_count}")
        
        # Show gap penalties
        gap_penalties = details.get("gap_penalties", [])
        for gap in gap_penalties:
            nutrient = gap["nutrient"]
            current = gap["current"]
            target = gap["target"]
            deficit = gap["deficit"]
            deficit_pct = gap["deficit_pct"]
            priority = gap["priority"]
            weight = gap["weight"]
            penalty = gap["penalty"]
            unit = gap.get("unit", "")
            
            print(f"    {nutrient}: {current:.1f}{unit} / {target:.1f}{unit} target "
                f"(-{deficit:.1f}{unit}, {deficit_pct*100:.0f}% deficit)")
            print(f"      Priority: {priority}, Weight: {weight:.1f}x, Penalty: {penalty:.2f}")
        
        print(f"\n  Excesses: {excess_count}")
        
        # Show excess penalties
        excess_penalties = details.get("excess_penalties", [])
        for excess in excess_penalties:
            nutrient = excess["nutrient"]
            current = excess["current"]
            threshold = excess["threshold"]
            overage = excess["overage"]
            overage_pct = excess["overage_pct"]
            penalty = excess["penalty"]
            unit = excess.get("unit", "")
            
            print(f"    {nutrient}: {current:.1f}{unit} / {threshold:.1f}{unit} limit "
                f"(+{overage:.1f}{unit}, {overage_pct*100:.0f}% over)")
            print(f"      Penalty: {penalty:.2f}")
        
        # Show summary
        total_gap_penalty = details.get("total_gap_penalty", 0.0)
        total_excess_penalty = details.get("total_excess_penalty", 0.0)
        bonus = details.get("perfect_match_bonus", 0.0)
        
        print(f"\n  Total Gap Penalty: {total_gap_penalty:.2f}")
        print(f"  Total Excess Penalty: {total_excess_penalty:.2f}")
        print(f"  Perfect Match Bonus: {bonus:.2f}")
        print(f"  ")
        print(f"  Base Score: {details.get('base_score', 1.0):.2f}")
        print(f"  Final Score: {details.get('final_score', 0.0):.2f}")

    # =========================================================================
    # Scorer integration methods
    # =========================================================================

    def _score(self, args: List[str]) -> None:
        """
        Debug scorer output for a meal.
        
        Args:
            args: [meal_id, optional --meal flag, optional --template flag]
        
        Examples:
            recommend score 123a
            recommend score N1
            recommend score pending --meal breakfast
            recommend score 20 --template lunch.balanced
        """
        if not args:
            print("\nUsage: recommend score <meal_id> [--meal <category>] [--template <path>]")
            print("\nExamples:")
            print("  recommend score 123a")
            print("  recommend score N1")
            print("  recommend score pending --meal breakfast")
            print("  recommend score 20 --template lunch.balanced")
            print()
            return
        
        # Check dependencies
        if not self.ctx.scorers:
            print("\nScorer system not initialized")
            print("Check meal_plan_config.json and user preferences")
            print()
            return
        
        # Parse arguments
        meal_id = args[0]
        meal_category = None
        template_override = None
        
        i = 1
        while i < len(args):
            if args[i] == "--meal" and i + 1 < len(args):
                meal_category = args[i + 1]
                i += 2
            elif args[i] == "--template" and i + 1 < len(args):
                template_override = args[i + 1]
                i += 2
            else:
                i += 1
        
        # Build scoring context (now with template override support)
        context = self._build_scoring_context(meal_id, meal_category, template_override)
        if not context:
            return
        
        # Score the meal
        self._score_meal(context)

    def _build_scoring_context(
        self, 
        meal_id: str, 
        meal_category: Optional[str],
        template_override: Optional[str] = None  # NEW: support --template flag
    ) -> Optional['ScoringContext']:
        """Build scoring context from meal ID."""
        from meal_planner.models.scoring_context import MealLocation, ScoringContext
        from meal_planner.analyzers.meal_analyzer import MealAnalyzer
        
        # ... existing code to determine location and get items ...
        
        if meal_id.lower() == "pending":
            location = MealLocation.PENDING
            
            if not meal_category:
                print("\nError: --meal required for pending")
                print("Example: recommend score pending --meal breakfast")
                print()
                return None
            
            pending = self.ctx.pending_mgr.load()
            if not pending or not pending.get('items'):
                print(f"\nNo pending items for {meal_category}")
                print()
                return None
            
            items = self._extract_pending_meal_items(pending['items'], meal_category)
            
            if not items:
                print(f"\nNo items found for pending {meal_category}")
                print()
                return None
            
            meal_id_str = None
            
        else:
            location = MealLocation.WORKSPACE
            
            ws = self.ctx.planning_workspace
            meal = None
            
            for candidate in ws['candidates']:
                if candidate['id'].upper() == meal_id.upper():
                    meal = candidate
                    break
            
            if not meal:
                print(f"\nMeal '{meal_id}' not found in workspace")
                print("Use 'plan show' to see available meals")
                print()
                return None
            
            items = meal.get('items', [])
            meal_category = meal.get('meal_name', 'unknown')
            meal_id_str = meal['id']
        
        # Get template path - NOW PROPERLY FROM CONFIG
        template_path = self._get_template_for_meal(meal_category, template_override)
        
        # ERROR if no template found
        if not template_path:
            print(f"\nError: No template found for meal category '{meal_category}'")
            print(f"Available meal categories in config:")
            
            if self.ctx.thresholds:
                meal_templates = self.ctx.thresholds.thresholds.get('meal_templates', {})
                for cat in meal_templates.keys():
                    print(f"  - {cat}")
            
            print(f"\nEither:")
            print(f"  1. Add a template for '{meal_category}' to meal_plan_config.json")
            print(f"  2. Use --template flag to specify one explicitly")
            print()
            return None
        
        # Run analysis
        analyzer = MealAnalyzer(
            self.ctx.master,
            self.ctx.nutrients,
            self.ctx.thresholds
        )
        
        try:
            analysis_result = analyzer.calculate_analysis(
                items=items,
                template_path=template_path,
                meal_name=meal_category,
                meal_id=meal_id_str
            )
        except Exception as e:
            print(f"\nAnalysis error: {e}")
            print()
            return None
        
        # Build totals dict
        totals_dict = {}
        if hasattr(analysis_result.totals, 'to_dict'):
            totals_dict = analysis_result.totals.to_dict()
        else:
            totals_dict = {
                'cal': getattr(analysis_result.totals, 'calories', 0),
                'prot_g': getattr(analysis_result.totals, 'protein_g', 0),
                'carbs_g': getattr(analysis_result.totals, 'carbs_g', 0),
                'fat_g': getattr(analysis_result.totals, 'fat_g', 0),
                'sugar_g': getattr(analysis_result.totals, 'sugar_g', 0),
                'gl': getattr(analysis_result.totals, 'glycemic_load', 0)
            }
        
        context = ScoringContext(
            location=location,
            meal_id=meal_id_str,
            meal_category=meal_category,
            template_path=template_path,
            items=items,
            totals=totals_dict,
            analysis_result=analysis_result
        )
        
        return context


    def _score_meal(self, context: 'ScoringContext') -> None:
        """Score and display results for a meal."""
        
        # Display header
        meal_display = context.meal_id if context.meal_id else "pending"
        print(f"\nScoring meal: {meal_display} ({context.meal_category})")
        
        # Show template being used
        if context.template_path:
            print(f"Template: {context.template_path}")
        
        print(f"Items: {context.item_count()}")
        
        if context.totals:
            cal = context.totals.get('cal', 0)
            prot = context.totals.get('prot_g', 0)
            carbs = context.totals.get('carbs_g', 0)
            fat = context.totals.get('fat_g', 0)
            print(f"Total: {cal:.0f} cal, {prot:.0f}g prot, {carbs:.0f}g carbs, {fat:.0f}g fat")
        print()
        
        # Run each scorer
        scorer_results = []
        weights = self.ctx.thresholds.get_recommendation_weights()
        
        for scorer_name, scorer in self.ctx.scorers.items():
            result = scorer.calculate_score(context)
            scorer_results.append(result)
            
            weight = weights.get(scorer_name, 0.0)
            weighted = result.get_weighted_score(weight)
            
            print(f"=== {scorer_name.upper()} ===")
            print(f"Raw Score: {result.raw_score:.3f}")
            print(f"Weight: {weight:.1f}")
            print(f"Weighted Score: {weighted:.3f}")
            print()
            
            # Display details
            if result.details:
                self._display_scorer_details(scorer_name, result.details)
            print()
        
        # Calculate aggregate
        final_score = sum(
            r.get_weighted_score(weights.get(r.scorer_name, 0.0))
            for r in scorer_results
        )
        
        print(f"=== AGGREGATE SCORE ===")
        print(f"Final Score: {final_score:.3f}")
        print()

    def _display_scorer_details(self, scorer_name: str, details: Dict[str, Any]) -> None:
        """Display scorer-specific details."""
        if scorer_name == "nutrient_gap":
            self._display_nutrient_gap_details(details)

    def _display_nutrient_gap_details(self, details: Dict[str, Any]) -> None:
        """Display nutrient gap scorer details."""
        print("Gap Analysis:")
        
        gap_count = details.get("gap_count", 0)
        excess_count = details.get("excess_count", 0)
        
        print(f"  Gaps: {gap_count}")
        
        # Show gap penalties
        gap_penalties = details.get("gap_penalties", [])
        for gap in gap_penalties:
            nutrient = gap["nutrient"]
            current = gap["current"]
            target_min = gap["target_min"]
            target_max = gap.get("target_max")
            deficit = gap["deficit"]
            # deficit_pct = gap["deficit_pct"]  # Don't display this anymore
            priority = gap["priority"]
            weight = gap["weight"]
            penalty = gap["penalty"]
            unit = gap.get("unit", "")
            
            # Format target display - show range if max exists
            if target_max is not None:
                target_str = f"{target_min:.1f}-{target_max:.1f}{unit}"
            else:
                target_str = f"{target_min:.1f}{unit}"
            
            # CLEANER: Just show current / target / deficit (no redundant %)
            print(f"    {nutrient}: {current:.1f}{unit} / {target_str} target (-{deficit:.1f}{unit})")
            print(f"      Priority: {priority}, Weight: {weight:.1f}x, Penalty: {penalty:.2f}")
        
        print(f"\n  Excesses: {excess_count}")
        
        # Show excess penalties
        excess_penalties = details.get("excess_penalties", [])
        for excess in excess_penalties:
            nutrient = excess["nutrient"]
            current = excess["current"]
            threshold = excess["threshold"]
            overage = excess["overage"]
            # overage_pct = excess["overage_pct"]  # Don't display this anymore
            penalty = excess["penalty"]
            unit = excess.get("unit", "")
            
            # CLEANER: Just show current / limit / overage (no redundant %)
            print(f"    {nutrient}: {current:.1f}{unit} / {threshold:.1f}{unit} limit (+{overage:.1f}{unit})")
            print(f"      Penalty: {penalty:.2f}")
        
        # Show summary
        total_gap_penalty = details.get("total_gap_penalty", 0.0)
        total_excess_penalty = details.get("total_excess_penalty", 0.0)
        bonus = details.get("perfect_match_bonus", 0.0)
        
        print(f"\n  Total Gap Penalty: {total_gap_penalty:.2f}")
        print(f"  Total Excess Penalty: {total_excess_penalty:.2f}")
        print(f"  Perfect Match Bonus: {bonus:.2f}")
        print(f"  ")
        print(f"  Base Score: {details.get('base_score', 1.0):.2f}")
        print(f"  Final Score: {details.get('final_score', 0.0):.2f}")

    def _get_template_for_meal(self, meal_category: str, template_override: Optional[str] = None) -> Optional[str]:
        """
        Get template path for a meal category from config.
        
        Resolution order:
        1. If template_override provided via --template flag, use that
        2. Otherwise, get templates for meal_category from config
        3. If multiple templates exist, use first one
        4. If no templates exist for category, return None (caller should error)
        
        Args:
            meal_category: Meal name (breakfast, lunch, etc.)
            template_override: Optional template path from --template flag
        
        Returns:
            Template path string or None if not found
        """
        # If explicit override provided, use it
        if template_override:
            return template_override
        
        # Get meal templates from config
        if not self.ctx.thresholds:
            return None
        
        meal_templates = self.ctx.thresholds.thresholds.get('meal_templates', {})
        
        # Normalize meal category
        meal_lower = meal_category.lower() if meal_category else ''
        
        # Get templates for this meal category
        category_templates = meal_templates.get(meal_lower, {})
        
        if not category_templates:
            # No templates defined for this meal category
            return None
        
        # Get first template key (they're typically named like "protein_low_carb", "balanced", etc.)
        template_keys = list(category_templates.keys())
        if not template_keys:
            return None
        
        first_template = template_keys[0]
        
        # Return full path: "meal_category.template_name"
        return f"{meal_lower}.{first_template}"

    def _extract_pending_meal_items(self, all_items: List[Dict], meal_category: str) -> List[Dict]:
        """
        Extract items for a specific meal from pending items list.
        
        Args:
            all_items: All pending items (includes time markers and codes)
            meal_category: Target meal category
        
        Returns:
            List of items belonging to target meal
        """
        from meal_planner.utils.time_utils import categorize_time
        
        meal_items = []
        current_meal = None
        
        for item in all_items:
            # Time marker - update current meal context
            if 'time' in item and 'code' not in item:
                time_str = item.get('time', '')
                meal_override = item.get('meal_override')
                current_meal = categorize_time(time_str, meal_override)
                # Include time marker in output
                meal_items.append(item)
                continue
            
            # Code item - add if it belongs to target meal
            if current_meal and current_meal.lower() == meal_category.lower():
                meal_items.append(item)
        
        return meal_items

    def _generate_candidates(self, args: List[str]) -> None:
        """
        Generate meal candidates using history search.
        
        Args:
            args: [meal_type, optional count]
        
        Examples:
            recommend generate lunch
            recommend generate breakfast 20
        """
        # Set defaults
        meal_type = None
        count = 10
        
        # Parse arguments
        if len(args) >= 1:
            meal_type = args[0].lower()  # normalize to lowercase
            
        if len(args) >= 2:
            try:
                count = int(args[1])
                if count < 1 or count > 50:
                    print("\nError: count must be between 1 and 50")
                    print()
                    return
            except ValueError:
                print(f"\nError: Invalid count '{args[1]}' - must be a number")
                print()
                return
        
        # Validate required meal_type
        if not meal_type:
            print("\nUsage: recommend generate <meal_type> [count]")
            print("\nExamples:")
            print("  recommend generate lunch")
            print("  recommend generate breakfast 15")
            print()
            return
        
        # Optional: Validate meal_type against known templates
        if self.ctx.thresholds:
            valid_meals = self.ctx.thresholds.get_default_meal_sequence()
            if valid_meals and meal_type not in valid_meals:
                print(f"\nWarning: '{meal_type}' is not in standard meal sequence")
                print(f"Valid types: {', '.join(valid_meals)}")
                print("Continuing anyway...\n")
        
        # Generate candidates
        print(f"\nGenerating {count} candidates for {meal_type}...")
        
        from meal_planner.generators import MealGenerator
        generator = MealGenerator(self.ctx.master, self.ctx.log)
        
        candidates = generator.generate_candidates(
            meal_type=meal_type,
            max_candidates=count,
            lookback_days=60
        )
        
        if not candidates:
            print(f"\nNo {meal_type} meals found in history")
            print("Try:")
            print("  - Different meal type")
            print("  - Increasing lookback days (future feature)")
            print()
            return
        
        # Save to workspace
        self.ctx.workspace_mgr.set_generated_candidates(
            meal_type=meal_type,
            raw_candidates=candidates
        )
        
        # Display results
        print(f"\nGenerated {len(candidates)} raw candidates for {meal_type}")
        print()
    
    def _filter(self, args: List[str]) -> None:
        """
        Apply pre-score filters to raw generated candidates.
        
        Filters applied:
        - Lock constraints (include/exclude)
        - Availability constraints (exclude_from_recommendations)
        
        Usage:
            recommend filter
            recommend filter --verbose
        
        Args:
            args: Optional flags (--verbose for detailed output)
        """
        # Check for verbose flag
        verbose = "--verbose" in args or "-v" in args
        
        # Check for generated candidates
        gen_cands = self.ctx.workspace_mgr.get_generated_candidates()
        
        if not gen_cands:
            print("\nNo generated candidates to filter")
            print("Run 'recommend generate <meal_type>' first")
            print()
            return
        
        raw_candidates = gen_cands.get("raw", [])
        meal_type = gen_cands.get("meal_type", "unknown")
        
        if not raw_candidates:
            print("\nNo raw candidates found")
            print()
            return
        
        print(f"\n=== FILTERING {len(raw_candidates)} {meal_type.upper()} CANDIDATES ===\n")
        
        # Load locks from workspace
        workspace = self.ctx.workspace_mgr.load()
        locks = workspace.get("locks", {"include": {}, "exclude": []})
        
        # Initialize filter
        from meal_planner.filters import PreScoreFilter
        pre_filter = PreScoreFilter(locks=locks, user_prefs=self.ctx.user_prefs)
        
        # Apply filters
        filtered_candidates = pre_filter.filter_candidates(raw_candidates)
        
        # Save filtered candidates
        self.ctx.workspace_mgr.update_filtered_candidates(filtered_candidates)
        
        # Display results
        stats = pre_filter.get_filter_stats(len(raw_candidates), len(filtered_candidates))
        print(stats)
        print()
        
        if verbose and len(filtered_candidates) < len(raw_candidates):
            # Show what was rejected
            rejected_count = len(raw_candidates) - len(filtered_candidates)
            print(f"\nRejection breakdown:")
            
            # Identify rejected candidates
            filtered_dates = {c.get("source_date") for c in filtered_candidates}
            rejected = [c for c in raw_candidates if c.get("source_date") not in filtered_dates]
            
            for i, candidate in enumerate(rejected[:10], 1):  # Show first 10
                codes = [item["code"] for item in candidate.get("items", []) if "code" in item]
                codes_str = ", ".join(codes)
                print(f"  {i}. {candidate.get('description')}: {codes_str}")
            
            if rejected_count > 10:
                print(f"  ... and {rejected_count - 10} more")
            print()
        
        if filtered_candidates:
            print(f"Filtered candidates ready for scoring")
            print(f"Next: recommend score (or recommend show to preview)")
        else:
            print(f"All candidates filtered out - adjust locks or generate more")
        
        print()

    def _show(self, args: List[str]) -> None:
        """
        Show generated candidates.
        
        Usage:
            recommend show          # Show all candidates (one-line summaries)
            recommend show G3       # Show detailed view of G3
        
        Args:
            args: Optional [candidate_id]
        """
        # Check for generated candidates
        gen_cands = self.ctx.workspace_mgr.get_generated_candidates()
        
        if not gen_cands:
            print("\nNo generated candidates to show")
            print("Run 'recommend generate <meal_type>' first")
            print()
            return
        
        meal_type = gen_cands.get("meal_type", "unknown")
        
        # Determine which list to show (filtered if available, else raw)
        filtered = gen_cands.get("filtered", [])
        raw = gen_cands.get("raw", [])
        
        candidates = filtered if filtered else raw
        list_type = "filtered" if filtered else "raw"
        
        if not candidates:
            print(f"\nNo {list_type} candidates")
            print()
            return
        
        # Show specific candidate
        if args:
            candidate_id = args[0].upper()
            self._show_candidate_detail(candidates, candidate_id, meal_type)
            return
        
        # Show all candidates (one-line summaries)
        self._show_all_candidates(candidates, meal_type, list_type)

    def _show_all_candidates(
        self,
        candidates: List[Dict[str, Any]],
        meal_type: str,
        list_type: str
    ) -> None:
        """
        Show all candidates with one-line summaries.
        
        Args:
            candidates: List of candidate dicts
            meal_type: Meal type
            list_type: "raw" or "filtered"
        """
        print(f"\n=== {meal_type.upper()} CANDIDATES ({list_type.upper()}) ===")
        print()
        
        for candidate in candidates:
            candidate_id = candidate.get("id", "???")
            description = candidate.get("description", "")
            
            # Get item codes
            items = candidate.get("items", [])
            codes = [item["code"] for item in items if "code" in item]
            
            # Calculate quick stats using ReportBuilder
            from meal_planner.reports import ReportBuilder
            builder = ReportBuilder(self.ctx.master, self.ctx.nutrients)
            report = builder.build_from_items(items, title="temp")
            totals = report.totals
            
            # Format one-line summary
            cal = totals.calories
            pro = totals.protein_g
            carb = totals.carbs_g
            gl = totals.glycemic_load
            
            codes_str = ", ".join(codes[:4])  # First 4 codes
            if len(codes) > 4:
                codes_str += f" +{len(codes)-4}"
            
            print(f"{candidate_id:4s} {description:15s} | {codes_str:35s} | "
                f"{cal:4.0f}cal {pro:4.1f}p {carb:4.1f}c GL{gl:4.1f}")
        
        print()
        print(f"Total: {len(candidates)} candidates")
        print(f"Use 'recommend show <id>' for details")
        print()

    def _show_candidate_detail(
        self,
        candidates: List[Dict[str, Any]],
        candidate_id: str,
        meal_type: str
    ) -> None:
        """
        Show detailed view of a specific candidate.
        
        Args:
            candidates: List of candidate dicts
            candidate_id: ID to show (e.g., "G3")
            meal_type: Meal type
        """
        # Find candidate
        candidate = None
        for c in candidates:
            if c.get("id", "").upper() == candidate_id:
                candidate = c
                break
        
        if not candidate:
            print(f"\nCandidate '{candidate_id}' not found")
            print(f"Available: {', '.join([c.get('id', '?') for c in candidates])}")
            print()
            return
        
        # Display detailed view
        print(f"\n=== CANDIDATE {candidate_id}: {meal_type.upper()} ===")
        print()
        
        # Metadata
        print(f"Source: {candidate.get('description', 'Unknown')}")
        print(f"Method: {candidate.get('generation_method', 'Unknown')}")
        if "filter_passed" in candidate:
            print(f"Filter: {'PASSED' if candidate['filter_passed'] else 'REJECTED'}")
        print()
        
        # Items
        items = candidate.get("items", [])
        print("Items:")
        for item in items:
            if "code" not in item:
                continue
            
            code = item["code"]
            mult = item.get("mult", 1.0)
            
            # Get food name
            row = self.ctx.master.lookup_code(code)
            if row:
                food_name = row[self.ctx.master.cols.option]
            else:
                food_name = "Unknown"
            
            if abs(mult - 1.0) < 0.01:
                print(f"  {code:8s} {food_name}")
            else:
                print(f"  {code:8s} x{mult:g} {food_name}")
        
        print()
        
        # Nutritional analysis
        from meal_planner.reports import ReportBuilder
        builder = ReportBuilder(self.ctx.master, self.ctx.nutrients)
        report = builder.build_from_items(items, title="Analysis")
        
        # Display totals
        totals = report.totals
        print("Nutritional Totals:")
        print(f"  Calories:  {totals.calories:.0f}")
        print(f"  Protein:   {totals.protein_g:.1f}g")
        print(f"  Carbs:     {totals.carbs_g:.1f}g")
        print(f"  Fat:       {totals.fat_g:.1f}g")
        print(f"  Fiber:     {totals.fiber_g:.1f}g")
        print(f"  Sugar:     {totals.sugar_g:.1f}g")
        print(f"  GL:        {totals.glycemic_load:.1f}")
        print()

    def _discard(self, args: List[str]) -> None:
        """
        Discard generated candidates from workspace.
        
        Usage:
            recommend discard           # Discard all (raw, filtered, scored)
            recommend discard raw       # Discard only raw candidates
            recommend discard filtered  # Discard only filtered candidates
            recommend discard scored    # Discard only scored candidates (future)
        
        Args:
            args: Optional [array_name]
        """
        # Check for generated candidates
        gen_cands = self.ctx.workspace_mgr.get_generated_candidates()
        
        if not gen_cands:
            print("\nNo generated candidates to discard")
            print()
            return
        
        # Determine what to discard
        valid_arrays = ['raw', 'filtered', 'scored']
        
        if not args:
            # Discard all
            target_arrays = ['raw', 'filtered', 'scored']
            target_label = "all candidates"
        else:
            # Discard specific array
            array_name = args[0].lower()
            
            if array_name not in valid_arrays:
                print(f"\nError: Invalid array '{array_name}'")
                print(f"Valid arrays: {', '.join(valid_arrays)}")
                print()
                return
            
            target_arrays = [array_name]
            target_label = f"{array_name} candidates"
        
        # Count what will be discarded
        meal_type = gen_cands.get("meal_type", "unknown")
        raw_count = len(gen_cands.get("raw", []))
        filtered_count = len(gen_cands.get("filtered", []))
        scored_count = len(gen_cands.get("scored", []))  # Future
        
        # Show what will be lost
        print(f"\n=== DISCARD {target_label.upper()} ===")
        print(f"Meal type: {meal_type}")
        print()
        
        total_to_discard = 0
        
        if 'raw' in target_arrays and raw_count > 0:
            print(f"  Raw candidates: {raw_count}")
            total_to_discard += raw_count
        
        if 'filtered' in target_arrays and filtered_count > 0:
            print(f"  Filtered candidates: {filtered_count}")
            total_to_discard += filtered_count
        
        if 'scored' in target_arrays and scored_count > 0:
            print(f"  Scored candidates: {scored_count}")
            total_to_discard += scored_count
        
        if total_to_discard == 0:
            print(f"  No {target_label} to discard")
            print()
            return
        
        print()
        print(f"This will PERMANENTLY delete {total_to_discard} candidate(s)")
        print()
        
        # Idiot check - require explicit "yes"
        response = input("Type 'yes' to confirm: ").strip().lower()
        
        if response != "yes":
            print("\nCancelled")
            print()
            return
        
        # Perform discard
        if not args:
            # Discard entire generated_candidates section
            self.ctx.workspace_mgr.clear_generated_candidates()
            print(f"\nDiscarded all candidates ({total_to_discard} total)")
        else:
            # Discard specific array(s)
            workspace = self.ctx.workspace_mgr.load()
            
            if "generated_candidates" in workspace:
                for array_name in target_arrays:
                    if array_name in workspace["generated_candidates"]:
                        workspace["generated_candidates"][array_name] = []
                
                self.ctx.workspace_mgr.save(workspace)
            
            print(f"\nDiscarded {target_label} ({total_to_discard} total)")
        
        print()
