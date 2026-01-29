# meal_planner/commands/glucose_command.py
"""
Glucose command - glycemic load analysis with narrative output.

PHASE 3 CHANGES: Updated to use thresholds from JSON for risk scoring and curve classification.
"""
import shlex
from typing import List, Dict, Any, Optional

from .base import Command, register_command
from meal_planner.reports.report_builder import ReportBuilder
from meal_planner.parsers import CodeParser
from meal_planner.models import DailyTotals
from meal_planner.utils.time_utils import normalize_meal_name


@register_command
class GlucoseCommand(Command):
    """Show glycemic load analysis."""
    
    name = "glucose"
    help_text = "Show glucose analysis (glucose [date] [--meal \"MORNING SNACK\"] [--detail])"
    
    def execute(self, args: str) -> None:
        """
        Show glucose/glycemic load analysis.
        
        Args:
            args: Optional date (YYYY-MM-DD) and flags
                  --meal <meal_name>: Show specific meal only (use quotes for multi-word names)
                  --detail: Show component breakdowns
        """
        # PHASE 3: Check thresholds availability - glucose analysis requires them
        if not self._check_thresholds("Glucose analysis"):
            return
        
        # Parse arguments (handles quotes properly)
        try:
            parts = shlex.split(args.strip()) if args.strip() else []
        except ValueError:
            # Fallback to simple split if shlex fails
            parts = args.strip().split() if args.strip() else []
        
        # Parse flags
        show_detail = "--detail" in parts
        
        # Parse --meal flag
        meal_filter = None
        if "--meal" in parts:
            meal_idx = parts.index("--meal")
            if meal_idx + 1 < len(parts):
                meal_parts = []
                for i in range(meal_idx + 1, len(parts)):
                    if parts[i].startswith("--"):
                        break
                    meal_parts.append(parts[i])
                
                if meal_parts:
                    meal_filter = normalize_meal_name(" ".join(meal_parts))
        
        # Get date parts (non-flag arguments)
        date_parts = [p for p in parts 
                     if not p.startswith("--") 
                     and (parts.index(p) == 0 or parts[parts.index(p) - 1] != "--meal")]
        
        builder = ReportBuilder(self.ctx.master)
        
        if not date_parts:
            # Use pending
            report = self._get_pending_report(builder)
            date_label = "pending"
        else:
            # Use log date
            query_date = date_parts[0]
            report = self._get_log_report(builder, query_date)
            date_label = query_date
        
        if report is None:
            return
        
        # Get meal breakdown
        breakdown = report.get_meal_breakdown()
        
        if breakdown is None:
            print("\n(No time markers present - glucose analysis requires meal timing)\n")
            print("Add time markers to your meals using format: @HH:MM or @H:MM\n")
            return
        
        # Filter to specific meal if requested
        if meal_filter:
            breakdown = [(name, time, totals) for name, time, totals in breakdown 
                        if name == meal_filter]
            if not breakdown:
                print(f"\nMeal '{meal_filter}' not found.\n")
                return
        
        # Show analysis for each meal
        print(f"\n{'=' * 70}")
        print(f"Glucose Analysis - {date_label}")
        print(f"{'=' * 70}\n")
        
        for meal_name, first_time, totals in breakdown:
            self._analyze_meal(meal_name, first_time, totals, show_detail)
    
    def _get_pending_report(self, builder):
        """Get report from pending items."""
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            pending = None
        
        if pending is None or not pending.get("items"):
            print("\n(No active day. Use 'start' and 'add' first.)\n")
            return None
        
        items = pending.get("items", [])
        return builder.build_from_items(items, title="Pending Analysis")
    
    def _get_log_report(self, builder, query_date: str):
        """Get report from log date."""
        entries = self.ctx.log.get_entries_for_date(query_date)
        
        if entries.empty:
            print(f"\nNo log entries found for {query_date}.\n")
            return None
        
        codes_col = self.ctx.log.cols.codes
        all_codes = ", ".join([
            str(v) for v in entries[codes_col].fillna("") 
            if str(v).strip()
        ])
        
        if not all_codes.strip():
            print(f"\nNo codes found for {query_date}.\n")
            return None
        
        items = CodeParser.parse(all_codes)
        return builder.build_from_items(items, title=f"Analysis for {query_date}")
    
    def _analyze_meal(self, meal_name: str, first_time: str, 
                      totals: DailyTotals, show_detail: bool) -> None:
        """Analyze and display glucose impact for a single meal."""
        # Calculate GI from GL
        gi = None
        if totals.carbs_g > 0:
            gi = (totals.glycemic_load / totals.carbs_g) * 100
        
        # Build meal dict for risk calculation
        meal_dict = {
            'carbs_g': totals.carbs_g,
            'fat_g': totals.fat_g,
            'protein_g': totals.protein_g,
            'fiber_g': totals.fiber_g,
            'gi': gi
        }
        
        # Calculate risk using thresholds
        risk = self._compute_risk_scores(meal_dict)
        
        # Classify curve using thresholds
        curve = self._classify_glucose_curve(meal_dict, risk)
        
        # Format output
        print(f"{'-' * 70}")
        print(f"{meal_name} ({first_time})")
        print(f"{'-' * 70}")
        print()
        
        # Main narrative
        print(f"Expected Pattern: {curve['curve_label']}")
        print(f"  {curve['curve_description']}")
        print()
        
        print(f"Risk Level: {risk['risk_rating'].upper()} ({risk['risk_score']:.1f}/10)")
        print()
        
        # Key concerns (top warnings only)
        concerns = self._get_key_concerns(totals, risk, gi)
        if concerns:
            print("Key Concerns:")
            for concern in concerns[:3]:  # Top 3 only
                print(f"  * {concern}")
            print()
        
        # Recommendations
        recs = self._get_recommendations(totals, risk, curve)
        if recs:
            print("Suggestions:")
            for rec in recs[:2]:  # Top 2 only
                print(f"  -> {rec}")
            print()
        
        # Detail breakdown if requested
        if show_detail:
            self._show_detail_breakdown(totals, risk, gi)
    
    def _compute_risk_scores(self, meal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute glucose risk score and components.
        
        PHASE 3: Now uses thresholds from JSON instead of hardcoded values.
        """
        carbs_g = _safe_get(meal, "carbs_g", 0.0)
        fat_g = _safe_get(meal, "fat_g", 0.0)
        protein_g = _safe_get(meal, "protein_g", 0.0)
        fiber_g = _safe_get(meal, "fiber_g", 0.0)
        gi = meal.get("gi")
        
        # PHASE 3: Get scoring configuration from thresholds
        scoring = self.ctx.thresholds.get_glucose_scoring()
        
        # Calculate component scores using thresholds
        carb_risk = self._get_score_for_value(carbs_g, scoring['carb_risk_ranges'])
        gi_factor = self._get_factor_for_value(gi, scoring['gi_speed_factors'])
        base_carb_risk = min(carb_risk * gi_factor, 10.0)
        
        fat_delay = self._get_score_for_value(fat_g, scoring['fat_delay_ranges'])
        protein_tail = self._get_score_for_value(protein_g, scoring['protein_tail_ranges'])
        fiber_buffer = self._get_score_for_value(fiber_g, scoring['fiber_buffer_ranges'])
        
        # PHASE 3: Use weights from thresholds
        weights = scoring['risk_score_weights']
        raw_score = (
            base_carb_risk
            + weights['fat_delay'] * fat_delay
            + weights['protein_tail'] * protein_tail
            - weights['fiber_buffer'] * fiber_buffer
        )
        
        risk_score = max(0.0, min(10.0, raw_score))
        
        # PHASE 3: Use rating thresholds from JSON
        rating = self._get_risk_rating(risk_score, scoring['risk_rating_thresholds'])
        
        return {
            "risk_score": risk_score,
            "risk_rating": rating,
            "components": {
                "carb_risk": carb_risk,
                "gi_speed_factor": gi_factor,
                "base_carb_risk": base_carb_risk,
                "fat_delay_risk": fat_delay,
                "protein_tail_risk": protein_tail,
                "fiber_buffer": fiber_buffer,
                "raw_score_before_clamp": raw_score,
            },
        }
    
    def _classify_glucose_curve(self, meal: Dict[str, Any], 
                                risk_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classify expected glucose curve shape.
        
        PHASE 3: Now uses curve classification rules from JSON.
        """
        carbs_g = _safe_get(meal, "carbs_g", 0.0)
        fat_g = _safe_get(meal, "fat_g", 0.0)
        protein_g = _safe_get(meal, "protein_g", 0.0)
        fiber_g = _safe_get(meal, "fiber_g", 0.0)
        gi = meal.get("gi")
        risk_score = risk_info.get("risk_score", 0.0)
        
        # PHASE 3: Get curve rules from thresholds
        curves = self.ctx.thresholds.get_curve_classification()
        
        # Check very low carb first
        if carbs_g < curves['very_low_carb_max']:
            return {
                "curve_shape": "flat_or_minimal_rise",
                "curve_label": "Flat / Minimal Rise",
                "curve_description": (
                    "Very low carb content. Expect flat CGM line or small bump "
                    "with no significant spike."
                )
            }
        
        # Check delayed spike (pizza effect)
        delayed = curves['delayed_spike']
        if (carbs_g >= delayed['min_carbs'] and fat_g >= delayed['min_fat']):
            return {
                "curve_shape": "delayed_spike",
                "curve_label": delayed['label'],
                "curve_description": delayed['curve_description']
            }
        
        # Check double hump
        double = curves['double_hump']
        if (carbs_g >= double['min_carbs'] and 
            double['min_fat'] <= fat_g <= double['max_fat'] and 
            protein_g >= double['min_protein']):
            return {
                "curve_shape": "double_hump",
                "curve_label": double['label'],
                "curve_description": double['curve_description']
            }
        
        # Check blunted spike
        blunted = curves['blunted_spike']
        if (carbs_g >= blunted['min_carbs'] and 
            fiber_g >= blunted['min_fiber'] and 
            fat_g < blunted['max_fat']):
            # Use template for description
            desc = blunted['curve_description_template'].format(
                carbs=int(carbs_g),
                fiber=int(fiber_g)
            )
            return {
                "curve_shape": "blunted_spike",
                "curve_label": blunted['label'],
                "curve_description": desc
            }
        
        # Check spike then dip
        spike_dip = curves['spike_then_dip']
        if (carbs_g >= spike_dip['min_carbs'] and 
            gi and gi >= spike_dip['min_gi'] and 
            fat_g < spike_dip['max_fat'] and 
            fiber_g < spike_dip['max_fiber']):
            return {
                "curve_shape": "spike_then_dip",
                "curve_label": spike_dip['label'],
                "curve_description": spike_dip['curve_description']
            }
        
        # Default case
        default = curves['default']
        desc = default['curve_description_template'].format(
            carbs=int(carbs_g),
            risk_score=risk_score
        )
        return {
            "curve_shape": "moderate_single_spike",
            "curve_label": default['label'],
            "curve_description": desc
        }
    
    def _get_key_concerns(self, totals: DailyTotals, risk: dict, gi: Optional[float]) -> List[str]:
        """
        Extract top concerns from risk analysis.
        
        PHASE 3: Uses some thresholds, but concern messages are still somewhat hardcoded.
        This could be further improved in a future phase.
        """
        concerns = []
        components = risk['components']
        
        # High carb load
        if totals.carbs_g > 60:
            concerns.append(f"Large carb load ({int(totals.carbs_g)}g)")
        elif totals.carbs_g > 40:
            concerns.append(f"Moderate carb load ({int(totals.carbs_g)}g)")
        
        # Fast GI
        if gi and gi > 70:
            concerns.append(f"Fast absorption (GI {int(gi)} = rapid spike)")
        elif gi and gi > 60:
            concerns.append(f"Moderate-fast absorption (GI {int(gi)})")
        
        # Low fiber
        if components['fiber_buffer'] < 1.0:
            concerns.append("Minimal fiber buffering")
        
        # High fat with carbs
        if totals.fat_g > 25 and totals.carbs_g > 30:
            concerns.append(f"High fat ({int(totals.fat_g)}g) may delay spike")
        
        # High sugar
        if totals.sugar_g > 30:
            concerns.append(f"High sugar content ({int(totals.sugar_g)}g)")
        
        # Low protein
        if totals.protein_g < 15 and totals.carbs_g > 30:
            concerns.append(f"Low protein buffer ({int(totals.protein_g)}g)")
        
        return concerns
    
    def _get_recommendations(self, totals: DailyTotals, risk: dict, curve: dict) -> List[str]:
        """Generate actionable recommendations."""
        recs = []
        
        if risk['risk_score'] > 7:
            recs.append("Consider reducing portion size or splitting into two smaller meals")
        
        curve_shape = curve.get('curve_shape', '')
        if curve_shape == 'sharp_early_spike':
            recs.append("Add protein/fat before carbs to slow absorption")
        
        if curve_shape == 'delayed_spike':
            recs.append("Watch for late spike 2-3 hours after eating")
        
        if totals.protein_g < 15 and totals.carbs_g > 30:
            recs.append("Add more protein to stabilize glucose response")
        
        if risk['components']['fiber_buffer'] < 1.0:
            recs.append("Add high-fiber foods to blunt the spike")
        
        return recs
    
    def _show_detail_breakdown(self, totals: DailyTotals, risk: dict, gi: Optional[float]) -> None:
        """Show detailed component breakdown."""
        comp = risk['components']
        
        print("Detailed Breakdown:")
        print(f"  Carbs:         {totals.carbs_g:>6.1f}g  -> base risk: {comp['carb_risk']:.1f}")
        
        if gi:
            print(f"  GI:            {gi:>6.0f}     -> speed factor: {comp['gi_speed_factor']:.1f}x")
        
        print(f"  Fat:           {totals.fat_g:>6.1f}g  -> delay risk: +{comp['fat_delay_risk']:.1f}")
        print(f"  Protein:       {totals.protein_g:>6.1f}g  -> tail risk: +{comp['protein_tail_risk']:.1f}")
        print(f"  Fiber:         {totals.fiber_g:>6.1f}g  -> buffer: -{comp['fiber_buffer']:.1f}")
        print(f"  {'-' * 40}")
        print(f"  Total Risk:    {risk['risk_score']:>6.1f} / 10")
        print()
    
    # PHASE 3: Helper methods for threshold lookups
    
    def _get_score_for_value(self, value: float, ranges: List[Dict]) -> float:
        """Get score for a value using range definitions from thresholds."""
        range_def = self.ctx.thresholds.get_value_for_range(value, ranges)
        return range_def.get('score', 0.0) if range_def else 0.0
    
    def _get_factor_for_value(self, value: Optional[float], ranges: List[Dict]) -> float:
        """Get factor for a value using range definitions from thresholds."""
        if value is None:
            return 1.0  # Neutral factor if no value
        range_def = self.ctx.thresholds.get_value_for_range(value, ranges)
        return range_def.get('factor', 1.0) if range_def else 1.0
    
    def _get_risk_rating(self, score: float, thresholds: List[Dict]) -> str:
        """Get risk rating for a score using threshold definitions."""
        rating_def = self.ctx.thresholds.get_value_for_range(score, thresholds)
        return rating_def.get('rating', 'unknown') if rating_def else 'unknown'


# Helper function
def _safe_get(meal: Dict[str, Any], key: str, default: float = 0.0) -> float:
    """Safely extract numeric value from meal dict."""
    value = meal.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default