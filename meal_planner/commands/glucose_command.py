"""
Glucose command to provide detail information about a meal's predictive effect on CGM data
"""
"""
Glucose command - glycemic load analysis.
"""
from typing import List, Dict, Any, Optional, Tuple

from .base import Command, register_command
from meal_planner.reports.report_builder import ReportBuilder
from meal_planner.parsers import CodeParser


@register_command
class GlucoseCommand(Command):
    """Show glycemic load analysis."""
    
    name = "glucose"
    help_text = "Show glycemic analysis (glucose or glucose YYYY-MM-DD)"
    
    def execute(self, args: str) -> None:
        """
        Show glucose/glycemic load analysis.
        
        Args:
            args: Optional date (YYYY-MM-DD)
        """
        parts = args.strip().split() if args.strip() else []
        
        self.show_all_meals = "--all" in parts

        builder = ReportBuilder(self.ctx.master)

        date_parts = [p for p in parts if not p.startswith("--")]

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
        
        # Show glucose analysis
        self._show_glucose_analysis(report, date_label)
    
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
    """
    --------------------------------------------------------------------
    """    
    def _show_glucose_analysis(self, report, date_label):
        """Display glucose analysis."""
        print(f"\n=== Detailed Glycemic Analysis ({date_label}) ===\n")
        
        # Get meal breakdown if time markers present
        breakdown = report.get_meal_breakdown()

        for meal_name, first_time, totals in breakdown:
            if self.show_all_meals or "SNACK" not in meal_name: 
                print(meal_name, first_time)
                meal_dict = totals.to_dict()
                meal_dict['calories'] = meal_dict.pop('cal')
                meal_dict['protein_g'] = meal_dict.pop('prot_g')
                meal_dict['gi'] = 100 * meal_dict['gl'] / meal_dict['carbs_g']
                print(meal_dict)
                risks = self.compute_risk_scores(meal_dict)
                print(risks)


    def compute_risk_scores(self, meal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute a glucose 'risk score' (0–10) and its components.
        
        Expected keys in `meal` (all optional, defaults to 0 or neutral):
        - 'carbs_g'   : grams of carbohydrate
        - 'fat_g'     : grams of fat
        - 'protein_g' : grams of protein
        - 'fiber_g'   : grams of fiber
        - 'gi'        : glycemic index (0–100, or None)
        
        Returns a dict:
        {
            "risk_score": float in [0, 10],
            "risk_rating": "low" | "medium" | "high" | "very_high",
            "components": {
                "carb_risk": float,
                "gi_speed_factor": float,
                "fat_delay_risk": float,
                "protein_tail_risk": float,
                "fiber_buffer": float,
                "base_carb_risk": float,
                "raw_score_before_clamp": float
            }
        }
        """
        carbs_g = _safe_get(meal, "carbs_g", 0.0)
        fat_g = _safe_get(meal, "fat_g", 0.0)
        protein_g = _safe_get(meal, "protein_g", 0.0)
        fiber_g = _safe_get(meal, "fiber_g", 0.0)
        gi_value_raw = meal.get("gi", None)
        gi = None
        if gi_value_raw is not None:
            try:
                gi = float(gi_value_raw)
            except (TypeError, ValueError):
                gi = None

        carb_risk = _carb_risk_score(carbs_g)
        gi_factor = _gi_speed_factor(gi)
        base_carb_risk = min(carb_risk * gi_factor, 10.0)

        fat_delay = _fat_delay_score(fat_g)
        protein_tail = _protein_tail_score(protein_g)
        fiber_buffer = _fiber_buffer_score(fiber_g)

        # Weighted combination (you can tweak weights if desired)
        raw_score = (
            base_carb_risk
            + 0.6 * fat_delay       # fat increases late spike risk
            + 0.5 * protein_tail    # protein adds delayed tail risk
            - 0.7 * fiber_buffer    # fiber subtracts risk
        )

        # Clamp to [0, 10]
        risk_score = max(0.0, min(10.0, raw_score))

        # Convert to categorical rating
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
                

def _safe_get(meal: Dict[str, Any], key: str, default: float = 0.0) -> float:
    """Utility to pull numeric fields from the meal dict with a default."""
    value = meal.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def _carb_risk_score(carbs_g: float) -> float:
    """
    Map carb grams to a 0–10 risk contribution.
    Thresholds are based on clinical carb ranges.
    """
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
    """
    Convert GI into a speed multiplier on carb risk.
    """
    if gi is None or gi <= 0:
        return 1.0  # unknown: neutral
    if gi < 40:
        return 0.8  # slow
    elif gi < 60:
        return 1.0  # medium
    else:
        return 1.2  # fast

def _fat_delay_score(fat_g: float) -> float:
    """
    Score for fat-driven delay and insulin resistance (0–7).
    """
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
    """
    Score for protein-driven delayed glucose via gluconeogenesis (0–4).
    """
    if protein_g <= 10:
        return 0.0
    elif protein_g <= 20:
        return 1.0
    elif protein_g <= 35:
        return 2.0
    else:
        return 4.0

def _fiber_buffer_score(fiber_g: float) -> float:
    """
    Score for fiber’s protective, spike-flattening effect (0–5).
    Higher score = more buffering (subtracts from total risk).
    """
    if fiber_g <= 2:
        return 0.0
    elif fiber_g <= 6:
        return 1.0
    elif fiber_g <= 10:
        return 3.0
    else:
        return 5.0

            
