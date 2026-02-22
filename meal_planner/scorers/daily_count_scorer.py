# meal_planner/scorers/daily_count_scorer.py
"""
Daily Count Scorer - penalises candidates that push a group's daily
total above its configured maximum.

Consumes a pre-resolved DailyCountTally (built once per scoring session
by DiversityContext.build()) and the candidate's own items to compute
the final per-group totals, then applies a linear slope penalty for
any excess above max_total.

Score interpretation:
    1.0  - no group is over its daily limit (including this candidate)
    0.0  - penalty is >= 1.0 (one or more groups heavily exceeded)

The raw score feeds into FitnessResult.penalties under the key
"diversity_daily_count", consistent with how other penalty components
are stored.
"""
from typing import Dict, Any, List, Optional

from .base_scorer import Scorer
from .diversity_context import DiversityContext, DailyCountTally
from meal_planner.models.scoring_context import ScoringContext, ScoringResult


class DailyCountScorer(Scorer):
    """
    Scores a candidate meal against daily ingredient-count limits.

    For each configured group the scorer:
        1. Looks up the pre-resolved tally (codes already seen today
           across pending and any designated planning sources).
        2. Adds the candidate's own contribution for that group.
        3. Computes excess = max(0, combined_total - max_total).
        4. Applies penalty = excess * penalty_slope.

    The sum of all group penalties is subtracted from a perfect score
    of 1.0, clamped to [0.0, 1.0].

    Construction:
        DailyCountScorer is initialised with the standard scorer
        arguments plus an optional DiversityContext.  When
        diversity_context is None (scorer disabled / config absent)
        calculate_score() returns a neutral score of 1.0.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        master,
        thresholds,
        user_prefs,
        diversity_context: Optional[DiversityContext] = None,
    ):
        """
        Initialise scorer.

        Args:
            config:            Scorer-specific config (currently unused;
                               all parameters come from thresholds).
            master:            MasterLoader instance.
            thresholds:        ThresholdsManager instance.
            user_prefs:        UserPreferencesManager instance.
            diversity_context: Pre-built DiversityContext for this session.
                               If None the scorer returns neutral scores.
        """
        super().__init__(config, master, thresholds, user_prefs)
        self._diversity_context = diversity_context

    # ------------------------------------------------------------------
    # Scorer interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "daily_count"

    def calculate_score(self, context: ScoringContext) -> ScoringResult:
        """
        Score a candidate meal for daily ingredient count violations.

        Args:
            context: Scoring context containing the candidate's items.

        Returns:
            ScoringResult with raw_score in [0.0, 1.0] and a details
            dict describing per-group contributions and penalties.
        """
        # ------------------------------------------------------------------
        # Guard: no context means scorer was not configured / is disabled
        # ------------------------------------------------------------------
        if self._diversity_context is None or self._diversity_context.daily_count is None:
            return ScoringResult(
                scorer_name=self.name,
                raw_score=1.0,
                details={"reason": "daily_count scorer not configured or disabled"},
            )

        tally: DailyCountTally = self._diversity_context.daily_count

        # ------------------------------------------------------------------
        # Load group definitions from thresholds
        # ------------------------------------------------------------------
        dc_config = self.thresholds.get_daily_count_config()
        if dc_config is None:
            return ScoringResult(
                scorer_name=self.name,
                raw_score=1.0,
                details={"reason": "daily_count config unavailable"},
            )

        groups: List[Dict[str, Any]] = dc_config.get("groups", [])
        if not groups:
            return ScoringResult(
                scorer_name=self.name,
                raw_score=1.0,
                details={"reason": "no groups defined"},
            )

        # ------------------------------------------------------------------
        # Build candidate contribution per group
        # ------------------------------------------------------------------
        candidate_code_mults = self._extract_codes_with_mult(context.items)
        candidate_contributions = self._compute_contributions(
            candidate_code_mults, groups
        )

        # ------------------------------------------------------------------
        # Score each group
        # ------------------------------------------------------------------
        group_details: List[Dict[str, Any]] = []
        total_penalty = 0.0

        for group in groups:
            gid          = group["group_id"]          # already uppercase
            max_total    = group["max_total"]
            penalty_slope = group["penalty_slope"]
            label        = group.get("label", gid)

            existing     = tally.get(gid)
            candidate    = candidate_contributions.get(gid, 0.0)
            combined     = existing + candidate

            excess       = max(0.0, combined - max_total)
            penalty      = excess * penalty_slope

            group_details.append({
                "group_id":    gid,
                "label":       label,
                "existing":    round(existing, 4),
                "candidate":   round(candidate, 4),
                "combined":    round(combined, 4),
                "max_total":   max_total,
                "excess":      round(excess, 4),
                "penalty_slope": penalty_slope,
                "penalty":     round(penalty, 4),
            })

            total_penalty += penalty

        # ------------------------------------------------------------------
        # Final score
        # ------------------------------------------------------------------
        raw_score = self._clamp_score(1.0 - total_penalty)

        return ScoringResult(
            scorer_name=self.name,
            raw_score=raw_score,
            details={
                "groups":           group_details,
                "total_penalty":    round(total_penalty, 4),
                "resolved_sources": tally.resolved_sources,
                "skipped_sources":  tally.skipped_sources,
                "candidate_codes":  [c for c, _ in candidate_code_mults],
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_codes_with_mult(self, items: List[Dict[str, Any]]) -> List[tuple]:
        """
        Extract (code, multiplier) pairs from candidate items.

        Time marker dicts (no 'code' key) are skipped.
        Multiplier defaults to 1.0 when the field is absent.

        Args:
            items: Candidate meal items list from ScoringContext.

        Returns:
            List of (uppercase_code, mult) tuples.
        """
        result = []
        for item in items or []:
            if isinstance(item, dict) and "code" in item:
                code = str(item["code"]).strip().upper()
                if code:
                    mult = float(item.get("mult", 1.0))
                    result.append((code, mult))
        return result

    def _compute_contributions(
        self,
        code_mults: List[tuple],
        groups: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """
        Sum the candidate's contributions per group.

        Contribution per item = code_value * item_multiplier.
        A code may appear in multiple groups; each group receives its
        contribution independently (multi-group accumulation).

        Args:
            code_mults: List of (uppercase_code, mult) tuples from the candidate.
            groups:     Group definitions from normalised config.

        Returns:
            Dict mapping group_id (uppercase) to total contribution from
            this candidate.
        """
        # Build index: code -> [(group_id, code_value), ...]
        index: Dict[str, List[tuple]] = {}
        for group in groups:
            gid = group["group_id"]
            for code, code_value in group.get("codes", {}).items():
                cu = code.upper()
                if cu not in index:
                    index[cu] = []
                index[cu].append((gid, float(code_value)))

        contributions: Dict[str, float] = {}
        for code, mult in code_mults:
            matches = index.get(code)
            if matches:
                for gid, code_value in matches:
                    contributions[gid] = (
                        contributions.get(gid, 0.0) + code_value * mult
                    )

        return contributions