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

    # =========================================================================
    # Public API
    # =========================================================================

    def run(self) -> Dict[str, Any]:
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
            # Seed initial population
            self.initialize_population()

        # TODO: Future - epoch loop goes here
        # for epoch in range(1, self.config.epochs_per_run + 1):
        #     summary = self.run_epoch(epoch)
        #     self.display_epoch_progress(summary)
        #     if self._check_convergence(summary.diversity):
        #         break

        # Write results
        self.write_results()

        # Display summary
        self.display_final_summary()

        return self._build_summary_dict()

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

        print(f"Seeding initial population (target: {target} members)...")
        print()

        while self.population.general_size < target and attempts < max_attempts:
            attempts += 1

            # Generate random member for general population
            member = self.breeding.generate_random_member(
                epoch=0,
                tier=MemberTier.GENERAL,
            )

            if member is None:
                print("Error: Failed to generate random member (insufficient pool codes)")
                break

            # Validate structure
            is_valid, issues = member.validate(self.config)
            if not is_valid:
                # Should not happen with random generation, but be safe
                print(f"  Warning: Generated invalid member: {', '.join(issues)}")
                continue

            # Assign ID and attempt insertion
            self.population.assign_id(member)
            added = self.population.add_member(member)

            if not added:
                duplicates += 1

            # Progress display every 25% or every 100 members
            if self.population.general_size % max(1, target // 4) == 0:
                print(
                    f"  {self.population.general_size}/{target} members "
                    f"({attempts} attempts, {duplicates} duplicates)"
                )

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

        print(f"DEBUG:")
        totals = self.fitness_engine.calculate_nutrient_totals(member.genomes[0])
        print(f"DEBUG: totals\n{totals}")

    # =========================================================================
    # Epoch loop (stubs for future implementation)
    # =========================================================================

    def run_epoch(self, epoch: int) -> EpochSummary:
        """
        Execute one epoch of the GA.

        Stub for future implementation. Sequence:
        1. Graduate aged-out immigrants -> general pop, rerank, cull
        2. Generate random immigrants up to pool cap
        3. Breed from combined population
        4. Validate, filter, score new members
        5. Rerank general population, cull to target
        6. Compute diversity metrics
        7. Display epoch progress

        Args:
            epoch: Current epoch number

        Returns:
            EpochSummary with counts and metrics
        """
        # TODO: Implement epoch processing
        return EpochSummary(epoch=epoch)

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