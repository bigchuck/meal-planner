# meal_planner/commands/recommend_command.py
"""
Recommend command for meal optimization suggestions.

Analyzes meal gaps/excesses and suggests additions, portions, or swaps.
"""
import shlex
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import date, timedelta, datetime
from .base import Command, CommandHistoryMixin, register_command
from meal_planner.analyzers.meal_analyzer import MealAnalyzer
from meal_planner.models.analysis_result import DailyContext
from meal_planner.parsers import parse_selection_to_items
from meal_planner.utils.time_utils import categorize_time, normalize_meal_name, MEAL_NAMES
from meal_planner.models.scoring_context import MealLocation, ScoringContext
from meal_planner.generators.history_meal_generator import HistoryMealGenerator
from meal_planner.models.scoring_context import ScoringContext, MealLocation
from meal_planner.reports.report_builder import ReportBuilder
from meal_planner.filters import (
    NutrientConstraintFilter,
    PreScoreFilter,
    LeftoverMatchFilter,
    MutualExclusionFilter,
    ConditionalRequirementFilter
)
import pandas as pd        

@register_command
class RecommendCommand(Command, CommandHistoryMixin):
    """Generate recommendations for meal optimization."""
    
    name = ("recommend", "reco")
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
        elif subcommand == "status":
            self._status(subargs)
        elif subcommand == "show":
            self._show(subargs)
        elif subcommand == "filter":
            self._filter(subargs)
        elif subcommand == "score":
            self._score(subargs)
        elif subcommand == "discard":
            self._discard(subargs)
        elif subcommand == "reset":
            self._reset(subargs)
        elif subcommand == "help":
            self._help()
        elif subcommand == "accept":
            self._accept(subargs)
        elif subcommand == "debugdump":
            self._debugdump(subargs)
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
        print("Subcommands:")
        print("  recommend generate <meal_type> [--method <method>] [--count N] [--template <template>] ")
        print("    <method> := [history|exhaustive]")
        print("    <template> := [template name used for exhaustive]")
        print("  recommend status [--verbose]") 
        print("  recommend reset [--force]")
        print("  recommend show [rejected] [[id]|--limit N [--skip N]]")
        print("  recommend filter [--verbose]")
        print("  recommend score [--verbose]")
        print("  recommend accept <G-ID> [--as <id>] [--desc <text>]")
        print("  recommend discard [array]")
        print("    <array> := [raw|filtered|scored]")
        print("  recommend debugdump <array> <filename>")
        print("    <array> := [raw|filtered|rejected|scored]")
        print("Pipeline flow:")
        print("  1. recommend generate lunch      # Generate raw candidates")
        print("  2. recommend status              # Check pipeline state")
        print("  3. recommend filter              # Apply pre-score filters")
        print("  4. recommend status              # Verify filtering results")
        print("  5. recommend score               # Score filtered candidates")
        print("  6. recommend accept G3           # Accept a recommendation")
        print("  7. recommend discard             # Clean up when done")
        print()

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

    # =========================================================================
    # Scorer integration methods
    # =========================================================================

    def _score(self, args: List[str]) -> None:
        """
        Score filtered candidates.
        
        Incremental by default - only processes candidates without score_result.
        Use --rescore to clear all score_result and reprocess everything.
        
        Usage:
            recommend score              # Score only unscored filtered candidates
            recommend score --rescore    # Rescore all filtered candidates
            recommend score --verbose    # Show detailed scoring info
        
        Args:
            args: Optional flags (--verbose, --rescore)
        """
        # Parse flags
        verbose = "--verbose" in args or "-v" in args
        rescore = "--rescore" in args
        
        # Check dependencies
        if not self.ctx.scorers:
            print("\nScorer system not initialized")
            print("Check meal_plan_config.json and user preferences")
            print()
            return
        
        reco_workspace = self.ctx.workspace_mgr.load_reco()

        # Check for candidates
        gen_cands = reco_workspace.get("generated_candidates", {})

        # gen_cands = self.ctx.workspace_mgr.get_generated_candidates()
        
        if not gen_cands:
            print("\nNo generated candidates to score")
            print("Run 'recommend generate <meal_type>' first")
            print()
            return
        
        all_candidates = gen_cands.get("candidates", [])
        meal_type = gen_cands.get("meal_type", "unknown")
        
        # Find filtered (passed) candidates
        filtered_candidates = [c for c in all_candidates 
                            if c.get("filter_result") is not None 
                            and c.get("filter_result", {}).get("passed", False)]
        
        if not filtered_candidates:
            print("\nNo filtered candidates to score")
            print("Run 'recommend filter' first")
            print()
            return
        
        # Handle --rescore: clear score_result
        if rescore:
            cleared_count = sum(1 for c in filtered_candidates 
                            if c.get("score_result") is not None)
            
            if cleared_count > 0:
                for c in filtered_candidates:
                    if c.get("score_result") is not None:
                        c["score_result"] = None
                print(f"\n[RESCORE] Cleared {cleared_count} score results\n")
        
        # Find candidates to score (filtered + no score_result)
        candidates_to_score = [c for c in filtered_candidates 
                            if c.get("score_result") is None]
        
        if not candidates_to_score:
            already_scored = len(filtered_candidates)
            print(f"\nAll {already_scored} filtered candidates already scored")
            print("Use 'recommend score --rescore' to reprocess with new scoring config")
            print()
            return
        
        # Get template for this meal type
        template_path = self._get_template_for_meal(meal_type)
        
        print(f"\n=== SCORING {len(candidates_to_score)} {meal_type.upper()} CANDIDATES ===")
        if rescore:
            print(f"(Rescoring mode - processing all filtered candidates)")
        else:
            already_done = len(filtered_candidates) - len(candidates_to_score)
            if already_done > 0:
                print(f"(Incremental mode - {already_done} already scored, processing new ones)")
        print()
        
        if template_path:
            print(f"Using template: {template_path}")
        else:
            print(f"Warning: No template for '{meal_type}' - using best guess")
        print()
        
        # Score each candidate
        failed_count = 0
        
        for i, candidate in enumerate(candidates_to_score, 1):
            candidate_id = candidate.get("id", "???")
            
            if verbose:
                print(f"Scoring {candidate_id}... ({i}/{len(candidates_to_score)})")
            
            try:
                score_data = self._score_candidate(
                    candidate,
                    meal_type,
                    template_path
                )
                # Store score_result
                candidate["score_result"] = score_data
                
            except Exception as e:
                failed_count += 1
                if verbose:
                    print(f"  ERROR: {e}")
        
        # Save back to reco workspace
        # reco_workspace = self.ctx.workspace_mgr.load_reco()
        self.ctx.workspace_mgr.save_reco(reco_workspace)
        
        # Display results
        success_count = len(candidates_to_score) - failed_count
        print(f"\nScored {success_count}/{len(candidates_to_score)} candidates successfully")
        
        if failed_count > 0:
            print(f"Failed to score {failed_count} candidates")
        
        total_scored = sum(1 for c in all_candidates if c.get("score_result") is not None)
        print(f"\nTotal scored candidates: {total_scored} (out of {len(all_candidates)})")
        print()
        
        # Show top scored candidates
        scored_candidates = [c for c in all_candidates if c.get("score_result") is not None]
        scored_candidates.sort(key=lambda x: x["score_result"].get("aggregate_score", 0), 
                            reverse=True)
        
        self._display_scored_summary(scored_candidates[:10], meal_type, verbose)
        
        print()
        print("Next: recommend show <id> (detailed view)")
        print("      recommend accept <id> (add to workspace)")
        print()

    def _score_candidate(
        self,
        candidate: Dict[str, Any],
        meal_type: str,
        template_path: Optional[str]
    ) -> Dict[str, Any]:
        """
        Score a single candidate.
        
        Phase 2: Works with unified candidate structure.
        Extracts meal data, runs scorers, returns score dict only.
        
        Args:
            candidate: Unified candidate dict with meal structure
            meal_type: Meal category (breakfast, lunch, etc.)
            template_path: Template path for analysis
        
        Returns:
            Score result dict with aggregate_score, scores, analysis
        """        
        candidate_id = candidate.get("id")
        
        # Extract from unified structure
        meal = candidate.get("meal", {})
        items = meal.get("items", [])
        totals_dict = meal.get("totals", {})
        
        # If totals not in meal, calculate them
        if not totals_dict:
            from meal_planner.reports import ReportBuilder
            report_builder = ReportBuilder(self.ctx.master)
            report = report_builder.build_from_items(items, title="Scoring")
            totals = report.totals
            
            totals_dict = {
                'cal': getattr(totals, 'calories', 0),
                'prot_g': getattr(totals, 'protein_g', 0),
                'carbs_g': getattr(totals, 'carbs_g', 0),
                'fat_g': getattr(totals, 'fat_g', 0),
                'fiber_g': getattr(totals, 'fiber_g', 0),
                'sugar_g': getattr(totals, 'sugar_g', 0),
                'gl': getattr(totals, 'glycemic_load', 0)
            }
        # Run analysis
        analyzer = MealAnalyzer(
            self.ctx.master,
            self.ctx.thresholds
        )
        
        analysis_result = analyzer.calculate_analysis(
            items=items,
            template_path=template_path,
            meal_name=meal_type,
            meal_id=candidate_id
        )
        
        # Build scoring context
        from meal_planner.models.scoring_context import ScoringContext, MealLocation
        
        context = ScoringContext(
            location=MealLocation.CANDIDATE,
            meal_id=candidate_id,
            meal_category=meal_type,
            template_path=template_path,
            items=items,
            totals=totals_dict,
            analysis_result=analysis_result
        )
        
        # Run all scorers
        scorer_results = {}
        weights = self.ctx.thresholds.get_recommendation_weights()
        
        for scorer_name, scorer in self.ctx.scorers.items():
            result = scorer.calculate_score(context)
            weight = weights.get(scorer_name, 0.0)
            
            scorer_results[scorer_name] = {
                "raw": result.raw_score,
                "weighted": result.get_weighted_score(weight),
                "details": result.details
            }
        
        # Calculate aggregate score
        aggregate_score = sum(
            scorer_results[name]["weighted"]
            for name in scorer_results
        )
        
        # Return score data only (not the candidate)
        return {
            "aggregate_score": aggregate_score,
            "scores": scorer_results
        }
    
    def _display_scored_summary(
        self,
        scored_candidates: List[Dict[str, Any]],
        meal_type: str,
        verbose: bool
    ) -> None:
        """
        Display summary of scored candidates.
        
        Args:
            scored_candidates: List of scored candidates (sorted by score)
            meal_type: Meal category
            verbose: Show detailed info
        """
        print(f"\n=== RANKED {meal_type.upper()} CANDIDATES ===")
        print()
        print(f"{'Rank':<6}{'ID':<8}{'Score':<8}Description")
        print(f"{'-'*6}{'-'*8}{'-'*8}{'-'*50}")
        
        for rank, candidate in enumerate(scored_candidates, 1):
            candidate_id = candidate.get("id", "???")
            score_result = candidate.get("score_result", {})
            score = score_result.get("aggregate_score", 0.0)
            description = candidate.get("meal", {}).get("description", "No description")
            
            # Truncate long descriptions
            if len(description) > 47:
                description = description[:44] + "..."
            
            print(f"{rank:<6}{candidate_id:<8}{score:<8.3f}{description}")
            
            # Verbose: show gap/excess summary
            if verbose:
                scores = score_result.get("scores", {})
                nutrient_gap = scores.get("nutrient_gap", {})
                details = nutrient_gap.get("details", {})
                
                gap_penalties = details.get("gap_penalties", [])
                excess_penalties = details.get("excess_penalties", [])
                
                if gap_penalties:
                    gap_strs = [f"{g['nutrient']}(-{g.get('deficit', 0):.1f})" for g in gap_penalties[:3]]
                    print(f"{'':>14}Gaps: {', '.join(gap_strs)}")
                if excess_penalties:
                    excess_strs = [f"{e['nutrient']}(+{e.get('overage', 0):.1f})" for e in excess_penalties[:3]]
                    print(f"{'':>14}Excesses: {', '.join(excess_strs)}")
        
        print()

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
            print(f"      Priority: {priority}, Weight: {weight:.3f}x, Penalty: {penalty:.3f}")
        
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
        Generate meal candidates using specified method.
        
        Usage:
            recommend generate <meal_type> [--method history|exhaustive] [--count N] [--template NAME] [--reset]
        
        Args:
            args: Command arguments
        """
        # Parse arguments
        if not args:
            print("\nUsage: recommend generate <meal_type> [--method history|exhaustive] [--count N] [--template NAME]")
            print("\nMethods:")
            print("  history (default): Generate from meal history")
            print("  exhaustive: Generate all combinations from component pools")
            print()
            return
        
        meal_type = args[0] if args else None
        if not meal_type:
            print("\nError: meal_type required")
            print()
            return
        
        # Parse flags
        method = "history"
        count = 50
        reset = False
        template_name = None
        
        i = 1
        while i < len(args):
            if args[i] == "--method" and i + 1 < len(args):
                method = args[i + 1]
                if method not in ["history", "exhaustive"]:
                    print(f"\nError: Invalid method '{method}'")
                    print("Valid methods: history, exhaustive")
                    print()
                    return
                i += 2
            elif args[i] == "--count" and i + 1 < len(args):
                try:
                    count = int(args[i + 1])
                    if count <= 0:
                        print("\nError: --count must be positive")
                        print()
                        return
                except ValueError:
                    print(f"\nError: Invalid count '{args[i + 1]}'")
                    print()
                    return
                i += 2
            elif args[i] == "--template" and i + 1 < len(args):
                template_name = args[i + 1]
                i += 2
            else:
                print(f"\nError: Unknown flag '{args[i]}'")
                print()
                return
        
        # Rest of method unchanged...
        # (normalize meal type, handle reset, check for mismatches, route to generator)
        
        # Normalize meal type
        from meal_planner.utils.time_utils import normalize_meal_name, MEAL_NAMES
        normalized_meal = normalize_meal_name(meal_type)
        if normalized_meal not in MEAL_NAMES:
            print(f"\nError: Invalid meal type '{meal_type}'")
            print(f"Valid types: {', '.join(MEAL_NAMES)}")
            print()
            return
        
        meal_key = normalized_meal.lower()
        
        # Load workspace
        workspace = self.ctx.workspace_mgr.load()
        reco_workspace = self.ctx.workspace_mgr.load_reco()

        # Check for existing generation session
        gen_state = reco_workspace.get("generation_state", {})
        existing_method = gen_state.get("method")
        existing_meal = gen_state.get("meal_type")
        
        # Check for method/meal mismatch
        if gen_state and (existing_method != method or existing_meal != meal_key):
            print(f"\nWarning: Active generation session exists:")
            print(f"  Current: {existing_method} for {existing_meal}")
            print(f"  Requested: {method} for {meal_key}")
            print()
            print("Use --reset to clear and start new session")
            print()
            return
        
        # Route to appropriate generator
        if method == "history":
            self._generate_from_history(meal_key, count, workspace, reco_workspace, template_name)
        else:  # exhaustive
            self._generate_exhaustive(meal_key, count, workspace, reco_workspace, template_name)
    
    def _filter(self, args: List[str]) -> None:
        """
        Apply pre-score filters to candidates.
        
        Refactored into 3 phases:
        1. Setup and preparation
        2. Execute filters in sequence
        3. Wrap up and persist results
        
        Usage:
            recommend filter              # Process only unfiltered candidates
            recommend filter --refilter   # Reprocess all candidates
            recommend filter --verbose    # Show detailed output
        
        Args:
            args: Optional flags (--verbose, --refilter)
        """
        # =========================================================================
        # PHASE 1: SETUP AND PREPARATION
        # =========================================================================
        
        # Parse command flags
        verbose = "--verbose" in args or "-v" in args
        refilter = "--refilter" in args
        
        # Load candidates and workspace data
        gen_cands = self.ctx.workspace_mgr.get_generated_candidates()
        
        if not gen_cands:
            print("\nNo generated candidates to filter")
            print("Run 'recommend generate <meal_type>' first")
            print()
            return
        
        all_candidates = gen_cands.get("candidates", [])
        meal_type = gen_cands.get("meal_type", "unknown")
        
        if not all_candidates:
            print("\nNo candidates found")
            print()
            return
        
        # Handle --refilter: clear filter_result and score_result
        if refilter:
            cleared_count = 0
            score_cleared_count = 0
            for candidate in all_candidates:
                if candidate.get("filter_result") is not None:
                    candidate["filter_result"] = None
                    cleared_count += 1
                if candidate.get("score_result") is not None:
                    candidate["score_result"] = None
                    score_cleared_count += 1
            
            if cleared_count > 0:
                print(f"\n[REFILTER] Cleared {cleared_count} filter results")
                if score_cleared_count > 0:
                    print(f"[REFILTER] Cleared {score_cleared_count} score results (scoring depends on filtering)")
                print()
        
        # Find candidates to process (incremental by default)
        candidates_to_filter = [c for c in all_candidates if c.get("filter_result") is None]
        
        if not candidates_to_filter:
            already_filtered = sum(1 for c in all_candidates if c.get("filter_result") is not None)
            print(f"\nAll {already_filtered} candidates already filtered")
            print("Use 'recommend filter --refilter' to reprocess with new constraints")
            print()
            return
        
        # Load context data needed by filters
        workspace = self.ctx.workspace_mgr.load()
        reco_workspace = self.ctx.workspace_mgr.load_reco()
        gen_state = reco_workspace.get("generation_state", {})
        template_name = gen_state.get("template_name")
        
        locks = workspace.get("locks", {"include": {}, "exclude": []})
        inventory = workspace.get("inventory", {"leftovers": {}, "batch": {}, "rotating": {}})
        
        # Check collect_all mode
        collect_all = self.ctx.thresholds.thresholds.get(
            "recommendation", {}
        ).get("collect_all_rejection_reasons", False)
        
        if collect_all and verbose:
            print("[DEBUG MODE: Collecting all rejection reasons]\n")
        
        # Display header
        print(f"\n=== FILTERING {len(candidates_to_filter)} {meal_type.upper()} CANDIDATES ===")
        if refilter:
            print(f"(Refiltering mode - processing all candidates)")
        else:
            already_done = len(all_candidates) - len(candidates_to_filter)
            if already_done > 0:
                print(f"(Incremental mode - {already_done} already filtered, processing new ones)")
        print()
        
        # Initialize rejection_reasons tracking on all candidates
        for candidate in candidates_to_filter:
            candidate["rejection_reasons"] = []
        
        # =========================================================================
        # PHASE 2: EXECUTE FILTERS IN SEQUENCE
        # =========================================================================
        
        # Build filter registry - filters run in order
        filters_to_run = self._build_filter_registry(
            meal_type=meal_type,
            template_name=template_name,
            locks=locks,
            inventory=inventory,
            collect_all=collect_all
        )
        
        # Execute each filter
        for filter_name, filter_instance, filter_config in filters_to_run:
            if filter_instance is None:
                # Filter not available (e.g., no template for nutrient constraints)
                if verbose and filter_config.get("warn_if_missing"):
                    print(f"Warning: {filter_config['warn_message']}")
                    print()
                continue
            
            # Run filter directly - all filters use unified structure
            passed, rejected = filter_instance.filter_candidates(candidates_to_filter)
            
            # Map results back to original candidates
            self._apply_filter_results(
                candidates_to_filter,
                passed,
                rejected,
                collect_all
            )
            
            # Display stats if verbose
            if verbose:
                stats = filter_instance.get_filter_stats(
                    len(candidates_to_filter),
                    len(passed)
                )
                print(f"{filter_name}: {stats}")
                print()
        
        # =========================================================================
        # PHASE 3: WRAP UP AND PERSIST RESULTS
        # =========================================================================
        
        # Transform rejection_reasons into filter_result for each candidate
        passed_count = 0
        rejected_count = 0
        
        for candidate in candidates_to_filter:
            rejection_reasons = candidate.pop("rejection_reasons", [])
            
            if rejection_reasons:
                candidate["filter_result"] = {
                    "passed": False,
                    "violations": rejection_reasons
                }
                rejected_count += 1
            else:
                candidate["filter_result"] = {
                    "passed": True,
                    "violations": []
                }
                passed_count += 1
        
        # Save updated candidates back to workspace
        reco_workspace["generated_candidates"] = gen_cands
        self.ctx.workspace_mgr.save_reco(reco_workspace)
        
        # Display summary
        print(f"\nFiltering complete:")
        print(f"  Processed:      {len(candidates_to_filter)} candidates")
        print(f"  Passed filters: {passed_count} candidates")
        print(f"  Rejected:       {rejected_count} candidates")
        
        total_passed = sum(1 for c in all_candidates 
                        if c.get("filter_result", {}).get("passed", False))
        print(f"\nTotal filtered candidates: {total_passed} (out of {len(all_candidates)})")
        print()
        
        print(f"Next: Run 'recommend score' to rank filtered candidates")
        print()

    def _build_filter_registry(
        self,
        meal_type: str,
        template_name: Optional[str],
        locks: Dict[str, Any],
        inventory: Dict[str, Any],
        collect_all: bool
    ) -> List[Tuple[str, Optional[Any], Dict[str, Any]]]:
        """
        Build registry of filters to execute in order.
        
        Returns list of (filter_name, filter_instance, config_dict) tuples.
        Config dict contains metadata about how to run the filter.
        
        Args:
            meal_type: Meal category (breakfast, lunch, etc.)
            template_name: Optional template name for nutrient constraints
            locks: Lock configuration from workspace
            inventory: Inventory data from workspace
            collect_all: Whether to collect all rejection reasons
        
        Returns:
            List of (name, instance, config) tuples
        """
        filters = []
        
        # Filter 1: Nutrient Constraints
        if template_name:
            nutrient_filter = NutrientConstraintFilter(
                self.ctx.master,
                self.ctx.thresholds,
                meal_type=meal_type,
                template_name=template_name
            )
            filters.append((
                "Nutrient Constraints",
                nutrient_filter,
                {"warn_if_missing": False}
            ))
        else:
            filters.append((
                "Nutrient Constraints",
                None,
                {
                    "warn_if_missing": True,
                    "warn_message": "No template specified in generation state\nSkipping nutrient constraint filtering"
                }
            ))
        
        # Filter 2: Mutual Exclusion (NEW)
        meal_filters = self._get_meal_filters(meal_type)
        exclusion_rules = meal_filters.get("mutual_exclusions", [])
        
        if exclusion_rules:
            mutual_exclusion_filter = MutualExclusionFilter(
                meal_type=meal_type,
                thresholds_mgr=self.ctx.thresholds,
                exclusion_rules=exclusion_rules
            )
            mutual_exclusion_filter.set_collect_all(collect_all)
            
            filters.append((
                "Mutual Exclusion",
                mutual_exclusion_filter,
                {"warn_if_missing": False}
            ))
        
        # Filter 3: Conditional Requirements (NEW)
        requirement_rules = meal_filters.get("conditional_requirements", [])
        
        if requirement_rules:
            conditional_req_filter = ConditionalRequirementFilter(
                meal_type=meal_type,
                thresholds_mgr=self.ctx.thresholds,
                requirement_rules=requirement_rules
            )
            conditional_req_filter.set_collect_all(collect_all)
            
            filters.append((
                "Conditional Requirements",
                conditional_req_filter,
                {"warn_if_missing": False}
            ))
        
        # Filter 4: Pre-Score (locks, availability, inventory checks)
        prescore_filter = PreScoreFilter(
            locks=locks,
            meal_type=meal_type,
            user_prefs=self.ctx.user_prefs,
            inventory=inventory
        )
        prescore_filter.set_collect_all(collect_all)
        
        filters.append((
            "Lock/Availability/Inventory",
            prescore_filter,
            {"warn_if_missing": False}
        ))
        
        # Filter 5: Leftover Matching
        leftover_filter = LeftoverMatchFilter(
            inventory=inventory,
            allow_under_use=False
        )
        leftover_filter.set_collect_all(collect_all)
        
        filters.append((
            "Leftover Matching",
            leftover_filter,
            {"warn_if_missing": False}
        ))
        
        return filters

    def _apply_filter_results(
        self,
        original_candidates: List[Dict[str, Any]],
        passed: List[Dict[str, Any]],
        rejected: List[Dict[str, Any]],
        collect_all: bool
    ) -> None:
        """
        Apply filter results back to original candidate list.
        
        Updates rejection_reasons on candidates that were rejected.
        In collect_all mode, candidates stay in the list but accumulate reasons.
        
        Args:
            original_candidates: Original unified candidate list (modified in-place)
            passed: Candidates that passed this filter
            rejected: Candidates rejected by this filter
            collect_all: Whether we're in accumulate mode
        """
        # Build lookup of results
        passed_ids = {c["id"] for c in passed}
        rejected_dict = {r["id"]: r for r in rejected}
        
        # Update rejection_reasons on original candidates
        for candidate in original_candidates:
            cand_id = candidate["id"]
            
            if cand_id not in passed_ids:
                # This candidate was rejected - merge reasons
                rejected_info = rejected_dict.get(cand_id)
                if rejected_info:
                    candidate["rejection_reasons"] = rejected_info.get("rejection_reasons", [])

    def _show(self, args: List[str]) -> None:
        """
        Show candidates with enhanced range syntax and display options.
        
        Phase 1 Enhancements:
        - Range support: single (5), range (1-5), list (1,3,7), or omit for all
        - Display modes:
        * Single candidate: always detailed view
        * Multiple candidates without flags: detailed view (existing behavior)
        * Multiple candidates with flags: compact one-line view
        - New flags: --items, --gaps, --excesses, --nutrients
        - View support: accepts view names in addition to array names
        
        Usage:
            recommend show                          # All candidates, detailed view
            recommend show G3                       # Specific candidate, detailed view
            recommend show scored 5                 # Position 5, detailed view
            recommend show scored 1-10 --items      # Range with items, compact view
            recommend show scored --gaps            # All with gaps, compact view
            recommend show finalists 1,3,7 --nutrients # Specific positions, compact view
            recommend show rejected --items --gaps  # Multiple flags, compact view
        
        Args:
            args: Optional arguments [array|view] [range|id] [flags]
        """
        # Parse arguments
        candidate_id = None
        array_or_view_name = None
        range_spec = None  # Can be int, range, List[int], or "all"
        limit = None
        skip = 0
        
        # Display flags
        items_flag = False
        gaps_flag = False
        excesses_flag = False
        nutrients_flag = False
        
        i = 0
        while i < len(args):
            arg = args[i]
            
            # Check for flags first
            if arg == "--items":
                items_flag = True
                i += 1
                continue
            
            if arg == "--gaps":
                gaps_flag = True
                i += 1
                continue
            
            if arg == "--excesses":
                excesses_flag = True
                i += 1
                continue
            
            if arg == "--nutrients":
                nutrients_flag = True
                i += 1
                continue
            
            if arg == "--limit":
                if i + 1 < len(args):
                    try:
                        limit = int(args[i + 1])
                        if limit <= 0:
                            print("\nError: --limit must be positive")
                            print()
                            return
                        i += 2
                        continue
                    except ValueError:
                        print(f"\nError: Invalid limit value '{args[i + 1]}'")
                        print()
                        return
            
            if arg == "--skip":
                if i + 1 < len(args):
                    try:
                        skip = int(args[i + 1])
                        if skip < 0:
                            print("\nError: --skip must be non-negative")
                            print()
                            return
                        i += 2
                        continue
                    except ValueError:
                        print(f"\nError: Invalid skip value '{args[i + 1]}'")
                        print()
                        return
            
            # Check if this is an array name, view name, or candidate ID
            # First, check for array names (built-in)
            if arg.lower() in ["scored", "filtered", "rejected", "raw"]:
                array_or_view_name = arg.lower()
                
                # Check if next arg is a range specification
                if i + 1 < len(args):
                    next_arg = args[i + 1]
                    # Skip if it's a flag
                    if not next_arg.startswith("--"):
                        try:
                            range_spec = self._parse_range(next_arg)
                            i += 2  # Consume both array and range
                            continue
                        except ValueError:
                            # Not a range, just array name
                            pass
                i += 1
                continue
            
            # Check for view names
            view_names = self._get_view_names()
            if arg in view_names:
                array_or_view_name = arg  # Store view name
                
                # Check if next arg is a range specification
                if i + 1 < len(args):
                    next_arg = args[i + 1]
                    # Skip if it's a flag
                    if not next_arg.startswith("--"):
                        try:
                            range_spec = self._parse_range(next_arg)
                            i += 2  # Consume both view and range
                            continue
                        except ValueError:
                            # Not a range, just view name
                            pass
                i += 1
                continue
            
            # Otherwise assume it's a candidate ID
            if not candidate_id and not array_or_view_name:
                candidate_id = arg.upper()
                i += 1
                continue
            
            # Unknown argument
            print(f"\nError: Unknown argument '{arg}'")
            print()
            return
        
        # Load candidates
        gen_cands = self.ctx.workspace_mgr.get_generated_candidates()
        
        if not gen_cands:
            print("\nNo generated candidates to show")
            print("Run 'recommend generate <meal_type>' first")
            print()
            return
        
        meal_type = gen_cands.get("meal_type", "unknown")
        
        # Validate flags usage
        any_display_flag = items_flag or gaps_flag or excesses_flag or nutrients_flag
        
        # Case 1: Show specific candidate by ID (detailed view, ignore flags)
        if candidate_id and not array_or_view_name and not range_spec:
            if any_display_flag:
                print("\nWarning: Display flags ignored for detailed candidate view")
            
            all_candidates = gen_cands.get("candidates", [])
            
            for candidate in all_candidates:
                if candidate.get("id", "").upper() == candidate_id:
                    # Determine state for display context
                    list_name = self._determine_candidate_state(candidate)
                    self._show_candidate_detail(candidate, meal_type, list_name)
                    return
            
            # Not found
            print(f"\nCandidate {candidate_id} not found")
            print()
            return
        
        # Case 2: Show from array or view with optional range and flags
        if array_or_view_name:
            # Determine if this is an array or view
            is_view = array_or_view_name not in ["scored", "filtered", "rejected", "raw"]
            
            if is_view:
                # Get candidates from view
                candidates = self._get_candidates_for_view(array_or_view_name)
                list_type = f"view:{array_or_view_name}"
            else:
                # Get candidates from array
                candidates = self._get_candidates_by_state(gen_cands, array_or_view_name)
                list_type = array_or_view_name
            
            if not candidates:
                print(f"\nNo candidates in {array_or_view_name}")
                print()
                return
            
            # Apply range if specified
            if range_spec:
                candidates_to_show = self._apply_range(candidates, range_spec)
                if not candidates_to_show:
                    print(f"\nNo candidates match range specification")
                    print()
                    return
            else:
                # No range specified means all candidates
                candidates_to_show = candidates
            
            # Determine display mode:
            # - Single candidate: always detailed view
            # - Multiple candidates with flags: compact view
            # - Multiple candidates without flags: detailed view
            
            if len(candidates_to_show) == 1:
                # Single candidate - always show detail
                candidate = candidates_to_show[0]
                self._show_candidate_detail(candidate, meal_type, list_type)
                return
            
            # Multiple candidates
            if any_display_flag:
                # With flags: compact display
                self._show_candidates_compact(
                    candidates_to_show,
                    meal_type,
                    list_type,
                    limit=limit,
                    skip=skip,
                    items=items_flag,
                    gaps=gaps_flag,
                    excesses=excesses_flag,
                    nutrients=nutrients_flag
                )
            else:
                # Without flags: detailed display (existing behavior)
                self._show_all_candidates(
                    candidates_to_show,
                    meal_type,
                    list_type,
                    limit=limit,
                    skip=skip,
                    items=False  # Old --items behavior disabled
                )
            return
        
        # Case 3: No specific array/view - show default (priority-based)
        all_candidates = gen_cands.get("candidates", [])
        
        scored = [c for c in all_candidates if c.get("score_result") is not None]
        filtered = [c for c in all_candidates 
                if c.get("filter_result") is not None 
                and c.get("filter_result").get("passed") == True]
        rejected = [c for c in all_candidates 
                if c.get("filter_result") is not None
                and c.get("filter_result").get("passed") == False]
        raw = [c for c in all_candidates if c.get("filter_result") is None]
        
        # Determine which to show based on priority
        if scored:
            scored.sort(key=lambda x: x.get("score_result", {}).get("aggregate_score", 0), 
            reverse=True)
            candidates = scored
            list_type = "scored"
        elif filtered:
            candidates = filtered
            list_type = "filtered"
        elif rejected:
            candidates = rejected
            list_type = "rejected"
        else:
            candidates = raw
            list_type = "raw"
        
        if not candidates:
            print(f"\nNo candidates available")
            print()
            return
        
        # Display: flags determine display mode
        # - With flags: compact one-line view
        # - Without flags: detailed view (existing behavior)
        if any_display_flag:
            self._show_candidates_compact(
                candidates,
                meal_type,
                list_type,
                limit=limit,
                skip=skip,
                items=items_flag,
                gaps=gaps_flag,
                excesses=excesses_flag,
                nutrients=nutrients_flag
            )
        else:
            # Detailed display
            self._show_all_candidates(
                candidates,
                meal_type,
                list_type,
                limit=limit,
                skip=skip,
                items=False
            )


    def _apply_range(
        self,
        candidates: List[Dict[str, Any]],
        range_spec: Union[int, range, List[int], str]
    ) -> List[Dict[str, Any]]:
        """
        Apply range specification to candidate list.
        
        Args:
            candidates: List of candidates
            range_spec: Range specification (int, range, List[int], or "all")
        
        Returns:
            Filtered list of candidates
        """
        if range_spec == "all":
            return candidates
        
        if isinstance(range_spec, int):
            # Single position (1-based)
            if range_spec > len(candidates):
                return []
            return [candidates[range_spec - 1]]
        
        if isinstance(range_spec, range):
            # Range of positions (1-based)
            result = []
            for pos in range_spec:
                if pos <= len(candidates):
                    result.append(candidates[pos - 1])
            return result
        
        if isinstance(range_spec, list):
            # List of specific positions (1-based)
            result = []
            for pos in range_spec:
                if pos <= len(candidates):
                    result.append(candidates[pos - 1])
            return result
        
        return candidates


    def _show_candidates_compact(
        self,
        candidates: List[Dict[str, Any]],
        meal_type: str,
        list_type: str,
        limit: Optional[int] = None,
        skip: int = 0,
        items: bool = False,
        gaps: bool = False,
        excesses: bool = False,
        nutrients: bool = False
    ) -> None:
        """
        Show candidates in compact format with specified flags.
        
        Args:
            candidates: List of candidate dicts
            meal_type: Meal type
            list_type: Array or view name
            limit: Maximum number to show
            skip: Number to skip from start
            items: Show items flag
            gaps: Show gaps flag
            excesses: Show excesses flag
            nutrients: Show nutrients flag
        """
        total_count = len(candidates)
        
        # Apply skip
        if skip >= total_count:
            print(f"\nNo candidates to show (skip={skip} >= total={total_count})")
            print()
            return
        
        # Determine what to display
        start_idx = skip
        end_idx = min(total_count, skip + limit) if limit else total_count
        display_candidates = candidates[start_idx:end_idx]
        
        # Header
        print(f"\n=== {meal_type.upper()} CANDIDATES ({list_type.upper()}) ===")
        
        # Show pagination info
        if limit or skip:
            print(f"Showing {len(display_candidates)} of {total_count} "
                f"(positions {start_idx+1}-{end_idx})")
        else:
            print(f"Total: {total_count} candidates")
        
        print()
        
        # Build flags dict
        flags = {
            "items": items,
            "gaps": gaps,
            "excesses": excesses,
            "nutrients": nutrients
        }
        
        # Display each candidate
        for i, candidate in enumerate(display_candidates):
            actual_position = start_idx + i + 1
            self._display_candidate_compact(candidate, actual_position, flags)
        
        print()

    def _apply_range(
        self,
        candidates: List[Dict[str, Any]],
        range_spec: Union[int, range, List[int], str]
    ) -> List[Dict[str, Any]]:
        """
        Apply range specification to candidate list.
        
        Args:
            candidates: List of candidates
            range_spec: Range specification (int, range, List[int], or "all")
        
        Returns:
            Filtered list of candidates
        """
        if range_spec == "all":
            return candidates
        
        if isinstance(range_spec, int):
            # Single position (1-based)
            if range_spec > len(candidates):
                return []
            return [candidates[range_spec - 1]]
        
        if isinstance(range_spec, range):
            # Range of positions (1-based)
            result = []
            for pos in range_spec:
                if pos <= len(candidates):
                    result.append(candidates[pos - 1])
            return result
        
        if isinstance(range_spec, list):
            # List of specific positions (1-based)
            result = []
            for pos in range_spec:
                if pos <= len(candidates):
                    result.append(candidates[pos - 1])
            return result
        
        return candidates


    def _show_candidates_compact(
        self,
        candidates: List[Dict[str, Any]],
        meal_type: str,
        list_type: str,
        limit: Optional[int] = None,
        skip: int = 0,
        items: bool = False,
        gaps: bool = False,
        excesses: bool = False,
        nutrients: bool = False
    ) -> None:
        """
        Show candidates in compact format with specified flags.
        
        Args:
            candidates: List of candidate dicts
            meal_type: Meal type
            list_type: Array or view name
            limit: Maximum number to show
            skip: Number to skip from start
            items: Show items flag
            gaps: Show gaps flag
            excesses: Show excesses flag
            nutrients: Show nutrients flag
        """
        total_count = len(candidates)
        
        # Apply skip
        if skip >= total_count:
            print(f"\nNo candidates to show (skip={skip} >= total={total_count})")
            print()
            return
        
        # Determine what to display
        start_idx = skip
        end_idx = min(total_count, skip + limit) if limit else total_count
        display_candidates = candidates[start_idx:end_idx]
        
        # Header
        print(f"\n=== {meal_type.upper()} CANDIDATES ({list_type.upper()}) ===")
        
        # Show pagination info
        if limit or skip:
            print(f"Showing {len(display_candidates)} of {total_count} "
                f"(positions {start_idx+1}-{end_idx})")
        else:
            print(f"Total: {total_count} candidates")
        
        print()
        
        # Build flags dict
        flags = {
            "items": items,
            "gaps": gaps,
            "excesses": excesses,
            "nutrients": nutrients
        }
        
        # Display each candidate
        for i, candidate in enumerate(display_candidates):
            actual_position = start_idx + i + 1
            self._display_candidate_compact(candidate, actual_position, flags)
        
        print()


        
    def _show_by_position(
        self,
        gen_cands: Dict[str, Any],
        array_name: str,
        position: int,
        meal_type: str
    ) -> None:
        """
        Show candidate at specific position in array.
        
        Phase 2: Queries unified list by state.
        
        Args:
            gen_cands: Generated candidates dict
            array_name: State to search (scored/filtered/rejected/raw)
            position: 1-based position in that state
            meal_type: Meal type
        """
        # Get candidates by state
        candidates = self._get_candidates_by_state(gen_cands, array_name)
        
        if not candidates:
            print(f"\nNo {array_name} candidates")
            print()
            return
        
        # Check position bounds (1-based)
        if position > len(candidates):
            print(f"\nPosition {position} out of range ({len(candidates)} {array_name} candidates available)")
            print()
            return
        
        # Get candidate (convert to 0-based index)
        candidate = candidates[position - 1]
        
        # Show it
        self._show_candidate_detail(candidate, meal_type, array_name)

    def _show_all_candidates(
        self,
        candidates: List[Dict[str, Any]],
        meal_type: str,
        list_type: str,
        limit: Optional[int] = None,
        skip: int = 0,
        items: bool = False
    ) -> None:
        """
        Show all candidates with compact totals or detailed macro tables.
        
        FULL REPLACEMENT: Now shows totals in compact view and uses ReportBuilder for --items
        
        Args:
            candidates: List of candidate dicts
            meal_type: Meal type
            list_type: "raw", "filtered", or "scored"
            limit: Maximum number of candidates to show (None = all)
            skip: Number of candidates to skip from start
            items: If True, show full macro tables using ReportBuilder
        """
        total_count = len(candidates)
        
        # Apply skip
        if skip >= total_count:
            print(f"\nNo candidates to show (skip={skip} >= total={total_count})")
            print()
            return
        
        # Determine what to display
        start_idx = skip
        end_idx = min(total_count, skip + limit) if limit else total_count
        display_candidates = candidates[start_idx:end_idx]
        
        # Header
        print(f"\n=== {meal_type.upper()} CANDIDATES ({list_type.upper()}) ===")
        
        # Show pagination info
        if limit or skip:
            print(f"Showing {len(display_candidates)} of {total_count} "
                f"(positions {start_idx+1}-{end_idx})")
        else:
            print(f"Total: {total_count} candidates")
        
        print()
        
        if items:
            # DETAILED VIEW - Use ReportBuilder for macro tables
            from meal_planner.reports import ReportBuilder
            
            for i, candidate in enumerate(display_candidates):
                actual_position = start_idx + i + 1
                candidate_id = candidate.get("id", "???")
                
                # Header
                print(f"=== CANDIDATE {candidate_id} ===")
                
                # Source info
                source_date = candidate.get("source_date", "unknown")
                source_time = candidate.get("source_time", "")
                source_str = f"Source: {source_date} {meal_type}"
                if source_time:
                    source_str += f" ({source_time})"
                print(source_str)
                
                # Rank/score info
                if list_type == "scored":
                    rank = actual_position
                    score = candidate.get("aggregate_score", 0.0)
                    print(f"Rank: {rank}  Score: {score:.3f}")
                else:
                    print(f"Position: {actual_position}  List: {list_type}")
                
                print()
                
                # Build and print report using ReportBuilder
                builder = ReportBuilder(self.ctx.master)
                items_list = candidate.get("meal", {}).get("items", [])
                report = builder.build_from_items(items_list, title="")
                
                # Print using ReportBuilder's format (verbose=True for full table)
                report.print(verbose=True)
                
                print()
        else:
            # COMPACT VIEW - One line per candidate with totals
            # Column headers
            if list_type == "scored":
                print(f"{'Pos':<6}{'Rank':<6}{'ID':<8}{'Score':<8}Totals")
                print(f"{'-'*6}{'-'*6}{'-'*8}{'-'*8}{'-'*60}")
            else:
                print(f"{'Pos':<6}{'Rank':<6}{'ID':<8}{'List':<8}Totals")
                print(f"{'-'*6}{'-'*6}{'-'*8}{'-'*8}{'-'*60}")
            
            # Display candidates
            for i, candidate in enumerate(display_candidates):
                actual_position = start_idx + i + 1
                candidate_id = candidate.get("id", "???")
                rank = actual_position
                
                # Get or calculate totals
                totals = self._get_candidate_totals(candidate)
                
                # Format totals string
                totals_str = (f"{int(totals['cal'])} cal | {int(totals['prot_g'])}g P | "
                            f"{int(totals['carbs_g'])}g C | {int(totals['fat_g'])}g F | "
                            f"GL {int(totals['gl'])}")
                
                # Format score/list column
                if list_type == "scored":
                    score = candidate.get("score_result", {}).get("aggregate_score", 0.0)
                    score_str = f"{score:.3f}"
                else:
                    score_str = list_type
                
                print(f"{actual_position:<6}{rank:<6}{candidate_id:<8}{score_str:<8}{totals_str}")
            
            print()
        
        # Navigation hints
        if end_idx < total_count:
            remaining = total_count - end_idx
            next_skip = end_idx
            next_limit = limit if limit else 20
            print(f"{remaining} more candidates available")
            print(f"Next: recommend show --limit {next_limit} --skip {next_skip}")
            print()
        
        if items:
            print("Use 'recommend show <id>' for full scoring details")
        else:
            print("Use 'recommend show <id>' for full details")
            print("Use 'recommend show --items' to see macro tables")
        print()

    def _show_candidate_detail(
        self,
        candidates: List[Dict[str, Any]],
        candidate_id: str,
        meal_type: str
    ) -> None:
        """
        Show detailed view of a specific candidate.
        
        MODIFIED: Include scoring details if candidate is scored.
        
        Args:
            candidates: List of candidates
            candidate_id: ID to show (e.g., "G3")
            meal_type: Meal type
        """
        # Find candidate
        candidate = None
        for cand in candidates:
            if cand.get("id", "").upper() == candidate_id:
                candidate = cand
                break
        
        if not candidate:
            print(f"\nCandidate {candidate_id} not found")
            print()
            return
        
        # Header
        is_scored = "aggregate_score" in candidate
        score_label = " (SCORED)" if is_scored else ""
        
        print(f"\n=== CANDIDATE {candidate_id}{score_label} ===")
        
        # Source info
        source_date = candidate.get("source_date", "unknown")
        source_time = candidate.get("source_time", "")
        print(f"Source: {source_date} {meal_type}")
        if source_time:
            print(f"Time: {source_time}")
        
        # Score if available
        if is_scored:
            score = candidate.get("aggregate_score", 0.0)
            print(f"Aggregate Score: {score:.3f}")
        
        print()
        
        # Items
        print("Items:")
        items = candidate.get("meal", {}).get("items", [])
        for item in items:
            if "code" in item:
                code = item["code"]
                multiplier = item.get("mult", 1.0)
                
                # Get description from master
                desc = ""
                try:
                    food_data = self.ctx.master.lookup_code(code)
                    if food_data:
                        desc = food_data.get('option', '')
                except:
                    pass
                
                mult_str = f" x{multiplier:.1f}"
                desc_str = f"  ({desc})" if desc else ""
                print(f"  - {code}{mult_str}{desc_str}")
        
        # Totals if available
        totals = candidate.get("totals", {})
        if totals:
            print()
            print("Totals:")
            print(f"  Calories: {totals.get('cal', 0):.0f}")
            print(f"  Protein:  {totals.get('prot_g', 0):.1f}g")
            print(f"  Carbs:    {totals.get('carbs_g', 0):.1f}g")
            print(f"  Fat:      {totals.get('fat_g', 0):.1f}g")
            print(f"  Fiber:    {totals.get('fiber_g', 0):.1f}g")
            print(f"  GL:       {totals.get('gl', 0):.1f}")
        
        # Scoring details if scored
        if is_scored:
            print()
            self._display_candidate_scoring_details(candidate)
        
        print()

    def _show_rejected(
        self,
        limit: Optional[int] = None,
        skip: int = 0,
        items: bool = False
    ) -> None:
        """
        Show all rejected candidates with compact totals or detailed macro tables.
        
        FULL REPLACEMENT: Added items flag and totals display
        
        Args:
            limit: Maximum number to show (None = all)
            skip: Number to skip from start
            items: If True, show full macro tables using ReportBuilder
        """
        gen_cands = self.ctx.workspace_mgr.get_generated_candidates()
        if not gen_cands:
            print("\nNo generated candidates")
            print()
            return

        rejected = gen_cands.get("rejected", [])
        if not rejected:
            print("\nNo rejected candidates")
            print()
            return
        
        meal_type = gen_cands.get("meal_type", "unknown")
        total_count = len(rejected)
        
        # Apply skip
        if skip >= total_count:
            print(f"\nNo rejected candidates to show (skip={skip} >= total={total_count})")
            print()
            return
        
        # Determine what to display
        start_idx = skip
        end_idx = min(total_count, skip + limit) if limit else total_count
        display_rejected = rejected[start_idx:end_idx]
        
        # Header
        print(f"\n=== REJECTED {meal_type.upper()} CANDIDATES ===")
        
        # Show pagination info
        if limit or skip:
            print(f"Showing {len(display_rejected)} of {total_count} "
                f"(positions {start_idx+1}-{end_idx})")
        else:
            print(f"Total: {total_count} rejected")
        
        print()
        
        if items:
            # DETAILED VIEW - Use ReportBuilder for macro tables
            from meal_planner.reports import ReportBuilder
            
            for i, candidate in enumerate(display_rejected):
                actual_position = start_idx + i + 1
                candidate_id = candidate.get("id", "???")
                
                # Get rejection reasons
                reasons = candidate.get("rejection_reasons", [])
                
                # Header
                print(f"=== REJECTED CANDIDATE {candidate_id} ===")
                
                # Rejection reasons
                if reasons:
                    print(f"Rejection reasons: {', '.join(reasons)}")
                
                # Source info
                source_date = candidate.get("source_date", "unknown")
                source_time = candidate.get("source_time", "")
                source_str = f"Source: {source_date} {meal_type}"
                if source_time:
                    source_str += f" ({source_time})"
                print(source_str)
                print(f"Position: {actual_position}")
                
                print()
                
                # Build and print report using ReportBuilder
                builder = ReportBuilder(self.ctx.master)
                items_list = candidate.get("meal", {}).get("items", [])
                report = builder.build_from_items(items_list, title="")
                
                # Print using ReportBuilder's format
                report.print(verbose=True)
                
                print()
        else:
            # COMPACT VIEW - One line per candidate with totals
            # Column headers
            print(f"{'Pos':<6}{'Rank':<6}{'ID':<8}{'List':<8}Totals")
            print(f"{'-'*6}{'-'*6}{'-'*8}{'-'*8}{'-'*60}")
            
            # Display rejected candidates
            for i, candidate in enumerate(display_rejected):
                actual_position = start_idx + i + 1
                candidate_id = candidate.get("id", "???")
                rank = actual_position
                
                # Get or calculate totals
                totals = self._get_candidate_totals(candidate)
                
                # Format totals string
                totals_str = (f"{int(totals['cal'])} cal | {int(totals['prot_g'])}g P | "
                            f"{int(totals['carbs_g'])}g C | {int(totals['fat_g'])}g F | "
                            f"GL {int(totals['gl'])}")
                
                print(f"{actual_position:<6}{rank:<6}{candidate_id:<8}{'rejected':<8}{totals_str}")
            
            print()
        
        # Navigation hints
        if end_idx < total_count:
            remaining = total_count - end_idx
            next_skip = end_idx
            next_limit = limit if limit else 20
            print(f"{remaining} more rejected available")
            print(f"Next: recommend show rejected --limit {next_limit} --skip {next_skip}")
            print()
        
        if items:
            print("Use 'recommend show rejected <id>' for full details including rejection reasons")
        else:
            print("Use 'recommend show rejected <id>' for details")
            print("Use 'recommend show rejected --items' to see macro tables")
        print()

    def _get_candidate_totals(self, candidate: Dict[str, Any]) -> Dict[str, float]:
        """
        Get or calculate nutritional totals for a candidate.
        
        Args:
            candidate: Candidate dict
        
        Returns:
            Dict with keys: cal, prot_g, carbs_g, fat_g, gl
        """
        # Check if totals already exist
        if "totals" in candidate:
            totals = candidate["totals"]
            # Ensure all required keys exist
            return {
                'cal': totals.get('cal', 0),
                'prot_g': totals.get('prot_g', 0),
                'carbs_g': totals.get('carbs_g', 0),
                'fat_g': totals.get('fat_g', 0),
                'gl': totals.get('gl', 0)
            }
        
        # Calculate from items
        from meal_planner.reports import ReportBuilder
        
        builder = ReportBuilder(self.ctx.master)
        items = candidate.get("meal", {}).get("items", [])
        
        if not items:
            return {'cal': 0, 'prot_g': 0, 'carbs_g': 0, 'fat_g': 0, 'gl': 0}
        
        report = builder.build_from_items(items, title="Totals")
        totals_obj = report.totals
        
        return {
            'cal': getattr(totals_obj, 'calories', 0),
            'prot_g': getattr(totals_obj, 'protein_g', 0),
            'carbs_g': getattr(totals_obj, 'carbs_g', 0),
            'fat_g': getattr(totals_obj, 'fat_g', 0),
            'gl': getattr(totals_obj, 'glycemic_load', 0)
        }

    def _show_candidate_detail(
        self,
        candidate: Dict[str, Any],
        meal_type: str,
        list_name: str
    ) -> None:
        """
        Show detailed view of a specific candidate.
        
        MODIFIED: Now accepts single candidate dict and list_name instead of searching
        
        Args:
            candidate: Candidate dict
            meal_type: Meal type
            list_name: Which list the candidate is from (scored/filtered/rejected/raw)
        """
        candidate_id = candidate.get("id", "???")
        
        # Header
        is_scored = candidate.get("score_result") != None
        is_rejected = list_name == "rejected"
        
        if is_rejected:
            status_label = " (REJECTED)"
        elif is_scored:
            status_label = " (SCORED)"
        else:
            status_label = f" ({list_name.upper()})"
        
        print(f"\n=== CANDIDATE {candidate_id}{status_label} ===")
        
        # Rejection reasons if applicable
        if is_rejected:
            filter_result = candidate.get("filter_result", {})
            violations = filter_result.get("violations", [])            
            if violations:
                print(f"\nREJECTION REASONS ({len(violations)}):")
                for violation in violations:
                    if ":" in violation:
                        violation_type, details = violation.split(":", 1)
                        print(f"  - {violation_type}: {details}")
                    else:
                        print(f"  - {violation}")
        
        # Source info
        source_date = candidate.get("source_date", "unknown")
        source_time = candidate.get("source_time", "")
        print(f"\nSource: {source_date} {meal_type}")
        if source_time:
            print(f"Time: {source_time}")
        
        # Score if available
        if is_scored:
            score = candidate.get("score_result", {}).get("aggregate_score", 0.0)
            print(f"Aggregate Score: {score:.3f}")
        
        print()
        
        # Build and print report using ReportBuilder (same as --items view)
        from meal_planner.reports import ReportBuilder

        builder = ReportBuilder(self.ctx.master)
        items_list = candidate.get("meal", {}).get("items", [])
        report = builder.build_from_items(items_list, title="")

        # Print using ReportBuilder's format (verbose=True for full table)
        report.print(verbose=True)
        
        # Scoring details if scored
        if is_scored:
            print()
            self._display_candidate_scoring_details(candidate)
        
        print()

    def _display_candidate_scoring_details(self, candidate: Dict[str, Any]) -> None:
            """
            Display scoring details for a candidate.
            
            Args:
                candidate: Scored candidate dict
            """
            score_result = candidate.get("score_result", {})
            scores = score_result.get("scores", {})
            
            # Show each scorer's contribution
            for scorer_name, scorer_data in scores.items():
                raw = scorer_data.get("raw", 0.0)
                weighted = scorer_data.get("weighted", 0.0)
                
                print(f"=== {scorer_name.upper()} ===")
                print(f"Raw Score: {raw:.3f}")
                print(f"Weighted Score: {weighted:.3f}")
                print()
                
                # Show scorer-specific details
                details = scorer_data.get("details", {})
                if scorer_name == "nutrient_gap":
                    self._display_nutrient_gap_details(details)
                # Future scorers can add their display logic here
            
            # Show gaps/excesses summary from scoring details (not analysis object)
            if "nutrient_gap" in scores:
                details = scores["nutrient_gap"].get("details", {})
                gap_penalties = details.get("gap_penalties", [])
                excess_penalties = details.get("excess_penalties", [])
                
                if gap_penalties or excess_penalties:
                    print("=== NUTRITIONAL ANALYSIS ===")
                    
                    if gap_penalties:
                        print(f"Gaps ({len(gap_penalties)}):")
                        for gap in gap_penalties:
                            nutrient = gap.get("nutrient", "unknown")
                            deficit = gap.get("deficit", 0)
                            print(f"  - {nutrient}: -{deficit:.1f}")
                    
                    if excess_penalties:
                        print(f"Excesses ({len(excess_penalties)}):")
                        for excess in excess_penalties:
                            nutrient = excess.get("nutrient", "unknown")
                            overage = excess.get("overage", 0)
                            print(f"  - {nutrient}: +{overage:.1f}")
                    
                    print()

    def _discard(self, args: List[str]) -> None:
        """
        Discard candidates from workspace.
        
        Usage:
            recommend discard             # Full reset (all candidates + state)
            recommend discard raw         # Discard only raw candidates
            recommend discard filtered    # Discard filtered + rejected
            recommend discard scored      # Discard only scored
        
        Args:
            args: Optional array name (raw|filtered|scored), empty for full reset
        """
        # Determine what to discard
        if not args:
            # Full reset
            target_arrays = ['raw', 'filtered', 'scored']
            target_label = "all"
            full_reset = True
        else:
            array_name = args[0].lower()
            if array_name not in ['raw', 'filtered', 'scored']:
                print(f"\nUnknown array: {array_name}")
                print("Valid options: raw, filtered, scored")
                print("Or use 'recommend discard' with no args for full reset")
                print()
                return
            
            # Determine cascade
            if array_name == 'raw':
                target_arrays = ['raw', 'filtered', 'scored']
                target_label = "raw (and filtered, scored)"
            elif array_name == 'filtered':
                target_arrays = ['filtered', 'scored']
                target_label = "filtered (and scored)"
            else:  # scored
                target_arrays = ['scored']
                target_label = "scored"
            
            full_reset = False
        
        # Check for candidates
        gen_cands = self.ctx.workspace_mgr.get_generated_candidates()
        
        if not gen_cands:
            print("\nNo candidates to discard")
            print()
            return
        
        # Count what will be discarded
        meal_type = gen_cands.get("meal_type", "unknown")
        # Count candidates by status
        all_candidates = gen_cands.get("candidates", [])
        raw_count = 0
        filtered_count = 0
        rejected_count = 0
        scored_count = 0
        
        for candidate in all_candidates:
            filter_result = candidate.get("filter_result")
            score_result = candidate.get("score_result")
            
            if score_result is not None:
                scored_count += 1
            elif filter_result is None:
                raw_count += 1
            elif filter_result.get("passed") == True:
                filtered_count += 1
            elif filter_result.get("passed") == False:
                rejected_count += 1
       
        # Show what will be lost
        print(f"\n=== DISCARD {target_label.upper()} ===")
        print(f"Meal type: {meal_type}")
        print()
        
        if full_reset or 'raw' in target_arrays:
            # Deleting all candidates
            total_to_delete = len(all_candidates)
            
            if total_to_delete == 0:
                print(f"  No candidates to discard")
                print()
                return
                
            print(f"  Candidates to delete: {total_to_delete}")
            if raw_count > 0:
                print(f"    - Raw: {raw_count}")
            if filtered_count > 0:
                print(f"    - Filtered: {filtered_count}")
            if rejected_count > 0:
                print(f"    - Rejected: {rejected_count}")
            if scored_count > 0:
                print(f"    - Scored: {scored_count}")
            
            print()
            print(f"This will PERMANENTLY delete {total_to_delete} candidate(s)")
            if full_reset:
                print("Generation state will be fully reset (cursor and session cleared)")
        
        elif 'filtered' in target_arrays:
            # Clearing filter_result and score_result
            candidates_affected = sum(1 for c in all_candidates 
                                     if c.get("filter_result") is not None or c.get("score_result") is not None)
            
            if candidates_affected == 0:
                print(f"  No filtered/scored data to clear")
                print()
                return
            
            print(f"  Candidates to clear filter/score data: {candidates_affected}")
            if filtered_count > 0:
                print(f"    - Filtered: {filtered_count}")
            if rejected_count > 0:
                print(f"    - Rejected: {rejected_count}")
            if scored_count > 0:
                print(f"    - Scored: {scored_count}")
            
            print()
            print(f"This will clear filter/score data from {candidates_affected} candidate(s)")
            print("(Candidates will remain but filter_result and score_result will be cleared)")
        
        elif 'scored' in target_arrays:
            # Clearing only score_result
            if scored_count == 0:
                print(f"  No scored data to clear")
                print()
                return
            
            print(f"  Candidates to clear score data: {scored_count}")
            
            print()
            print(f"This will clear score data from {scored_count} candidate(s)")
            print("(Candidates will remain but score_result will be cleared)")
        
        print()
        
        # Idiot check - require explicit "yes"
        response = input("Type 'yes' to confirm: ").strip().lower()
        
        if response != "yes":
            print("\nCancelled")
            print()
            return
      
        # Load reco workspace
        reco_workspace = self.ctx.workspace_mgr.load_reco()
        
        # Perform discard
        if full_reset or raw_count > 0:
            # Complete reset - clear everything
            reco_workspace["generated_candidates"] = {}
            reco_workspace["generation_state"] = {}
            self.ctx.workspace_mgr.save_reco(reco_workspace)
            
            print(f"\nDiscarded all candidates ({raw_count} total)")
            print("Generation state fully reset - ready for new generation")
        else:
            # Partial discard - clear specific fields from candidates
            all_candidates = reco_workspace["generated_candidates"].get("candidates", [])
            
            if 'filtered' in target_arrays:
                # Clear both filter_result and score_result
                cleared_count = 0
                for candidate in all_candidates:
                    if candidate.get("filter_result") is not None or candidate.get("score_result") is not None:
                        candidate["filter_result"] = None
                        candidate["score_result"] = None
                        cleared_count += 1
                
                self.ctx.workspace_mgr.save_reco(reco_workspace)
                print(f"\nCleared filter and score data from {cleared_count} candidate(s)")
                print("Note: Candidates remain in workspace. Use 'recommend discard' (no args) to delete all candidates.")
            
            elif 'scored' in target_arrays:
                # Clear only score_result
                cleared_count = 0
                for candidate in all_candidates:
                    if candidate.get("score_result") is not None:
                        candidate["score_result"] = None
                        cleared_count += 1
                
                self.ctx.workspace_mgr.save_reco(reco_workspace)
                print(f"\nCleared score data from {cleared_count} candidate(s)")
                print("Note: Candidates remain in workspace. Use 'recommend discard' (no args) to delete all candidates.")
        
        print()

    def _accept(self, args: List[str]) -> None:
        """
        Accept a scored candidate and move it to planning workspace.
        
        Syntax:
            recommend accept <G-ID> [--as <custom_id>] [--desc <text>]
        
        Args:
            args: [G-ID] and optional flags
        
        Examples:
            recommend accept G3
            recommend accept G3 --as lunch-friday
            recommend accept G5 --desc "high protein option"
            recommend accept G7 --as dinner-v1 --desc "vegetarian"
        """
        if not args:
            print("\nUsage: recommend accept <G-ID> [--as <custom_id>] [--desc <text>]")
            print("\nExamples:")
            print("  recommend accept G3")
            print("  recommend accept G3 --as lunch-friday")
            print("  recommend accept G5 --desc \"high protein option\"")
            print()
            return
        
        # Parse arguments
        g_id = args[0].upper()
        custom_id = None
        description = None
        
        i = 1
        while i < len(args):
            if args[i] == "--as" and i + 1 < len(args):
                custom_id = args[i + 1]
                i += 2
            elif args[i] == "--desc" and i + 1 < len(args):
                # Join remaining args as description
                description = " ".join(args[i + 1:])
                # Remove quotes if present
                if description.startswith('"') and description.endswith('"'):
                    description = description[1:-1]
                elif description.startswith("'") and description.endswith("'"):
                    description = description[1:-1]
                break
            else:
                i += 1
        
        # Validate G-ID format
        if not g_id.startswith("G"):
            print(f"\nError: Invalid ID '{g_id}' - must be a G-ID (e.g., G3)")
            print()
            return
        
        # Get scored candidates
        gen_cands = self.ctx.workspace_mgr.get_generated_candidates()
        
        if not gen_cands:
            print("\nNo generated candidates found")
            print("Run the recommendation pipeline first")
            print()
            return
        
        all_candidates = gen_cands.get("candidates", [])
        scored_candidates = [c for c in all_candidates if c.get("score_result") is not None]
        
        if not scored_candidates:
            print("\nNo scored candidates found")
            print("Run 'recommend score' first")
            print()
            return
        
        # Find the candidate
        candidate = None
        for c in scored_candidates:
            if c.get("id", "").upper() == g_id:
                candidate = c
                break
        
        if not candidate:
            print(f"\nCandidate '{g_id}' not found in scored candidates")
            print(f"Available: {', '.join(c.get('id', '?') for c in scored_candidates)}")
            print()
            return
        
        # Determine target ID
        target_id = custom_id if custom_id else g_id
        
        # Load workspace and check for collisions
        workspace = self.ctx.workspace_mgr.load()
        
        if target_id in workspace.get("meals", {}):
            print(f"\nError: Meal ID '{target_id}' already exists in workspace")
            print("Choose a different ID with --as flag")
            print()
            return
        
        # Expand any CM. codes to constituent food items
        from meal_planner.parsers import CodeParser
        
        candidate_items = candidate.get("meal", {}).get("items", [])
        expanded_items = []
        
        for item in candidate_items:
            if 'code' not in item:
                expanded_items.append(item)
                continue
            code = item['code'].upper()
            if code.startswith('CM.'):
                # Access nested master dict directly to get combo_expansion
                code_upper = code.upper()
                if code_upper in self.ctx.master._master_dict:
                    cm_entry = self.ctx.master._master_dict[code_upper]
                    
                    if 'combo_expansion' in cm_entry:
                        # Parse the stored expansion string
                        expansion_str = cm_entry['combo_expansion']
                        component_items = CodeParser.parse(expansion_str)
                        
                        # Apply CM item's multiplier to all components
                        item_mult = item.get('mult', 1.0)
                        for comp in component_items:
                            if 'code' in comp:
                                comp['mult'] = comp.get('mult', 1.0) * item_mult
                                expanded_items.append(comp)
                    else:
                        print(f"\nWarning: CM. code '{code}' has no expansion data, keeping as-is")
                        expanded_items.append(item)
                else:
                    print(f"\nWarning: CM. code '{code}' not found in master, keeping as-is")
                    expanded_items.append(item)
            else:
                expanded_items.append(item)

        candidate_items = expanded_items

        # Prepare meal data for workspace
        meal_data = {
            "description": description if description else candidate.get("description", ""),
            "analyzed_as": candidate.get("analyzed_as"),
            "created": datetime.now().isoformat(),
            "meal_name": candidate.get("meal").get("meal_type").upper(),
            "type": "recommendation",
            "items": candidate_items,
            "totals": candidate.get("totals", {}),
            "source_date": candidate.get("source_date"),
            "source_time": candidate.get("source_time"),
            "parent_id": candidate.get("parent_id"),
            "ancestor_id": candidate.get("ancestor_id"),
            "modification_log": candidate.get("modification_log", []),
            "meets_constraints": candidate.get("meets_constraints", True),
            "immutable": True,  # Always immutable when accepted
            "history": []
        }
        
        # Add history entry
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        history_note = f"Accepted from recommend {g_id}"
        
        # Process inventory - reserve leftovers, note batch/rotating usage
        leftover_reserved = []
        batch_used = []
        rotating_used = []
        rotating_depleted_warnings = []
        
        inventory = workspace.get("inventory", {
            "leftovers": {},
            "batch": {},
            "rotating": {}
        })
        
        for item in meal_data["items"]:
            code = item.get("code", "").upper()
            mult = item.get("mult", 1.0)
            
            # Check leftovers
            if code in inventory["leftovers"]:
                leftover_item = inventory["leftovers"][code]
                leftover_item["reserved"] = True
                leftover_reserved.append(f"{code} ({mult:g}x)")
            
            # Check batch items
            if code in inventory["batch"]:
                batch_used.append(f"{code} ({mult:g}x per serving, remains available)")
            
            # Check rotating items
            if code in inventory["rotating"]:
                rotating_item = inventory["rotating"][code]
                status = rotating_item.get("status", "available")
                
                if status == "depleted":
                    rotating_depleted_warnings.append(code)
                else:
                    rotating_used.append(code)
        
        # Update history note with inventory actions
        if leftover_reserved:
            history_note += f" | Reserved leftovers: {', '.join(leftover_reserved)}"
        
        meal_data["history"].append({
            "timestamp": timestamp,
            "command": f"accept {g_id}",
            "note": history_note
        })
        
        # Add to workspace
        workspace["meals"][target_id] = meal_data
        
        # Save workspace
        self.ctx.workspace_mgr.save(workspace)
        
        # Refresh planning_workspace in context so accepted meal appears
        self.ctx.planning_workspace = self.ctx.workspace_mgr.convert_to_planning_workspace(workspace)
        
        # Report success
        meal_name = meal_data.get("meal_name", "meal")
        cal = meal_data.get("totals", {}).get("cal", 0)
        prot = meal_data.get("totals", {}).get("prot_g", 0)
        
        desc_str = f' - "{meal_data["description"]}"' if meal_data["description"] else ""
        
        print(f"\nAccepted {g_id} as meal #{target_id} ({meal_name}, {cal:.0f} cal, {prot:.0f}g prot){desc_str}")
        print("Meal marked immutable - use 'plan modify' to create mutable variant")
        print("Note: Candidates remain in workspace - use 'recommend discard' to clear when done")
        print()
        
        # Show inventory actions
        if leftover_reserved:
            print(f"Reserved leftovers ({len(leftover_reserved)}):")
            for item_desc in leftover_reserved:
                print(f"  - {item_desc}")
            print()
        
        if batch_used:
            print(f"Used batch items ({len(batch_used)}):")
            for item_desc in batch_used:
                print(f"  - {item_desc}")
            print()
        
        if rotating_used:
            print(f"Used rotating items ({len(rotating_used)}):")
            for code in rotating_used:
                print(f"  - {code} (available)")
            print()
        
        if rotating_depleted_warnings:
            print(f"WARNING: Depleted rotating items in plan ({len(rotating_depleted_warnings)}):")
            for code in rotating_depleted_warnings:
                print(f"  - {code} (currently depleted)")
            print()
        
        if not leftover_reserved and not batch_used and not rotating_used:
            print("No inventory items used in this meal")
            print()
        
        print(f"Use 'plan show {target_id}' to view details")
        print()

    def _debugdump(self, args: List[str]) -> None:
        """
        Dump candidate array to JSON for offline analysis.
        
        Usage:
            recommend debugdump <array> <filename>
        
        Args:
            args: [array_name, filename]
        
        Examples:
            recommend debugdump scored analysis.json
            recommend debugdump rejected rejected.json
        """
        if len(args) < 2:
            print("\nUsage: recommend debugdump <array> <filename>")
            print("\nArrays: raw, filtered, rejected, scored")
            print("\nExamples:")
            print("  recommend debugdump scored analysis.json")
            print("  recommend debugdump rejected rejected_analysis.json")
            print()
            return
        
        array_name = args[0].lower()
        filename = args[1]
        
        # Validate array name
        valid_arrays = ["raw", "filtered", "rejected", "scored"]
        if array_name not in valid_arrays:
            print(f"\nError: Invalid array '{array_name}'")
            print(f"Valid arrays: {', '.join(valid_arrays)}")
            print()
            return
        
        # Check for candidates
        gen_cands = self.ctx.workspace_mgr.get_generated_candidates()
        
        if not gen_cands:
            print("\nNo generated candidates to dump")
            print("Run 'recommend generate <meal_type>' first")
            print()
            return
        
        # Get array
        candidates = gen_cands.get(array_name, [])
        
        if not candidates:
            print(f"\nNo {array_name} candidates to dump")
            print()
            return
        
        meal_type = gen_cands.get("meal_type", "unknown")
        
        # Build enriched data structure
        print(f"\nBuilding debug dump for {len(candidates)} {array_name} candidates...")
        
        from meal_planner.reports import ReportBuilder
        
        enriched_data = []
        
        for i, candidate in enumerate(candidates, 1):
            # Basic info
            enriched_candidate = {
                "id": candidate.get("id", f"?{i}"),
                "position": i,
                "source": {
                    "date": candidate.get("source_date", "unknown"),
                    "time": candidate.get("source_time", ""),
                    "meal_type": meal_type
                }
            }
            
            # Enrich items with descriptions
            items = candidate.get("meal", {}).get("items", [])
            enriched_items = []
            
            for item in items:
                if "code" in item:
                    code = item["code"]
                    mult = item.get("mult", 1.0)
                    
                    # Get description from master
                    desc = ""
                    try:
                        food_data = self.ctx.master.lookup_code(code)
                        if food_data:
                            desc = food_data.get('option', '')
                    except:
                        pass
                    
                    enriched_items.append({
                        "code": code,
                        "mult": mult,
                        "description": desc
                    })
            
            enriched_candidate["items"] = enriched_items
            
            # Calculate macros and micros using ReportBuilder
            builder = ReportBuilder(self.ctx.master)
            report = builder.build_from_items(items, title="")
            
            totals = report.totals
            
            # Macros
            enriched_candidate["macros"] = {
                "calories": round(totals.calories, 1),
                "protein_g": round(totals.protein_g, 1),
                "carbs_g": round(totals.carbs_g, 1),
                "fat_g": round(totals.fat_g, 1),
                "fiber_g": round(totals.fiber_g, 1),
                "sugar_g": round(totals.sugar_g, 1),
                "glycemic_load": round(totals.glycemic_load, 1)
            }
            
            # Micros
            enriched_candidate["micros"] = {
                "sodium_mg": round(totals.sodium_mg, 1),
                "potassium_mg": round(totals.potassium_mg, 1),
                "vitA_mcg": round(totals.vitA_mcg, 1),
                "vitC_mg": round(totals.vitC_mg, 1),
                "iron_mg": round(totals.iron_mg, 1)
            }
            
            # Array-specific metadata
            metadata = {}
            
            if array_name == "scored":
                metadata["score"] = candidate.get("aggregate_score", 0.0)
                metadata["rank"] = i
                
                # Scoring breakdown
                scores = candidate.get("scores", {})
                if scores:
                    breakdown = {}
                    for scorer_name, scorer_data in scores.items():
                        breakdown[scorer_name] = {
                            "raw": scorer_data.get("raw", 0.0),
                            "weighted": scorer_data.get("weighted", 0.0)
                        }
                    metadata["scoring_breakdown"] = breakdown
            
            elif array_name == "rejected":
                reasons = candidate.get("rejection_reasons", [])
                metadata["rejection_reasons"] = reasons
            
            elif array_name == "filtered":
                # Any filter warnings
                warnings = candidate.get("leftover_under_use", [])
                if warnings:
                    metadata["warnings"] = warnings
            
            elif array_name == "raw":
                # Generation method
                gen_method = candidate.get("generation_method", "unknown")
                metadata["generation_method"] = gen_method
                
                template_info = candidate.get("template_info", {})
                if template_info:
                    metadata["template"] = template_info.get("template_name", "")
            
            if metadata:
                enriched_candidate["metadata"] = metadata
            
            enriched_data.append(enriched_candidate)
        
        # Write to file
        import json
        
        try:
            with open(filename, 'w') as f:
                json.dump(enriched_data, f, indent=2)
            
            print(f"\nDumped {len(enriched_data)} {array_name} candidates to {filename}")
            import os
            print(f"File size: {os.path.getsize(filename)} bytes")
            print()
            
        except Exception as e:
            print(f"\nError writing file: {e}")
            print()

    def _generate_from_history(self, meal_key: str, count: int, 
                          workspace: Dict[str, Any], reco_workspace: Dict[str, Any],
                          template_name: Optional[str] = None) -> None:
        """
        Generate candidates from meal history (original method).
        
        Args:
            meal_key: Normalized meal type key
            count: Number of candidates to generate
            workspace: Workspace dict
        """
        # Determine which template to use for filtering
        if not template_name:
            template_name = self._select_default_template(meal_key)
            if not template_name:
                print(f"Multiple templates found for {meal_key}, please specify:")
                print("  recommend generate {meal_key} --method history --template <name>")
                return
    
        print(f"\nGenerating {count} candidates from history for {meal_key.upper()}...")
        
        from meal_planner.generators import HistoryMealGenerator
        generator = HistoryMealGenerator(self.ctx.master, self.ctx.log)
        
        candidates = generator.generate_candidates(
            meal_type=meal_key,
            max_candidates=count,
            lookback_days=60
        )
        
        if not candidates:
            print(f"\nNo {meal_key} meals found in history")
            print("Try:")
            print("  - Different meal type")
            print("  - Increasing lookback days (future feature)")
            print()
            return

        for candidate in candidates:
            items = candidate.get("items", [])
            candidate["totals"] = self._calculate_candidate_totals(items)
        
        self.ctx.workspace_mgr.set_generated_candidates(
            meal_type=meal_key,
            raw_candidates=candidates,
            cursor=0,
            append=False
        )
        
        # Load reco workspace
        reco_workspace = self.ctx.workspace_mgr.load_reco()
        
        # Set candidates (history generation replaces, not appends)
        if "generated_candidates" not in reco_workspace:
            reco_workspace["generated_candidates"] = {}
        
        # Update generation state
        reco_workspace["generation_state"] = {
            "method": "history",
            "meal_type": meal_key,
            "template_name": template_name,
            "cursor": len(candidates)
        }
        
        # Save once
        self.ctx.workspace_mgr.save_reco(reco_workspace)

        # Display results
        print(f"\nGenerated {len(candidates)} raw candidates for {meal_key}")
        print()

    def _generate_exhaustive(self, meal_key: str, count: int, 
                        workspace: Dict[str, Any], reco_workspace: Dict[str, Any],
                        template_name: Optional[str]) -> None:
        """
        Generate candidates exhaustively from component pools.
        
        Args:
            meal_key: Normalized meal type key
            count: Number of candidates to generate
            workspace: Workspace dict
            template_name: Specific template to use (None = use first available)
        """
        # Load or initialize generation state
        gen_state = reco_workspace.get("generation_state", {})
        cursor = gen_state.get("cursor", 0)
        
        print(f"\n=== EXHAUSTIVE GENERATION: {meal_key.upper()} ===")
        print(f"Generating {count} candidates starting from position {cursor}")
        if template_name:
            print(f"Using template: {template_name}")
        print()
        
        from meal_planner.generators import ExhaustiveMealGenerator
        generator = ExhaustiveMealGenerator(self.ctx.master, self.ctx.thresholds)
        
        candidates, new_cursor = generator.generate_batch(
            meal_type=meal_key,
            count=count,
            cursor=cursor,
            template_name=template_name
        )

        if not candidates:
            print("No more combinations available")
            print()
            return
        
        for candidate in candidates:
            items = candidate.get("items", [])
            candidate["totals"] = self._calculate_candidate_totals(items)

        self.ctx.workspace_mgr.set_generated_candidates(
            meal_type=meal_key,
            raw_candidates=candidates,
            cursor=cursor,
            append=(cursor > 0)
        )

        reco_workspace = self.ctx.workspace_mgr.load_reco()

        reco_workspace["generation_state"] = {
            "method": "exhaustive",
            "meal_type": meal_key,
            "cursor": new_cursor,
            "template_name": template_name
        }

        # Save reco workspace once with everything
        self.ctx.workspace_mgr.save_reco(reco_workspace)

        # Display results
        print(f"Generated {len(candidates)} candidates (positions {cursor}-{new_cursor-1})")
        print(f"Total raw candidates in workspace: {new_cursor}")
        print()

    def _reset(self, args: List[str]) -> None:
        """
        Reset the recommendation generation session.
        
        Clears both generation_state and generated_candidates, allowing
        fresh generation with any method/meal combination.
        
        Usage:
            recommend reset           # Reset with confirmation
            recommend reset --force   # Skip confirmation
        
        Args:
            args: Optional [--force] flag
        """
        # Check for force flag
        force = "--force" in args or "-f" in args
        
        # Load reco workspace
        reco_workspace = self.ctx.workspace_mgr.load_reco()

        # Check for existing generation session
        gen_state = reco_workspace.get("generation_state", {})
        gen_cands = reco_workspace.get("generated_candidates", {})
                
        # Check if there's anything to reset
        has_state = bool(gen_state)
        has_raw = len(gen_cands.get("raw", [])) > 0
        has_filtered = len(gen_cands.get("filtered", [])) > 0
        has_scored = len(gen_cands.get("scored", [])) > 0
        has_rejected = len(gen_cands.get("rejected", [])) > 0
        
        if not (has_state or has_raw or has_filtered or has_scored or has_rejected):
            print("\nNo active generation session to reset")
            print()
            return
        
        # Show what will be reset
        print("\n=== RESET GENERATION SESSION ===")
        
        if has_state:
            existing_method = gen_state.get("method", "unknown")
            existing_meal = gen_state.get("meal_type", "unknown")
            existing_cursor = gen_state.get("cursor")
            
            print(f"\nGeneration State:")
            print(f"  Method: {existing_method}")
            print(f"  Meal: {existing_meal}")
            if existing_cursor is not None:
                print(f"  Cursor: {existing_cursor}")
        
        if has_raw or has_filtered or has_scored or has_rejected:
            print(f"\nGenerated Candidates:")
            if has_raw:
                print(f"  Raw: {len(gen_cands.get('raw', []))} candidates")
            if has_filtered:
                print(f"  Filtered: {len(gen_cands.get('filtered', []))} candidates")
            if has_scored:
                print(f"  Scored: {len(gen_cands.get('scored', []))} candidates")
            if has_rejected:
                print(f"  Rejected: {len(gen_cands.get('rejected', []))} candidates")
        
        print()
        
        # Confirmation unless --force
        if not force:
            print("This will PERMANENTLY clear the generation session")
            response = input("Type 'yes' to confirm: ").strip().lower()
            
            if response != "yes":
                print("\nReset cancelled")
                print()
                return
        
        # Perform reset
        reco_workspace["generation_state"] = {}
        reco_workspace["generated_candidates"] = {
            "raw": [],
            "filtered": [],
            "rejected": [],
            "scored": []
        }

        self.ctx.workspace_mgr.save_reco(reco_workspace)
        
        print("\n✓ Generation session reset")
        print("Ready for new generation with any method/meal combination")
        print()
    
    def _select_default_template(self, meal_key: str) -> Optional[str]:
        """
        Select default template for meal type.
        
        Returns:
            Template name if exactly one exists, None if multiple or none
        """
        meal_gen = self.ctx.thresholds.get_meal_generation()
        if not meal_gen:
            return None
        
        templates = meal_gen.get(meal_key, {})
        
        if len(templates) == 0:
            print(f"No generation templates defined for {meal_key}")
            return None
        elif len(templates) == 1:
            # Use the only template
            return list(templates.keys())[0]
        else:
            # Multiple templates - require explicit selection
            return None

    def _get_candidates_by_state(
        self,
        gen_cands: Dict[str, Any],
        state: str
    ) -> List[Dict[str, Any]]:
        """
        Get candidates filtered by state.
        
        Args:
            gen_cands: Generated candidates dict
            state: One of "raw", "filtered", "rejected", "scored"
        
        Returns:
            List of candidates in that state
        """
        all_candidates = gen_cands.get("candidates", [])
        
        if state == "raw":
            return [c for c in all_candidates if c.get("filter_result") is None]
        elif state == "filtered":
            return [c for c in all_candidates 
                if c.get("filter_result") is  not None 
                and c.get("filter_result", {}).get("passed") == True]
        elif state == "rejected":
            return [c for c in all_candidates 
                if c.get("filter_result") is  not None 
                and c.get("filter_result", {}).get("passed") == False]
        elif state == "scored":
            scored = [c for c in all_candidates if c.get("score_result") is not None]
            return sorted(scored, key=lambda x: x.get("score_result", {}).get("aggregate_score", 0), reverse=True)
        else:
            return []
        
    def _determine_candidate_state(self, candidate: Dict[str, Any]) -> str:
        """
        Determine the state of a candidate for display purposes.
        
        Args:
            candidate: Candidate dict
        
        Returns:
            State name: "scored", "filtered", "rejected", or "raw"
        """
        if candidate.get("score_result") is not None:
            return "scored"
        elif candidate.get("filter_result") is not None and candidate.get("filter_result", {}).get("passed") == True:
            return "filtered"
        elif candidate.get("filter_result") is not None:
            return "rejected"
        else:
            return "raw"
            
    def _calculate_candidate_totals(self, items: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Calculate nutritional totals from items list.
        
        Optimized lightweight version - just arithmetic, no formatting.
        Used during candidate generation to pre-populate totals.
        Calculates both macros and micros.
        
        Args:
            items: List of item dicts with code and mult
        
        Returns:
            Dict with macro keys (cal, prot_g, carbs_g, fat_g, sugar_g, gl) 
            and micro keys (fiber_g, sodium_mg, potassium_mg, vitA_mcg, vitC_mg, iron_mg)
        """
        totals = {
            'cal': 0.0,
            'prot_g': 0.0,
            'carbs_g': 0.0,
            'fat_g': 0.0,
            'sugar_g': 0.0,
            'gl': 0.0,
            'fiber_g': 0.0,
            'sodium_mg': 0.0,
            'potassium_mg': 0.0,
            'vitA_mcg': 0.0,
            'vitC_mg': 0.0,
            'iron_mg': 0.0
        }

        if not items:
            return totals
        
        for item in items:
            code = str(item["code"]).upper()
            mult = float(item.get("mult", 1.0))
            
            # Lookup food in master for macros
            food = self.ctx.master.lookup_code(code)
            
            if food is not None:
                # Direct accumulation - just multiply and add (MACROS)
                totals['cal'] += food.get('cal', 0) * mult
                totals['prot_g'] += food.get('prot_g', 0) * mult
                totals['carbs_g'] += food.get('carbs_g', 0) * mult
                totals['fat_g'] += food.get('fat_g', 0) * mult
                totals['sugar_g'] += food.get('sugar_g', 0) * mult
                totals['gl'] += food.get('GL', 0) * mult
            
            # Get nutrients for micros
            nutrients = self.ctx.master.get_nutrients(code)
            
            if nutrients is not None:
                # Direct accumulation - just multiply and add (MICROS)
                totals['fiber_g'] += nutrients.get('fiber_g', 0) * mult
                totals['sodium_mg'] += nutrients.get('sodium_mg', 0) * mult
                totals['potassium_mg'] += nutrients.get('potassium_mg', 0) * mult
                totals['vitA_mcg'] += nutrients.get('vitA_mcg', 0) * mult
                totals['vitC_mg'] += nutrients.get('vitC_mg', 0) * mult
                totals['iron_mg'] += nutrients.get('iron_mg', 0) * mult
        
        return totals
    
    def _status(self, args: List[str]) -> None:
        """
        Show recommendation pipeline status.
        
        Displays counts of candidates in each stage:
        - Raw (generated but unfiltered)
        - Filtered (passed filtering)
        - Rejected (failed filtering)
        - Scored (filtered and scored)
        
        Usage:
            recommend status
            recommend status --verbose    # Show additional details
        
        Args:
            args: Optional flags (--verbose)
        """
        verbose = "--verbose" in args or "-v" in args
        
        # Check for generated candidates
        gen_cands = self.ctx.workspace_mgr.get_generated_candidates()
        
        if not gen_cands:
            print("\n=== RECOMMENDATION PIPELINE STATUS ===")
            print("\nNo active recommendation session")
            print()
            print("Start with: recommend generate <meal_type>")
            print()
            return
        
        all_candidates = gen_cands.get("candidates", [])
        meal_type = gen_cands.get("meal_type", "unknown")
        
        # Load generation state
        reco_workspace = self.ctx.workspace_mgr.load_reco()
        gen_state = reco_workspace.get("generation_state", {})
        method = gen_state.get("method", "unknown")
        template_name = gen_state.get("template_name", "none")
        
        # Count candidates by state
        raw_count = sum(1 for c in all_candidates if c.get("filter_result") is None)
        
        filtered_count = sum(1 for c in all_candidates 
                            if c.get("filter_result") is not None 
                            and c.get("filter_result").get("passed") == True)
        
        rejected_count = sum(1 for c in all_candidates 
                            if c.get("filter_result") is not None
                            and c.get("filter_result").get("passed") == False)
        
        scored_count = sum(1 for c in all_candidates 
                        if c.get("score_result") is not None)
        
        total_count = len(all_candidates)
        
        # Display header
        print(f"\n=== RECOMMENDATION PIPELINE STATUS ===")
        print()
        print(f"Meal Type:    {meal_type.upper()}")
        print(f"Method:       {method}")
        print(f"Template:     {template_name}")
        print()
        
        # Display counts
        print("Pipeline Stage                Count    %")
        print("-" * 45)
        
        # Raw (unfiltered)
        raw_pct = (raw_count / total_count * 100) if total_count > 0 else 0
        print(f"Raw (unfiltered)           {raw_count:>8}  {raw_pct:>5.1f}%")
        
        # Filtered (passed)
        filtered_pct = (filtered_count / total_count * 100) if total_count > 0 else 0
        status_filtered = "→" if raw_count == 0 else " "
        print(f"{status_filtered} Filtered (passed)        {filtered_count:>8}  {filtered_pct:>5.1f}%")
        
        # Rejected
        rejected_pct = (rejected_count / total_count * 100) if total_count > 0 else 0
        status_rejected = "→" if raw_count == 0 else " "
        print(f"{status_rejected} Rejected (failed)        {rejected_count:>8}  {rejected_pct:>5.1f}%")
        
        # Scored
        scored_pct = (scored_count / total_count * 100) if total_count > 0 else 0
        status_scored = "→" if filtered_count > 0 and scored_count > 0 else " "
        print(f"{status_scored} Scored (ranked)          {scored_count:>8}  {scored_pct:>5.1f}%")
        
        print("-" * 45)
        print(f"Total                     {total_count:>8}  100.0%")
        print()
        
        # Show next step suggestion
        if raw_count > 0:
            print(f"Next: recommend filter              # Process {raw_count} unfiltered candidates")
        elif filtered_count > 0 and scored_count == 0:
            print(f"Next: recommend score               # Score {filtered_count} filtered candidates")
        elif scored_count > 0:
            print(f"Next: recommend show scored         # View top recommendations")
            print(f"      recommend accept <G-ID>       # Accept a candidate")
        elif rejected_count > 0 and filtered_count == 0:
            print("All candidates were rejected - consider:")
            print("  - Adjusting constraints in template")
            print("  - Using different locks")
            print("  - Generating more candidates")
        
        print()
        
        # Verbose mode: Show rejection reason breakdown
        if verbose and rejected_count > 0:
            print("=== REJECTION BREAKDOWN ===")
            print()
            
            # Count rejection reasons
            reason_counts = {}
            for candidate in all_candidates:
                filter_result = candidate.get("filter_result")
                if filter_result and not filter_result.get("passed"):
                    violations = filter_result.get("violations", [])
                    for violation in violations:
                        # Extract reason type (e.g., "nutrient:protein<40" -> "nutrient")
                        reason_type = violation.split(":")[0] if ":" in violation else violation
                        reason_counts[reason_type] = reason_counts.get(reason_type, 0) + 1
            
            if reason_counts:
                print("Rejection Reasons:")
                for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
                    print(f"  {reason:<25} {count:>5} candidates")
            
            print()

    def _get_meal_filters(self, meal_type: str) -> Dict[str, Any]:
        """
        Get meal_filters section for specific meal type from config.
        
        Args:
            meal_type: Meal category (breakfast, lunch, dinner, etc.)
        
        Returns:
            Dict with 'mutual_exclusions' and 'conditional_requirements' lists,
            or empty dict with empty lists if not configured
        """
        if not self.ctx.thresholds or not self.ctx.thresholds.is_valid:
            return {"mutual_exclusions": [], "conditional_requirements": []}
        
        meal_filters = self.ctx.thresholds.thresholds.get("meal_filters", {})
        meal_type_filters = meal_filters.get(meal_type, {})
        
        return {
            "mutual_exclusions": meal_type_filters.get("mutual_exclusions", []),
            "conditional_requirements": meal_type_filters.get("conditional_requirements", [])
        }
    
    def _parse_range(self, token: str) -> Union[int, range, List[int], str]:
        """
        Parse range syntax from a token.
        
        Args:
            token: Token to parse (could be: 5, 1-5, 1,3,7, or "all")
        
        Returns:
            - int: Single position
            - range: Range object for hyphenated ranges
            - List[int]: List of specific positions
            - str: "all" literal
        
        Raises:
            ValueError: If token cannot be parsed as range
        """
        # Check for "all"
        if token.lower() == "all":
            return "all"
        
        # Check for comma-separated list (1,3,7)
        if "," in token:
            try:
                positions = [int(p.strip()) for p in token.split(",")]
                if any(p <= 0 for p in positions):
                    raise ValueError("Positions must be positive")
                return positions
            except ValueError as e:
                raise ValueError(f"Invalid position list: {token}") from e
        
        # Check for hyphenated range (1-5)
        if "-" in token:
            try:
                parts = token.split("-")
                if len(parts) != 2:
                    raise ValueError("Range must be format 'start-end'")
                start = int(parts[0].strip())
                end = int(parts[1].strip())
                if start <= 0 or end <= 0:
                    raise ValueError("Range positions must be positive")
                if start > end:
                    raise ValueError("Range start must be <= end")
                return range(start, end + 1)  # +1 because range is exclusive
            except ValueError as e:
                raise ValueError(f"Invalid range: {token}") from e
        
        # Try single integer
        try:
            pos = int(token)
            if pos <= 0:
                raise ValueError("Position must be positive")
            return pos
        except ValueError as e:
            raise ValueError(f"Invalid position: {token}") from e


    def _get_view_names(self) -> List[str]:
        """
        Get list of available view names from reco workspace.
        
        Returns:
            List of view names
        """
        reco_workspace = self.ctx.workspace_mgr.load_reco()
        views = reco_workspace.get("views", {})
        return list(views.keys())


    def _get_view(self, view_name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific view from reco workspace.
        
        Args:
            view_name: Name of the view
        
        Returns:
            View dict or None if not found
        """
        reco_workspace = self.ctx.workspace_mgr.load_reco()
        views = reco_workspace.get("views", {})
        return views.get(view_name)


    def _get_candidates_for_view(self, view_name: str) -> List[Dict[str, Any]]:
        """
        Get candidates for a specific view, preserving view's sort order.
        
        Args:
            view_name: Name of the view
        
        Returns:
            List of candidate dicts in view's order
        """
        # Get view
        view = self._get_view(view_name)
        if not view:
            return []
        
        # Get candidate IDs from view
        candidate_ids = view.get("candidate_ids", [])
        if not candidate_ids:
            return []
        
        # Get all candidates
        gen_cands = self.ctx.workspace_mgr.get_generated_candidates()
        if not gen_cands:
            return []
        
        all_candidates = gen_cands.get("candidates", [])
        
        # Build ID to candidate map
        id_to_candidate = {c.get("id"): c for c in all_candidates}
        
        # Get candidates in view's order
        result = []
        for cid in candidate_ids:
            if cid in id_to_candidate:
                result.append(id_to_candidate[cid])
        
        return result


    def _format_items_line(self, candidate: Dict[str, Any]) -> str:
        """
        Format items from a candidate in compact food code format.
        
        Format: "code1 xMULT1,code2,code3 xMULT3"
        Only show multiplier if != 1.0
        
        Args:
            candidate: Candidate dict
        
        Returns:
            Formatted items string
        """
        meal = candidate.get("meal", {})
        items = meal.get("items", [])
        
        # Extract codes and multipliers, sort alphabetically
        code_mult_pairs = []
        for item in items:
            if "code" in item:
                code = item["code"]
                mult = item.get("multiplier", 1.0)
                code_mult_pairs.append((code, mult))
        
        # Sort by code
        code_mult_pairs.sort(key=lambda x: x[0].lower())
        
        # Format with multipliers
        formatted = []
        for code, mult in code_mult_pairs:
            if mult == 1.0:
                formatted.append(code)
            else:
                formatted.append(f"{code} x{mult}")
        
        return ",".join(formatted)


    def _format_gaps_line(self, candidate: Dict[str, Any]) -> str:
        """
        Format nutrient gaps (deficiencies) from filter violations.
        
        Parses filter_result violations to extract gaps (< constraints).
        Format: "fiber<10,vitC<20"
        
        Args:
            candidate: Candidate dict
        
        Returns:
            Formatted gaps string, or empty if no gaps
        """
        filter_result = candidate.get("filter_result", {})
        violations = filter_result.get("violations", [])
        
        gaps = []
        for violation in violations:
            # Skip non-nutrient violations
            if not violation.startswith("nutrient:"):
                continue
            
            # Strip "nutrient:" prefix
            constraint = violation[9:]  # Remove "nutrient:"
            
            # Strip suffix like "(soft_limit)"
            if "(" in constraint:
                constraint = constraint[:constraint.index("(")]
            
            # Check if it's a gap (< constraint)
            if "<" in constraint:
                gaps.append(constraint)
        
        return ",".join(gaps) if gaps else ""


    def _format_excesses_line(self, candidate: Dict[str, Any]) -> str:
        """
        Format nutrient excesses from filter violations.
        
        Parses filter_result violations to extract excesses (> constraints).
        Format: "fat>30.0,sodium>2000"
        
        Args:
            candidate: Candidate dict
        
        Returns:
            Formatted excesses string, or empty if no excesses
        """
        filter_result = candidate.get("filter_result", {})
        violations = filter_result.get("violations", [])
        
        excesses = []
        for violation in violations:
            # Skip non-nutrient violations
            if not violation.startswith("nutrient:"):
                continue
            
            # Strip "nutrient:" prefix
            constraint = violation[9:]  # Remove "nutrient:"
            
            # Strip suffix like "(soft_limit)"
            if "(" in constraint:
                constraint = constraint[:constraint.index("(")]
            
            # Check if it's an excess (> constraint)
            if ">" in constraint:
                excesses.append(constraint)
        
        return ",".join(excesses) if excesses else ""

    def _format_nutrients_lines(self, candidate: Dict[str, Any]) -> tuple[str, str]:
        """
        Format nutrient lines (macros and micros) from a candidate.
        
        Reads from candidate["meal"]["totals"] dictionary.
        Returns two lines showing actual consumed amounts:
        - Macros: "Cal 520 | Pro 45g | Carb 58g | Fat 12g | Sugar 5g | GL 2"
        - Micros: "Fiber 18g | Sodium 890mg | Potas 1200mg | VitA 450mcg | VitC 38mg | Iron 4.2mg"
        
        Args:
            candidate: Candidate dict
        
        Returns:
            Tuple of (macros_line, micros_line)
        """
        meal = candidate.get("meal", {})
        totals = meal.get("totals", {})
        
        if not totals:
            return ("Cal 0 | Pro 0g | Carb 0g | Fat 0g | Sugar 0g | GL 0", 
                    "Fiber 0g | Sodium 0mg | Potas 0mg | VitA 0mcg | VitC 0mg | Iron 0.0mg")
        
        # Macros
        cal = totals.get("cal", 0)
        pro = totals.get("prot_g", 0)
        carb = totals.get("carbs_g", 0)
        fat = totals.get("fat_g", 0)
        sugar = totals.get("sugar_g", 0)
        gl = totals.get("gl", 0)
        
        macros = f"Cal {cal:.0f} | Pro {pro:.0f}g | Carb {carb:.0f}g | Fat {fat:.0f}g | Sugar {sugar:.0f}g | GL {gl:.1f}"
        
        # Micros
        fiber = totals.get("fiber_g", 0)
        sodium = totals.get("sodium_mg", 0)
        potas = totals.get("potassium_mg", 0)
        vitA = totals.get("vitA_mcg", 0)
        vitC = totals.get("vitC_mg", 0)
        iron = totals.get("iron_mg", 0)
        
        micros = f"Fiber {fiber:.0f}g | Sodium {sodium:.0f}mg | Potas {potas:.0f}mg | VitA {vitA:.0f}mcg | VitC {vitC:.0f}mg | Iron {iron:.1f}mg"
        
        return macros, micros

    def _display_candidate_compact(
        self,
        candidate: Dict[str, Any],
        position: int,
        flags: Dict[str, bool]
    ) -> None:
        """
        Display a candidate in compact one-line format based on flags.
        
        Single flag: One line with ID, score, and flag data
        Multiple flags: Multiple lines stacked
        
        Args:
            candidate: Candidate dict
            position: Position in list (for display)
            flags: Dict of flag names to bool (items, gaps, excesses, nutrients)
        """
        candidate_id = candidate.get("id", "???")
        
        # Get score if available
        score_result = candidate.get("score_result")
        if score_result:
            score = score_result.get("aggregate_score", 0.0)
            score_str = f"{score:.3f}"
        else:
            score_str = "N/A"
        
        # Count active flags
        active_flags = [k for k, v in flags.items() if v]
        
        if len(active_flags) == 0:
            # No flags - shouldn't happen, but handle gracefully
            print(f"{candidate_id}: {score_str}")
            return
        
        if len(active_flags) == 1:
            # Single flag - one line format
            flag = active_flags[0]
            
            if flag == "items":
                items_str = self._format_items_line(candidate)
                print(f"{candidate_id}: {score_str}, Items: {items_str}")
            
            elif flag == "gaps":
                gaps_str = self._format_gaps_line(candidate)
                if gaps_str:
                    print(f"{candidate_id}: {score_str}, Gaps: {gaps_str}")
                else:
                    print(f"{candidate_id}: {score_str}, Gaps: (none)")
            
            elif flag == "excesses":
                excesses_str = self._format_excesses_line(candidate)
                if excesses_str:
                    print(f"{candidate_id}: {score_str}, Excesses: {excesses_str}")
                else:
                    print(f"{candidate_id}: {score_str}, Excesses: (none)")
            
            elif flag == "nutrients":
                # Nutrients needs two lines
                macros, micros = self._format_nutrients_lines(candidate)
                print(f"{candidate_id}: {score_str}")
                print(f"  Macros: {macros}")
                print(f"  Micros: {micros}")
        
        else:
            # Multiple flags - stack them
            print(f"{candidate_id}: {score_str}")
            
            if flags.get("items"):
                items_str = self._format_items_line(candidate)
                print(f"  Items: {items_str}")
            
            if flags.get("gaps"):
                gaps_str = self._format_gaps_line(candidate)
                if gaps_str:
                    print(f"  Gaps: {gaps_str}")
                else:
                    print(f"  Gaps: (none)")
            
            if flags.get("excesses"):
                excesses_str = self._format_excesses_line(candidate)
                if excesses_str:
                    print(f"  Excesses: {excesses_str}")
                else:
                    print(f"  Excesses: (none)")
            
            if flags.get("nutrients"):
                macros, micros = self._format_nutrients_lines(candidate)
                print(f"  Macros: {macros}")
                print(f"  Micros: {micros}")



    # NOTE: Phase 2 will add field name mapping
    # This is a placeholder for the nutrient field name discussion
    FIELD_NAME_MAPPING = {
        # To be established in Phase 2
        # "fiber": "meal.totals.Fiber (g)",
        # "sodium": "meal.totals.Sodium (mg)",
        # etc.
    }