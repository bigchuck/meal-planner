# meal_planner/generators/ga_population.py
"""
Population management for the Genetic Algorithm engine.

The population has two tiers:
- General population: Target size from config, culled by fitness after each epoch.
- Immigrant pool: Random members with epoch-counted tenure, protected from culling.

Both tiers are available for breeding selection. Offspring always enter the
general population regardless of parent tier.

For the initial milestone, immigrant pool lifecycle (graduation, epoch-based
aging) and diversity metrics are stubbed. The core container with uniqueness
checking, ranking, and serialization is fully implemented.

Classes:
    DiversityMetrics - Snapshot of population health (stub)
    Population       - Two-tier population manager
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Set
from collections import OrderedDict

from meal_planner.generators.ga_config import GAConfig, MemberTier
from meal_planner.generators.ga_member import Member, FitnessResult, Genome


# =============================================================================
# DiversityMetrics (stub for future epochs)
# =============================================================================

@dataclass
class DiversityMetrics:
    """
    Snapshot of population health for epoch progress display.

    Populated by compute_diversity_metrics() during epoch processing.
    Stubbed for the initial milestone; will be fleshed out when
    breeding and epoch loops are implemented.
    """
    elite_turnover: float = 0.0
    acceptance_rate: float = 0.0
    duplicate_rate: float = 0.0
    immigrant_graduation_rate: float = 0.0
    best_score: float = 0.0
    median_score: float = 0.0
    worst_score: float = 0.0
    generation_count: int = 0


# =============================================================================
# Population
# =============================================================================

class Population:
    """
    Two-tier population manager.

    General population: Target size from config. Members are ranked by
    fitness (descending), with genome length (ascending) as tiebreaker.
    After each epoch, lowest-ranked members beyond the target size are culled.

    Immigrant pool: Random members injected each epoch with a fixed tenure.
    Protected from culling during their tenure. On aging out, they are
    batch-inserted into the general population, which is then reranked
    and culled. Immigrants participate in breeding selection alongside
    general population members.

    Uniqueness is enforced across both tiers. A member's identity_key()
    (tuple of frozensets of codes per genome) must be unique in the
    entire population. A rolling history of recently generated identity
    keys detects the "spinning wheels" condition where the same
    candidates are being regenerated repeatedly.
    """

    # Max size of the rolling generation history
    GENERATION_HISTORY_LIMIT = 1000

    def __init__(self, config: GAConfig):
        """
        Initialize empty population.

        Args:
            config: GA configuration with population_size, immigrant params, etc.
        """
        self.config = config

        # General population members, maintained in ranked order
        self._general: List[Member] = []

        # Immigrant pool members
        self._immigrants: List[Member] = []

        # Identity keys of all current members (both tiers) for O(1) uniqueness
        self._identity_set: Set[Tuple] = set()

        # Rolling history of generated identity keys for repeat detection
        self._generation_history: OrderedDict = OrderedDict()

        # Epoch tracking for diversity metrics
        self._previous_elite_keys: List[Tuple] = []

        # Counters for current epoch (reset each epoch)
        self._epoch_stats = {
            "attempted": 0,
            "accepted": 0,
            "duplicate_population": 0,
            "duplicate_history": 0,
        }

        # Running member ID counter
        self._next_id = 1

    # =========================================================================
    # Properties - population access
    # =========================================================================

    @property
    def general_members(self) -> List[Member]:
        """General population members, sorted by fitness (best first)."""
        return list(self._general)

    @property
    def immigrant_members(self) -> List[Member]:
        """Current immigrant pool members."""
        return list(self._immigrants)

    @property
    def all_members(self) -> List[Member]:
        """
        Combined general + immigrant members, sorted by fitness.

        Used for breeding selection across both tiers.
        """
        combined = self._general + self._immigrants
        combined.sort(key=self._sort_key)
        return combined

    @property
    def general_size(self) -> int:
        """Number of members in general population."""
        return len(self._general)

    @property
    def immigrant_size(self) -> int:
        """Number of members in immigrant pool."""
        return len(self._immigrants)

    @property
    def size(self) -> int:
        """Total members across both tiers."""
        return len(self._general) + len(self._immigrants)

    # =========================================================================
    # Member insertion
    # =========================================================================

    def assign_id(self, member: Member) -> None:
        """
        Assign the next available member ID.

        Args:
            member: Member to assign an ID to
        """
        member.member_id = f"GA-{self._next_id}"
        self._next_id += 1

    def add_member(self, member: Member) -> bool:
        """
        Add a validated, scored member to the appropriate tier.

        Checks uniqueness against entire population (both tiers) and
        against the rolling generation history. If unique, the member
        is inserted into the correct tier based on member.tier.

        The member must already have an assigned member_id (via assign_id)
        and should be validated and (optionally) scored before insertion.

        Args:
            member: Validated member to insert

        Returns:
            True if added (unique), False if duplicate
        """
        self._epoch_stats["attempted"] += 1

        identity = member.identity_key()

        # Check against current population
        if identity in self._identity_set:
            self._epoch_stats["duplicate_population"] += 1
            return False

        # Check against rolling generation history
        if identity in self._generation_history:
            self._epoch_stats["duplicate_history"] += 1
            return False

        # Record in generation history
        self.record_generation_attempt(identity)

        # Add to identity set
        self._identity_set.add(identity)

        # Insert into appropriate tier
        if member.tier == MemberTier.IMMIGRANT:
            self._immigrants.append(member)
        else:
            self._general.append(member)

        self._epoch_stats["accepted"] += 1
        return True

    def is_duplicate(self, member: Member) -> bool:
        """
        Check if member already exists in population or recent history.

        Does not modify any state. Use for pre-check before scoring
        to avoid scoring a member that will be rejected.

        Args:
            member: Member to check

        Returns:
            True if duplicate
        """
        identity = member.identity_key()
        return identity in self._identity_set or identity in self._generation_history

    # =========================================================================
    # Ranking and culling
    # =========================================================================

    def rerank(self) -> None:
        """
        Re-sort general population by fitness.

        Primary key: aggregate fitness score (descending, higher is better)
        Secondary key: genome length (ascending, shorter preferred)

        Members without fitness results sort to the end.
        """
        self._general.sort(key=self._sort_key)

    def cull_general(self) -> int:
        """
        Trim general population to target size.

        Removes lowest-ranked members (end of sorted list) that exceed
        the configured population_size. Removes their identity keys
        from the uniqueness set.

        Returns:
            Number of members culled
        """
        target = self.config.population_size
        if len(self._general) <= target:
            return 0

        # Members to remove (lowest ranked, at end of list)
        culled = self._general[target:]
        self._general = self._general[:target]

        # Remove culled identity keys
        for member in culled:
            self._identity_set.discard(member.identity_key())

        return len(culled)

    @staticmethod
    def _sort_key(member: Member):
        """
        Sort key for population ranking.

        Primary: fitness score descending (negate for ascending sort)
        Secondary: genome length ascending (shorter preferred)
        Unscored members sort to the end (score = negative infinity)
        """
        if member.fitness is not None:
            score = -member.fitness.aggregate_score  # negate for descending
        else:
            score = float('inf')  # unscored sort to end
        return (score, member.genome_length())

    # =========================================================================
    # Immigrant pool lifecycle (stubs for future implementation)
    # =========================================================================

    def graduate_immigrants(self, current_epoch: int) -> Tuple[int, int]:
        """
        Process aged-out immigrants at start of epoch.

        Immigrants whose birth_epoch + tenure <= current_epoch are removed
        from the immigrant pool. They are batch-inserted into the general
        population, which is then reranked and culled.

        Args:
            current_epoch: Current epoch number

        Returns:
            Tuple of (num_graduated_to_general, num_culled_on_graduation)
        """
        tenure = self.config.immigrant_tenure_epochs
        graduating = []
        remaining = []

        for member in self._immigrants:
            if member.birth_epoch + tenure <= current_epoch:
                graduating.append(member)
            else:
                remaining.append(member)

        if not graduating:
            return (0, 0)

        self._immigrants = remaining

        # Move graduating immigrants to general population
        # Their identity keys are already in _identity_set
        for member in graduating:
            member.tier = MemberTier.GENERAL
            self._general.append(member)

        # Rerank and cull
        self.rerank()
        num_culled = self.cull_general()

        return (len(graduating), num_culled)

    # =========================================================================
    # Selection for breeding (stub for future implementation)
    # =========================================================================

    def select_one(self) -> Member:
        """
        Select a single member via rank-based roulette.

        Uses the same weighting as select_pair(): combined population
        (general + immigrant) ranked by fitness, with selection
        probability proportional to (N - rank + 1) ^ pressure.

        Returns:
            Selected Member

        Raises:
            ValueError: If population is empty
        """
        import random

        combined = self.all_members
        if not combined:
            raise ValueError("Cannot select from empty population")

        n = len(combined)
        pressure = self.config.selection_pressure
        weights = [(n - i) ** pressure for i in range(n)]

        return random.choices(combined, weights=weights, k=1)[0]

    def select_pair(self) -> Tuple[Member, Member]:
        """
        Select two distinct members for breeding via rank-based roulette.

        Operates over combined population (general + immigrant).
        Higher-ranked members have proportionally higher selection
        probability controlled by config.selection_pressure.

        Returns:
            Tuple of two distinct Members

        Raises:
            ValueError: If population has fewer than 2 members
        """
        import random

        combined = self.all_members
        if len(combined) < 2:
            raise ValueError(
                f"Need at least 2 members for breeding, have {len(combined)}"
            )

        # Rank-based roulette: assign weight based on rank position
        # Rank 1 (best) gets highest weight, rank N gets lowest
        # Weight = (N - rank + 1) ^ pressure
        n = len(combined)
        pressure = self.config.selection_pressure
        weights = [(n - i) ** pressure for i in range(n)]

        # Select first parent
        parent_a = random.choices(combined, weights=weights, k=1)[0]

        # Select second parent (must be different)
        # Remove parent_a from candidates and adjust weights
        remaining = []
        remaining_weights = []
        for i, member in enumerate(combined):
            if member.member_id != parent_a.member_id:
                remaining.append(member)
                remaining_weights.append(weights[i])

        parent_b = random.choices(remaining, weights=remaining_weights, k=1)[0]

        return (parent_a, parent_b)

    # =========================================================================
    # Generation history for duplicate detection
    # =========================================================================

    def record_generation_attempt(self, identity_key: Tuple) -> None:
        """
        Record a candidate's identity in rolling history.

        Used to detect repeated generation of the same candidates
        ("spinning wheels" condition). History is bounded to
        GENERATION_HISTORY_LIMIT entries, oldest entries are evicted.

        Args:
            identity_key: Member's identity_key() result
        """
        # Move to end if already present (update recency)
        if identity_key in self._generation_history:
            self._generation_history.move_to_end(identity_key)
        else:
            self._generation_history[identity_key] = True

        # Evict oldest if over limit
        while len(self._generation_history) > self.GENERATION_HISTORY_LIMIT:
            self._generation_history.popitem(last=False)

    def get_generation_repeat_rate(self) -> float:
        """
        Fraction of this epoch's generation attempts that were repeats.

        Returns:
            0.0 to 1.0 ratio, or 0.0 if no attempts
        """
        attempted = self._epoch_stats["attempted"]
        if attempted == 0:
            return 0.0
        repeats = (
            self._epoch_stats["duplicate_population"]
            + self._epoch_stats["duplicate_history"]
        )
        return repeats / attempted

    # =========================================================================
    # Diversity metrics
    # =========================================================================

    def compute_diversity_metrics(self, epoch: int) -> DiversityMetrics:
        """
        Compute population health metrics for this epoch.

        Compares current elite against previous epoch's snapshot
        to determine turnover rate.

        Args:
            epoch: Current epoch number

        Returns:
            DiversityMetrics snapshot
        """
        metrics = DiversityMetrics()
        metrics.generation_count = self._epoch_stats["attempted"]

        # Acceptance rate
        attempted = self._epoch_stats["attempted"]
        if attempted > 0:
            metrics.acceptance_rate = self._epoch_stats["accepted"] / attempted
            metrics.duplicate_rate = 1.0 - metrics.acceptance_rate

        # Score statistics from general population
        scored = [m for m in self._general if m.fitness is not None]
        if scored:
            scores = [m.fitness.aggregate_score for m in scored]
            scores.sort(reverse=True)
            metrics.best_score = scores[0]
            metrics.worst_score = scores[-1]
            mid = len(scores) // 2
            metrics.median_score = scores[mid]

        # Elite turnover
        if self._previous_elite_keys:
            current_elite = [m.identity_key() for m in self._general[:len(self._previous_elite_keys)]]
            if current_elite:
                changed = sum(
                    1 for k in current_elite if k not in self._previous_elite_keys
                )
                metrics.elite_turnover = changed / len(current_elite)

        return metrics

    def snapshot_elite(self, top_n: int = 10) -> None:
        """
        Capture current top-N identity keys for next epoch's turnover calc.

        Should be called at end of each epoch after final ranking.

        Args:
            top_n: Number of top members to track
        """
        self._previous_elite_keys = [
            m.identity_key() for m in self._general[:top_n]
        ]

    def reset_epoch_stats(self) -> None:
        """Reset per-epoch counters. Call at start of each epoch."""
        self._epoch_stats = {
            "attempted": 0,
            "accepted": 0,
            "duplicate_population": 0,
            "duplicate_history": 0,
        }

    # =========================================================================
    # Display
    # =========================================================================

    def display_summary(self, verbose: bool = False) -> None:
        """
        Print population summary to terminal.

        Args:
            verbose: If True, show individual member details
        """
        print(f"\n=== GA POPULATION ===")
        print(f"General population:   {self.general_size}/{self.config.population_size}")
        print(f"Immigrant pool:       {self.immigrant_size}")
        print(f"Total unique:         {len(self._identity_set)}")
        print(f"Generation history:   {len(self._generation_history)}")
        print()

        if self._general:
            scored = [m for m in self._general if m.fitness is not None]
            if scored:
                scores = [m.fitness.aggregate_score for m in scored]
                print(f"Scored members:       {len(scored)}")
                print(f"Best score:           {max(scores):.3f}")
                print(f"Median score:         {sorted(scores)[len(scores)//2]:.3f}")
                print(f"Worst score:          {min(scores):.3f}")
            else:
                print(f"No members scored yet")
            print()

        if verbose and self._general:
            print(f"{'Rank':<6}{'ID':<10}{'Score':<10}{'Len':<6}{'Origin':<8}{'Codes'}")
            print(f"{'-'*6}{'-'*10}{'-'*10}{'-'*6}{'-'*8}{'-'*50}")
            for rank, member in enumerate(self._general, 1):
                score_str = (
                    f"{member.fitness.aggregate_score:.3f}"
                    if member.fitness else "---"
                )
                codes_str = member._build_description()
                if len(codes_str) > 47:
                    codes_str = codes_str[:44] + "..."
                print(
                    f"{rank:<6}{member.member_id:<10}{score_str:<10}"
                    f"{member.genome_length():<6}{member.origin.value:<8}"
                    f"{codes_str}"
                )
                
                if verbose and member.fitness and member.fitness.nutrient_scores:
                    for nname, ndata in member.fitness.nutrient_scores.items():
                        print(
                            f"{'':>10}{nname}: {ndata['value']:.1f} "
                            f"raw={ndata['raw_score']:.3f} "
                            f"w={ndata['weighted_score']:.3f}"
                         )
                        
            print()

    # =========================================================================
    # Serialization
    # =========================================================================

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize entire population state for ga_population.json.

        Includes both tiers, config snapshot, generation history size,
        and epoch state needed for restart.

        Returns:
            Complete population state dict
        """
        return {
            "config": self.config.to_dict(),
            "general_population": [m.to_dict() for m in self._general],
            "immigrant_pool": [m.to_dict() for m in self._immigrants],
            "next_id": self._next_id,
            "generation_history_size": len(self._generation_history),
            "stats": {
                "general_size": self.general_size,
                "immigrant_size": self.immigrant_size,
                "total_unique": len(self._identity_set),
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], config: GAConfig) -> 'Population':
        """
        Restore population from saved state for restart capability.

        Rebuilds the identity set from loaded members. Generation
        history is not restored (bounded and regenerated naturally).

        Args:
            data: Dict from to_dict()
            config: GAConfig (may differ from saved config)

        Returns:
            Restored Population instance
        """
        pop = cls(config)

        # Restore general population
        for member_data in data.get("general_population", []):
            member = Member.from_dict(member_data)
            pop._general.append(member)
            pop._identity_set.add(member.identity_key())

        # Restore immigrant pool
        for member_data in data.get("immigrant_pool", []):
            member = Member.from_dict(member_data)
            pop._immigrants.append(member)
            pop._identity_set.add(member.identity_key())

        # Restore ID counter
        pop._next_id = data.get("next_id", pop.size + 1)

        # Rerank general population
        pop.rerank()

        return pop

    def to_candidate_list(self) -> List[Dict[str, Any]]:
        """
        Export general population as reco-compatible candidate dicts.

        Used when GA completes to write results into the reco workspace.
        Only exports general population (immigrants are transient).

        Returns:
            List of candidate dicts sorted by fitness (best first)
        """
        return [m.to_candidate_dict() for m in self._general]