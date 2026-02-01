# meal_planner/generators/exhaustive_meal_generator.py
"""
Exhaustive combinatorial meal candidate generation.

Generates all possible meal combinations from component pools and templates.
"""
from typing import List, Dict, Any, Optional, Iterator, Tuple
import itertools

from meal_planner.data import MasterLoader


class ExhaustiveMealGenerator:
    """
    Generates meal candidates by exhaustively combining components.
    
    Uses:
    - Component pools from config (protein sources, vegetables, etc.)
    - Generation templates (structure: 1 protein + 2-3 vegetables + optional starch)
    - Combinatorial logic to create all valid combinations
    - Cursor-based iteration for batched generation
    """
    
    def __init__(self, master: MasterLoader, thresholds_mgr):
        """
        Initialize exhaustive generator.
        
        Args:
            master: Master food database
            thresholds_mgr: ThresholdsManager with component_pools and generation_templates
        """
        self.master = master
        self.thresholds_mgr = thresholds_mgr
        
        # Extract config sections we need
        if thresholds_mgr and thresholds_mgr.is_valid:
            config = thresholds_mgr.thresholds
            self.component_pools = config.get('component_pools', {})
            self.generation_templates = config.get('meal_generation', {})
        else:
            self.component_pools = {}
            self.generation_templates = {}
    
    def generate_batch(
        self,
        meal_type: str,
        count: int,
        cursor: int = 0,
        template_name: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Generate a batch of candidates starting from cursor position.
        
        Args:
            meal_type: Meal category (breakfast, lunch, dinner, etc.)
            count: Number of candidates to generate
            cursor: Current position in combinatorial space
            template_name: Specific template to use (None = use first available)
        
        Returns:
            Tuple of (candidates_list, new_cursor_position)
        """
        # Step 1: Load component pools
        pools = self._load_component_pools()
        
        # Step 2: Load generation template for meal_type
        template = self._load_generation_template(meal_type, template_name)
        
        if not template:
            return [], cursor
        
        # Step 3: Create iterator for all combinations
        combo_iterator = self._create_combination_iterator(template, pools)
        
        # Step 4: Skip to cursor position
        combo_iterator = self._advance_to_cursor(combo_iterator, cursor)
        
        # Step 5: Generate next 'count' combinations
        candidates = self._generate_candidates_from_iterator(
            combo_iterator, 
            count, 
            meal_type,
            template
        )
        
        # Step 6: Calculate new cursor position
        new_cursor = cursor + len(candidates)
        
        return candidates, new_cursor    

    def _load_component_pools(self) -> Dict[str, List[str]]:
        """
        Load component pools from configuration.
        
        Component pools define groups of interchangeable foods:
        - protein_sources: ["SO.1", "SO.11", "FI.8", ...]
        - vegetables: ["VE.14", "VE.36", "@salad_greens"]
        - salad_greens: ["VE.14", "VE.15", "VE.16"]
        
        Handles @references to other pools (e.g., @salad_greens expands to its contents).
        Validates all food codes exist in master.
        
        Returns:
            Dict mapping pool_name -> list of food codes
        """
        if not self.component_pools:
            return {}
        
        resolved_pools = {}
        
        # First pass: copy all pools as-is
        for pool_name, pool_items in self.component_pools.items():
            if not isinstance(pool_items, list):
                print(f"Warning: Pool '{pool_name}' is not a list, skipping")
                continue
            resolved_pools[pool_name] = pool_items.copy()
        
        # Second pass: resolve @references
        # Keep iterating until no more references found (handles nested references)
        max_iterations = 10  # Prevent infinite loops
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            changes_made = False
            
            for pool_name, pool_items in resolved_pools.items():
                expanded_items = []
                
                for item in pool_items:
                    if isinstance(item, str) and item.startswith('@'):
                        # Reference to another pool
                        ref_pool_name = item[1:]  # Remove @
                        
                        if ref_pool_name not in resolved_pools:
                            print(f"Warning: Pool '{pool_name}' references unknown pool '@{ref_pool_name}', skipping reference")
                            continue
                        
                        # Expand reference
                        ref_items = resolved_pools[ref_pool_name]
                        expanded_items.extend(ref_items)
                        changes_made = True
                    else:
                        # Regular food code
                        expanded_items.append(item)
                
                # Update pool with expanded items
                if changes_made:
                    resolved_pools[pool_name] = expanded_items
            
            # If no changes made, we're done
            if not changes_made:
                break
        
        if iteration >= max_iterations:
            print("Warning: Max iterations reached resolving pool references, possible circular reference")

        if iteration >= max_iterations:
            print("Warning: Max iterations reached resolving pool references, possible circular reference")
        
        # Third pass: expand patterns (items ending with ".")
        pattern_expanded_pools = {}
        
        for pool_name, pool_items in resolved_pools.items():
            expanded_items = []
            
            for item in pool_items:
                if isinstance(item, str) and item.endswith('.') and len(item) > 1:
                    # This is a pattern - expand to matching codes
                    prefix = item.upper()
                    all_codes = self.master.get_all_codes()
                    matches = [code for code in all_codes if code.startswith(prefix)]
                    
                    if not matches:
                        print(f"Warning: Pattern '{item}' in pool '{pool_name}' matches no food codes, skipping")
                        continue
                    
                    expanded_items.extend(matches)
                else:
                    expanded_items.append(item)
            
            pattern_expanded_pools[pool_name] = expanded_items
        
        # Fourth pass: validate food codes and remove duplicates
        validated_pools = {}
        
        for pool_name, pool_items in pattern_expanded_pools.items():
            validated_items = []
            seen_codes = set()
            
            for item in pool_items:
                # Skip if still a reference (shouldn't happen, but be safe)
                if isinstance(item, str) and item.startswith('@'):
                    print(f"Warning: Unresolved reference '{item}' in pool '{pool_name}', skipping")
                    continue
                
                # Normalize code
                code = item.upper() if isinstance(item, str) else str(item).upper()
                
                # Skip duplicates
                if code in seen_codes:
                    continue
                
                # Validate against master
                row = self.master.lookup_code(code)
                if row is None:
                    print(f"Warning: Food code '{code}' in pool '{pool_name}' not found in master, skipping")
                    continue
                
                validated_items.append(code)
                seen_codes.add(code)
            
            if validated_items:
                validated_pools[pool_name] = validated_items
            else:
                print(f"Warning: Pool '{pool_name}' has no valid items after validation")
        
        return validated_pools
    
    def _load_generation_template(self, meal_type: str, template_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Load generation template for specific meal type.
        
        Structure: meal_generation > meal_type > template_name
        {
            "breakfast": {
                "protein_low_carb": {
                    "targets_ref": "meal_templates.breakfast.protein_low_carb",
                    "components": {
                        "protein": {
                            "pool_ref": "breakfast_proteins",
                            "count": {"min": 1, "max": 2},
                            "required": true
                        },
                        "vegetable": {
                            "pool_ref": "breakfast_vegetables",
                            "count": {"min": 0, "max": 3},
                            "required": false
                        }
                    },
                    "constraints": {
                        "max_total_components": 4,
                        "base_code_uniqueness": true,
                        "nutrient_limits": {...}
                    }
                }
            }
        }
        
        Args:
            meal_type: Meal category (breakfast, lunch, etc.)
            template_name: Specific template name (e.g., "protein_low_carb")
                        If None, uses first available template for meal_type
        
        Returns:
            Template dict or None if not found
        """
        if not self.generation_templates:
            print(f"No generation templates defined in config")
            return None
        
        # Look up meal type
        meal_templates = self.generation_templates.get(meal_type)
        if meal_templates is None:
            meal_templates = self.generation_templates.get(meal_type.lower())
        
        if meal_templates is None:
            print(f"No generation templates found for meal type '{meal_type}'")
            print(f"Available meal types: {', '.join(self.generation_templates.keys())}")
            return None
        
        if not isinstance(meal_templates, dict):
            print(f"Templates for '{meal_type}' must be a dict")
            return None
        
        # Select specific template or use first one
        if template_name:
            template = meal_templates.get(template_name)
            if template is None:
                print(f"Template '{template_name}' not found for '{meal_type}'")
                print(f"Available templates: {', '.join(meal_templates.keys())}")
                return None
        else:
            # Use first available template
            if len(meal_templates) == 0:
                print(f"No templates available for '{meal_type}'")
                return None
            
            template_name = list(meal_templates.keys())[0]
            template = meal_templates[template_name]
            print(f"Using default template '{template_name}' for '{meal_type}'")
        
        # Validate template structure
        if not isinstance(template, dict):
            print(f"Template '{template_name}' for '{meal_type}' must be a dict")
            return None
        
        # Require 'components' section
        if 'components' not in template:
            print(f"Template '{template_name}' for '{meal_type}' missing 'components' section")
            return None
        
        components = template['components']
        if not isinstance(components, dict):
            print(f"Template '{template_name}' for '{meal_type}': 'components' must be a dict")
            return None
        
        if len(components) == 0:
            print(f"Template '{template_name}' for '{meal_type}': 'components' cannot be empty")
            return None
        
        # Validate each component
        for comp_name, component in components.items():
            if comp_name.startswith('_'):
                continue
            if not isinstance(component, dict):
                print(f"Template '{template_name}': component '{comp_name}' must be a dict")
                return None
            
            # Require 'pool_ref' field
            if 'pool_ref' not in component:
                print(f"Template '{template_name}': component '{comp_name}' missing 'pool_ref' field")
                return None
            
            # Require 'count' field with min/max
            if 'count' not in component:
                print(f"Template '{template_name}': component '{comp_name}' missing 'count' field")
                return None
            
            count_spec = component['count']
            if not isinstance(count_spec, dict):
                print(f"Template '{template_name}': component '{comp_name}' 'count' must be a dict")
                return None
            
            if 'min' not in count_spec or 'max' not in count_spec:
                print(f"Template '{template_name}': component '{comp_name}' 'count' must have 'min' and 'max'")
                return None
            
            count_min = count_spec['min']
            count_max = count_spec['max']
            
            if not isinstance(count_min, int) or count_min < 0:
                print(f"Template '{template_name}': component '{comp_name}' 'count.min' must be non-negative integer")
                return None
            
            if not isinstance(count_max, int) or count_max < count_min:
                print(f"Template '{template_name}': component '{comp_name}' 'count.max' must be >= count.min")
                return None
            
            # Validate 'required' flag if present (defaults to false)
            if 'required' in component:
                if not isinstance(component['required'], bool):
                    print(f"Template '{template_name}': component '{comp_name}' 'required' must be boolean")
                    return None
        
        # Validate constraints section if present
        if 'constraints' in template:
            constraints = template['constraints']
            
            if not isinstance(constraints, dict):
                print(f"Template '{template_name}': 'constraints' must be a dict")
                return None
            
            # Validate max_total_components if present
            if 'max_total_components' in constraints:
                max_total = constraints['max_total_components']
                if not isinstance(max_total, int) or max_total <= 0:
                    print(f"Template '{template_name}': 'max_total_components' must be positive integer")
                    return None
            
            # Validate base_code_uniqueness if present
            if 'base_code_uniqueness' in constraints:
                if not isinstance(constraints['base_code_uniqueness'], bool):
                    print(f"Template '{template_name}': 'base_code_uniqueness' must be boolean")
                    return None
            
            # Note: nutrient_limits validation would be extensive, skip for now
            # The ThresholdsManager already validates this structure
        
        # Add template metadata
        template['_template_name'] = template_name
        template['_meal_type'] = meal_type
        
        return template    
    
    def _create_combination_iterator(
        self,
        template: Dict[str, Any],
        pools: Dict[str, List[str]]
    ) -> Iterator[List[Tuple[str, str, float]]]:
        """
        Create iterator that generates all valid meal combinations.
        
        For a template with:
        - protein: 1-2 items from pool of 5 → C(5,1) + C(5,2) combinations
        - vegetable: 0-3 items from pool of 10 → C(10,0) + C(10,1) + ... combinations
        
        This generates combinations like:
        - [("protein", "SO.1", 1.0), ("vegetable", "VE.14", 0.5), ("vegetable", "VE.36", 0.5)]
        
        Args:
            template: Generation template structure
            pools: Component pools with food codes
        
        Yields:
            Lists of (component_name, food_code, multiplier) tuples
        """
        components = template.get('components', {})
        
        if not components:
            return iter([])
        
        # Get default multipliers from template
        default_multipliers = template.get('default_multipliers', {})
        
        # For each component, generate all possible selections
        component_selections = []
        component_names = []
        
        for comp_name, comp_spec in components.items():
            if comp_name.startswith('_'):
                continue
            pool_ref = comp_spec.get('pool_ref')
            count_spec = comp_spec.get('count', {})
            count_min = count_spec.get('min', 0)
            count_max = count_spec.get('max', 1)
            required = comp_spec.get('required', False)
            
            # Get the actual pool
            if pool_ref not in pools:
                print(f"Warning: Pool '{pool_ref}' referenced by component '{comp_name}' not found, skipping component")
                continue
            
            pool_items = pools[pool_ref]
            
            if not pool_items:
                print(f"Warning: Pool '{pool_ref}' for component '{comp_name}' is empty, skipping component")
                continue
            
            # Get default multiplier for this component (default to 1.0)
            # Try component name first, then pool_ref
            multiplier = default_multipliers.get(comp_name, 
                                                default_multipliers.get(pool_ref, 1.0))
            
            # Generate all combinations for each count in range
            all_combos_for_component = []
            
            # Determine actual range to iterate
            # If required=true and min=0, force min to 1
            actual_min = max(1, count_min) if required else count_min
            
            for n in range(actual_min, count_max + 1):
                # Handle n=0 case (empty selection)
                if n == 0:
                    all_combos_for_component.append([])
                else:
                    # Generate C(pool_items, n) combinations
                    for combo in itertools.combinations(pool_items, n):
                        # Convert to list of (comp_name, code, mult) tuples
                        combo_with_meta = [
                            (comp_name, code, multiplier) 
                            for code in combo
                        ]
                        all_combos_for_component.append(combo_with_meta)
            
            component_selections.append(all_combos_for_component)
            component_names.append(comp_name)
        
        # Generate cartesian product of all component selections
        if not component_selections:
            return iter([])
        
        # Use itertools.product to get all combinations across components
        for combo_across_components in itertools.product(*component_selections):
            # Flatten the nested structure
            # combo_across_components is a tuple of lists
            # Each list contains (comp_name, code, mult) tuples
            
            flattened = []
            for component_combo in combo_across_components:
                flattened.extend(component_combo)
            
            # Apply constraints if defined
            if self._passes_template_constraints(flattened, template):
                yield flattened
        
    def _passes_template_constraints(
        self,
        combination: List[Tuple[str, str, float]],
        template: Dict[str, Any]
    ) -> bool:
        """
        Check if combination passes template constraints.
        
        Constraints include:
        - max_total_components: Maximum number of food items in meal
        - base_code_uniqueness: Ensure no duplicate base codes (e.g., SO.1 and SO.1d)
        
        Args:
            combination: List of (comp_name, code, mult) tuples
            template: Template with constraints section
        
        Returns:
            True if combination passes all constraints
        """
        constraints = template.get('constraints', {})
        
        if not constraints:
            return True
        
        # Check max_total_components
        max_total = constraints.get('max_total_components')
        if max_total is not None:
            if len(combination) > max_total:
                return False
        
        # Check base_code_uniqueness
        if constraints.get('base_code_uniqueness', False):
            base_codes = set()
            for _, code, _ in combination:
                # Extract base code (remove variant suffix like 'd', 'w', etc.)
                # SO.1d -> SO.1, FI.8w -> FI.8
                base_code = code
                if len(code) > 0 and code[-1].isalpha() and '.' in code:
                    # Has potential suffix
                    base_code = code[:-1]
                
                if base_code in base_codes:
                    return False
                base_codes.add(base_code)
        
        return True
    
    def _advance_to_cursor(
        self,
        iterator: Iterator,
        cursor: int
    ) -> Iterator:
        """
        Skip iterator ahead to cursor position.
        
        This allows resuming generation from a previous session
        without regenerating already-seen candidates.
        
        Uses itertools.islice for efficient skipping without
        materializing skipped items in memory.
        
        Args:
            iterator: Combination iterator
            cursor: Position to skip to (0-based)
        
        Returns:
            Iterator advanced to cursor position
        """
        if cursor <= 0:
            # No skipping needed
            return iterator
        
        # Use islice to skip 'cursor' items efficiently
        # islice(iterator, cursor, None) returns iterator starting at position cursor
        # The skipped items are consumed but not stored
        advanced_iterator = itertools.islice(iterator, cursor, None)
        
        return advanced_iterator
    
    def _generate_candidates_from_iterator(
        self,
        iterator: Iterator[List[Tuple[str, str, float]]],
        count: int,
        meal_type: str,
        template: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Generate candidate meals from combination iterator.
        
        Converts raw combinations into candidate meal format:
        {
            "meal_type": "lunch",
            "items": [
                {"code": "SO.1", "mult": 1.0},
                {"code": "VE.14", "mult": 0.5}
            ],
            "generation_method": "exhaustive",
            "template_info": {
                "template_name": "protein_low_carb",
                "targets_ref": "meal_templates.breakfast.protein_low_carb"
            },
            "component_summary": {
                "protein": ["SO.1"],
                "vegetable": ["VE.14", "VE.36"]
            }
        }
        
        Args:
            iterator: Combination iterator yielding lists of (pool_name, code, mult) tuples
            count: Maximum number of candidates to generate
            meal_type: Meal category
            template: Template dict with metadata
        
        Returns:
            List of candidate meal dicts
        """
        candidates = []
        
        for i, combination in enumerate(iterator):
            if i >= count:
                break
            
            # Convert combination tuples to items list
            items = []
            component_summary = {}
            
            for pool_name, food_code, multiplier in combination:
                # Add to items
                items.append({
                    "code": food_code,
                    "mult": multiplier
                })
                
                # Track component summary (which pools contributed which codes)
                if pool_name not in component_summary:
                    component_summary[pool_name] = []
                component_summary[pool_name].append(food_code)
            
            # Build candidate
            candidate = {
                "meal_type": meal_type,
                "items": items,
                "generation_method": "exhaustive",
                "template_info": {
                    "template_name": template.get("_template_name"),
                    "targets_ref": template.get("targets_ref")
                },
                "component_summary": component_summary
            }
            
            candidates.append(candidate)
        
        return candidates
    
    def count_total_combinations(self, meal_type: str) -> int:
        """
        Calculate total number of possible combinations for a meal type.
        
        This helps users understand the combinatorial space size:
        - 5 proteins × C(10,2) vegetables × 3 starches = 675 combinations
        - 5 proteins × C(10,3) vegetables × 3 starches = 1800 combinations
        
        Args:
            meal_type: Meal category
        
        Returns:
            Total combination count (can be very large)
        """
        # TODO: Implement combination counting
        # Load template and pools
        # Calculate combinatorics for each component
        # Multiply to get total
        
        print(f"  [STUB] Counting combinations for {meal_type}...")
        
        return 0