# meal_planner/generators/ga_breeding.py
"""
Breeding pipeline for the Genetic Algorithm engine.

Provides genetic operators: crossover (1-point, 2-point), mutation,
and random member generation. Operates on genomes within meal slot
boundaries.

For the initial milestone, only generate_random_member() is fully
implemented. Crossover and mutation operators are stubbed for the
next phase when epoch processing is added.

Classes:
    BreedingResult   - Output of one breeding operation (stub)
    BreedingPipeline - Selection and genetic operators
"""
import random
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

from meal_planner.generators.ga_config import GAConfig, MealSlotConfig, MemberOrigin, MemberTier
from meal_planner.generators.ga_member import Member, Genome


# =============================================================================
# BreedingResult (stub for future crossover/mutation output)
# =============================================================================

@dataclass
class BreedingResult:
    """
    Output of one breeding operation.

    Attributes:
        offspring: List of new Member candidates (0-2 from crossover, 0-1 from mutation)
        operator: Which operator produced these ("crossover_1pt", "crossover_2pt", "mutation")
        parents: member_ids of parent members (for lineage tracking)
        discarded: True if the pairing was discarded (e.g., degenerate cut points)
    """
    offspring: List[Member] = field(default_factory=list)
    operator: str = ""
    parents: Tuple[str, str] = ("", "")
    discarded: bool = False


# =============================================================================
# BreedingPipeline
# =============================================================================

class BreedingPipeline:
    """
    Genetic operators for the GA population.

    At construction, resolves the unified set of food codes available
    for each meal slot by expanding all component pools referenced in
    the generation template. This unified pool is used for:
    - Random member generation (initial population and immigrant pool)
    - Mutation operator (replacement code selection)

    Crossover operates on existing genome codes and does not need the pool.

    The pipeline produces raw candidate Members that need validation,
    filtering, and scoring before entering the population.
    """

    def __init__(self, config: GAConfig, pool_codes: Dict[str, List[str]]):
        """
        Initialize breeding pipeline.

        Args:
            config: GA configuration (genome size limits, operator rates)
            pool_codes: Pre-resolved mapping of meal_type -> list of all
                        valid food codes for that slot. Built by
                        GAConfig.resolve_component_pools() in the orchestrator.
        """
        self.config = config
        self.pool_codes = pool_codes

        # Validate that we have codes for each meal slot
        for slot in config.meal_slots:
            codes = self.pool_codes.get(slot.meal_type, [])
            if not codes:
                print(
                    f"Warning: No food codes resolved for meal slot "
                    f"'{slot.meal_type}/{slot.template_name}'"
                )
            elif len(codes) < config.min_genome_size:
                print(
                    f"Warning: Pool for '{slot.meal_type}' has {len(codes)} codes, "
                    f"less than min_genome_size={config.min_genome_size}"
                )

    # =========================================================================
    # Random member generation
    # =========================================================================

    def generate_random_member(
        self,
        epoch: int,
        tier: MemberTier = MemberTier.GENERAL,
    ) -> Optional[Member]:
        """
        Create a completely random member.

        For each meal slot, randomly selects a genome size between
        min_genome_size and max_genome_size, then samples that many
        codes (without replacement) from the slot's unified code pool.

        Used for:
        - Initial population seeding (tier=GENERAL)
        - Immigrant pool injection each epoch (tier=IMMIGRANT)

        Args:
            epoch: Current epoch number (stored as birth_epoch)
            tier: Which tier this member enters (GENERAL or IMMIGRANT)

        Returns:
            New Member with random genomes, or None if a slot has
            insufficient codes to meet min_genome_size
        """
        genomes = []

        for slot in self.config.meal_slots:
            genome = self._random_genome(slot)
            if genome is None:
                return None
            genomes.append(genome)

        return Member(
            genomes=genomes,
            fitness=None,
            tier=tier,
            origin=MemberOrigin.RANDOM,
            birth_epoch=epoch,
        )

    def _random_genome(self, slot: MealSlotConfig) -> Optional[Genome]:
        """
        Generate a single random genome for a meal slot.

        Selects a random size within [min_genome_size, max_genome_size],
        capped by available pool size, then samples codes without
        replacement from the slot's code pool.

        Args:
            slot: MealSlotConfig identifying the meal type

        Returns:
            Genome with randomly selected codes, or None if the pool
            is too small for min_genome_size
        """
        codes = self.pool_codes.get(slot.meal_type, [])

        if len(codes) < self.config.min_genome_size:
            print(
                f"Error: Pool for '{slot.meal_type}' has {len(codes)} codes, "
                f"need at least {self.config.min_genome_size}"
            )
            return None

        # Determine genome size: random within config range, capped by pool
        max_possible = min(self.config.max_genome_size, len(codes))
        genome_size = random.randint(self.config.min_genome_size, max_possible)

        # Sample without replacement
        selected = random.sample(codes, genome_size)

        return Genome(codes=selected, meal_slot=slot.meal_type)

    # =========================================================================
    # Breeding operators (stubs for future implementation)
    # =========================================================================

    def breed(self, parent_a: Member, parent_b: Member, epoch: int) -> BreedingResult:
        """
        Apply genetic operators to a pair of parents.

        Randomly selects crossover (1pt or 2pt) or mutation based on
        configured rates. Crossover produces up to 2 offspring; mutation
        produces 1 offspring from one parent.

        Offspring genomes are deduplicated but NOT yet validated for
        size constraints or population uniqueness.

        Args:
            parent_a: First selected parent
            parent_b: Second selected parent
            epoch: Current epoch number for offspring birth_epoch

        Returns:
            BreedingResult with offspring and metadata
        """
        operator = self._select_operator()

        if operator == "crossover":
            return self._crossover(parent_a, parent_b, epoch)
        else:
            # Mutation: pick one parent at random
            parent = random.choice([parent_a, parent_b])
            return self._mutate_member(parent, epoch)

    def _select_operator(self) -> str:
        """
        Randomly select which operator to apply based on configured rates.

        Uses crossover_rate and mutation_rate from config. The random_rate
        is handled separately by the orchestrator (immigrant generation).

        Returns:
            "crossover" or "mutation"
        """
        # Normalize crossover and mutation rates (exclude random_rate)
        cx = self.config.crossover_rate
        mu = self.config.mutation_rate
        total = cx + mu

        if total <= 0:
            return "crossover"

        if random.random() < (cx / total):
            return "crossover"
        return "mutation"

    def _crossover(
        self, parent_a: Member, parent_b: Member, epoch: int
    ) -> BreedingResult:
        """
        Apply crossover operator to produce offspring.

        Stub: will implement one-point and two-point crossover
        that respects genome/meal-slot boundaries.

        Args:
            parent_a: First parent
            parent_b: Second parent
            epoch: Current epoch for offspring birth_epoch

        Returns:
            BreedingResult with 0-2 offspring
        """
        # TODO: Implement crossover_one_point and crossover_two_point
        return BreedingResult(
            offspring=[],
            operator="crossover",
            parents=(parent_a.member_id, parent_b.member_id),
            discarded=True,
        )

    def _mutate_member(self, parent: Member, epoch: int) -> BreedingResult:
        """
        Apply mutation operator to a single parent.

        Stub: will select random positions in a genome and replace
        codes with alternatives from the unified pool.

        Args:
            parent: Parent member to mutate
            epoch: Current epoch for offspring birth_epoch

        Returns:
            BreedingResult with 0-1 offspring
        """
        # TODO: Implement mutation with unified pool selection
        return BreedingResult(
            offspring=[],
            operator="mutation",
            parents=(parent.member_id, ""),
            discarded=True,
        )

    def crossover_one_point(
        self, genome_a: Genome, genome_b: Genome
    ) -> Tuple[Optional[Genome], Optional[Genome]]:
        """
        One-point crossover on a single meal slot's genomes.

        Stub for future implementation.
        """
        # TODO: Implement
        return (None, None)

    def crossover_two_point(
        self, genome_a: Genome, genome_b: Genome
    ) -> Tuple[Optional[Genome], Optional[Genome]]:
        """
        Two-point crossover on a single meal slot's genomes.

        Stub for future implementation.
        """
        # TODO: Implement
        return (None, None)

    def mutate(self, parent: Member, epoch: int) -> Optional[Member]:
        """
        Mutation operator on a single parent.

        Stub for future implementation.
        """
        # TODO: Implement
        return None

    # =========================================================================
    # Diagnostics
    # =========================================================================

    def pool_summary(self) -> str:
        """
        Human-readable summary of available code pools.

        Returns:
            Multi-line string with pool sizes per meal slot
        """
        lines = ["=== Breeding Pool Summary ==="]
        for slot in self.config.meal_slots:
            codes = self.pool_codes.get(slot.meal_type, [])
            lines.append(
                f"  {slot.meal_type}/{slot.template_name}: "
                f"{len(codes)} codes, "
                f"genome range {self.config.min_genome_size}-{self.config.max_genome_size}"
            )
            if codes and len(codes) <= 20:
                lines.append(f"    codes: {', '.join(codes)}")
        return "\n".join(lines)