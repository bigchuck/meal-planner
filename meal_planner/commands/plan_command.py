# meal_planner/commands/plan_command.py
"""
Plan command - meal planning workspace for exploring options.

Provides subcommands for searching historical meals, creating variants,
and promoting candidates to pending.
"""
import shlex
import copy
from typing import List, Dict, Any, Optional, Tuple
import re

from .base import Command, register_command
from meal_planner.reports.report_builder import ReportBuilder
from meal_planner.utils.time_utils import categorize_time, normalize_meal_name, MEAL_NAMES
from meal_planner.parsers import CodeParser, eval_multiplier_expression

@register_command
class PlanCommand(Command):
    """Meal planning workspace."""
    
    name = "plan"
    help_text = "Meal planning workspace (plan help for subcommands)"
    
    def execute(self, args: str) -> None:
        """
        Route to appropriate subcommand.
        
        Args:
            args: Subcommand and its arguments
        """
        # Parse arguments (handles quotes properly)
        try:
            parts = shlex.split(args) if args.strip() else []
        except ValueError:
            # Fallback to simple split if shlex fails
            parts = args.strip().split() if args.strip() else []
        
        # No args or help request
        if not parts or parts[0] == "help":
            self._show_help()
            return
        
        subcommand = parts[0]
        subargs = parts[1:]
        
        # Route to subcommand handlers
        if subcommand == "search":
            self._search(subargs)
        elif subcommand == "show":
            self._show(subargs)
        elif subcommand == "add":
            self._add(subargs)
        elif subcommand == "rm":
            self._rm(subargs)
        elif subcommand == "move":
            self._move(subargs)
        elif subcommand == "ins":
            self._ins(subargs)
        elif subcommand == "setmult":
            self._setmult(subargs)
        elif subcommand == "promote":
            self._promote(subargs)
        elif subcommand == "discard":
            self._discard(subargs)
        elif subcommand == "invent":
            self._invent(subargs)
        elif subcommand == "report":
            self._report(subargs)
        else:
            print(f"\nUnknown subcommand: {subcommand}")
            print("Use 'plan help' to see available subcommands\n")
    
    def _show_help(self) -> None:
        """Display help for all subcommands."""
        print("""
=== Meal Planning Workspace ===

The planning workspace lets you search for historical meals, explore variants,
and promote candidates to your pending day.

Subcommands:

  search <meal> [options]     Search for meals matching criteria
                              Options:
                                --history N (default 10)
                                --<nutrient> min=X max=Y
                              
                              Example:
                                plan search lunch --history 10 --carbs_g max=50

  show [id]                   Show workspace contents
                              Without id: list all candidates
                              With id: detailed view of candidate
  
  add <id> <codes>            Add items to candidate (creates variant)
                              Example: plan add 2 VE.T1, FR.3
  
  rm <id> <indices>           Remove items from candidate (creates variant)
                              Example: plan rm 2 1,3
  
  setmult <id> <idx> <mult>   Set multiplier for item (creates variant)
                              Example: plan setmult 2 3 1.5
              
  move <id> <idx> <idx>       Move the item to a different place in the plan
                              Example: plan move 1 2 3

  ins <id> <idx> <codes>      Insert the codes at the index in the plan (creates variant)
                              Example: plan ins 1 2 SA.3
  
  promote <id> <HH:MM>        Promote candidate to pending at time
                              Example: plan promote 2 12:30
  
  discard                     Clear entire planning workspace
  
  invent <meal_name>          Create blank candidate to build from scratch
                              Example: plan invent lunch
  
  report <id> [--nutrients]   Show detailed breakdown for candidate
                              Example: plan report 2 --nutrients

Notes:
  - Workspace is session-only (cleared on exit)
  - Search automatically deduplicates by date/meal and composition
  - Modifications create variants (2 -> 2a -> 2b)
  - Invented meals use ID format N1, N2, etc.
  - Original item order is preserved throughout
""")
    
    # =========================================================================
    # Subcommand implementations (Phase 2+)
    # =========================================================================

    def _search(self, args: List[str]) -> None:
        """Search for meals and add to workspace."""
        if not args:
            print("\nUsage: plan search <meal_name> [--history N] [--<nutrient> min=X max=Y]")
            print("\nExamples:")
            print("  plan search lunch --history 10")
            print("  plan search lunch --carbs_g max=50 --gl max=15 --prot_g min=25")
            print("  plan search dinner --history 5 --cal max=600")
            print()
            return
        
        # Parse meal name (first arg)
        meal_name = normalize_meal_name(args[0])
        
        # Parse options
        history_count = 10  # default
        constraints = {}
        
        i = 1
        while i < len(args):
            arg = args[i]
            
            if arg == "--history":
                if i + 1 < len(args):
                    try:
                        history_count = int(args[i + 1])
                        i += 2
                        continue
                    except ValueError:
                        pass
            
            # Nutrient constraint: --<nutrient> min=X max=Y
            if arg.startswith("--"):
                nutrient = arg[2:]  # Remove --
                constraint = {}
                
                # Look ahead for min=X or max=Y
                i += 1
                while i < len(args) and not args[i].startswith("--"):
                    part = args[i]
                    if "=" in part:
                        key, val = part.split("=", 1)
                        if key in ("min", "max"):
                            try:
                                constraint[key] = float(val)
                            except ValueError:
                                pass
                    i += 1
                
                if constraint:
                    constraints[nutrient] = constraint
                continue
            
            i += 1
        
        # Execute search
        print(f"\n=== Searching for {meal_name} ===")
        print(f"History: Last {history_count} days")
        if constraints:
            constraint_strs = []
            for nutrient, bounds in constraints.items():
                if "min" in bounds and "max" in bounds:
                    constraint_strs.append(f"{nutrient} {bounds['min']}-{bounds['max']}")
                elif "min" in bounds:
                    constraint_strs.append(f"{nutrient} >={bounds['min']}")  # Changed
                elif "max" in bounds:
                    constraint_strs.append(f"{nutrient} <={bounds['max']}")  # Changed
            print(f"Constraints: {', '.join(constraint_strs)}")
        print()
      
        # Get log entries
        from datetime import date, timedelta
        end_date = date.today()
        start_date = end_date - timedelta(days=history_count)
        
        log_df = self.ctx.log.get_date_range(str(start_date), str(end_date))
        
        if log_df.empty:
            print("No log entries found in date range.\n")
            return
        
        # Search through log entries
        builder = ReportBuilder(self.ctx.master, self.ctx.nutrients)
        found_meals = []

        for _, row in log_df.iterrows():
            entry_date = str(row[self.ctx.log.cols.date])
            codes_str = str(row[self.ctx.log.cols.codes])
            
            if not codes_str or codes_str == "nan":
                continue
            
            # Parse items
            items = CodeParser.parse(codes_str)
            
            # Get meal breakdown
            report = builder.build_from_items(items, title="Search")
            breakdown = report.get_meal_breakdown()
            
            if not breakdown:
                continue

            # Look for target meal
            for m_name, first_time, meal_totals in breakdown:
                if m_name != meal_name:
                    continue
                
                # Extract items for this meal (in order)
                meal_items = self._extract_meal_items_in_order(items, meal_name)
                
                # Check for composite meals (L.* codes)
                has_composite = any(
                    item.get('code', '').upper().startswith('L.')
                    for item in meal_items
                )
                
                if has_composite:
                    continue  # Skip composite meals
                
                # Check constraints
                meets_constraints = self._check_constraints(meal_totals, constraints)
                
                if not meets_constraints:
                    continue
                
                # Create candidate data
                candidate_data = {
                    'source_date': entry_date,
                    'meal_name': meal_name,
                    'original_time': first_time,
                    'items': meal_items,
                    'totals': meal_totals.to_dict(),
                    'meets_constraints': True,
                    'modified': False,
                    'invented': False
                }
                
                found_meals.append(candidate_data)
        
        # Add to workspace (with duplicate detection)
        added_count = 0
        
        dup_date = []
        dup_composition = []

        for candidate in found_meals:
            dup_type = self._check_duplicate(candidate)

            if dup_type == "date":
                dup_date.append(candidate)
            elif dup_type == "composition":
                dup_composition.append(candidate)
            else:
                self._add_search_result(candidate)
                added_count += 1

        # Report results
        print(f"Found {len(found_meals)} meals matching criteria")
        print(f"Added {added_count} new candidates to workspace")

        if dup_date:
            print(f"Skipped {len(dup_date)} duplicate date(s):")
            for meal in dup_date:
                date = meal.get('source_date')
                print(f"  - {date}: already in workspace")
        
        if dup_composition:
            print(f"Skipped {len(dup_composition)} duplicate composition(s):")
            for meal in dup_composition[:5]:  # Show first 5
                date = meal.get('source_date')
                items = meal.get('items', [])
                codes = ', '.join([f"{i.get('code', '')} x{i.get('mult', 1.0):g}" 
                                if abs(i.get('mult', 1.0) - 1.0) > 1e-9 
                                else i.get('code', '')
                                for i in items if 'code' in i])
                print(f"  - {date}: {codes}")
            if len(dup_composition) > 5:
                print(f"  ... and {len(dup_composition) - 5} more")


            if len(dup_date) > 0:
                print(f"Skipped {len(dup_date)} duplicate date(s)")
            
            if len(dup_composition) > 0:
                print(f"Skipped {len(dup_composition)} duplicate composition(s)")
        
        total = len(self.ctx.planning_workspace['candidates'])
        print(f"\nWorkspace now has {total} total candidate(s)")
        print("Use 'plan show' to review\n")
    
    def _show(self, args: List[str]) -> None:
        """Show workspace contents."""
        if args:
            # Show specific candidate
            self._show_detail(args[0])
        else:
            # Show all candidates
            self._show_all()
    
    def _show_all(self) -> None:
        """Show all candidates grouped by meal type."""
        ws = self.ctx.planning_workspace
        
        if not ws['candidates']:
            print("\nPlanning workspace is empty.")
            print("Use 'plan search <meal>' to find candidates\n")
            return
        
        # Group by meal type
        by_meal = {}
        for c in ws['candidates']:
            meal = c['meal_name']
            if meal not in by_meal:
                by_meal[meal] = []
            by_meal[meal].append(c)
        
        print("\n=== Planning Workspace ===\n")
        
        for meal_name in sorted(by_meal.keys()):
            print(f"{meal_name}:")
            candidates = by_meal[meal_name]
            
            for c in candidates:
                status = "[OK]" if c.get("meets_constraints", True) else "[X]"  # Changed
                
                tags = []
                if c.get("modified"):
                    tags.append("Modified")
                if c.get("invented"):
                    tags.append("Invented")
                
                tag_str = " " + " ".join(tags) if tags else ""
                
                source = c.get("source_date", "")
                if source:
                    print(f"  #{c['id']} [{source}]{tag_str} {status}")
                else:
                    print(f"  #{c['id']}{tag_str} {status}")
            
            print()
        
        print("Use 'plan show <id>' for details")
        print("Use 'plan report <id>' for full breakdown")
        print()

    def _show_detail(self, candidate_id: str) -> None:
        """Show detailed view of candidate."""
        # Find candidate
        candidate = self._find_candidate(candidate_id)
        if not candidate:
            print(f"Candidate '{candidate_id}' not found.")
            return
        
        print(f"\n=== Candidate #{candidate_id} ===")
        
        # Header info
        if candidate.get('invented'):
            print(f"Type: Invented")
        elif candidate.get('modified'):
            parent_id = candidate.get('parent_id', '')
            ancestor_id = candidate.get('ancestor_id', '')
            print(f"Type: Modified (based on #{parent_id}, original #{ancestor_id})")
        else:
            print(f"Type: Original")
        
        if candidate.get('source_date'):
            print(f"Source: {candidate['source_date']} @ {candidate.get('original_time', '')}")
        
        print(f"Meal: {candidate['meal_name']}")
        
        status = "[OK] Meets constraints" if candidate.get('meets_constraints', True) else "[X] Constraint violations"  # Changed
        print(f"Status: {status}")
        
        # Modifications log
        if candidate.get('modifications'):
            print("\nModifications:")
            for mod in candidate['modifications']:
                print(f"  * {mod}")  # Changed from bullet to asterisk
        
        # Items list (in order)
        print("\nItems (in original order):")
        items = candidate.get('items', [])
        
        for i, item in enumerate(items, 1):
            code = item.get('code', '')
            mult = item.get('mult', 1.0)
            
            # Look up description
            row = self.ctx.master.lookup_code(code)
            desc = row.get(self.ctx.master.cols.option, '') if row else '(not found)'
            
            if abs(mult - 1.0) < 1e-9:
                print(f"  {i}. {code} - {desc}")
            else:
                print(f"  {i}. {code} x{mult:g} - {desc}")
        
        # Totals
        totals = candidate.get('totals', {})
        print("\nTotals:")
        print(f"  Cal: {int(totals.get('cal', 0))} | "
              f"P: {int(totals.get('prot_g', 0))}g | "
              f"C: {int(totals.get('carbs_g', 0))}g | "
              f"F: {int(totals.get('fat_g', 0))}g | "
              f"Sugars: {int(totals.get('sugar_g', 0))}g | "
              f"GL: {int(totals.get('gl', 0))}")
        
        print(f"Use 'plan report {candidate['id']}' for full breakdown")
    
    def _discard(self, args: List[str]) -> None:
        """Clear planning workspace."""
        ws = self.ctx.planning_workspace
        count = len(ws['candidates'])
        
        if count == 0:
            print("\nPlanning workspace is already empty.\n")
            return
        
        # Confirm if there are many candidates
        if count > 5:
            print(f"\nClear {count} candidates from planning workspace? (y/n): ", end="")
            response = input().strip().lower()
            if response not in ('y', 'yes'):
                print("Cancelled.\n")
                return
        
        # Clear workspace
        self.ctx.planning_workspace = {
            "candidates": [],
            "next_numeric_id": 1,
            "next_invented_id": 1
        }
        
        print(f"\nCleared {count} candidate(s) from planning workspace.\n")
    
    # =========================================================================
    # Helper methods for Phase 2
    # =========================================================================
    
    def _get_candidate(self, id_str: str) -> Optional[Dict[str, Any]]:
        """Find candidate by ID in workspace."""
        for c in self.ctx.planning_workspace['candidates']:
            if c['id'] == id_str:
                return c
        return None
    
    def _add_search_result(self, candidate_data: Dict) -> str:
        """Add search result to workspace, assign ID."""
        ws = self.ctx.planning_workspace
        
        # Assign sequential numeric ID
        id_str = str(ws['next_numeric_id'])
        ws['next_numeric_id'] += 1
        
        # Deep copy to avoid reference issues
        candidate_copy = copy.deepcopy(candidate_data)
        candidate_copy['id'] = id_str
        candidate_copy['parent_id'] = None
        candidate_copy['ancestor_id'] = id_str
    
        ws['candidates'].append(candidate_copy)

        return id_str
    
    def _extract_meal_items_in_order(self, all_items: List[Dict],
                                     target_meal: str) -> List[Dict]:
        """Extract items belonging to target meal, preserving order."""
        meal_items = []
        current_meal = None
        
        for item in all_items:
            # Time marker - update current meal context
            if 'time' in item and 'code' not in item:
                time_str = item.get('time', '')
                meal_override = item.get('meal_override')
                current_meal = categorize_time(time_str, meal_override)
                continue
            
            # Code item - add if it belongs to target meal
            if current_meal == target_meal:
                meal_items.append(item)
        
        return meal_items
    
    def _calculate_totals(self, items: List[Dict]) -> Dict[str, float]:
        """Calculate nutrient totals for items list."""
        totals = {
            'cal': 0.0,
            'prot_g': 0.0,
            'carbs_g': 0.0,
            'fat_g': 0.0,
            'sugar_g': 0.0,
            'gl': 0.0
        }
        
        for item in items:
            if 'code' not in item:
                continue
            
            code = item['code']
            mult = item.get('mult', 1.0)
            
            nutrients = self.ctx.master.get_nutrient_totals(code, mult)
            if nutrients:
                for key in totals.keys():
                    totals[key] += nutrients.get(key, 0.0)
        
        return totals
    
    def _check_constraints(self, meal_totals, constraints: Dict) -> bool:
        """Check if meal totals meet constraints."""
        if not constraints:
            return True
        
        totals_dict = meal_totals.to_dict()
        
        for nutrient, bounds in constraints.items():
            # Map nutrient name to totals dict key
            value = totals_dict.get(nutrient)
            
            if value is None:
                continue  # Nutrient not available
            
            if 'min' in bounds and value < bounds['min']:
                return False
            
            if 'max' in bounds and value > bounds['max']:
                return False
        
        return True
    
    def _check_duplicate(self, candidate_data: Dict) -> Optional[str]:
        """
        Check for duplicates, return type.
        
        Returns:
            None - not a duplicate
            "date" - duplicate by date/meal
            "composition" - duplicate by items
        """
        source_date = candidate_data.get('source_date')
        meal_name = candidate_data.get('meal_name')
        items = candidate_data.get('items', [])
        
        if source_date is None:
            return None
        
        # Normalize for composition comparison
        normalized_items = self._normalize_items_for_comparison(items)
        
        for c in self.ctx.planning_workspace['candidates']:
            # Only check against originals, not variants
            if c.get('modified', False):
                continue
            
            # Level 1: Same date and meal (fast path)
            if (c.get('source_date') == source_date and 
                c.get('meal_name') == meal_name):
                return "date"
            
            # Level 2: Same composition (within same meal type)
            if c.get('meal_name') == meal_name:
                existing_normalized = self._normalize_items_for_comparison(
                    c.get('items', [])
                )
                if normalized_items == existing_normalized:
                    return "composition"
        
        return None
    
    def _normalize_items_for_comparison(self, items: List[Dict]) -> tuple:
        """
        Create normalized, order-independent representation.
        
        Used only for duplicate detection, not storage.
        """
        # Extract only code items (skip time markers)
        code_items = []
        for item in items:
            if 'code' not in item:
                continue
            
            code = item['code'].upper().strip()
            mult = float(item.get('mult', 1.0))
            
            # Round multiplier to avoid floating point issues
            mult = round(mult, 6)
            
            code_items.append((code, mult))
        
        # Sort for order-independence
        result = tuple(sorted(code_items))
        return result

    """
    > plan search lunch --history 10 --carbs_g max=50 --gl max=15
    > plan show
    > plan show 1
    > plan discard
    """
    
    
    def _add(self, args: List[str]) -> None:
            """
            Add items to existing candidate (creates variant).
            
            Usage: plan add <id> <codes>
            Example: plan add 2 VE.T1, FR.4 x0.5
            """           
            if len(args) < 2:
                print("Usage: plan add <id> <codes>")
                print("Example: plan add 2 VE.T1, FR.4 x0.5")
                return
            
            candidate_id = args[0]
            codes_str = ' '.join(args[1:])
            
            # Find candidate
            candidate = self._find_candidate(candidate_id)
            if not candidate:
                print(f"Candidate '{candidate_id}' not found.")
                return
            
            # Parse new codes
            new_items = CodeParser.parse(codes_str)
            if not new_items:
                print("No valid codes found.")
                return

            # Check if invented - modify in-place
            if candidate.get('type') == 'invented':
                candidate['items'].extend(new_items)
                candidate['modification_log'].append(f"Added {len(new_items)} item(s)")
                candidate['totals'] = self._calculate_totals(candidate['items'])
                
                print(f"Updated #{candidate['id']} (added {len(new_items)} item(s))")
                self._show_detail(candidate['id'])
                return

            # Create variant
            variant = copy.deepcopy(candidate)
            variant['items'].extend(new_items)
            
            # Track modification
            variant['parent_id'] = candidate['id']
            variant['ancestor_id'] = candidate.get('ancestor_id', candidate['id'])
            if 'modification_log' not in variant:
                variant['modification_log'] = []
            variant['modification_log'].append(f"Added {len(new_items)} item(s)")
            
            # Assign variant ID and add to workspace
            new_id = self._assign_variant_id(candidate['id'])
            variant['id'] = new_id
            
            ws = self.ctx.planning_workspace
            ws['candidates'].append(variant)
            
            # Recalculate totals
            variant['totals'] = self._calculate_totals(variant['items'])
            
            print(f"Created variant #{new_id} (added {len(new_items)} item(s) to #{candidate_id})")
            self._show_detail(new_id)
    
    def _rm(self, args: List[str]) -> None:
        """
        Remove items from candidate (creates variant).
        
        Usage: plan rm <id> <indices>
        Example: plan rm 2 3,5 or plan rm 2 3-5
        """
        candidate_id = args[0]
        indices_str = args[1]

        # Find candidate
        candidate = self._find_candidate(candidate_id)
        if not candidate:
            print(f"Candidate '{candidate_id}' not found.")
            return
        
        n = len(candidate['items'])
        if n == 0:
            print("No items to remove.")
            return
        
        # Parse indices (1-based to 0-based)
        indices = self._parse_indices(indices_str, n)
        if not indices:
            print("No valid indices.")
            return

        # Check if invented - modify in-place
        if candidate.get('type') == 'invented':
            # Remove items in reverse order
            for idx in reversed(sorted(indices)):
                del candidate['items'][idx]
            candidate['modification_log'].append(f"Removed {len(indices)} item(s)")
            candidate['totals'] = self._calculate_totals(candidate['items'])
            
            print(f"Updated #{candidate['id']} (removed {len(indices)} item(s))")
            self._show_detail(candidate['id'])
            return
        
        # Create variant
        variant = copy.deepcopy(candidate)
        
        # Remove items in reverse order
        for idx in reversed(sorted(indices)):
            del variant['items'][idx]
        
        # Track modification
        variant['parent_id'] = candidate['id']
        variant['ancestor_id'] = candidate.get('ancestor_id', candidate['id'])
        if 'modification_log' not in variant:
            variant['modification_log'] = []
        variant['modification_log'].append(f"Removed {len(indices)} item(s)")
        
        # Assign variant ID and add to workspace
        new_id = self._assign_variant_id(candidate['id'])
        variant['id'] = new_id
        
        ws = self.ctx.planning_workspace
        ws['candidates'].append(variant)
        
        # Recalculate totals
        variant['totals'] = self._calculate_totals(variant['items'])
        
        print(f"Created variant #{new_id} (removed {len(indices)} item(s) from #{candidate_id})")
        self._show_detail(new_id)
    
    def _move(self, args: List[str]) -> None:
        """
        Move item within candidate (creates variant).
        
        Usage: plan move <id> <from> <to>
        Example: plan move 2 3 1
        """
        if len(args) != 3:
            print("Usage: plan move <id> <from> <to>")
            print("Example: plan move 2 3 1")
            return
        
        candidate_id = args[0]
        
        try:
            from_idx = int(args[1])
            to_idx = int(args[2])
        except ValueError:
            print("Invalid indices. Use integers.")
            return
        
        # Find candidate
        candidate = self._find_candidate(candidate_id)
        if not candidate:
            print(f"Candidate '{candidate_id}' not found.")
            return
        
        n = len(candidate['items'])
        if n == 0:
            print("No items to move.")
            return
        
        if not (1 <= from_idx <= n and 1 <= to_idx <= n):
            print(f"Indices must be between 1 and {n}.")
            return

        # Check if invented - modify in-place
        if candidate.get('type') == 'invented':
            # Convert to 0-based and move
            from_idx -= 1
            to_idx -= 1
        
            item = candidate['items'].pop(from_idx)
            candidate['items'].insert(to_idx, item)
            candidate['modification_log'].append(f"Moved item from {from_idx+1} to {to_idx+1}")
            candidate['totals'] = self._calculate_totals(candidate['items'])
            
            print(f"Updated #{candidate['id']} (moved item)")
            self._show_detail(candidate['id'])
            return
        
        # Create variant
        variant = copy.deepcopy(candidate)
        
        # Convert to 0-based and move
        from_idx -= 1
        to_idx -= 1
        
        item = variant['items'].pop(from_idx)
        variant['items'].insert(to_idx, item)
        
        # Track modification
        variant['parent_id'] = candidate['id']
        variant['ancestor_id'] = candidate.get('ancestor_id', candidate['id'])
        if 'modification_log' not in variant:
            variant['modification_log'] = []
        variant['modification_log'].append(f"Moved item from {from_idx+1} to {to_idx+1}")
        
        # Assign variant ID and add to workspace
        new_id = self._assign_variant_id(candidate['id'])
        variant['id'] = new_id
        
        ws = self.ctx.planning_workspace
        ws['candidates'].append(variant)
        
        # Recalculate totals
        variant['totals'] = self._calculate_totals(variant['items'])
        
        print(f"Created variant #{new_id} (moved item in #{candidate_id})")
        self._show_detail(new_id)
    
    def _setmult(self, args: List[str]) -> None:
        """
        Set multiplier for item in candidate (creates variant).
        
        Usage: plan setmult <id> <idx> <mult>
        Example: plan setmult 2 3 1.5
        """
        if len(args) != 3:
            print("Usage: plan setmult <id> <idx> <mult>")
            print("Example: plan setmult 2 3 1.5")
            return
        
        candidate_id = args[0]
        
        try:
            idx = int(args[1])
        except ValueError:
            print("Invalid index. Use integer.")
            return
        
        mult_str = args[2].strip()
        
        # Handle leading dot
        if mult_str.startswith("."):
            mult_str = "0" + mult_str
        
        # Evaluate multiplier
        try:
            mult = eval_multiplier_expression(mult_str)
        except Exception:
            print(f"Invalid multiplier: {mult_str}")
            return
        
        # Find candidate
        candidate = self._find_candidate(candidate_id)
        if not candidate:
            print(f"Candidate '{candidate_id}' not found.")
            return
        
        n = len(candidate['items'])
        if not (1 <= idx <= n):
            print(f"Index must be between 1 and {n}.")
            return
        
        # Convert to 0-based
        idx -= 1
        
        # Check if it's a code item
        item = candidate['items'][idx]
        if "code" not in item:
            print("Cannot set multiplier on time marker.")
            return

        # Check if invented - modify in-place
        if candidate.get('type') == 'invented':
            # Set multiplier
            old_mult = candidate['items'][idx].get('mult', 1.0)
            candidate['items'][idx]['mult'] = mult
            candidate['modification_log'].append(f"Changed item {idx+1} mult from {old_mult:g} to {mult:g}")
            candidate['totals'] = self._calculate_totals(candidate['items'])
            
            print(f"Updated #{candidate['id']} (changed mult on item)")
            self._show_detail(candidate['id'])
            return
        
        # Create variant
        variant = copy.deepcopy(candidate)
        
        # Set multiplier
        old_mult = variant['items'][idx].get('mult', 1.0)
        variant['items'][idx]['mult'] = mult
        
        # Track modification
        variant['parent_id'] = candidate['id']
        variant['ancestor_id'] = candidate.get('ancestor_id', candidate['id'])
        if 'modification_log' not in variant:
            variant['modification_log'] = []
        variant['modification_log'].append(f"Changed item {idx+1} mult from {old_mult:g} to {mult:g}")
        
        # Assign variant ID and add to workspace
        new_id = self._assign_variant_id(candidate['id'])
        variant['id'] = new_id
        
        ws = self.ctx.planning_workspace
        ws['candidates'].append(variant)
        
        # Recalculate totals
        variant['totals'] = self._calculate_totals(variant['items'])
        
        print(f"Created variant #{new_id} (changed multiplier in #{candidate_id})")
        self._show_detail(new_id)
    
    def _ins(self, args: List[str]) -> None:
        """
        Insert items at position in candidate (creates variant).
        
        Usage: plan ins <id> <position> <codes>
        Example: plan ins 2 3 B.1 *1.5, S2.4
        """
        
        if len(args) < 3:
            print("Usage: plan ins <id> <position> <codes>")
            print("Example: plan ins 2 3 B.1 *1.5, S2.4")
            return
        
        candidate_id = args[0]
        
        try:
            pos = int(args[1])
        except ValueError:
            print("Invalid position. Use integer.")
            return
        
        codes_str = ' '.join(args[2:])
        
        # Find candidate
        candidate = self._find_candidate(candidate_id)
        if not candidate:
            print(f"Candidate '{candidate_id}' not found.")
            return
        
        # Parse new codes
        new_items = CodeParser.parse(codes_str)
        if not new_items:
            print("No valid codes found.")
            return
        
        n = len(candidate['items'])
        
        # Clamp position (1-based, can be n+1 to append)
        pos = max(1, min(pos, n + 1))

        # Check if invented - modify in-place
        if candidate.get('type') == 'invented':
            # Convert to 0-based and insert
            pos -= 1
            for i, item in enumerate(new_items):
                candidate['items'].insert(pos + i, item)
            candidate['modification_log'].append(f"Inserted {len(new_items)} item(s) at position {pos+1}")
            candidate['totals'] = self._calculate_totals(candidate['items'])
            
            print(f"Updated #{candidate['id']} (inserted {len(new_items)} item(s))")
            self._show_detail(candidate['id'])
            return
        
        # Create variant
        variant = copy.deepcopy(candidate)
        
        # Convert to 0-based and insert
        pos -= 1
        for i, item in enumerate(new_items):
            variant['items'].insert(pos + i, item)
        
        # Track modification
        variant['parent_id'] = candidate['id']
        variant['ancestor_id'] = candidate.get('ancestor_id', candidate['id'])
        if 'modification_log' not in variant:
            variant['modification_log'] = []
        variant['modification_log'].append(f"Inserted {len(new_items)} item(s) at position {pos+1}")
        
        # Assign variant ID and add to workspace
        new_id = self._assign_variant_id(candidate['id'])
        variant['id'] = new_id
        
        ws = self.ctx.planning_workspace
        ws['candidates'].append(variant)
        
        # Recalculate totals
        variant['totals'] = self._calculate_totals(variant['items'])
        
        print(f"Created variant #{new_id} (inserted {len(new_items)} item(s) into #{candidate_id})")
        self._show_detail(new_id)
    
    def _invent(self, args: List[str]) -> None:
        """
        Create blank candidate for manual construction.
        
        Usage: plan invent <meal_name>
        Example: plan invent lunch
        """
        
        if len(args) == 0:
            print("Usage: plan invent <meal_name>")
            print("Example: plan invent lunch")
            print("   or: plan invent \"afternoon snack\"")
            return
        
        # Join all parts and normalize
        meal_input = ' '.join(args)
        meal_name = normalize_meal_name(meal_input)
        
        # Validate meal name
        if meal_name not in MEAL_NAMES:
            print(f"Invalid meal name: {meal_input}")
            print(f"Valid names: {', '.join(MEAL_NAMES)}")
            return
        
        ws = self.ctx.planning_workspace
        
        # Assign N-prefixed ID
        invented_id = f"N{ws['next_invented_id']}"
        ws['next_invented_id'] += 1
        
        # Create blank candidate
        candidate = {
            'id': invented_id,
            'type': 'invented',
            'meal_name': meal_name,
            'items': [],
            'totals': self._calculate_totals([]),  # Empty totals
            'source_date': None,
            'source_time': None,
            'constraints_met': True,
            'modification_log': []
        }
        
        ws['candidates'].append(candidate)
        
        print(f"Created blank candidate #{invented_id} for {meal_name}")
        print("Use 'plan add {0} <codes>' to add items".format(invented_id))

    def _promote(self, args: List[str]) -> None:
        """
        Promote candidate to pending file.
        
        Usage: plan promote <id> <HH:MM> [--force]
        Example: plan promote 2a 12:30
        """
        if len(args) < 2:
            print("Usage: plan promote <id> <HH:MM> [--force]")
            print("Example: plan promote 2a 12:30")
            return
        
        candidate_id = args[0]
        time_str = args[1]
        force = '--force' in args or '-f' in args
        
        # Validate time format
        if not re.match(r'^\d{1,2}:\d{2}$', time_str):
            print(f"Invalid time format: {time_str}")
            print("Use HH:MM format (e.g., 12:30)")
            return
        
        # Find candidate
        candidate = self._find_candidate(candidate_id)
        if not candidate:
            print(f"Candidate '{candidate_id}' not found.")
            return
        
        if not candidate['items']:
            print(f"Candidate #{candidate['id']} has no items to promote.")
            return
        
        # Load or create pending
        try:
            pending = self.ctx.pending_mgr.load()
        except Exception:
            pending = None
        
        if pending is None:
            from datetime import date
            pending = {
                "date": str(date.today()),
                "items": []
            }
        
        # Check for time collision
        existing_times = [item.get('time') for item in pending.get('items', []) 
                         if 'time' in item and item.get('time')]
        
        if time_str in existing_times:
            if not force:
                print(f"Pending already has a meal at {time_str}")
                print("Use --force to append anyway")
                return
            else:
                print(f"Warning: Pending already has a meal at {time_str}, appending anyway...")
        
        # Create time marker (no meal_override - HH:MM is sufficient)
        time_marker = {"time": time_str}
        
        # Deep copy candidate items
        items_to_add = [time_marker] + copy.deepcopy(candidate['items'])
        
        # Append to pending
        pending['items'].extend(items_to_add)
        
        # Save
        self.ctx.pending_mgr.save(pending)
        
        meal_label = candidate.get('meal_name', 'meal')
        print(f"Promoted #{candidate['id']} ({meal_label}) to pending at {time_str}")
        print(f"Added {len(candidate['items'])} item(s) to pending")
    
    def _report(self, args: List[str]) -> None:
        """
        Show detailed report for candidate.
        
        Usage: plan report <id> [--recipes] [--nutrients]
        Example: plan report 2a --nutrients
        """
        if len(args) < 1:
            print("Usage: plan report <id> [--recipes] [--nutrients]")
            print("Example: plan report 2a --nutrients")
            return
        
        candidate_id = args[0]
        show_recipes = '--recipes' in args or '--recipe' in args
        show_nutrients = '--nutrients' in args or '--nutrient' in args or '--micro' in args
        
        # Find candidate
        candidate = self._find_candidate(candidate_id)
        if not candidate:
            print(f"Candidate '{candidate_id}' not found.")
            return
        
        if not candidate['items']:
            print(f"Candidate #{candidate['id']} has no items to report.")
            return
        
        # Build report
        builder = ReportBuilder(self.ctx.master, self.ctx.nutrients)
        
        # Create title
        meal_label = candidate.get('meal_name', 'meal')
        source_label = candidate.get('source_date', 'Invented')
        title = f"Report for Candidate #{candidate['id']} ({meal_label} from {source_label})"
        
        report = builder.build_from_items(candidate['items'], title=title)
        
        # Show main report
        report.print()
        
        # Show micronutrients if requested
        if show_nutrients and self.ctx.nutrients:
            self._show_report_nutrients(report)
        
        # Show recipes if requested
        if show_recipes and self.ctx.recipes:
            self._show_report_recipes(report)
    
    def _show_report_nutrients(self, report) -> None:
        """Show micronutrients for codes in report."""
        # Track codes we've seen (to show each only once)
        seen_codes = set()
        codes_in_order = []
        
        # Get codes in order they appear
        for row in report.rows:
            code = row.code
            if code not in seen_codes:
                if self.ctx.nutrients.has_nutrients(code):
                    codes_in_order.append(code)
                    seen_codes.add(code)
        
        if not codes_in_order:
            print("\n(No micronutrient data for these items)\n")
            return
        
        # Get available nutrient columns
        available = self.ctx.nutrients.get_available_nutrients()
        if not available:
            print("\n(No micronutrient data available)\n")
            return
        
        # Show micronutrients
        print("=== Micronutrients ===")
        print()
        
        # Header
        print(f"{'Code':<10} {'x':>4} {'Fiber':>8} {'Sodium':>8} {'Potass':>8} {'VitA':>8} {'VitC':>8} {'Iron':>8}")
        print(f"{'':10} {'':>4} {'(g)':>8} {'(mg)':>8} {'(mg)':>8} {'(mcg)':>8} {'(mg)':>8} {'(mg)':>8}")
        print("-" * 78)

        # Data rows - show ALL rows with their multiplied values
        for row in report.rows:
            t = row.totals.rounded()
            mult_str = self._format_mult(row.multiplier)
            
            print(f"{row.code:<10} {mult_str:>4} {int(t.fiber_g):>8} {int(t.sodium_mg):>8} "
                f"{int(t.potassium_mg):>8} {int(t.vitA_mcg):>8} "
                f"{int(t.vitC_mg):>8} {int(t.iron_mg):>8}")
        
        # Separator and total
        print("-" * 78)
        t = report.totals.rounded()
        print(f"{'Total':10} {'':>4} {int(t.fiber_g):>8} {int(t.sodium_mg):>8} "
            f"{int(t.potassium_mg):>8} {int(t.vitA_mcg):>8} "
            f"{int(t.vitC_mg):>8} {int(t.iron_mg):>8}")
        
        print()

    def _format_mult(self, mult: float) -> str:
        """Format multiplier (borrowed from ReportBuilder)."""
        if abs(mult - round(mult)) < 1e-9:
            s = str(int(round(mult)))
            if len(s) <= 4:
                return s
            return s[:4]
        
        for dp in (3, 2, 1, 0):
            s = f"{mult:.{dp}f}"
            if '.' in s:
                s = s.rstrip('0')
                if s.endswith('.'):
                    s = s[:-1]
            if len(s) <= 4:
                return s
        
        if mult < 1:
            for dp in (3, 2, 1):
                s = f"{mult:.{dp}f}"[1:]
                if len(s) <= 4:
                    return s
        
        s = f"{mult:.1f}"
        return s[:4]

    def _show_report_recipes(self, report) -> None:
        """Show recipes for codes in report (once per code, in order)."""
        # Track codes we've seen (to show each recipe only once)
        seen_codes = set()
        codes_in_order = []
        
        # Get codes in order they appear
        for row in report.rows:
            code = row.code
            if code not in seen_codes:
                if self.ctx.recipes.has_recipe(code):
                    codes_in_order.append(code)
                    seen_codes.add(code)
        
        if not codes_in_order:
            print("\n(No recipes available for these items)\n")
            return
        
        # Show recipes
        print("=== Recipes ===")
        print()
        
        for code in codes_in_order:
            formatted = self.ctx.recipes.format_recipe(code)
            if formatted:
                print(formatted)

    # =========================================================================
    # Helper methods
    # =========================================================================
        
    def _find_candidate(self, candidate_id: str):
        """Find candidate by ID (case-insensitive)."""
        ws = self.ctx.planning_workspace
        candidate_id_upper = candidate_id.upper()
        for c in ws['candidates']:
            if c['id'].upper() == candidate_id_upper:
                return c
        return None
    
    def _assign_variant_id(self, parent_id: str) -> str:
        """
        Assign variant ID based on parent.
        
        Examples:
            parent="2" -> "2a"
            parent="2a" -> "2b"
            parent="2b" -> "2c"
        """
        ws = self.ctx.planning_workspace
        
        # Extract base numeric ID
        if parent_id[0] == 'N':
            # Invented meal variant
            base = parent_id.rstrip('abcdefghijklmnopqrstuvwxyz')
        else:
            # Search result variant
            base = parent_id.rstrip('abcdefghijklmnopqrstuvwxyz')
        
        # Find highest existing variant letter for this base
        letters = []
        for c in ws['candidates']:
            c_id = c['id']
            if c_id.startswith(base) and len(c_id) > len(base):
                suffix = c_id[len(base):]
                if suffix.isalpha() and len(suffix) == 1:
                    letters.append(suffix)
        
        # Assign next letter
        if not letters:
            next_letter = 'a'
        else:
            last_letter = max(letters)
            next_letter = chr(ord(last_letter) + 1)
        
        return base + next_letter
    
    def _parse_indices(self, indices_str: str, max_idx: int) -> list:
        """
        Parse indices string into 0-based list.
        
        Args:
            indices_str: String like "3,5" or "2-4"
            max_idx: Maximum valid index (length of list)
        
        Returns:
            List of 0-based indices
        """
        indices = set()
        
        for part in indices_str.split(","):
            part = part.strip()
            if not part:
                continue
            
            if "-" in part:
                # Range: "2-4"
                try:
                    a, b = part.split("-", 1)
                    start = int(a.strip())
                    end = int(b.strip())
                    for i in range(min(start, end), max(start, end) + 1):
                        if 1 <= i <= max_idx:
                            indices.add(i - 1)  # Convert to 0-based
                except ValueError:
                    pass
            else:
                # Single index
                try:
                    i = int(part)
                    if 1 <= i <= max_idx:
                        indices.add(i - 1)  # Convert to 0-based
                except ValueError:
                    pass
        
        return sorted(indices)