"""
Calculate glucose prediction
"""
"""
Glucose impact calculator for meal planning.

Calculates glucose-related metrics from meal data including glycemic load,
meal timing, and estimated glucose response patterns.
"""
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class GlucoseMetrics:
    """Container for glucose-related calculations."""
    total_gl: float
    peak_gl: float  # Highest single-meal GL
    meal_count: int
    avg_gl_per_meal: float
    time_weighted_gl: float  # GL adjusted for meal spacing
    estimated_peak_time: Optional[str]  # When glucose likely peaks
    meal_distribution_score: float  # How well-distributed meals are (0-1)
    

class GlucoseCalculator:
    """
    Calculates glucose impact metrics from meal data.
    
    Uses glycemic load values and meal timing to estimate glucose response.
    """
    
    # Time constants (minutes)
    GLUCOSE_PEAK_TIME = 45  # Minutes to peak after eating
    GLUCOSE_CLEAR_TIME = 180  # Minutes to return to baseline
    IDEAL_MEAL_GAP = 240  # Ideal gap between meals (4 hours)
    
    def __init__(self):
        """Initialize calculator."""
        pass
    
    """
    -----------------------------------------------------------------
    Extracted from ChatGPT discussion 2025-11-20
    -----------------------------------------------------------------
    """

    def analyze_meal(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Convenience wrapper:
        Takes an item list makes a meal (summed values)
        returns both risk scores and curve-shape classification.
        
        Example meal dict:
        meal = {
            "carbs_g": 55,
            "fat_g": 22,
            "protein_g": 25,
            "fiber_g": 6,
            "gi": 62
        }
        """
        # compute meal totals, make dictionary
        meal_carbs_g = 0
        meal_fat_g = 0
        meal_protein_g = 0
        meal_fiber_g = 0
        for item in items:
            meal_carbs_g = float(item.get("carbs_g", 0.0))
            meal_fat_g = float(item.get("fat_g", 0.0))
            meal_protein_g = float(item.get("protein_g", 0.0))
            meal_fiber_g = float(item.get("fiber_g", 0.0))
        meal_gi = _compute_meal_gi_from_items(items)
        meal = {"carbs_g":meal_carbs_g, "fat_g":meal_fat_g, "protein_g":meal_protein_g, "fiber_g":meal_fiber_g, "gi":meal_gi}

        risk = self.compute_risk_scores(meal)
        curve = self.classify_glucose_curve(meal, risk_info=risk)
        return {
            "input_meal": meal,
            "risk": risk,
            "curve": curve,
        }

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

    def classify_glucose_curve(self, 
        meal: Dict[str, Any],
        risk_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Classify the expected post-prandial glucose curve shape for the meal.
        
        Inputs:
        meal dict (same expectations as compute_risk_scores).
        risk_info: optional output from compute_risk_scores() for reuse.
        
        Returns:
        {
            "curve_shape": <string id>,
            "curve_label": <short human label>,
            "curve_description": <longer explanation>
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

        risk_score = float(risk_info.get("risk_score", 0.0))

        # 1) Very low carbs → flat line / minimal rise
        if carbs_g < 10:
            shape = "flat_or_minimal_rise"
            label = "Flat / very low rise"
            desc = (
                "Carbohydrate content is very low; CGM is expected to show a flat line "
                "or only a small bump with no significant spike."
            )

        # 2) Classic sharp early spike: high GI, low fat, moderate+ carbs
        elif carbs_g >= 30 and (gi is not None and gi >= 60) and fat_g < 10 and fiber_g < 6:
            shape = "sharp_early_spike"
            label = "Sharp early spike"
            desc = (
                "High and fast carbohydrates with little fat or fiber buffering. "
                "Expect a quick rise and early peak within ~20–45 minutes "
                "followed by a gradual decline."
            )

        # 3) High carb + high fat → delayed 'pizza' spike
        elif carbs_g >= 40 and fat_g >= 20:
            shape = "delayed_high_spike"
            label = "Delayed high spike (pizza effect)"
            desc = (
                "Substantial carbs plus high fat. Fat slows gastric emptying and reduces "
                "insulin sensitivity, so the initial rise may be modest, but a larger "
                "spike is expected 90–180 minutes after the meal with a prolonged tail."
            )

        # 4) Moderate carbs, moderate fat, high protein → double hump
        elif 20 <= carbs_g <= 40 and 10 <= fat_g <= 25 and protein_g >= 25:
            shape = "double_hump"
            label = "Double-hump pattern"
            desc = (
                "Mixed meal with moderate carbs, notable fat, and high protein. "
                "Expect a modest early bump, some decline, and then a second slower "
                "rise 2–3 hours later as protein is converted to glucose."
            )

        # 5) Carbs plus high fiber, low-moderate fat → blunted spike
        elif carbs_g >= 15 and fiber_g >= 8 and fat_g < 20:
            shape = "blunted_spike"
            label = "Blunted / smoothed spike"
            desc = (
                "Carbohydrates are present but accompanied by high fiber, which slows "
                "absorption and flattens the curve. Expect a slower, lower peak with "
                "a smoother rise and fall."
            )

        # 6) High carb, high GI, low fiber, low fat → spike then dip (reactive)
        elif carbs_g >= 25 and (gi is not None and gi >= 60) and fat_g < 10 and fiber_g < 4:
            shape = "spike_then_dip_risk"
            label = "Spike then possible dip"
            desc = (
                'Fast, low-fiber carbohydrates with little fat. Expect a strong early '
                "spike and higher risk of a subsequent dip (reactive hypoglycemia pattern)."
            )

        # 7) Default: moderate, single hump
        else:
            shape = "moderate_single_spike"
            label = "Moderate single spike"
            desc = (
                "Meal composition suggests a moderate rise with a single main peak "
                "and no pronounced delay or double-hump. Overall impact follows "
                "the total carb load and risk score."
            )

        return {
            "curve_shape": shape,
            "curve_label": label,
            "curve_description": desc,
            "risk_score_used": risk_score,
        }

def _compute_meal_gi_from_items(items: List[Dict[str, Any]]) -> Optional[float]:
    """
    Each item dict should have:
    - 'gl'       : Gl for that food
    - 'carbs_g'  : grams of carb for the portion actually eaten
    Returns the carb-weighted GI for the meal, or None if total carbs ~ 0.

    meal-gi = 100 x summed GL / summed carbs
    """
    num = 0.0
    denom = 0.0

    for item in items:
        try:
            gl = float(item.get("gl", 0.0))
        except (TypeError, ValueError):
            continue

        try:
            carbs = float(item.get("carbs_g", 0.0))
        except (TypeError, ValueError):
            carbs = 0.0

        if carbs <= 0:
            continue

        num += 100 * gl
        denom += carbs

    if denom <= 0:
        return None  # effectively no carbs → GI not meaningful

    return num / denom

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


