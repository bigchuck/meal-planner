# meal_planner/scorers/interday_scorer.py
"""
Interday Diversity Scorer - penalises candidates that repeat ingredient
groups present in the same meal slot on recent prior days.

Consumes a pre-resolved InterdayGroupPresence (built once per scoring
session by DiversityContext.build()) and the candidate's own items plus
its target meal slot (context.meal_slot).

Penalty formula per group, per prior day:

    recency_factor = recency_decay ** (day_offset - 1)
    same_slot_penalty  = group_weight * penalty_slope * recency_factor
    cross_slot_penalty = same_slot_penalty * cross_slot_weight

Penalties accumulate unbounded across groups and days.  The exhaustive
pipeline clips the output to [0.0, 1.0] via _clamp_score(); the GA
consumes the raw penalty directly from FitnessResult.penalties.

If context.meal_slot is None the scorer returns a neutral 1.0 — this
keeps legacy call sites that pre-date Step 2 safe.
"""
from typing import Dict, Any, List, Optional

from .base_scorer import Scorer
from .diversity_context import DiversityContext, InterdayGroupPresence
from meal_planner.models.scoring_context import ScoringContext, ScoringResult


class InterdayScorer(Scorer):
    """
    Scores a candidate meal for interday ingredient group repetition.

    For each group the candidate touches, inspects the same meal slot
    across recent history days and applies a recency-weighted additive
    penalty.  Cross-slot appearances incur a reduced penalty scaled by
    cross_slot_weight (default 0.0 = disabled).

    Construction:
        InterdayScorer is initialised with the standard scorer arguments
        plus an optional DiversityContext.  When diversity_context is None
        (scorer disabled / config absent) calculate_score() returns 1.0.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        master,
        thresholds,
        user_prefs,
        diversity_context: Optional[DiversityContext] = None,
    ):
        super().__init__(config, master, thresholds, user_prefs)
        self._diversity_context = diversity_context

    # ------------------------------------------------------------------
    # Scorer interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "interday"

    def calculate_score(self, context: ScoringContext) -> ScoringResult:
        """
        Score a candidate meal for interday group repetition.

        Args:
            context: Scoring context containing the candidate's items and
                     meal_slot (uppercase canonical name e.g. "LUNCH").

        Returns:
            ScoringResult with raw_score in [0.0, 1.0] and a details
            dict describing per-group, per-day penalties.
        """
        # ------------------------------------------------------------------
        # Guard: context or presence missing
        # ------------------------------------------------------------------
        if self._diversity_context is None or self._diversity_context.interday is None:
            return ScoringResult(
                scorer_name=self.name,
                raw_score=1.0,
                details={"reason": "interday scorer not configured or disabled"},
            )

        meal_slot = getattr(context, "meal_slot", None)
        if not meal_slot:
            return ScoringResult(
                scorer_name=self.name,
                raw_score=1.0,
                details={"reason": "meal_slot not set on ScoringContext"},
            )

        meal_slot = meal_slot.strip().upper()

        # ------------------------------------------------------------------
        # Load config
        # ------------------------------------------------------------------
        interday_cfg = self.thresholds.get_interday_config()
        if interday_cfg is None:
            return ScoringResult(
                scorer_name=self.name,
                raw_score=1.0,
                details={"reason": "interday config unavailable"},
            )

        groups: Dict[str, Any] = interday_cfg.get("groups", {})
        if not groups:
            return ScoringResult(
                scorer_name=self.name,
                raw_score=1.0,
                details={"reason": "no groups defined"},
            )

        lookback_days:    int   = interday_cfg["lookback_days"]
        recency_decay:    float = interday_cfg["recency_decay"]
        cross_slot_weight: float = interday_cfg.get("cross_slot_weight", 0.0)
        penalty_slope:    float = interday_cfg["penalty_slope"]

        presence: InterdayGroupPresence = self._diversity_context.interday

        # ------------------------------------------------------------------
        # Determine which groups the candidate contributes to
        # ------------------------------------------------------------------
        candidate_groups = self._candidate_groups(context.items, groups)
        if not candidate_groups:
            return ScoringResult(
                scorer_name=self.name,
                raw_score=1.0,
                details={
                    "reason":          "candidate touches no tracked groups",
                    "total_penalty":   0.0,
                    "resolved_days":   presence.resolved_days,
                    "skipped_days":    presence.skipped_days,
                },
            )

        # ------------------------------------------------------------------
        # Accumulate penalties across days and groups
        # ------------------------------------------------------------------
        group_details: List[Dict[str, Any]] = []
        total_penalty = 0.0

        for offset in range(1, lookback_days + 1):
            if offset not in presence.resolved_days:
                continue  # no log data for this day

            recency_factor = recency_decay ** (offset - 1)

            for group_name in sorted(candidate_groups):
                # --- same-slot penalty ---
                same_slot_tally = presence.get_slot(offset, meal_slot)
                same_weight = same_slot_tally.get(group_name, 0.0)

                if same_weight > 0.0:
                    penalty = same_weight * penalty_slope * recency_factor
                    total_penalty += penalty
                    group_details.append({
                        "day_offset":     offset,
                        "slot":           meal_slot,
                        "match":          "same_slot",
                        "group":          group_name,
                        "history_weight": round(same_weight, 4),
                        "recency_factor": round(recency_factor, 4),
                        "penalty_slope":  penalty_slope,
                        "penalty":        round(penalty, 4),
                    })

                # --- cross-slot penalty (fast-path skip when weight is 0) ---
                if cross_slot_weight > 0.0:
                    day_data = presence.day_slots.get(offset, {})
                    for slot_key, slot_tally in day_data.items():
                        if slot_key == meal_slot:
                            continue  # already handled above
                        cross_weight = slot_tally.get(group_name, 0.0)
                        if cross_weight > 0.0:
                            penalty = (
                                cross_weight
                                * penalty_slope
                                * recency_factor
                                * cross_slot_weight
                            )
                            total_penalty += penalty
                            group_details.append({
                                "day_offset":       offset,
                                "slot":             slot_key,
                                "match":            "cross_slot",
                                "group":            group_name,
                                "history_weight":   round(cross_weight, 4),
                                "recency_factor":   round(recency_factor, 4),
                                "penalty_slope":    penalty_slope,
                                "cross_slot_weight": cross_slot_weight,
                                "penalty":          round(penalty, 4),
                            })

        raw_score = self._clamp_score(1.0 - total_penalty)

        return ScoringResult(
            scorer_name=self.name,
            raw_score=raw_score,
            details={
                "meal_slot":       meal_slot,
                "group_details":   group_details,
                "total_penalty":   round(total_penalty, 4),
                "resolved_days":   presence.resolved_days,
                "skipped_days":    presence.skipped_days,
                "candidate_groups": sorted(candidate_groups),
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _candidate_groups(
        self,
        items: List[Dict[str, Any]],
        groups: Dict[str, Any],
    ) -> List[str]:
        """
        Determine which tracked groups the candidate contributes to.

        A group is considered present if any candidate item with mult > 0
        matches one of the group's codes.

        Args:
            items:  Candidate meal items from ScoringContext.
            groups: Normalised group definitions (group_name -> {codes: [...]}).

        Returns:
            List of group_names the candidate touches (uppercase).
        """
        # Build code -> [group_name, ...] index
        index: Dict[str, List[str]] = {}
        for group_name, group_def in groups.items():
            for code in group_def.get("codes", []):
                cu = code.upper()
                if cu not in index:
                    index[cu] = []
                index[cu].append(group_name)

        hit: set = set()
        for item in items or []:
            if not isinstance(item, dict) or "code" not in item:
                continue
            mult = float(item.get("mult", 1.0))
            if mult <= 0.0:
                continue
            cu = str(item["code"]).strip().upper()
            for group_name in index.get(cu, []):
                hit.add(group_name)

        return list(hit)