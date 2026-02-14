# meal_planner/generators/ga_member.py
"""
Member and Genome representation for the Genetic Algorithm engine.

A Member is a candidate solution in the GA population. Each Member
contains one or more Genomes (one per meal slot), where each Genome
is a sorted list of food codes with implicit multiplier of 1.0.

Two Members are considered identical (for population uniqueness) if
they have the same set of food codes in each corresponding genome.
A single different food code in any genome is enough to distinguish them.

Classes:
    Genome        - A single meal expressed as sorted food codes
    FitnessResult - Detailed scoring breakdown (per-nutrient + aggregate)
    Member        - A candidate with genomes, fitness, and population metadata
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, FrozenSet
from datetime import datetime

from meal_planner.generators.ga_config import GAConfig, MemberOrigin, MemberTier


# =============================================================================
# Genome
# =============================================================================

@dataclass
class Genome:
    """
    A single meal expressed as a sorted list of food codes.

    Each genome maps to one meal slot (e.g., "lunch"). All codes have
    an implicit multiplier of 1.0. Codes are stored sorted for
    consistent hashing and comparison.

    Attributes:
        codes: Sorted list of food codes (e.g., ["FI.8", "SO.1", "VE.14"])
        meal_slot: Which meal slot this genome represents (e.g., "lunch")
    """
    codes: List[str]
    meal_slot: str

    def __post_init__(self):
        """Ensure codes are sorted on creation."""
        self.codes = sorted(self.codes)

    def as_frozen(self) -> FrozenSet[str]:
        """
        Immutable set representation for hashing.

        Returns:
            FrozenSet of food codes
        """
        return frozenset(self.codes)

    def contains_code(self, code: str) -> bool:
        """
        Check if a food code exists in this genome.

        Args:
            code: Food code to check (e.g., "SO.1")

        Returns:
            True if code is present
        """
        return code in self.codes

    def replace_code(self, old_code: str, new_code: str) -> 'Genome':
        """
        Return a new Genome with old_code replaced by new_code.

        Maintains sorted order. Used by the mutation operator.
        If old_code is not present, returns a copy unchanged.

        Args:
            old_code: Code to replace
            new_code: Replacement code

        Returns:
            New Genome instance with the substitution applied
        """
        new_codes = [new_code if c == old_code else c for c in self.codes]
        return Genome(codes=new_codes, meal_slot=self.meal_slot)

    def deduplicate(self) -> 'Genome':
        """
        Return a new Genome with duplicate codes removed.

        Preserves sorted order. First occurrence of each code is kept.

        Returns:
            New Genome with unique codes only
        """
        seen = set()
        unique_codes = []
        for code in self.codes:
            if code not in seen:
                seen.add(code)
                unique_codes.append(code)
        return Genome(codes=unique_codes, meal_slot=self.meal_slot)

    def is_valid(self, min_size: int, max_size: int) -> bool:
        """
        Check if genome meets size constraints.

        Should be called after deduplicate() to check effective size.

        Args:
            min_size: Minimum number of codes (from GAConfig)
            max_size: Maximum number of codes (from GAConfig)

        Returns:
            True if len(codes) is within [min_size, max_size]
        """
        return min_size <= len(self.codes) <= max_size

    def size(self) -> int:
        """Number of food codes in this genome."""
        return len(self.codes)

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize for JSON storage.

        Returns:
            Dict with codes and meal_slot
        """
        return {
            "codes": self.codes,
            "meal_slot": self.meal_slot,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Genome':
        """
        Deserialize from JSON storage.

        Args:
            data: Dict with 'codes' and 'meal_slot'

        Returns:
            Genome instance
        """
        return cls(
            codes=data.get("codes", []),
            meal_slot=data.get("meal_slot", ""),
        )

    def __repr__(self) -> str:
        return f"Genome({self.meal_slot}: {', '.join(self.codes)})"


# =============================================================================
# FitnessResult
# =============================================================================

@dataclass
class FitnessResult:
    """
    Detailed scoring breakdown for a GA member.

    Unlike the existing 0-1 nutrient_gap scorer, this uses unbounded
    linear scoring with per-nutrient contributions. The aggregate_score
    is the weighted sum of all nutrient scores, producing a continuous
    value where higher is better. Individual nutrient scores can go
    negative as penalties when values exceed acceptable ranges.

    Attributes:
        aggregate_score: Weighted sum of all nutrient scores (primary sort key)
        nutrient_scores: Per-nutrient breakdown dict
            {
                "protein": {
                    "value": 42.0,
                    "midpoint": 45.0,
                    "min": 35.0,
                    "max": 55.0,
                    "raw_score": 0.70,
                    "weight": 2.0,
                    "weighted_score": 1.40,
                    "mode": "midpoint"
                },
                "gl": {
                    "value": 8.0,
                    "max": 15.0,
                    "headroom": 7.0,
                    "raw_score": 0.47,
                    "weight": 1.0,
                    "weighted_score": 0.47,
                    "mode": "headroom"
                }
            }
        penalties: Named deductions beyond nutrient scoring
        metadata: Additional info (timestamp, config snapshot, etc.)
    """
    aggregate_score: float = 0.0
    nutrient_scores: Dict[str, Dict[str, float]] = field(default_factory=dict)
    penalties: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize for JSON workspace output.

        Returns:
            Dict suitable for inclusion in candidate score_result
        """
        return {
            "aggregate_score": self.aggregate_score,
            "nutrient_scores": self.nutrient_scores,
            "penalties": self.penalties,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FitnessResult':
        """
        Deserialize from JSON storage.

        Args:
            data: Dict with scoring fields

        Returns:
            FitnessResult instance
        """
        if not data:
            return cls()
        return cls(
            aggregate_score=data.get("aggregate_score", 0.0),
            nutrient_scores=data.get("nutrient_scores", {}),
            penalties=data.get("penalties", {}),
            metadata=data.get("metadata", {}),
        )

    def __repr__(self) -> str:
        return f"FitnessResult(score={self.aggregate_score:.3f}, nutrients={len(self.nutrient_scores)})"


# =============================================================================
# Member
# =============================================================================

@dataclass
class Member:
    """
    A candidate solution in the GA population.

    Contains one or more Genomes (one per meal slot), fitness data,
    and population management metadata. For v1 single-meal, the
    genomes list has exactly one entry.

    Population uniqueness is determined by identity_key(): two Members
    are identical if every corresponding genome has the same set of
    food codes. A single different code in any genome distinguishes them.

    Attributes:
        genomes: List of Genome objects, one per meal slot
        fitness: Scoring result (None until scored)
        tier: GENERAL or IMMIGRANT
        origin: RANDOM or BRED
        birth_epoch: Epoch number when created
        member_id: Unique string identifier within the population
    """
    genomes: List[Genome]
    fitness: Optional[FitnessResult] = None
    tier: MemberTier = MemberTier.GENERAL
    origin: MemberOrigin = MemberOrigin.RANDOM
    birth_epoch: int = 0
    member_id: str = ""

    def identity_key(self) -> Tuple[FrozenSet[str], ...]:
        """
        Hashable identity for population uniqueness checks.

        Returns a tuple of frozen code sets, one per genome in slot
        order. Two Members with the same identity_key are considered
        duplicates and only one may exist in the population.

        Returns:
            Tuple of FrozenSets, one per genome
        """
        return tuple(g.as_frozen() for g in self.genomes)

    def identity_hash(self) -> int:
        """
        Integer hash derived from identity_key.

        Suitable for set/dict membership checks.

        Returns:
            Hash of the identity key
        """
        return hash(self.identity_key())

    def genome_length(self) -> int:
        """
        Total number of food codes across all genomes.

        Used as secondary sort key (shorter = preferred at same fitness).

        Returns:
            Sum of all genome sizes
        """
        return sum(g.size() for g in self.genomes)

    def is_scored(self) -> bool:
        """Whether this member has a fitness result."""
        return self.fitness is not None

    def validate(self, config: GAConfig) -> Tuple[bool, List[str]]:
        """
        Structural validation against config constraints.

        Checks:
        - Correct number of genomes for configured meal_slots
        - Each genome meets min/max size constraints
        - No duplicate codes within any single genome

        Does NOT check population uniqueness (that's Population's job).

        Args:
            config: GAConfig with genome size limits and meal slot count

        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []

        # Check genome count matches meal slots
        expected_count = len(config.meal_slots)
        actual_count = len(self.genomes)
        if actual_count != expected_count:
            issues.append(
                f"Expected {expected_count} genome(s) for {expected_count} meal slot(s), "
                f"got {actual_count}"
            )

        for i, genome in enumerate(self.genomes):
            prefix = f"Genome[{i}] ({genome.meal_slot})"

            # Check for duplicate codes
            if len(genome.codes) != len(set(genome.codes)):
                dupes = [c for c in genome.codes if genome.codes.count(c) > 1]
                issues.append(f"{prefix}: duplicate codes: {set(dupes)}")

            # Check size constraints
            if not genome.is_valid(config.min_genome_size, config.max_genome_size):
                issues.append(
                    f"{prefix}: size {genome.size()} outside range "
                    f"[{config.min_genome_size}, {config.max_genome_size}]"
                )

        return (len(issues) == 0, issues)

    def all_codes(self) -> List[str]:
        """
        Flat list of all food codes across all genomes.

        Returns:
            Combined sorted list of codes from all genomes
        """
        codes = []
        for genome in self.genomes:
            codes.extend(genome.codes)
        return sorted(codes)

    def to_items_list(self) -> List[Dict[str, Any]]:
        """
        Convert genomes to the items list format used by the reco pipeline.

        All items have mult=1.0 since GA enforces unit multipliers.

        Returns:
            List of {"code": "XX.N", "mult": 1.0} dicts
        """
        items = []
        for genome in self.genomes:
            for code in genome.codes:
                items.append({"code": code, "mult": 1.0})
        return items

    def to_candidate_dict(self) -> Dict[str, Any]:
        """
        Convert to reco pipeline candidate format for workspace output.

        Produces a dict compatible with the existing candidate structure,
        marked with type="ga" and using the GA-specific score_result format.

        For single-meal (v1), the meal dict contains items from the
        single genome. Multi-meal output format is deferred.

        Returns:
            Candidate dict for workspace storage
        """
        # Build meal data from first genome (v1 single-meal)
        primary_genome = self.genomes[0] if self.genomes else None

        meal_data = {
            "items": self.to_items_list(),
            "meal_type": primary_genome.meal_slot if primary_genome else "",
            "description": self._build_description(),
        }

        # Generation metadata
        gen_metadata = {
            "method": "genetic",
            "origin": self.origin.value,
            "birth_epoch": self.birth_epoch,
            "tier": self.tier.value,
            "timestamp": datetime.now().isoformat(),
        }

        # Score result (if scored)
        score_result = None
        if self.fitness is not None:
            score_result = {
                "aggregate_score": self.fitness.aggregate_score,
                "scores": {
                    "ga_fitness": {
                        "raw": self.fitness.aggregate_score,
                        "weighted": self.fitness.aggregate_score,
                        "details": self.fitness.to_dict(),
                    }
                },
            }

        return {
            "id": self.member_id,
            "type": "ga",
            "meal": meal_data,
            "generation_metadata": gen_metadata,
            "filter_result": None,
            "score_result": score_result,
        }

    def _build_description(self) -> str:
        """
        Build a human-readable description string.

        Returns:
            Comma-separated list of all codes across genomes
        """
        parts = []
        for genome in self.genomes:
            parts.append(",".join(genome.codes))
        return " | ".join(parts)

    # --- Serialization (full GA format, not reco candidate format) ---

    def to_dict(self) -> Dict[str, Any]:
        """
        Full serialization for ga_population.json storage.

        Includes all fields needed to restore population state.

        Returns:
            Complete member dict
        """
        result = {
            "member_id": self.member_id,
            "genomes": [g.to_dict() for g in self.genomes],
            "tier": self.tier.value,
            "origin": self.origin.value,
            "birth_epoch": self.birth_epoch,
        }

        if self.fitness is not None:
            result["fitness"] = self.fitness.to_dict()

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Member':
        """
        Deserialize from ga_population.json storage.

        Args:
            data: Dict from to_dict()

        Returns:
            Restored Member instance
        """
        genomes = [
            Genome.from_dict(g) for g in data.get("genomes", [])
        ]

        fitness_data = data.get("fitness")
        fitness = FitnessResult.from_dict(fitness_data) if fitness_data else None

        # Parse enums with fallback
        try:
            tier = MemberTier(data.get("tier", "general"))
        except ValueError:
            tier = MemberTier.GENERAL

        try:
            origin = MemberOrigin(data.get("origin", "random"))
        except ValueError:
            origin = MemberOrigin.RANDOM

        return cls(
            genomes=genomes,
            fitness=fitness,
            tier=tier,
            origin=origin,
            birth_epoch=data.get("birth_epoch", 0),
            member_id=data.get("member_id", ""),
        )

    def to_filter_dict(self) -> dict:
        """
        Produce a candidate dict in the shape the filter pipeline expects.

        The existing filters (PreScoreFilter, MutualExclusionFilter,
        ConditionalRequirementFilter) extract food codes from:
            candidate["meal"]["items"][i]["code"]

        This adapter builds that structure from the member's genomes.
        All codes get mult=1.0 since GA members don't carry multipliers.

        Returns:
            Dict compatible with BaseFilter.filter_candidates() input
        """
        items = []
        for genome in self.genomes:
            for code in genome.codes:
                items.append({"code": code, "mult": 1.0})

        return {
            "meal": {"items": items},
            "rejection_reasons": [],
        }

    def __repr__(self) -> str:
        score_str = f", score={self.fitness.aggregate_score:.3f}" if self.fitness else ""
        genome_str = " | ".join(repr(g) for g in self.genomes)
        return (
            f"Member({self.member_id}, {self.tier.value}/{self.origin.value}, "
            f"epoch={self.birth_epoch}{score_str}, [{genome_str}])"
        )