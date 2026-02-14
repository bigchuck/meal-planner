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
        Apply crossover operator across all meal slots.

        For each meal slot, crosses the corresponding genomes from
        both parents using either one-point or two-point crossover
        (selected randomly, biased toward one-point for short genomes).

        Produces up to 2 offspring Members. An offspring is discarded
        if any of its genomes came back None (failed size validation
        after deduplication).

        Args:
            parent_a: First parent (selected via rank-based roulette)
            parent_b: Second parent
            epoch: Current epoch for offspring birth_epoch

        Returns:
            BreedingResult with 0-2 offspring
        """
        child_1_genomes = []
        child_2_genomes = []
        operator_name = None

        for slot_idx in range(len(self.config.meal_slots)):
            genome_a = parent_a.genomes[slot_idx]
            genome_b = parent_b.genomes[slot_idx]

            # Choose 1pt or 2pt: use 2pt only if both genomes >= 4 codes
            # and coin flip favors it
            use_two_point = (
                len(genome_a.codes) >= 4
                and len(genome_b.codes) >= 4
                and random.random() < 0.5
            )

            if use_two_point:
                g1, g2 = self.crossover_two_point(genome_a, genome_b)
                operator_name = operator_name or "crossover_2pt"
            else:
                g1, g2 = self.crossover_one_point(genome_a, genome_b)
                operator_name = operator_name or "crossover_1pt"

            child_1_genomes.append(g1)
            child_2_genomes.append(g2)

        # Build offspring — discard if any genome slot is None
        offspring = []

        if all(g is not None for g in child_1_genomes):
            offspring.append(Member(
                genomes=child_1_genomes,
                tier=MemberTier.GENERAL,
                origin=MemberOrigin.BRED,
                birth_epoch=epoch,
            ))

        if all(g is not None for g in child_2_genomes):
            offspring.append(Member(
                genomes=child_2_genomes,
                tier=MemberTier.GENERAL,
                origin=MemberOrigin.BRED,
                birth_epoch=epoch,
            ))

        return BreedingResult(
            offspring=offspring,
            operator=operator_name or "crossover_1pt",
            parents=(parent_a.member_id, parent_b.member_id),
            discarded=(len(offspring) == 0),
        )

    def _mutate_member(self, parent: Member, epoch: int) -> BreedingResult:
        """
        Apply mutation operator to a single parent.

        Selects a random meal slot, picks a random code position within
        that genome, and replaces it with a different code from the
        unified pool. The replacement must not already exist in the
        genome (no duplicates within a meal).

        If the only available replacement is the same code (pool
        exhausted relative to genome), the mutation fails and the
        result is marked discarded.

        The parent is never modified — a new Member is created.

        Args:
            parent: Parent member selected via rank-based roulette
            epoch: Current epoch for offspring birth_epoch

        Returns:
            BreedingResult with 0 or 1 offspring
        """
        # 1. Pick a random meal slot (genome index)
        slot_idx = random.randrange(len(parent.genomes))
        genome = parent.genomes[slot_idx]
        meal_type = self.config.meal_slots[slot_idx].meal_type

        # 2. Pick a random code position within the genome
        pos = random.randrange(len(genome.codes))
        old_code = genome.codes[pos]

        # 3. Build candidates: codes in the unified pool that are NOT
        #    already in this genome (ensures no intra-genome duplicates
        #    and guarantees the replacement differs from old_code)
        current_codes = set(genome.codes)
        pool = self.pool_codes.get(meal_type, [])
        candidates = [c for c in pool if c not in current_codes]

        if not candidates:
            # Pool exhausted — every code is already in this genome
            return BreedingResult(
                offspring=[],
                operator="mutation",
                parents=(parent.member_id, ""),
                discarded=True,
            )

        # 4. Select replacement
        new_code = random.choice(candidates)

        # 5. Build new genome with the replacement
        new_codes = list(genome.codes)
        new_codes[pos] = new_code
        new_genome = Genome(codes=new_codes, meal_slot=genome.meal_slot)

        # 6. Build new member with the mutated genome
        new_genomes = list(parent.genomes)
        new_genomes[slot_idx] = new_genome

        offspring = Member(
            genomes=new_genomes,
            tier=MemberTier.GENERAL,
            origin=MemberOrigin.BRED,
            birth_epoch=epoch,
        )

        return BreedingResult(
            offspring=[offspring],
            operator="mutation",
            parents=(parent.member_id, ""),
            discarded=False,
        )

    def crossover_one_point(
        self, genome_a: Genome, genome_b: Genome
    ) -> Tuple[Optional[Genome], Optional[Genome]]:
        """
        One-point crossover on a single meal slot's genomes.

        Picks a random interior cut point on each parent (not at
        position 0 or len), then swaps tails to produce two children.

        Example:
            Parent A (5 codes): [a1, a2 | a3, a4, a5]  cut at 2
            Parent B (7 codes): [b1, b2, b3, b4 | b5, b6, b7]  cut at 4
            Child 1: [a1, a2, b5, b6, b7]
            Child 2: [b1, b2, b3, b4, a3, a4, a5]

        After assembly, each child is deduplicated (codes that appear
        in both head and tail segments). Genome constructor auto-sorts.

        Returns None for a child if deduplication shrinks it below
        min_genome_size.

        Args:
            genome_a: First parent genome
            genome_b: Second parent genome

        Returns:
            Tuple of (child_1, child_2), either may be None
        """
        len_a = len(genome_a.codes)
        len_b = len(genome_b.codes)

        # Need at least 2 codes for an interior cut point
        if len_a < 2 or len_b < 2:
            return (None, None)

        # Interior cut: position 1 to len-1 inclusive
        cut_a = random.randint(1, len_a - 1)
        cut_b = random.randint(1, len_b - 1)

        # Swap tails
        child_1_codes = genome_a.codes[:cut_a] + genome_b.codes[cut_b:]
        child_2_codes = genome_b.codes[:cut_b] + genome_a.codes[cut_a:]

        # Build genomes (auto-sorts), then deduplicate
        child_1 = Genome(codes=child_1_codes, meal_slot=genome_a.meal_slot).deduplicate()
        child_2 = Genome(codes=child_2_codes, meal_slot=genome_a.meal_slot).deduplicate()

        # Validate size after dedup
        min_size = self.config.min_genome_size
        max_size = self.config.max_genome_size

        result_1 = child_1 if child_1.is_valid(min_size, max_size) else None
        result_2 = child_2 if child_2.is_valid(min_size, max_size) else None

        return (result_1, result_2)

    def crossover_two_point(
        self, genome_a: Genome, genome_b: Genome
    ) -> Tuple[Optional[Genome], Optional[Genome]]:
        """
        Two-point crossover on a single meal slot's genomes.

        Picks two distinct interior cut points on each parent, then
        swaps the middle segment to produce two children.

        Example:
            Parent A (5 codes): [a1 | a2, a3 | a4, a5]  cuts at 1,3
            Parent B (6 codes): [b1, b2 | b3, b4 | b5, b6]  cuts at 2,4
            Child 1: [a1, b3, b4, a4, a5]  (A head + B middle + A tail)
            Child 2: [b1, b2, a2, a3, b5, b6]  (B head + A middle + B tail)

        Falls back to one-point crossover if either parent has fewer
        than 4 codes (need at least 2 distinct interior positions).

        Returns None for a child if deduplication shrinks it below
        min_genome_size.

        Args:
            genome_a: First parent genome
            genome_b: Second parent genome

        Returns:
            Tuple of (child_1, child_2), either may be None
        """
        len_a = len(genome_a.codes)
        len_b = len(genome_b.codes)

        # Need at least 4 codes for two distinct interior cut points
        # (interior positions are 1..len-1, need at least 2 distinct)
        if len_a < 4 or len_b < 4:
            return self.crossover_one_point(genome_a, genome_b)

        # Pick two sorted, distinct interior cut points per parent
        cuts_a = sorted(random.sample(range(1, len_a), 2))
        cuts_b = sorted(random.sample(range(1, len_b), 2))

        i_a, j_a = cuts_a
        i_b, j_b = cuts_b

        # Swap middle segments
        # Child 1: A_head + B_middle + A_tail
        child_1_codes = (
            genome_a.codes[:i_a]
            + genome_b.codes[i_b:j_b]
            + genome_a.codes[j_a:]
        )
        # Child 2: B_head + A_middle + B_tail
        child_2_codes = (
            genome_b.codes[:i_b]
            + genome_a.codes[i_a:j_a]
            + genome_b.codes[j_b:]
        )

        # Build genomes (auto-sorts), then deduplicate
        child_1 = Genome(codes=child_1_codes, meal_slot=genome_a.meal_slot).deduplicate()
        child_2 = Genome(codes=child_2_codes, meal_slot=genome_a.meal_slot).deduplicate()

        # Validate size after dedup
        min_size = self.config.min_genome_size
        max_size = self.config.max_genome_size

        result_1 = child_1 if child_1.is_valid(min_size, max_size) else None
        result_2 = child_2 if child_2.is_valid(min_size, max_size) else None

        return (result_1, result_2)

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