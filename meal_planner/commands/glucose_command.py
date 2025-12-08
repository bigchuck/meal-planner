# meal_planner/commands/glucose_command.py
"""
Glucose command - glycemic load analysis with narrative output.
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
        # Parse arguments (handles quotes properly)
        try:
            parts = shlex.split(args.strip()) if args.strip() else []
        except ValueError:
            # Fallback to simple split if shlex fails
            parts = args.strip().split() if args.strip() else []
        
        # Parse flags
        show_detail = "--detail" in parts
        
        # Parse --meal flag (collect all parts until next flag)
        meal_filter = None
        if "--meal" in parts:
            meal_idx = parts.index("--meal")
            if meal_idx + 1 < len(parts):
                # Collect all parts until next flag or end
                meal_parts = []
                for i in range(meal_idx + 1, len(parts)):
                    if parts[i].startswith("--"):
                        break
                    meal_parts.append(parts[i])
                
                if meal_parts:
                    # Join and normalize
                    meal_filter = normalize_meal_name(" ".join(meal_parts))
        
        # Get date parts (non-flag arguments)
        date_parts = [p for p in parts 
                     if not p.startswith("--") 
                     and (parts.index(p) == 0 or parts[parts.index(p) - 1] != "--meal")]
        
        builder = ReportBuilder(self.ctx.master, self.ctx.nutrients)
        
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
            print("Add time markers to your meals using '@HH:MM' format:")
            print("  Example: add @08:00, B.1, S2.4")
            return
        
        # Filter meals
        meals_to_show = []
        for meal_name, first_time, totals in breakdown:
            # If filtering by specific meal, only check that
            if meal_filter:
                if meal_name == meal_filter:
                    meals_to_show.append((meal_name, first_time, totals))
                continue
            
            meals_to_show.append((meal_name, first_time, totals))
        
        if not meals_to_show:
            if meal_filter:
                print(f"\n(No meal found matching '{meal_filter}')\n")
            else:
                print("\n(No meals to analyze)\n")
            return
        
        # Show analysis
        print(f"\n=== Glucose Analysis ({date_label}) ===\n")
        
        for meal_name, first_time, totals in meals_to_show:
            self._show_meal_analysis(meal_name, first_time, totals, show_detail)
            print()
    
    def _get_pending_report(self, builder):
        """Get report from pending."""
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            pending = None
        
        if pending is None or not pending.get("items"):
            print("\n(No active day. Use 'start' and 'add' first.)\n")
            return None
        
        items = pending.get("items", [])
        return builder.build_from_items(items, title="Glucose Analysis")
    
    def _get_log_report(self, builder, query_date):
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
        return builder.build_from_items(items, title="Glucose Analysis")
    
    def _show_meal_analysis(self, meal_name: str, first_time: str, 
                           totals: DailyTotals, show_detail: bool) -> None:
        """Show narrative analysis for a single meal."""
        
        # Calculate GI from GL
        gi = None
        if totals.carbs_g > 0:
            gi = (totals.glycemic_load / totals.carbs_g) * 100
        
        # Build meal dict for risk calculation (NOW WITH REAL FIBER)
        meal_dict = {
            'carbs_g': totals.carbs_g,
            'fat_g': totals.fat_g,
            'protein_g': totals.protein_g,
            'fiber_g': totals.fiber_g,
            'gi': gi
        }

        
        # Calculate risk
        risk = self._compute_risk_scores(meal_dict)
        
        # Classify curve
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
    
    def _get_key_concerns(self, totals: DailyTotals, risk: dict, gi: Optional[float]) -> List[str]:
        """Extract top concerns from risk analysis."""
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
        
        if curve['curve_shape'] == 'sharp_early_spike':
            recs.append("Add protein/fat before carbs to slow absorption")
        
        if curve['curve_shape'] == 'delayed_high_spike':
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

    def _compute_risk_scores(self, meal: Dict[str, Any]) -> Dict[str, Any]:
        """Compute glucose risk score and components."""
        carbs_g = _safe_get(meal, "carbs_g", 0.0)
        fat_g = _safe_get(meal, "fat_g", 0.0)
        protein_g = _safe_get(meal, "protein_g", 0.0)
        fiber_g = _safe_get(meal, "fiber_g", 0.0)
        gi = meal.get("gi")
        
        carb_risk = _carb_risk_score(carbs_g)
        gi_factor = _gi_speed_factor(gi)
        base_carb_risk = min(carb_risk * gi_factor, 10.0)
        
        fat_delay = _fat_delay_score(fat_g)
        protein_tail = _protein_tail_score(protein_g)
        fiber_buffer = _fiber_buffer_score(fiber_g)
        
        raw_score = (
            base_carb_risk
            + 0.6 * fat_delay
            + 0.5 * protein_tail
            - 0.7 * fiber_buffer
        )
        
        risk_score = max(0.0, min(10.0, raw_score))
        
        if risk_score < 3:
            rating = "low"
        elif risk_score < 6:
            rating = "medium"
        elif risk_score < 8.5:
            rating = "high"
        else:
            rating = "very_high"
        
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
        """Classify expected glucose curve shape."""
        carbs_g = _safe_get(meal, "carbs_g", 0.0)
        fat_g = _safe_get(meal, "fat_g", 0.0)
        protein_g = _safe_get(meal, "protein_g", 0.0)
        fiber_g = _safe_get(meal, "fiber_g", 0.0)
        gi = meal.get("gi")
        
        risk_score = risk_info.get("risk_score", 0.0)
        
        # Very low carbs
        if carbs_g < 10:
            return {
                "curve_shape": "flat_or_minimal_rise",
                "curve_label": "Flat / Minimal Rise",
                "curve_description": (
                    "Very low carb content. Expect flat CGM line or small bump "
                    "with no significant spike."
                )
            }
        
        # Sharp early spike: high GI, low fat, moderate+ carbs
        if carbs_g >= 30 and gi and gi >= 60 and fat_g < 10 and fiber_g < 6:
            return {
                "curve_shape": "sharp_early_spike",
                "curve_label": "Sharp Early Spike ",
                "curve_description": (
                    f"High-GI carbs ({int(carbs_g)}g) with minimal fat/fiber buffering. "
                    "Quick rise with peak at 20-45 minutes, followed by gradual decline."
                )
            }
        
        # Delayed pizza spike: high carb + high fat
        if carbs_g >= 40 and fat_g >= 20:
            return {
                "curve_shape": "delayed_high_spike",
                "curve_label": "Delayed High Spike (Pizza Effect)",
                "curve_description": (
                    f"Substantial carbs ({int(carbs_g)}g) plus high fat ({int(fat_g)}g). "
                    "Initial rise modest, but expect larger spike 90-180 minutes later "
                    "with prolonged tail."
                )
            }
        
        # Double hump: moderate carbs, moderate fat, high protein
        if 20 <= carbs_g <= 40 and 10 <= fat_g <= 25 and protein_g >= 25:
            return {
                "curve_shape": "double_hump",
                "curve_label": "Double-Hump Pattern",
                "curve_description": (
                    "Mixed meal with moderate carbs, notable fat, and high protein. "
                    "Modest early bump, some decline, then second slower rise 2-3 hours later "
                    "as protein converts to glucose."
                )
            }
        
        # Blunted spike: carbs + high fiber
        if carbs_g >= 15 and fiber_g >= 8 and fat_g < 20:
            return {
                "curve_shape": "blunted_spike",
                "curve_label": "Blunted / Smoothed Spike",
                "curve_description": (
                    f"Carbs present ({int(carbs_g)}g) but high fiber ({int(fiber_g)}g) "
                    "slows absorption. Expect slower, lower peak with smooth rise and fall."
                )
            }
        
        # Spike then dip risk
        if carbs_g >= 25 and gi and gi >= 60 and fat_g < 10 and fiber_g < 4:
            return {
                "curve_shape": "spike_then_dip_risk",
                "curve_label": "Spike Then Possible Dip ",
                "curve_description": (
                    "Fast, low-fiber carbs with little fat. Strong early spike with "
                    "higher risk of subsequent dip (reactive hypoglycemia pattern)."
                )
            }
        
        # Default: moderate single spike
        return {
            "curve_shape": "moderate_single_spike",
            "curve_label": "Moderate Single Spike",
            "curve_description": (
                f"Moderate rise with single main peak. Overall impact follows "
                f"carb load ({int(carbs_g)}g) and risk score ({risk_score:.1f}/10)."
            )
        }


# Helper functions
def _safe_get(meal: Dict[str, Any], key: str, default: float = 0.0) -> float:
    """Safely extract numeric value from meal dict."""
    value = meal.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _carb_risk_score(carbs_g: float) -> float:
    """Map carb grams to risk contribution (0-10)."""
    if carbs_g <= 5:
        return 0.0
    elif carbs_g <= 20:
        return 2.0
    elif carbs_g <= 40:
        return 5.0
    elif carbs_g <= 70:
        return 8.0
    else:
        return 10.0


def _gi_speed_factor(gi: Optional[float]) -> float:
    """Convert GI to speed multiplier."""
    if gi is None or gi <= 0:
        return 1.0
    if gi < 40:
        return 0.8
    elif gi < 60:
        return 1.0
    else:
        return 1.2


def _fat_delay_score(fat_g: float) -> float:
    """Score for fat-driven delay (0-7)."""
    if fat_g <= 5:
        return 0.0
    elif fat_g <= 15:
        return 1.0
    elif fat_g <= 25:
        return 3.0
    elif fat_g <= 35:
        return 5.0
    else:
        return 7.0


def _protein_tail_score(protein_g: float) -> float:
    """Score for protein tail effect (0-4)."""
    if protein_g <= 10:
        return 0.0
    elif protein_g <= 20:
        return 1.0
    elif protein_g <= 35:
        return 2.0
    else:
        return 4.0


def _fiber_buffer_score(fiber_g: float) -> float:
    """Score for fiber protection (0-5)."""
    if fiber_g <= 2:
        return 0.0
    elif fiber_g <= 6:
        return 1.0
    elif fiber_g <= 10:
        return 3.0
    else:
        return 5.0