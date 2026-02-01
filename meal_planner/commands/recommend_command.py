# meal_planner/commands/recommend_command.py
"""
Recommend command for meal optimization suggestions.

Analyzes meal gaps/excesses and suggests additions, portions, or swaps.
"""
import shlex
from typing import List, Dict, Any, Optional, Tuple
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
        print("  recommend reset [--force]")
        print("  recommend show [rejected] [[id]|--limit N [--skip N]]")
        print("  recommend filter [--verbose]")
        print("  recommend score [--verbose]")
        print("  recommend accept <G-ID> [--as <id>] [--desc <text>]")
        print("  recommend discard [array]")
        print("    <array> := [raw|filtered|scored]")
        print("Pipeline flow:")
        print("  1. recommend generate lunch      # Generate raw candidates")
        print("  2. recommend show                # Preview candidates")
        print("  3. recommend filter              # Apply pre-score filters")
        print("  4. recommend show                # View filtered candidates")
        print("  5. recommend score               # Score filtered candidates")
        print("  6. recommend accept G3           # Accept a recommendation")
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
        Score all filtered candidates (batch operation).
        
        Replaces the old debug scoring command. Now scores all filtered
        candidates, ranks them, and saves results to workspace.
        
        Usage:
            recommend score           # Score all filtered candidates
            recommend score --verbose # Show detailed scoring info
        
        Args:
            args: Optional [--verbose] flag
        """
        # Check for verbose flag
        verbose = "--verbose" in args or "-v" in args
        
        # Check dependencies
        if not self.ctx.scorers:
            print("\nScorer system not initialized")
            print("Check meal_plan_config.json and user preferences")
            print()
            return
        
        # Check for filtered candidates
        gen_cands = self.ctx.workspace_mgr.get_generated_candidates()
        
        if not gen_cands:
            print("\nNo generated candidates to score")
            print("Run 'recommend generate <meal_type>' first")
            print()
            return
        
        filtered_candidates = gen_cands.get("filtered", [])
        meal_type = gen_cands.get("meal_type", "unknown")
        
        if not filtered_candidates:
            print("\nNo filtered candidates to score")
            print("Run 'recommend filter' first")
            print()
            return
        
        # Check if already scored (prevent accidental re-scoring)
        scored_candidates = gen_cands.get("scored", [])
        if scored_candidates:
            print("\nCandidates already scored")
            print(f"Found {len(scored_candidates)} scored candidates")
            print()
            print("To re-score, first discard scored candidates:")
            print("  recommend discard scored")
            print()
            return
        
        # Get template for this meal type
        template_path = self._get_template_for_meal(meal_type)
        
        print(f"\n=== SCORING {len(filtered_candidates)} {meal_type.upper()} CANDIDATES ===\n")
        
        if template_path:
            print(f"Using template: {template_path}")
        else:
            print(f"Warning: No template for '{meal_type}' - using best guess")
        print()
        
        # Score each candidate
        scored_results = []
        failed_candidates = []
        
        for i, candidate in enumerate(filtered_candidates, 1):
            candidate_id = candidate.get("id", "???")
            
            if verbose:
                print(f"Scoring {candidate_id}... ({i}/{len(filtered_candidates)})")
            
            try:
                scored_candidate = self._score_candidate(
                    candidate,
                    meal_type,
                    template_path
                )
                scored_results.append(scored_candidate)
            except Exception as e:
                failed_candidates.append((candidate_id, str(e)))
                if verbose:
                    print(f"  ERROR: {e}")
        
        # Sort by aggregate score (descending - best first)
        scored_results.sort(key=lambda x: x["aggregate_score"], reverse=True)
        
        # Save to workspace
        self.ctx.workspace_mgr.update_scored_candidates(scored_results)
        
        # Display results
        success_count = len(scored_results)
        print(f"\nScored {success_count}/{len(filtered_candidates)} candidates successfully")
        
        if failed_candidates:
            print(f"\nFailed to score {len(failed_candidates)} candidates:")
            for cand_id, error in failed_candidates:
                print(f"  {cand_id}: {error}")
        
        print()
        
        # Show top candidates
        self._display_scored_summary(scored_results, meal_type, verbose)
        
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
        
        Args:
            candidate: Candidate dict with items, id, etc.
            meal_type: Meal category (breakfast, lunch, etc.)
            template_path: Template path for analysis
        
        Returns:
            Scored candidate dict with scores and aggregate_score
        """        
        candidate_id = candidate.get("id")
        items = candidate.get("items", [])
        
        # Calculate nutritional totals
        report_builder = ReportBuilder(self.ctx.master)
        report = report_builder.build_from_items(items, title="Scoring")
        totals = report.totals  # Get the DailyTotals object from the report
        
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
        
        # Build totals dict
        totals_dict = {
            'cal': getattr(totals, 'calories', 0),
            'prot_g': getattr(totals, 'protein_g', 0),
            'carbs_g': getattr(totals, 'carbs_g', 0),
            'fat_g': getattr(totals, 'fat_g', 0),
            'fiber_g': getattr(totals, 'fiber_g', 0),
            'sugar_g': getattr(totals, 'sugar_g', 0),
            'gl': getattr(totals, 'glycemic_load', 0)
        }
        
        # Build scoring context
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
        
        # Build scored candidate
        scored_candidate = {
            **candidate,  # Include all original data
            "totals": totals_dict,
            "analysis": {
                "gaps": [
                    {
                        "nutrient": g.nutrient,
                        "current": g.current,
                        "target_min": g.target_min,
                        "target_max": g.target_max,
                        "deficit": g.deficit,
                        "priority": g.priority
                    }
                    for g in analysis_result.gaps
                ],
                "excesses": [
                    {
                        "nutrient": e.nutrient,
                        "current": e.current,
                        "threshold": e.threshold,
                        "overage": e.overage,
                        "priority": e.priority
                    }
                    for e in analysis_result.excesses
                ]
            },
            "scores": scorer_results,
            "aggregate_score": aggregate_score,
            "scored_at": datetime.now().isoformat()
        }
        
        return scored_candidate
    
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
            score = candidate.get("aggregate_score", 0.0)
            description = candidate.get("description", "No description")
            
            # Truncate long descriptions
            if len(description) > 47:
                description = description[:44] + "..."
            
            print(f"{rank:<6}{candidate_id:<8}{score:<8.3f}{description}")
            
            # Verbose: show gap/excess summary
            if verbose:
                analysis = candidate.get("analysis", {})
                gaps = analysis.get("gaps", [])
                excesses = analysis.get("excesses", [])
                
                if gaps:
                    gap_strs = [f"{g['nutrient']}(-{g['deficit']:.1f})" for g in gaps[:3]]
                    print(f"{'':>14}Gaps: {', '.join(gap_strs)}")
                if excesses:
                    excess_strs = [f"{e['nutrient']}(+{e['overage']:.1f})" for e in excesses[:3]]
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
        
        # Check for existing generation session
        gen_state = workspace.get("generation_state", {})
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
            self._generate_from_history(meal_key, count, workspace)
        else:  # exhaustive
            self._generate_exhaustive(meal_key, count, workspace, template_name)
    
    def _filter(self, args: List[str]) -> None:
        """
        Apply pre-score filters to raw generated candidates.
        
        Filters applied in order:
        1. Nutrient constraints (hard/soft limits from generation template)
        2. Lock constraints (include/exclude)
        3. Availability constraints (exclude_from_recommendations)
        4. Reserved items (inventory)
        5. Depleted rotating items
        6. Leftover portion matching (exact multiplier required)
        
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
        
        # Load workspace data
        workspace = self.ctx.workspace_mgr.load()
        locks = workspace.get("locks", {"include": {}, "exclude": []})
        inventory = workspace.get("inventory", {})

        gen_state = workspace.get("generation_state", {})
        meal_type = gen_state.get("meal_type")
        template_name = gen_state.get("template_name")

        current_candidates = raw_candidates
        all_rejected = []

        # PHASE 1: Nutrient constraint filtering (NEW)
        if not template_name:
            print("Warning: No template specified in generation state")
            print("Skipping nutrient constraint filtering")
            # Fall through to other filters
        else:
            # Use template for ALL candidates
            from meal_planner.filters.nutrient_constraint_filter import NutrientConstraintFilter
            nutrient_filter = NutrientConstraintFilter(
                self.ctx.master,
                self.ctx.thresholds,
                meal_type=meal_type,
                template_name=template_name  # From generation_state!
            )
           
            passed, rejected = nutrient_filter.filter_candidates(current_candidates)
            
            if verbose:
                print(f"Nutrient Constraints: {nutrient_filter.get_filter_stats(len(current_candidates), len(passed))}")
                if rejected:
                    print(f"  Rejected {len(rejected)} candidates:")
                    for r in rejected[:5]:  # Show first 5
                        reasons = r.get("rejection_reasons", [])
                        print(f"    - {r.get('id', '???')}: {', '.join(reasons)}")
                    if len(rejected) > 5:
                        print(f"    ... and {len(rejected) - 5} more")
                print()
            
            current_candidates = passed
            all_rejected.extend(rejected)
        
        # PHASE 2: Lock, availability, and inventory filtering (EXISTING)
        from meal_planner.filters import PreScoreFilter
        
        pre_filter = PreScoreFilter(
            locks=locks,
            meal_type=meal_type,
            inventory=inventory,
            user_prefs=self.ctx.user_prefs
        )
        
        filtered_candidates, rejected = pre_filter.filter_candidates(current_candidates)
        
        if verbose:
            print(f"Locks & Availability: {pre_filter.get_filter_stats(len(current_candidates), len(filtered_candidates))}")
            if rejected:
                print(f"  Rejected {len(rejected)} candidates:")
                for r in rejected[:5]:
                    reasons = r.get("rejection_reasons", [])
                    print(f"    - {r.get('id', '???')}: {', '.join(reasons)}")
                if len(rejected) > 5:
                    print(f"    ... and {len(rejected) - 5} more")
            print()
        
        all_rejected.extend(rejected)
        current_candidates = filtered_candidates
        
        # PHASE 3: Leftover match filtering (EXISTING)
        if inventory.get("leftovers"):
            from meal_planner.filters import LeftoverMatchFilter
            
            leftover_filter = LeftoverMatchFilter(
                inventory=inventory,
                allow_under_use=False
            )
            
            filtered_candidates, rejected = leftover_filter.filter_candidates(current_candidates)
            
            if verbose:
                print(f"Leftover Matching: {leftover_filter.get_filter_stats(len(current_candidates), len(filtered_candidates))}")
                if rejected:
                    print(f"  Rejected {len(rejected)} candidates for portion mismatch")
                print()
            
            all_rejected.extend(rejected)
            current_candidates = filtered_candidates
        
        # Summary
        print(f"Filtering complete:")
        print(f"  Started with:  {len(raw_candidates)} raw candidates")
        print(f"  Passed filters: {len(current_candidates)} candidates")
        print(f"  Rejected:      {len(all_rejected)} candidates")
        print()
        
        # Save results back to workspace
        self.ctx.workspace_mgr.set_filtered_candidates(
            filtered_candidates=current_candidates,
            rejected_candidates=all_rejected
        )
        
        print(f"Filtered candidates saved to workspace")
        print(f"Next: Run 'recommend score' to rank candidates")
        print()

    def _show(self, args: List[str]) -> None:
        """
        Show generated candidates with pagination and detail support.
        
        MODIFIED: Added --items flag and smart candidate lookup across all lists
        
        Usage:
            recommend show                      # Show all candidates (compact)
            recommend show --items              # Show all with macro tables
            recommend show G3                   # Show detailed view (searches all lists)
            recommend show --limit 10           # Show first 10 (compact)
            recommend show --limit 10 --items   # Show first 10 with macro tables
            recommend show --limit 5 --skip 10  # Paginated compact
            recommend show rejected             # Show rejected (compact)
            recommend show rejected --items     # Show rejected with macro tables
        
        Args:
            args: Optional arguments [rejected] [id|--limit N [--skip N] [--items]]
        """
        # Parse arguments
        rejected_mode = False
        candidate_id = None
        limit = None
        skip = 0
        items_flag = False
        
        i = 0
        while i < len(args):
            arg = args[i]
            
            if arg.lower() == "rejected":
                rejected_mode = True
                i += 1
            elif arg == "--limit":
                if i + 1 >= len(args):
                    print("\nError: --limit requires a number")
                    print()
                    return
                try:
                    limit = int(args[i + 1])
                    if limit <= 0:
                        print("\nError: --limit must be positive")
                        print()
                        return
                    i += 2
                except ValueError:
                    print(f"\nError: Invalid limit value '{args[i + 1]}'")
                    print()
                    return
            elif arg == "--skip":
                if i + 1 >= len(args):
                    print("\nError: --skip requires a number")
                    print()
                    return
                try:
                    skip = int(args[i + 1])
                    if skip < 0:
                        print("\nError: --skip must be non-negative")
                        print()
                        return
                    i += 2
                except ValueError:
                    print(f"\nError: Invalid skip value '{args[i + 1]}'")
                    print()
                    return
            elif arg == "--items":
                items_flag = True
                i += 1
            else:
                # Must be a candidate ID
                if candidate_id is not None:
                    print(f"\nError: Unexpected argument '{arg}'")
                    print()
                    return
                candidate_id = arg.upper()
                i += 1
        
        # Handle rejected mode
        if rejected_mode:
            if candidate_id:
                # Show specific rejected candidate
                self._show_rejected_detail(candidate_id)
            else:
                # Show rejected candidates (with pagination and items flag)
                self._show_rejected(limit=limit, skip=skip, items=items_flag)
            return
        
        # Check for generated candidates
        gen_cands = self.ctx.workspace_mgr.get_generated_candidates()
        
        if not gen_cands:
            print("\nNo generated candidates to show")
            print("Run 'recommend generate <meal_type>' first")
            print()
            return
        
        meal_type = gen_cands.get("meal_type", "unknown")
        
        # Show specific candidate - SMART SEARCH across all lists
        if candidate_id:
            if limit is not None or skip > 0 or items_flag:
                print("\nError: Cannot combine candidate ID with pagination/items flags")
                print()
                return
            
            # Search order: scored -> filtered -> rejected -> raw
            scored = gen_cands.get("scored", [])
            filtered = gen_cands.get("filtered", [])
            rejected = gen_cands.get("rejected", [])
            raw = gen_cands.get("raw", [])
            
            search_order = [
                (scored, "scored"),
                (filtered, "filtered"),
                (rejected, "rejected"),
                (raw, "raw")
            ]
            
            for candidates, list_name in search_order:
                if self._find_and_show_candidate(candidates, candidate_id, meal_type, list_name):
                    return
            
            # Not found in any list
            print(f"\nCandidate {candidate_id} not found in any list")
            print()
            return
        
        # Show list of candidates
        # Determine which list to show (scored > filtered > raw)
        scored = gen_cands.get("scored", [])
        filtered = gen_cands.get("filtered", [])
        raw = gen_cands.get("raw", [])
        
        if scored:
            candidates = scored
            list_type = "scored"
        elif filtered:
            candidates = filtered
            list_type = "filtered"
        else:
            candidates = raw
            list_type = "raw"
        
        if not candidates:
            print(f"\nNo {list_type} candidates")
            print()
            return
        
        # Show candidates with pagination
        self._show_all_candidates(candidates, meal_type, list_type, 
                                limit=limit, skip=skip, items=items_flag)

    def _find_and_show_candidate(
        self,
        candidates: List[Dict[str, Any]],
        candidate_id: str,
        meal_type: str,
        list_name: str
    ) -> bool:
        """
        Helper to find and show a candidate in a specific list.
        
        Args:
            candidates: List to search
            candidate_id: ID to find
            meal_type: Meal type
            list_name: Name of the list being searched
        
        Returns:
            True if found and displayed, False otherwise
        """
        for cand in candidates:
            if cand.get("id", "").upper() == candidate_id:
                # Found it - show with list context
                self._show_candidate_detail(cand, meal_type, list_name)
                return True
        return False

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
                items_list = candidate.get("items", [])
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
                    score = candidate.get("aggregate_score", 0.0)
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
        items = candidate.get("items", [])
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
                items_list = candidate.get("items", [])
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
        items = candidate.get("items", [])
        
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
        is_scored = "aggregate_score" in candidate
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
            reasons = candidate.get("rejection_reasons", [])
            if reasons:
                print(f"\nREJECTION REASONS ({len(reasons)}):")
                for reason in reasons:
                    if ":" in reason:
                        reason_type, details = reason.split(":", 1)
                        print(f"  - {reason_type}: {details}")
                    else:
                        print(f"  - {reason}")
        
        # Source info
        source_date = candidate.get("source_date", "unknown")
        source_time = candidate.get("source_time", "")
        print(f"\nSource: {source_date} {meal_type}")
        if source_time:
            print(f"Time: {source_time}")
        
        # Score if available
        if is_scored:
            score = candidate.get("aggregate_score", 0.0)
            print(f"Aggregate Score: {score:.3f}")
        
        print()
        
        # Build and print report using ReportBuilder (same as --items view)
        from meal_planner.reports import ReportBuilder

        builder = ReportBuilder(self.ctx.master)
        items_list = candidate.get("items", [])
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
        scores = candidate.get("scores", {})
        analysis = candidate.get("analysis", {})
        
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
        
        # Show gaps/excesses summary
        gaps = analysis.get("gaps", [])
        excesses = analysis.get("excesses", [])
        
        if gaps or excesses:
            print("=== NUTRITIONAL ANALYSIS ===")
            
            if gaps:
                print(f"Gaps ({len(gaps)}):")
                for gap in gaps:
                    nutrient = gap["nutrient"]
                    deficit = gap["deficit"]
                    print(f"  - {nutrient}: -{deficit:.1f}")
            
            if excesses:
                print(f"Excesses ({len(excesses)}):")
                for excess in excesses:
                    nutrient = excess["nutrient"]
                    overage = excess["overage"]
                    print(f"  - {nutrient}: +{overage:.1f}")
            
            print()

    def _discard(self, args: List[str]) -> None:
        """
        Discard generated candidates.
        
        Fully clears both generated_candidates and generation_state,
        allowing immediate re-generation without --reset.
        
        Usage:
            recommend discard           # Discard all (raw, filtered, scored)
            recommend discard raw       # Discard only raw candidates
            recommend discard filtered  # Discard only filtered candidates
            recommend discard scored    # Discard only scored candidates
        
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
            # Discard all - full reset
            target_arrays = ['raw', 'filtered', 'scored']
            target_label = "all candidates"
            full_reset = True
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
            full_reset = False
        
        # Count what will be discarded
        meal_type = gen_cands.get("meal_type", "unknown")
        raw_count = len(gen_cands.get("raw", []))
        filtered_count = len(gen_cands.get("filtered", []))
        rejected_count = len(gen_cands.get("rejected", []))
        scored_count = len(gen_cands.get("scored", []))
        
        # Show what will be lost
        print(f"\n=== DISCARD {target_label.upper()} ===")
        print(f"Meal type: {meal_type}")
        print()
        
        total_to_discard = 0
        
        if 'raw' in target_arrays and raw_count > 0:
            print(f"  Raw candidates: {raw_count}")
            total_to_discard += raw_count
        
        if 'filtered' in target_arrays:
            # When discarding filtered, also discard rejected (they come from same source)
            if filtered_count > 0 or rejected_count > 0:
                print(f"  Filtered candidates: {filtered_count}")
                print(f"  Rejected candidates: {rejected_count}")
                total_to_discard += filtered_count + rejected_count
        
        if 'scored' in target_arrays and scored_count > 0:
            print(f"  Scored candidates: {scored_count}")
            total_to_discard += scored_count
        
        if total_to_discard == 0:
            print(f"  No {target_label} to discard")
            print()
            return
        
        print()
        print(f"This will PERMANENTLY delete {total_to_discard} candidate(s)")
        if full_reset:
            print("Generation state will be fully reset (cursor and session cleared)")
        print()
        
        # Idiot check - require explicit "yes"
        response = input("Type 'yes' to confirm: ").strip().lower()
        
        if response != "yes":
            print("\nCancelled")
            print()
            return
        
        # Load workspace
        workspace = self.ctx.workspace_mgr.load()
        
        # Perform discard
        if full_reset:
            # Complete reset - clear everything
            workspace["generated_candidates"] = {}
            workspace["generation_state"] = {}
            self.ctx.workspace_mgr.save(workspace)
            
            print(f"\nDiscarded all candidates ({total_to_discard} total)")
            print("Generation state fully reset - ready for new generation")
        else:
            # Partial discard - clear specific arrays only
            if "generated_candidates" in workspace:
                for array_name in target_arrays:
                    if array_name in workspace["generated_candidates"]:
                        workspace["generated_candidates"][array_name] = []
                    
                    # When discarding filtered, also discard rejected
                    if array_name == "filtered":
                        workspace["generated_candidates"]["rejected"] = []
                
                self.ctx.workspace_mgr.save(workspace)
            
            print(f"\nDiscarded {target_label} ({total_to_discard} total)")
            print("Note: Generation state NOT reset. Use 'recommend discard' (no args) for full reset.")
        
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
        
        scored_candidates = gen_cands.get("scored", [])
        
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
        
        candidate_items = candidate.get("items", [])
        print(f"DEBUG: candidate_items\n{candidate_items}")
        expanded_items = []
        
        for item in candidate_items:
            print(f"DEBUG: item\n{item}")
            if 'code' not in item:
                expanded_items.append(item)
                continue
            code = item['code'].upper()
            print(f"DEBUG: code\n{code}")
            if code.startswith('CM.'):
                # Access nested master dict directly to get combo_expansion
                code_upper = code.upper()
                print(f"DEBUG: code_upper\n{code_upper}")
                if code_upper in self.ctx.master._master_dict:
                    cm_entry = self.ctx.master._master_dict[code_upper]
                    print(f"DEBUG: cm_entry\n{cm_entry}")
                    
                    if 'combo_expansion' in cm_entry:
                        # Parse the stored expansion string
                        expansion_str = cm_entry['combo_expansion']
                        print(f"DEBUG: expansion_str\n{expansion_str}")
                        component_items = CodeParser.parse(expansion_str)
                        
                        print(f"DEBUG: component_items\n{component_items}")
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
            "meal_name": candidate.get("meal_name"),
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
        
        # Remove from scored candidates array
        scored_candidates.remove(candidate)
        
        # Get counts for reporting
        raw_count = len(workspace["generated_candidates"].get("raw", []))
        filtered_count = len(workspace["generated_candidates"].get("filtered", []))
        rejected_count = len(workspace["generated_candidates"].get("filtered_out", []))
        scored_count = len(scored_candidates)
        
        # Clear ALL generated candidate arrays (accept is terminal operation)
        workspace["generated_candidates"]["raw"] = []
        workspace["generated_candidates"]["filtered"] = []
        workspace["generated_candidates"]["filtered_out"] = []
        workspace["generated_candidates"]["scored"] = []
        
        # Save workspace
        self.ctx.workspace_mgr.save(workspace)
        
        # CRITICAL: Refresh planning_workspace in context
        self.ctx.planning_workspace = self.ctx.workspace_mgr.convert_to_planning_workspace(workspace)
    
        # Report clearing
        print(f"\nCleared generation batch: {raw_count} raw, {filtered_count} filtered, "
          f"{rejected_count} rejected, {scored_count} scored")

        
        # Save workspace
        self.ctx.workspace_mgr.save(workspace)
        self.ctx.planning_workspace = self.ctx.workspace_mgr.convert_to_planning_workspace(workspace)
        
        # Report success
        meal_name = meal_data.get("meal_name", "meal")
        cal = meal_data.get("totals", {}).get("cal", 0)
        prot = meal_data.get("totals", {}).get("prot_g", 0)
        
        desc_str = f' - "{meal_data["description"]}"' if meal_data["description"] else ""
        
        print(f"\nAccepted {g_id} as meal #{target_id} ({meal_name}, {cal:.0f} cal, {prot:.0f}g prot){desc_str}")
        print("Meal marked immutable - use 'plan modify' to create mutable variant")
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

    def _generate_from_history(
        self, 
        meal_key: str, 
        count: int, 
        workspace: Dict[str, Any],
        template_name: Optional[str] = None 
    ) -> None:
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
        
        # Save to workspace
        self.ctx.workspace_mgr.set_generated_candidates(
            meal_type=meal_key,
            raw_candidates=candidates
        )
        
        # Reload workspace to get the updated version with generated_candidates
        workspace = self.ctx.workspace_mgr.load()
        
        # Update generation state
        workspace["generation_state"] = {
            "method": "history",
            "meal_type": meal_key,
            "template_name": template_name,  # NEW
            "cursor": len(candidates)
        }
        
        # Save workspace with generation state
        self.ctx.workspace_mgr.save(workspace)
        
        # Display results
        print(f"\nGenerated {len(candidates)} raw candidates for {meal_key}")
        print()

    def _generate_exhaustive(self, meal_key: str, count: int, workspace: dict, template_name: Optional[str] = None) -> None:
        """
        Generate candidates exhaustively from component pools.
        
        Args:
            meal_key: Normalized meal type key
            count: Number of candidates to generate
            workspace: Workspace dict
            template_name: Specific template to use (None = use first available)
        """
        # Load or initialize generation state
        gen_state = workspace.get("generation_state", {})
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
        
        # Save to workspace (append if continuing session)
        if cursor == 0:
            # Fresh start - replace
            self.ctx.workspace_mgr.set_generated_candidates(
                meal_type=meal_key,
                raw_candidates=candidates
            )
        else:
            # Continuation - append
            existing = self.ctx.workspace_mgr.get_generated_candidates()
            if existing:
                all_raw = existing.get("raw", []) + candidates
                self.ctx.workspace_mgr.set_generated_candidates(
                    meal_type=meal_key,
                    raw_candidates=all_raw
                )
        
        # Reload workspace to get updated version
        workspace = self.ctx.workspace_mgr.load()
        
        # Update generation state
        workspace["generation_state"] = {
            "method": "exhaustive",
            "meal_type": meal_key,
            "cursor": new_cursor,
            "template_name": template_name
        }
        
        # Save workspace with generation state
        self.ctx.workspace_mgr.save(workspace)
        
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
        
        # Load workspace
        workspace = self.ctx.workspace_mgr.load()
        
        # Check for existing generation session
        gen_state = workspace.get("generation_state", {})
        gen_cands = workspace.get("generated_candidates", {})
        
        # Check if there's anything to reset
        has_state = bool(gen_state)
        has_raw = len(gen_cands.get("raw", [])) > 0
        has_filtered = len(gen_cands.get("filtered", [])) > 0
        has_scored = len(gen_cands.get("scored", [])) > 0
        has_rejected = len(gen_cands.get("filtered_out", [])) > 0
        
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
                print(f"  Rejected: {len(gen_cands.get('filtered_out', []))} candidates")
        
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
        workspace["generation_state"] = {}
        workspace["generated_candidates"] = {
            "raw": [],
            "filtered": [],
            "filtered_out": [],
            "scored": []
        }
        
        self.ctx.workspace_mgr.save(workspace)
        
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