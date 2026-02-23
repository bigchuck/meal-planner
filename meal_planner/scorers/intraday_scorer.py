# meal_planner/scorers/intraday_scorer.py
"""
Intraday Diversity Scorer - penalises candidates that repeat ingredient
groups already present in other meals planned for the same day.

Consumes a pre-resolved IntradayMealPresence (built once per scoring
session by DiversityContext.build()) and the candidate's own items.

For each group the candidate contributes to, the scorer counts how many
source meals already contain that group (occurrence_count) and applies
an additive penalty:

    group_penalty = occurrences * penalty_per_occurrence * penalty_slope

Penalties accumulate unbounded across groups.  The exhaustive pipeline
clips the output to [0.0, 1.0] via the standard raw_score presentation;
the GA consumes the raw penalty directly from FitnessResult.penalties.
"""
from typing import Dict, Any, List, Optional

from .base_scorer import Scorer
from .diversity_context import DiversityContext, IntradayMealPresence
from meal_planner.models.scoring_context import ScoringContext, ScoringResult


class IntradayScorer(Scorer):
    """
    Scores a candidate meal for intraday ingredient group repetition.

    For each group the candidate touches, penalises based on how many
    other source meals (pending + planning references) already contain
    that group.  Multiple source-meal occurrences compound additively.

    Construction:
        IntradayScorer is initialised with the standard scorer arguments
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
        return "intraday"

    def calculate_score(self, context: ScoringContext) -> ScoringResult:
        """
        Score a candidate meal for intraday group repetition.

        Args:
            context: Scoring context containing the candidate's items.

        Returns:
            ScoringResult with raw_score in [0.0, 1.0] and a details
            dict describing per-group occurrences and penalties.
        """
        if self._diversity_context is None or self._diversity_context.intraday is None:
            return ScoringResult(
                scorer_name=self.name,
                raw_score=1.0,
                details={"reason": "intraday scorer not configured or disabled"},
            )

        presence: IntradayMealPresence = self._diversity_context.intraday

        intraday_cfg = self.thresholds.get_intraday_diversity_config()
        if intraday_cfg is None:
            return ScoringResult(
                scorer_name=self.name,
                raw_score=1.0,
                details={"reason": "intraday config unavailable"},
            )

        groups: Dict[str, Any] = intraday_cfg.get("groups", {})
        if not groups:
            return ScoringResult(
                scorer_name=self.name,
                raw_score=1.0,
                details={"reason": "no groups defined"},
            )

        penalty_per_occurrence: float = intraday_cfg["penalty_per_occurrence"]
        penalty_slope: float          = intraday_cfg["penalty_slope"]

        # Determine which groups the candidate contributes to
        candidate_groups = self._candidate_groups(context.items, groups)

        # Score each group
        group_details: List[Dict[str, Any]] = []
        total_penalty = 0.0

        for group_name in sorted(groups.keys()):
            if not candidate_groups.get(group_name, False):
                continue  # candidate doesn't touch this group

            occurrences = presence.occurrence_count(group_name)
            if occurrences == 0:
                continue  # no repetition

            penalty = occurrences * penalty_per_occurrence * penalty_slope

            group_details.append({
                "group":       group_name,
                "occurrences": occurrences,
                "penalty_per_occurrence": penalty_per_occurrence,
                "penalty_slope":          penalty_slope,
                "penalty":     round(penalty, 4),
            })

            total_penalty += penalty

        raw_score = self._clamp_score(1.0 - total_penalty)

        return ScoringResult(
            scorer_name=self.name,
            raw_score=raw_score,
            details={
                "groups":            group_details,
                "total_penalty":     round(total_penalty, 4),
                "resolved_sources":  presence.resolved_sources,
                "skipped_sources":   presence.skipped_sources,
                "candidate_groups":  [g for g, hit in candidate_groups.items() if hit],
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _candidate_groups(
        self,
        items: List[Dict[str, Any]],
        groups: Dict[str, Any],
    ) -> Dict[str, bool]:
        """
        Determine which groups the candidate contributes to.

        A group is considered present if any candidate item with mult > 0
        matches one of the group's codes.

        Args:
            items:  Candidate meal items from ScoringContext.
            groups: Normalised group definitions (group_name -> {codes: [...]}).

        Returns:
            Dict mapping group_name -> True if candidate touches that group.
        """
        # Build code -> [group_name, ...] index
        index: Dict[str, List[str]] = {}
        for group_name, group_def in groups.items():
            for code in group_def.get("codes", []):
                cu = code.upper()
                if cu not in index:
                    index[cu] = []
                index[cu].append(group_name)

        hit: Dict[str, bool] = {}
        for item in items or []:
            if not isinstance(item, dict) or "code" not in item:
                continue
            mult = float(item.get("mult", 1.0))
            if mult <= 0.0:
                continue
            cu = str(item["code"]).strip().upper()
            for group_name in index.get(cu, []):
                hit[group_name] = True

        return hit