# meal_planner/generators/ga_scoring.py
"""
Fitness scoring engine for the Genetic Algorithm.

Scores GA members using linear falloff from nutrient range midpoints,
producing continuous, unbounded fitness values that differentiate
candidates far better than the 0-1 pass/fail approach.

Two scoring modes per nutrient:
- midpoint: Reward proximity to center of a min/max range.
    Score = 1.0 at midpoint, 0.0 at boundary, negative beyond.
- headroom: Reward distance below a one-sided max limit (e.g., GL).
    Score = 1.0 at zero, 0.0 at max, negative above.

The aggregate fitness is a weighted sum of per-nutrient scores,
producing an unbounded positive value where higher is better.

Classes:
    NutrientTarget - Scoring target for a single nutrient
    FitnessEngine  - Computes fitness from member genomes
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from meal_planner.generators.ga_config import GAConfig
from meal_planner.generators.ga_member import Member, Genome, FitnessResult
from meal_planner.utils.nutrient_mapping import (
    NUTRIENT_SPECS,
    get_nutrient_spec,
    get_filter_totals_mapping,
)


# =============================================================================
# NutrientTarget
# =============================================================================

@dataclass
class NutrientTarget:
    """
    Scoring target for a single nutrient.

    Built from a meal_template's targets entry. Each target defines
    the ideal range and how the scoring function should behave.

    Attributes:
        name: Nutrient template key (e.g., "protein", "calories", "gl")
        csv_key: Column name in master.csv for lookup (e.g., "prot_g", "cal")
        min_value: Lower bound of acceptable range (None for headroom-only)
        max_value: Upper bound of acceptable range (None for min-only)
        midpoint: Target center point (calculated or explicit)
        weight: Importance multiplier for this nutrient's contribution
        mode: "midpoint" (reward center of range) or "headroom" (reward distance below max)
        unit: Display unit (e.g., "g", "mg", "")
    """
    name: str
    csv_key: str
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    midpoint: Optional[float] = None
    weight: float = 1.0
    mode: str = "midpoint"
    unit: str = ""

    @property
    def calculated_midpoint(self) -> float:
        """
        Midpoint of the range.

        If explicit midpoint is set, use that. Otherwise calculate
        from min and max. Falls back to max/2 for headroom mode,
        or min for min-only targets.

        Returns:
            Midpoint value
        """
        if self.midpoint is not None:
            return self.midpoint

        if self.min_value is not None and self.max_value is not None:
            return (self.min_value + self.max_value) / 2.0

        if self.max_value is not None:
            return self.max_value / 2.0

        if self.min_value is not None:
            return self.min_value

        return 0.0

    @property
    def range_width(self) -> float:
        """
        Full width of the range (max - min).

        Used for normalizing the linear falloff. Returns max_value
        for headroom mode (range is 0 to max).

        Returns:
            Range width, or 0.0 if not computable
        """
        if self.min_value is not None and self.max_value is not None:
            return self.max_value - self.min_value

        if self.max_value is not None:
            return self.max_value

        return 0.0

    @property
    def half_range(self) -> float:
        """
        Half the range width — the distance from midpoint to boundary.

        This is the denominator in the linear falloff calculation.

        Returns:
            Half range width, or 0.0 if not computable
        """
        return self.range_width / 2.0 if self.range_width > 0 else 0.0

    def summary(self) -> str:
        """Human-readable summary for display."""
        if self.mode == "headroom":
            return (
                f"{self.name}: headroom, max={self.max_value}{self.unit}, "
                f"weight={self.weight}"
            )
        else:
            min_str = f"{self.min_value}" if self.min_value is not None else "?"
            max_str = f"{self.max_value}" if self.max_value is not None else "?"
            return (
                f"{self.name}: midpoint, range={min_str}-{max_str}{self.unit}, "
                f"mid={self.calculated_midpoint:.1f}, weight={self.weight}"
            )

    def __repr__(self) -> str:
        return f"NutrientTarget({self.summary()})"


# =============================================================================
# FitnessEngine
# =============================================================================

class FitnessEngine:
    """
    Computes fitness scores for GA members.

    Built from a meal template's nutrient targets. For each nutrient,
    applies the appropriate scoring function (midpoint or headroom)
    with configurable weights, then sums to an aggregate fitness.

    This engine does NOT apply filters. The orchestrator handles
    filter pass/fail before calling score().
    """

    def __init__(self, targets: List[NutrientTarget], master_loader, config: GAConfig):
        """
        Args:
            targets: Nutrient scoring targets
            master_loader: MasterLoader for food code nutrient lookups
            config: GAConfig (for scoring_weights overrides)
        """
        self.targets = targets
        self.master = master_loader
        self.config = config

        # Build csv_key mapping for totals calculation
        self._csv_mapping = get_filter_totals_mapping()

    @classmethod
    def from_template(
        cls,
        thresholds_mgr,
        meal_type: str,
        template_name: str,
        master_loader,
        config: GAConfig,
    ) -> 'FitnessEngine':
        """
        Build FitnessEngine from a meal_templates entry in config.json.

        Follows the targets_ref from the generation template to find
        the meal_template, then reads its targets dict to construct
        NutrientTarget objects for each defined nutrient.

        Scoring mode is determined by the target's structure:
        - Has both min and max -> midpoint mode
        - Has only max (no min) -> headroom mode
        - Has only min (no max) -> midpoint mode with open upper end

        Weights come from config.scoring_weights, falling back to 1.0.

        Args:
            thresholds_mgr: ThresholdsManager with config data
            meal_type: Meal category (e.g., "lunch")
            template_name: Template name (e.g., "protein_low_carb")
            master_loader: MasterLoader instance
            config: GAConfig with scoring_weights

        Returns:
            Configured FitnessEngine

        Raises:
            ValueError: If template or targets not found
        """
        # Resolve targets_ref from generation template
        gen_template = thresholds_mgr.get_generation_template(meal_type, template_name)
        if not gen_template:
            raise ValueError(
                f"Generation template '{template_name}' not found "
                f"for meal type '{meal_type}'"
            )

        targets_ref = gen_template.get("targets_ref")
        if not targets_ref:
            raise ValueError(
                f"Generation template '{meal_type}/{template_name}' "
                f"has no targets_ref"
            )

        # Parse targets_ref: "meal_templates.breakfast.protein_low_carb"
        ref_parts = targets_ref.split(".")
        if len(ref_parts) < 3 or ref_parts[0] != "meal_templates":
            raise ValueError(
                f"Invalid targets_ref format: '{targets_ref}'. "
                f"Expected 'meal_templates.<meal_type>.<template_name>'"
            )

        target_meal_type = ref_parts[1]
        target_template_name = ref_parts[2]

        # Get the meal_template with actual nutrient ranges
        meal_templates = thresholds_mgr.thresholds.get("meal_templates", {})
        meal_template = meal_templates.get(target_meal_type, {}).get(target_template_name)
        if not meal_template:
            raise ValueError(
                f"Meal template not found at: "
                f"meal_templates.{target_meal_type}.{target_template_name}"
            )

        targets_dict = meal_template.get("targets", {})
        if not targets_dict:
            raise ValueError(
                f"Meal template '{target_meal_type}/{target_template_name}' "
                f"has no targets defined"
            )

        # Build NutrientTarget list from template targets
        nutrient_targets = []
        scoring_weights = config.scoring_weights

        for nutrient_key, target_def in targets_dict.items():
            if not isinstance(target_def, dict):
                continue

            # Look up the CSV key from the nutrient mapping
            spec = get_nutrient_spec(nutrient_key)
            if not spec:
                print(
                    f"Warning: Nutrient '{nutrient_key}' in template targets "
                    f"not found in NUTRIENT_SPECS, skipping"
                )
                continue

            min_val = target_def.get("min")
            max_val = target_def.get("max")

            # Determine scoring mode
            if max_val is not None and min_val is None:
                mode = "headroom"
            else:
                mode = "midpoint"

            # Get weight from config, fall back to 1.0
            weight = scoring_weights.get(nutrient_key, 1.0)

            nutrient_targets.append(
                NutrientTarget(
                    name=nutrient_key,
                    csv_key=spec.csv_key,
                    min_value=min_val,
                    max_value=max_val,
                    weight=weight,
                    mode=mode,
                    unit=spec.unit,
                )
            )

        if not nutrient_targets:
            raise ValueError(
                f"No scoreable nutrients found in template "
                f"'{target_meal_type}/{target_template_name}'"
            )

        return cls(targets=nutrient_targets, master_loader=master_loader, config=config)

    # =========================================================================
    # Scoring (stubs for Steps B, C, D)
    # =========================================================================

    def score(self, member: Member) -> FitnessResult:
        """
        Compute full fitness for a member.

        For each genome (meal slot), calculates nutrient totals from
        food codes, then scores each nutrient against its target using
        the appropriate scoring function (midpoint or headroom).

        Per-nutrient raw scores are multiplied by their weight, then
        summed to produce the aggregate fitness. The full breakdown
        is stored in FitnessResult for inspection and debugging.

        For v1 single-meal, there is one genome. Multi-meal would
        score each genome independently and sum the aggregates.

        Args:
            member: Member with populated genomes

        Returns:
            FitnessResult with aggregate score and per-nutrient breakdown
        """
        nutrient_scores = {}
        aggregate = 0.0

        # For each genome (v1: just one), calculate totals and score
        for genome in member.genomes:
            totals = self.calculate_nutrient_totals(genome)

            for target in self.targets:
                value = totals.get(target.name, 0.0)

                # Apply appropriate scoring function
                if target.mode == "headroom":
                    raw = self.score_nutrient_headroom(value, target)
                else:
                    raw = self.score_nutrient_midpoint(value, target)

                weighted = raw * target.weight
                aggregate += weighted

                # Build per-nutrient detail record
                detail = {
                    "value": round(value, 2),
                    "raw_score": round(raw, 4),
                    "weight": target.weight,
                    "weighted_score": round(weighted, 4),
                    "mode": target.mode,
                }

                if target.mode == "midpoint":
                    detail["midpoint"] = round(target.calculated_midpoint, 2)
                    if target.min_value is not None:
                        detail["min"] = target.min_value
                    if target.max_value is not None:
                        detail["max"] = target.max_value
                else:
                    if target.max_value is not None:
                        detail["max"] = target.max_value
                        detail["headroom"] = round(target.max_value - value, 2)

                nutrient_scores[target.name] = detail

        return FitnessResult(
            aggregate_score=round(aggregate, 4),
            nutrient_scores=nutrient_scores,
            penalties={},
            metadata={
                "genome_count": len(member.genomes),
                "target_count": len(self.targets),
            },
        )

    def score_nutrient_midpoint(self, value: float, target: NutrientTarget) -> float:
        """
        Linear falloff score for a range-based nutrient.

        At midpoint: score = 1.0
        At range boundary (min or max): score = 0.0
        Beyond range: score continues negative (no clamping)

        This means a meal that misses the range entirely gets penalized
        proportionally to how far it missed, giving the GA a gradient
        to follow back toward the target.

        For min-only targets (no max), half_range is set to min_value
        itself, so score = 1.0 at min and falls off linearly below.

        Args:
            value: Actual nutrient total
            target: NutrientTarget with min, max, midpoint

        Returns:
            Raw score (unbounded, can be negative)
        """
        midpoint = target.calculated_midpoint
        half = target.half_range

        if half <= 0:
            # Degenerate range (min == max or not computable)
            # Score 1.0 if exactly at midpoint, 0.0 otherwise
            return 1.0 if abs(value - midpoint) < 0.001 else 0.0

        distance = abs(value - midpoint)
        return 1.0 - (distance / half)
    
    def score_nutrient_headroom(self, value: float, target: NutrientTarget) -> float:
        """
        Headroom score for one-sided max nutrients (e.g., GL).

        Rewards distance below the limit. More headroom = higher score.

        At value = 0:   score = 1.0 (maximum headroom)
        At value = max:  score = 0.0 (no headroom)
        Above max:       score goes negative (penalty)

        Args:
            value: Actual nutrient total
            target: NutrientTarget with max_value

        Returns:
            Raw score (unbounded, can be negative)
        """
        max_val = target.max_value

        if max_val is None or max_val <= 0:
            # No max defined or zero max — can't score headroom
            return 0.0

        return 1.0 - (value / max_val)

    def calculate_nutrient_totals(self, genome: Genome) -> Dict[str, float]:
        """
        Sum nutrient values for all codes in a genome at mult=1.0.

        Looks up each food code in the master database and accumulates
        nutrient totals using the centralized template_key -> csv_key
        mapping from nutrient_mapping.py.

        Args:
            genome: Genome with food codes (all lowercase)

        Returns:
            Dict of template_key -> total value
            e.g., {"calories": 485.0, "protein": 42.3, "gl": 8.0, ...}
        """
        totals = {target.name: 0.0 for target in self.targets}

        # Build name -> csv_key lookup from our targets
        target_csv_keys = {target.name: target.csv_key for target in self.targets}

        for code in genome.codes:
            food = self.master.lookup_code(code)
            if food is None:
                print(f"Warning: Code '{code}' not found in master, skipping")
                continue

            for name, csv_key in target_csv_keys.items():
                totals[name] += food.get(csv_key, 0) or 0

        return totals
    
    # =========================================================================
    # Display
    # =========================================================================

    def display_targets(self) -> None:
        """Print all scoring targets for verification."""
        print("=== GA Scoring Targets ===")
        for target in self.targets:
            print(f"  {target.summary()}")
        print()