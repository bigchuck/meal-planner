# meal_planner/generators/genetic.py
"""
Genetic Algorithm orchestrator for the recommendation engine.

This is the ONLY module imported by recommend_command.py. It manages
the full GA lifecycle: load config, resolve pools, seed population,
run epoch loop (future), and write results to the workspace.

For the initial milestone, the orchestrator supports:
- Loading and validating GA config from config.json
- Resolving component pools for each meal slot
- Seeding an initial population with random members
- Writing the population to ga_population.json
- Display of population summary

Future phases will add the epoch loop with breeding, filtering,
scoring, and convergence detection.

Classes:
    EpochSummary      - Display data for one epoch (stub)
    GeneticAlgorithm  - Top-level orchestrator
"""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from meal_planner.generators.ga_config import GAConfig, MemberTier
from meal_planner.generators.ga_member import Member
from meal_planner.generators.ga_population import Population, DiversityMetrics
from meal_planner.generators.ga_breeding import BreedingPipeline
from meal_planner.filters.pre_score_filter import PreScoreFilter
from meal_planner.filters.mutual_exclusion_filter import MutualExclusionFilter
from meal_planner.filters.conditional_requirement_filter import ConditionalRequirementFilter


# =============================================================================
# EpochSummary (stub for future epoch loop)
# =============================================================================

@dataclass
class EpochSummary:
    """
    Display data for one epoch's progress line.

    Populated during run_epoch() and passed to display_epoch_progress().
    Stubbed for the initial milestone.
    """
    epoch: int = 0
    bred_count: int = 0
    immigrant_count: int = 0
    accepted_count: int = 0
    culled_count: int = 0
    graduated_count: int = 0
    diversity: DiversityMetrics = field(default_factory=DiversityMetrics)


class FilterStats:
    """
    Tracks per-filter rejection counts during a GA run.

    Used for diagnostics only — rejected members are discarded,
    not stored.  Counts are displayed in the population summary.
    """

    def __init__(self):
        self.counts = {}          # filter_name -> rejection count
        self.total_tested = 0     # total members submitted to filtering
        self.total_rejected = 0   # total members rejected by any filter

    def record_rejection(self, filter_name: str) -> None:
        """Increment rejection count for a specific filter."""
        self.counts[filter_name] = self.counts.get(filter_name, 0) + 1
        self.total_rejected += 1

    def record_test(self) -> None:
        """Increment the tested counter (call once per member)."""
        self.total_tested += 1

    @property
    def total_passed(self) -> int:
        return self.total_tested - self.total_rejected

    def display(self) -> None:
        """Print a compact summary of filter activity."""
        if self.total_tested == 0:
            return

        pass_rate = (
            self.total_passed / self.total_tested * 100
            if self.total_tested > 0
            else 0
        )
        print(f"  Filter stats: {self.total_passed}/{self.total_tested} passed ({pass_rate:.1f}%)")

        if self.counts:
            for name, count in sorted(self.counts.items(), key=lambda x: -x[1]):
                print(f"    {name:<30} {count:>5} rejected")


# =============================================================================
# GeneticAlgorithm
# =============================================================================

class GeneticAlgorithm:
    """
    Top-level orchestrator for the GA recommendation engine.

    This is the ONLY class imported by recommend_command.py.
    Manages the full lifecycle:
        config -> init population -> (epoch loop) -> output

    Usage from recommend_command.py:
        from meal_planner.generators.genetic import GeneticAlgorithm

        ga = GeneticAlgorithm(ctx)
        ga.initialize_population()
        ga.write_results()
        ga.display_final_summary()
    """

    # Filename for GA population state (alongside reco_workspace.json)
    GA_POPULATION_FILENAME = "meal_plan_ga_population.json"

    def __init__(self, ctx):
        """
        Initialize from command context.

        Loads GA config, resolves component pools, builds the
        BreedingPipeline, and initializes an empty Population.

        Args:
            ctx: CommandContext with master, thresholds, workspace_mgr, etc.

        Raises:
            ValueError: If GA config is missing or invalid
            ValueError: If no food codes resolve for any meal slot
        """
        self.ctx = ctx

        # Load and validate GA config
        if not ctx.thresholds or not ctx.thresholds.is_valid:
            raise ValueError("Thresholds/config not available")

        config_dict = ctx.thresholds.thresholds
        if "genetic" not in config_dict:
            raise ValueError(
                "No 'genetic' block found in config.json. "
                "Add a 'genetic' section with GA parameters."
            )

        self.config = GAConfig.from_config(config_dict)

        # Resolve component pools for each meal slot
        self.pool_codes = self.config.resolve_component_pools(ctx.thresholds)

        # Validate we got codes
        for slot in self.config.meal_slots:
            codes = self.pool_codes.get(slot.meal_type, [])
            if not codes:
                raise ValueError(
                    f"No food codes resolved for meal slot "
                    f"'{slot.meal_type}/{slot.template_name}'. "
                    f"Check component_pools and meal_generation in config.json."
                )

        # Build breeding pipeline
        self.breeding = BreedingPipeline(self.config, self.pool_codes)

        # Build fitness engine from meal template
        from meal_planner.generators.ga_scoring import FitnessEngine
        slot = self.config.meal_slots[0]  # v1: single meal slot
        self.fitness_engine = FitnessEngine.from_template(
            thresholds_mgr=ctx.thresholds,
            meal_type=slot.meal_type,
            template_name=slot.template_name,
            master_loader=ctx.master,
            config=self.config,
        )

        # Initialize empty population
        self.population = Population(self.config)

        # Determine output file path (same directory as reco workspace)
        workspace_dir = ctx.workspace_mgr.reco_filepath.parent
        self.ga_filepath = workspace_dir / self.GA_POPULATION_FILENAME

        # Build filter pipeline and stats tracker
        self.ga_filters = self._build_ga_filters()
        self.filter_stats = FilterStats()

        # Parse component count constraints from meal_generation config
        self._resolve_component_constraints()
        if self.component_constraints:
            comp_names = [c["name"] for c in self.component_constraints]
            print(f"Component constraints: {', '.join(comp_names)}")

    # =========================================================================
    # Public API
    # =========================================================================

    def run(self, restart: bool = False) -> Dict[str, Any]:
        """
        Execute the GA process.

        For the initial milestone, this seeds the population and writes
        results. Future phases will add the epoch loop.

        Full sequence (future):
        1. Check for existing population (restart capability)
        2. If no existing population, seed with random members
        3. Run epoch loop until limit or convergence
        4. Write final population to ga_population.json
        5. Return summary dict

        The existing load_existing_population() check in run() already handles
        the file-not-found case. The file deletion happens in _generate_ga()
        before GeneticAlgorithm is instantiated, so by the time run() is
        called, the file is already gone if --restart was used.
        No other changes needed inside run().


        Returns:
            Summary dict with stats
        """
        print()
        print(self.config.summary())
        print()
        print(self.breeding.pool_summary())
        print()

        self.fitness_engine.display_targets()

        # Check for existing population
        loaded = self.load_existing_population()
        if loaded:
            print(f"Loaded existing GA population from {self.ga_filepath.name}")
            print(f"  General: {self.population.general_size} members")
            print(f"  Immigrants: {self.population.immigrant_size} members")
            print()
        else:
            # Reset filter stats for this run
            self.filter_stats = FilterStats()
            # Seed initial population
            self.initialize_population()

        # Run epoch loop
        print(f"\nRunning {self.config.epochs_per_run} epochs...")
        print(
            f"{'Epoch':>6}  {'Bred':>5} {'Imm':>4} {'Acc':>4} "
            f"{'Cull':>5} {'Grad':>5} "
            f"{'Best':>9} {'Median':>9} {'GenPop':>6} {'ImmPop':>6}"
        )
        print("-" * 80)

        for epoch in range(1, self.config.epochs_per_run + 1):
            summary = self.run_epoch(epoch)

            # Gather score stats for display
            scored = [
                m.fitness.aggregate_score
                for m in self.population.general_members
                if m.fitness is not None
            ]
            best = max(scored) if scored else 0.0
            median = sorted(scored)[len(scored) // 2] if scored else 0.0

            # Compact progress line
            print(
                f"{epoch:>6}  "
                f"{summary.bred_count:>5} "
                f"{summary.immigrant_count:>4} "
                f"{summary.accepted_count:>4} "
                f"{summary.culled_count:>5} "
                f"{summary.graduated_count:>5} "
                f"{best:>9.3f} "
                f"{median:>9.3f} "
                f"{self.population.general_size:>6} "
                f"{self.population.immigrant_size:>6}"
            )

            # TODO: convergence detection
            # if self._check_convergence(summary):
            #     print(f"\nConvergence detected at epoch {epoch}")
            #     break

        print()


        # Write results
        self.write_results()

        # Display summary
        self.display_final_summary()

        return self._build_summary_dict()

    def _build_ga_filters(self):
        """
        Build the filter instances used to validate GA members.

        Creates filters once at initialization. Called from __init__()
        after config and context are available.

        Filters included:
            - PreScoreFilter:              locks, availability, reserved/depleted
            - MutualExclusionFilter:       food combo exclusions
            - ConditionalRequirementFilter: trigger -> required companion

        Filters excluded:
            - NutrientConstraintFilter:    handled by GA fitness scoring
            - LeftoverMatchFilter:         GA members have no portion data

        Returns:
            List of (filter_name, filter_instance) tuples
        """
        filters = []
        workspace = self.ctx.workspace_mgr.load()
        locks = workspace.get("locks", {})
        inventory = workspace.get("inventory", {})

        # Determine meal_type from config (first slot for v1)
        meal_type = self.config.meal_slots[0].meal_type

        # 1. PreScoreFilter — locks, availability, reserved/depleted
        prescore = PreScoreFilter(
            locks=locks,
            meal_type=meal_type,
            user_prefs=self.ctx.user_prefs,
            inventory=inventory,
        )
        prescore.set_collect_all(False)  # reject immediately
        filters.append(("PreScore (locks/availability)", prescore))

        # 2. MutualExclusionFilter — if rules exist for this meal type
        meal_filters_section = self.ctx.thresholds.thresholds.get("meal_filters", {})
        meal_type_filters = meal_filters_section.get(meal_type, {})

        exclusion_rules = meal_type_filters.get("mutual_exclusions", [])
        if exclusion_rules:
            mutual_filter = MutualExclusionFilter(
                meal_type=meal_type,
                thresholds_mgr=self.ctx.thresholds,
                exclusion_rules=exclusion_rules,
            )
            mutual_filter.set_collect_all(False)
            filters.append(("Mutual Exclusion", mutual_filter))

        # 3. ConditionalRequirementFilter — if rules exist
        requirement_rules = meal_type_filters.get("conditional_requirements", [])
        if requirement_rules:
            cond_filter = ConditionalRequirementFilter(
                meal_type=meal_type,
                thresholds_mgr=self.ctx.thresholds,
                requirement_rules=requirement_rules,
            )
            cond_filter.set_collect_all(False)
            filters.append(("Conditional Requirement", cond_filter))

        return filters

    def _resolve_component_constraints(self):
        """
        Parse meal_generation config to extract per-component count rules.

        Walks the generation template for the active meal slot, expands
        each component's pool_ref to a set of food codes, and records
        the min/max count constraints.

        Builds self.component_constraints: list of dicts, each with:
            - name: component name (e.g., "liquid_fuel", "protein")
            - codes: set of food codes from the expanded pool
            - min: minimum required count from this component
            - max: maximum allowed count from this component

        Returns:
            List of constraint dicts (also stored on self)
        """
        constraints = []

        # Get meal type and template name from first slot
        if not self.config.meal_slots:
            self.component_constraints = constraints
            return constraints

        slot = self.config.meal_slots[0]
        meal_type = slot.meal_type
        template_name = slot.template_name

        # Navigate config: meal_generation -> meal_type -> template_name -> components
        meal_gen = self.ctx.thresholds.thresholds.get("meal_generation", {})
        meal_type_gen = meal_gen.get(meal_type, {})
        template_gen = meal_type_gen.get(template_name, {})
        components = template_gen.get("components", {})

        if not components:
            self.component_constraints = constraints
            return constraints

        for comp_name, comp_config in components.items():
            pool_ref = comp_config.get("pool_ref", "")
            count_config = comp_config.get("count", {})
            min_count = count_config.get("min", 0)
            max_count = count_config.get("max", 99)

            # Expand pool_ref to actual codes
            if pool_ref:
                expanded = self.ctx.thresholds.expand_pool(pool_ref)
                codes = set(c.upper() for c in expanded)
            else:
                codes = set()

            if codes:
                constraints.append({
                    "name": comp_name,
                    "codes": codes,
                    "min": min_count,
                    "max": max_count,
                })

        self.component_constraints = constraints
        return constraints

    def _check_component_counts(self, member) -> str:
        """
        Check a member's codes against component count constraints.

        For each component, counts how many of the member's codes
        fall within that component's pool, then checks against
        the configured min/max.

        Args:
            member: Member to validate

        Returns:
            Empty string if all constraints pass.
            Violation description string if any constraint fails.
        """
        if not self.component_constraints:
            return ""

        # Collect all member codes into a set (uppercased)
        member_codes = set()
        for genome in member.genomes:
            for code in genome.codes:
                member_codes.add(code.upper())

        # Check each component
        for constraint in self.component_constraints:
            comp_name = constraint["name"]
            comp_codes = constraint["codes"]
            min_count = constraint["min"]
            max_count = constraint["max"]

            # Count how many member codes are in this component's pool
            count = len(member_codes & comp_codes)

            if count < min_count:
                return (
                    f"component({comp_name}): "
                    f"has {count}, needs at least {min_count}"
                )
            if count > max_count:
                return (
                    f"component({comp_name}): "
                    f"has {count}, max allowed is {max_count}"
                )

        return ""

    def _filter_member(self, member) -> bool:
        """
        Run a member through the GA filter pipeline.

        Converts the member to filter-compatible dict via the adapter,
        then runs each filter in sequence.  On first rejection the
        member is discarded and the failing filter name is recorded
        in self.filter_stats.

        Args:
            member: A Member instance (not yet in the population)

        Returns:
            True if the member passed all filters, False if rejected
        """
        self.filter_stats.record_test()

        # Adapt member to the dict shape filters expect
        candidate_dict = member.to_filter_dict()

        for filter_name, filter_instance in self.ga_filters:
            passed, rejected = filter_instance.filter_candidates([candidate_dict])

            if rejected:
                self.filter_stats.record_rejection(filter_name)
                return False

        # Component count check
        violation = self._check_component_counts(member)
        if violation:
            self.filter_stats.record_rejection("Component Counts")
            return False

        return True
    
    def _process_offspring(self, member, epoch: int) -> bool:
        """
        Pipeline for a newly created member: validate, filter, score, add.

        Used for both bred offspring and new immigrants. The caller
        sets the member's tier before calling this method.

        Args:
            member: New Member (not yet validated/scored/ID'd)
            epoch: Current epoch number

        Returns:
            True if member was added to population, False otherwise
        """
        # 1. Validate structure
        is_valid, issues = member.validate(self.config)
        if not is_valid:
            return False

        # 2. Filter
        if not self._filter_member(member):
            return False

        # 3. Check uniqueness (before scoring to avoid wasted work)
        if self.population.is_duplicate(member):
            return False

        # 4. Score
        member.fitness = self.fitness_engine.score(member)

        # 5. Assign ID and add to population
        self.population.assign_id(member)
        added = self.population.add_member(member)

        return added

    def initialize_population(self) -> None:
        """
        Seed initial population with random members.

        Generates random members until the population reaches its
        target size. Tracks and reports uniqueness rejections.
        Members are added to the general population tier.

        If the pool is small relative to population_size, some
        generation attempts will produce duplicates. A safety limit
        prevents infinite loops if the combinatorial space is too
        small for the requested population size.
        """
        target = self.config.population_size
        max_attempts = target * 10  # Safety limit
        attempts = 0
        duplicates = 0
        filtered_out = 0
        epoch = 0

        print(f"Seeding initial population (target: {target} members)...")
        print()

        while self.population.general_size < target and attempts < max_attempts:
            member = self.breeding.generate_random_member(epoch)
            attempts += 1

            if not member.validate(self.config):
                continue

            if not self._filter_member(member):
                filtered_out += 1
                continue

            if self.population.is_duplicate(member):
                duplicates += 1
                continue

            self.population.assign_id(member)
            self.population.add_member(member)

            # Progress display every 25% or every 100 members
            if self.population.general_size % max(1, target // 4) == 0:
                print(
                    f"Population seeded: {self.population.general_size} members "
                    f"in {attempts} attempts "
                    f"({duplicates} duplicates, {filtered_out} filtered out)"
                )
                self.filter_stats.display()

        # Score all members
        print(f"Scoring {self.population.general_size} members...")
        scored_count = 0
        for member in self.population.general_members:
            if not member.is_scored():
                member.fitness = self.fitness_engine.score(member)
                scored_count += 1

        # Rank by fitness
        self.population.rerank()
        print(f"  Scored {scored_count} members, population ranked")

        # Final status
        print()
        if self.population.general_size >= target:
            print(
                f"Population seeded: {self.population.general_size} members "
                f"in {attempts} attempts ({duplicates} duplicates)"
            )
        else:
            print(
                f"Warning: Only seeded {self.population.general_size}/{target} members "
                f"after {attempts} attempts ({duplicates} duplicates)"
            )
            print(
                "  The combinatorial space may be too small for the "
                "requested population size."
            )
            print(
                "  Consider: larger component pools, wider genome size range, "
                "or smaller population_size."
            )
        print()

    # =========================================================================
    # Epoch loop (stubs for future implementation)
    # =========================================================================

    def run_epoch(self, epoch: int) -> EpochSummary:
        """
        Execute one epoch of the GA.

        Sequence:
        1. Graduate aged-out immigrants → general pop, rerank, cull
        2. Generate random immigrants up to pool cap
        3. Breed from combined population
        4. Rerank general population, cull to target
        5. Return epoch summary

        Args:
            epoch: Current epoch number (1-based)

        Returns:
            EpochSummary with counts for display
        """
        summary = EpochSummary(epoch=epoch)

        # Reset per-epoch tracking
        self.filter_stats = FilterStats()
        self.population.reset_epoch_stats()

        # =================================================================
        # Step 1: Graduate aged-out immigrants
        # =================================================================
        graduated, grad_culled = self.population.graduate_immigrants(epoch)
        summary.graduated_count = graduated

        # =================================================================
        # Step 2: Generate random immigrants
        # =================================================================
        immigrant_target = self.config.immigrant_pool_size_per_epoch
        current_immigrants = self.population.immigrant_size
        max_total = self.config.max_immigrant_pool_total
        spots_available = max_total - current_immigrants
        to_generate = min(immigrant_target, spots_available)

        immigrants_added = 0
        immigrant_attempts = 0
        max_immigrant_attempts = to_generate * 5  # safety limit

        while immigrants_added < to_generate and immigrant_attempts < max_immigrant_attempts:
            immigrant_attempts += 1
            member = self.breeding.generate_random_member(
                epoch=epoch,
                tier=MemberTier.IMMIGRANT,
            )
            if member is None:
                break

            if self._process_offspring(member, epoch):
                immigrants_added += 1

        summary.immigrant_count = immigrants_added

        # =================================================================
        # Step 3: Breed from combined population
        # =================================================================
        breed_target = self.config.new_members_per_epoch
        bred_accepted = 0
        breed_attempts = 0

        # Need at least 2 members to breed
        if self.population.size >= 2:
            while breed_attempts < breed_target:
                breed_attempts += 1

                # Select parents and apply operator
                parent_a, parent_b = self.population.select_pair()
                result = self.breeding.breed(parent_a, parent_b, epoch)

                # Process each offspring through the pipeline
                for offspring in result.offspring:
                    if self._process_offspring(offspring, epoch):
                        bred_accepted += 1

        summary.bred_count = breed_attempts
        summary.accepted_count = bred_accepted + immigrants_added

        # =================================================================
        # Step 4: Rerank and cull general population
        # =================================================================
        self.population.rerank()
        culled = self.population.cull_general()
        summary.culled_count = culled + grad_culled

        return summary

    # =========================================================================
    # Output
    # =========================================================================

    def write_results(self) -> None:
        """
        Write GA population state to ga_population.json.

        Saves the full population state (both tiers, config, stats)
        for restart capability. Also writes a summary to the reco
        workspace for status display.
        """
        # Build full state dict
        state = {
            "ga_version": "1.0",
            "created": datetime.now().isoformat(),
            "population": self.population.to_dict(),
        }

        # Write ga_population.json
        try:
            with open(self.ga_filepath, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            print(f"GA population saved to {self.ga_filepath.name}")
        except Exception as e:
            print(f"Error saving GA population: {e}")
            return

        # Update reco workspace with GA summary
        try:
            reco_workspace = self.ctx.workspace_mgr.load_reco()
            reco_workspace["ga_state"] = {
                "population_file": self.ga_filepath.name,
                "general_size": self.population.general_size,
                "immigrant_size": self.population.immigrant_size,
                "last_updated": datetime.now().isoformat(),
            }
            self.ctx.workspace_mgr.save_reco(reco_workspace)
        except Exception as e:
            print(f"Warning: Failed to update reco workspace: {e}")

        print()

    def load_existing_population(self) -> bool:
        """
        Attempt to load a saved population for restart.

        Reads ga_population.json if it exists and restores the
        Population state. The loaded population uses the current
        config (not the saved one) so config changes take effect.

        Returns:
            True if population was loaded, False if starting fresh
        """
        if not self.ga_filepath.exists():
            return False

        try:
            with open(self.ga_filepath, 'r', encoding='utf-8') as f:
                state = json.load(f)

            pop_data = state.get("population")
            if not pop_data:
                return False

            self.population = Population.from_dict(pop_data, self.config)
            return True

        except (json.JSONDecodeError, Exception) as e:
            print(f"Warning: Failed to load GA population: {e}")
            print("Starting with fresh population.")
            return False

    # =========================================================================
    # Display
    # =========================================================================

    def display_epoch_progress(self, summary: EpochSummary) -> None:
        """
        Print epoch progress line to terminal.

        Format:
        Epoch 12/50 | Best: 14.7 Med: 11.2 | Bred: 25 Imm: 10 Acc: 18 |
                       Cull: 12 Grad: 3 | Elite-D: 20% Dup: 8%

        Args:
            summary: EpochSummary for this epoch
        """
        d = summary.diversity
        print(
            f"Epoch {summary.epoch}/{self.config.epochs_per_run} | "
            f"Best: {d.best_score:.1f} Med: {d.median_score:.1f} | "
            f"Bred: {summary.bred_count} Imm: {summary.immigrant_count} "
            f"Acc: {summary.accepted_count} | "
            f"Cull: {summary.culled_count} Grad: {summary.graduated_count} | "
            f"Elite-D: {d.elite_turnover:.0%} Dup: {d.duplicate_rate:.0%}"
        )

    def display_final_summary(self) -> None:
        """
        Print final results after GA completes.

        Shows population summary with optional verbose member listing.
        """
        self.population.display_summary(verbose=True)

    # =========================================================================
    # Convergence detection (stub for future)
    # =========================================================================

    def _check_convergence(self, metrics: DiversityMetrics) -> bool:
        """
        Determine if the GA should stop early.

        Stub for future implementation. Will check:
        - Elite turnover below threshold for N consecutive epochs
        - Acceptance rate below threshold
        - Generation repeat rate above threshold

        Args:
            metrics: Current epoch's diversity metrics

        Returns:
            True if convergence detected
        """
        # TODO: Implement convergence detection
        return False

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _build_summary_dict(self) -> Dict[str, Any]:
        """
        Build summary dict for return from run().

        Returns:
            Dict with population stats and config snapshot
        """
        return {
            "population_size": self.population.general_size,
            "immigrant_size": self.population.immigrant_size,
            "config": self.config.to_dict(),
            "pool_sizes": {
                meal_type: len(codes)
                for meal_type, codes in self.pool_codes.items()
            },
            "ga_file": str(self.ga_filepath),
        }