# meal_planner/generators/ga_config.py
"""
Configuration adapter for the Genetic Algorithm recommendation engine.

Reads and validates the 'genetic' block from config.json, providing
typed access to all GA parameters. Validates eagerly on construction
so configuration errors surface before a run starts.

Expected config.json structure:
{
    "genetic": {
        "population_size": 100,
        "epochs_per_run": 50,
        "new_members_per_epoch": 30,
        "crossover_rate": 0.7,
        "mutation_rate": 0.2,
        "random_rate": 0.1,
        "min_genome_size": 3,
        "max_genome_size": 8,
        "immigrant_pool_ratio": 0.10,
        "immigrant_tenure_epochs": 5,
        "meal_slots": [
            {
                "meal_type": "lunch",
                "template_name": "protein_low_carb"
            }
        ],
        "selection_pressure": 1.5,
        "scoring_weights": {
            "protein": 2.0,
            "calories": 1.5,
            "gl": 1.0,
            "fiber": 1.0
        }
    }
}
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class MemberOrigin(Enum):
    """How a member was created."""
    RANDOM = "random"
    BRED = "bred"


class MemberTier(Enum):
    """Which population tier a member belongs to."""
    GENERAL = "general"
    IMMIGRANT = "immigrant"


@dataclass
class MealSlotConfig:
    """
    Configuration for one meal slot within a GA member.

    Each member contains one genome per meal slot. For single-meal GA
    (v1), there is exactly one slot. Multi-meal will have multiple.

    Attributes:
        meal_type: Meal category (e.g., "lunch", "breakfast")
        template_name: Generation template name within meal_generation config
    """
    meal_type: str
    template_name: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MealSlotConfig':
        """
        Build from config dict entry.

        Args:
            data: Dict with 'meal_type' and 'template_name' keys

        Returns:
            MealSlotConfig instance

        Raises:
            ValueError: If required keys are missing
        """
        if not isinstance(data, dict):
            raise ValueError(f"Meal slot config must be a dict, got {type(data).__name__}")

        meal_type = data.get("meal_type")
        template_name = data.get("template_name")

        if not meal_type:
            raise ValueError("Meal slot config missing 'meal_type'")
        if not template_name:
            raise ValueError(f"Meal slot config for '{meal_type}' missing 'template_name'")

        return cls(meal_type=meal_type, template_name=template_name)


@dataclass
class GAConfig:
    """
    Typed access to the 'genetic' block in config.json.

    Validates on construction via validate(). All parameters have sensible
    defaults so a minimal config block can be used for initial testing.
    """
    # Population
    population_size: int = 100
    epochs_per_run: int = 50
    new_members_per_epoch: int = 30

    # Operator rates (should sum to ~1.0)
    crossover_rate: float = 0.7
    mutation_rate: float = 0.2
    random_rate: float = 0.1

    # Genome constraints
    min_genome_size: int = 3
    max_genome_size: int = 8

    # Immigrant pool
    immigrant_pool_ratio: float = 0.10
    immigrant_tenure_epochs: int = 5

    # Meal slots (each references a meal_generation template)
    meal_slots: List[MealSlotConfig] = field(default_factory=list)

    # Selection
    selection_pressure: float = 1.5

    # Scoring weights per nutrient
    scoring_weights: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> 'GAConfig':
        """
        Extract and validate the 'genetic' block from config.json.

        Accepts either the full config dict (looks for 'genetic' key)
        or just the genetic sub-dict directly.

        Args:
            config: Full config dict or genetic sub-dict

        Returns:
            Validated GAConfig instance

        Raises:
            ValueError: If 'genetic' block is missing or contains invalid values
        """
        # Accept either full config or just the genetic block
        if "genetic" in config:
            ga_block = config["genetic"]
        else:
            ga_block = config

        if not isinstance(ga_block, dict):
            raise ValueError("'genetic' config must be a dict")

        # Parse meal slots
        raw_slots = ga_block.get("meal_slots", [])
        meal_slots = []
        if isinstance(raw_slots, list):
            for i, slot_data in enumerate(raw_slots):
                try:
                    meal_slots.append(MealSlotConfig.from_dict(slot_data))
                except ValueError as e:
                    raise ValueError(f"meal_slots[{i}]: {e}")

        instance = cls(
            population_size=ga_block.get("population_size", 100),
            epochs_per_run=ga_block.get("epochs_per_run", 50),
            new_members_per_epoch=ga_block.get("new_members_per_epoch", 30),
            crossover_rate=ga_block.get("crossover_rate", 0.7),
            mutation_rate=ga_block.get("mutation_rate", 0.2),
            random_rate=ga_block.get("random_rate", 0.1),
            min_genome_size=ga_block.get("min_genome_size", 3),
            max_genome_size=ga_block.get("max_genome_size", 8),
            immigrant_pool_ratio=ga_block.get("immigrant_pool_ratio", 0.10),
            immigrant_tenure_epochs=ga_block.get("immigrant_tenure_epochs", 5),
            meal_slots=meal_slots,
            selection_pressure=ga_block.get("selection_pressure", 1.5),
            scoring_weights=ga_block.get("scoring_weights", {}),
        )

        # Validate
        errors = instance.validate()
        if errors:
            error_msg = "GA config validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            raise ValueError(error_msg)

        return instance

    @property
    def immigrant_pool_size_per_epoch(self) -> int:
        """Number of random immigrants generated each epoch."""
        return max(1, int(self.population_size * self.immigrant_pool_ratio))

    @property
    def max_immigrant_pool_total(self) -> int:
        """
        Theoretical max immigrant pool size.
        pool_size_per_epoch * tenure_epochs.
        """
        return self.immigrant_pool_size_per_epoch * self.immigrant_tenure_epochs

    @property
    def operator_rate_sum(self) -> float:
        """Sum of crossover, mutation, and random rates."""
        return self.crossover_rate + self.mutation_rate + self.random_rate

    def validate(self) -> List[str]:
        """
        Validate all config values.

        Returns:
            List of error messages. Empty list means valid.
        """
        errors = []

        # Population size
        if not isinstance(self.population_size, int) or self.population_size < 2:
            errors.append(f"population_size must be integer >= 2, got {self.population_size}")

        # Epochs
        if not isinstance(self.epochs_per_run, int) or self.epochs_per_run < 1:
            errors.append(f"epochs_per_run must be integer >= 1, got {self.epochs_per_run}")

        # New members per epoch
        if not isinstance(self.new_members_per_epoch, int) or self.new_members_per_epoch < 1:
            errors.append(f"new_members_per_epoch must be integer >= 1, got {self.new_members_per_epoch}")

        # Operator rates
        for name, rate in [("crossover_rate", self.crossover_rate),
                           ("mutation_rate", self.mutation_rate),
                           ("random_rate", self.random_rate)]:
            if not isinstance(rate, (int, float)) or rate < 0.0 or rate > 1.0:
                errors.append(f"{name} must be 0.0-1.0, got {rate}")

        rate_sum = self.operator_rate_sum
        if abs(rate_sum - 1.0) > 0.05:
            errors.append(
                f"Operator rates should sum to ~1.0 "
                f"(crossover={self.crossover_rate} + mutation={self.mutation_rate} "
                f"+ random={self.random_rate} = {rate_sum:.2f})"
            )

        # Genome size
        if not isinstance(self.min_genome_size, int) or self.min_genome_size < 2:
            errors.append(f"min_genome_size must be integer >= 2 (crossover needs at least 2 genes), got {self.min_genome_size}")

        if not isinstance(self.max_genome_size, int) or self.max_genome_size < 2:
            errors.append(f"max_genome_size must be integer >= 2, got {self.max_genome_size}")

        if self.min_genome_size > self.max_genome_size:
            errors.append(
                f"min_genome_size ({self.min_genome_size}) > max_genome_size ({self.max_genome_size})"
            )

        # Immigrant pool
        if not isinstance(self.immigrant_pool_ratio, (int, float)) or self.immigrant_pool_ratio < 0.0:
            errors.append(f"immigrant_pool_ratio must be >= 0.0, got {self.immigrant_pool_ratio}")

        if not isinstance(self.immigrant_tenure_epochs, int) or self.immigrant_tenure_epochs < 1:
            errors.append(f"immigrant_tenure_epochs must be integer >= 1, got {self.immigrant_tenure_epochs}")

        # Meal slots
        if not self.meal_slots:
            errors.append("meal_slots must contain at least one meal slot")

        # Selection pressure
        if not isinstance(self.selection_pressure, (int, float)) or self.selection_pressure < 1.0:
            errors.append(f"selection_pressure must be >= 1.0, got {self.selection_pressure}")

        # Scoring weights (optional but must be dict of str->number if present)
        if not isinstance(self.scoring_weights, dict):
            errors.append("scoring_weights must be a dict")
        else:
            for key, val in self.scoring_weights.items():
                if not isinstance(key, str):
                    errors.append(f"scoring_weights key must be string, got {type(key).__name__}")
                if not isinstance(val, (int, float)):
                    errors.append(f"scoring_weights['{key}'] must be numeric, got {type(val).__name__}")

        return errors

    def resolve_component_pools(self, thresholds_mgr) -> Dict[str, List[str]]:
        """
        Resolve the unified set of food codes available for each meal slot.

        For each meal slot, looks up the generation template's components,
        expands all pool references, and returns the full union of food codes.

        Args:
            thresholds_mgr: ThresholdsManager with component_pools and meal_generation

        Returns:
            Dict mapping meal_type -> list of all valid food codes (deduplicated)
            for each configured meal slot
        """
        result = {}

        for slot in self.meal_slots:
            template = thresholds_mgr.get_generation_template(
                slot.meal_type, slot.template_name
            )
            if not template:
                print(f"Warning: Generation template '{slot.template_name}' "
                      f"not found for meal type '{slot.meal_type}'")
                result[slot.meal_type] = []
                continue

            components = template.get("components", {})
            all_codes = set()

            for comp_name, comp_spec in components.items():
                if comp_name.startswith("_"):
                    continue
                pool_ref = comp_spec.get("pool_ref", "")
                if pool_ref:
                    expanded = thresholds_mgr.expand_pool(pool_ref)
                    all_codes.update(expanded)

            result[slot.meal_type] = sorted(c.lower() for c in all_codes)

        return result

    def summary(self) -> str:
        """
        Human-readable summary of GA configuration for display.

        Returns:
            Multi-line string with key parameters
        """
        lines = [
            "=== GA Configuration ===",
            f"Population size:      {self.population_size}",
            f"Epochs per run:       {self.epochs_per_run}",
            f"New members/epoch:    {self.new_members_per_epoch}",
            f"Genome size:          {self.min_genome_size}-{self.max_genome_size}",
            f"Operators:            crossover={self.crossover_rate:.0%} "
            f"mutation={self.mutation_rate:.0%} random={self.random_rate:.0%}",
            f"Selection pressure:   {self.selection_pressure}",
            f"Immigrant pool:       {self.immigrant_pool_ratio:.0%} of pop, "
            f"{self.immigrant_tenure_epochs} epoch tenure "
            f"(max pool: {self.max_immigrant_pool_total})",
        ]

        if self.meal_slots:
            slot_strs = [f"{s.meal_type}/{s.template_name}" for s in self.meal_slots]
            lines.append(f"Meal slots:           {', '.join(slot_strs)}")

        if self.scoring_weights:
            weight_strs = [f"{k}={v}" for k, v in self.scoring_weights.items()]
            lines.append(f"Scoring weights:      {', '.join(weight_strs)}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize back to config-compatible dict.

        Returns:
            Dict matching the expected config.json structure
        """
        return {
            "population_size": self.population_size,
            "epochs_per_run": self.epochs_per_run,
            "new_members_per_epoch": self.new_members_per_epoch,
            "crossover_rate": self.crossover_rate,
            "mutation_rate": self.mutation_rate,
            "random_rate": self.random_rate,
            "min_genome_size": self.min_genome_size,
            "max_genome_size": self.max_genome_size,
            "immigrant_pool_ratio": self.immigrant_pool_ratio,
            "immigrant_tenure_epochs": self.immigrant_tenure_epochs,
            "meal_slots": [
                {"meal_type": s.meal_type, "template_name": s.template_name}
                for s in self.meal_slots
            ],
            "selection_pressure": self.selection_pressure,
            "scoring_weights": self.scoring_weights,
        }