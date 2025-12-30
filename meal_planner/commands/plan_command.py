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
from datetime import datetime, date, timedelta

from .base import Command, register_command
from meal_planner.reports.report_builder import ReportBuilder
from meal_planner.utils.time_utils import categorize_time, normalize_meal_name, MEAL_NAMES
from meal_planner.parsers import CodeParser, eval_multiplier_expression, expand_aliases

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
        elif subcommand == "copy":
            self._copy(subargs)
        elif subcommand == "describe":
            self._describe(subargs)
        elif subcommand == "rename":
            self._rename(subargs)        
        elif subcommand == "history":
            self._history(subargs)        
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
                                --code/--codes <expression>
                              
                              Example:
                                plan search lunch --history 10 --carbs_g max=50
                                plan search breakfast --codes "bf.1 and bv.4"
                                plan search lunch --code mt.10 --cal max=500
                                plan search "afternoon snack" --codes "mt.11 or mt.12"

  show [id]                   Show workspace contents
                              Without id: list all candidates
                              With id: detailed view of candidate
  
  add <id> <codes>            Add items to candidate (creates variant)
                              Example: plan add 2 VE.T1, FR.3
  
  copy <id>                   Copy meal, strip analyzed_as field
                              Example: plan copy 123a

  rename <from> <to>          Rename a workspace meal
                              Example: plan rename 123a lunch-final
  
  describe <id> "text"        Set description for meal
                              Example: plan describe N1 "Tomorrow's breakfast"

  rm <id> <indices>           Remove items from candidate (creates variant)
                              Example: plan rm 2 1,3
  
  setmult <id> <idx> <mult>   Set multiplier for item (creates variant)
                              Example: plan setmult 2 3 1.5
              
  move <id> <idx> <idx>       Move the item to a different place in the plan
                              Example: plan move 1 2 3

  ins <id> <idx> <codes>      Insert the codes at the index in the plan (creates variant)
                              Example: plan ins 1 2 SA.3
  
  promote <id> <HH:MM> [meal] Promote candidate to pending at time
                              Optional: specify meal name to override time-based categorization
                              Example: plan promote 2 12:30
                              plan promote 2a 11:00 lunch
                              plan promote 3 14:00 "afternoon snack"
  
  discard                     Clear entire planning workspace
  
  invent <meal_name>          Create blank candidate to build from scratch
                              Example: plan invent lunch
  
  report <id> [--nutrients] [--verbose]   Show detailed breakdown for candidate
                              Example: plan report 2 --nutrients

Notes:
  - Workspace auto-saves after each modification
  - Workspace auto-loads on program startup
  - Search automatically deduplicates by date/meal and composition
  - Modifications create variants (2 -> 2a -> 2b)
  - Invented meals use ID format N1, N2, etc.
  - Original item order is preserved throughout
  - Code filtering: Supports boolean logic (AND, OR, NOT), spaces = AND
    Use quotes for multi-word meal names or complex expressions
""")
    
    # =========================================================================
    # Subcommand implementations
    # =========================================================================

    def _search(self, args: List[str]) -> None:
        """Search for meals and add to workspace."""
        if not args:
            print("\nUsage: plan search <meal_name> [--history N] [--code/--codes <expr>] [--<nutrient> min=X max=Y]")
            print("\nExamples:")
            print("  plan search lunch --history 10")
            print("  plan search lunch --carbs_g max=50 --gl max=15 --prot_g min=25")
            print("  plan search dinner --history 5 --cal max=600")
            print("  plan search breakfast --codes \"bf.1 and bv.4\"")
            print("  plan search lunch --code mt.10 --cal max=500")

            print()
            return
        # Check if first arg is a flag (user forgot meal name)
        if args[0].startswith("--"):
            print("\nError: Missing meal name")
            print("Usage: plan search <meal_name> [options]")
            print(f"\nValid meal names: {', '.join(MEAL_NAMES)}")
            print("\nExamples:")
            print("  plan search breakfast --history 90 --code bv.4")
            print("  plan search lunch --codes \"mt.10 and ve.t1\"")
            print("  plan search \"afternoon snack\" --cal max=300")
            print()
            return
        
        # Parse meal name (first arg)
        meal_name = normalize_meal_name(args[0])

        # Validate meal name
        if meal_name not in MEAL_NAMES:
            print(f"\nError: Invalid meal name '{args[0]}'")
            print(f"Valid meal names: {', '.join(MEAL_NAMES)}")
            print("\nExamples:")
            print("  plan search breakfast --history 90")
            print("  plan search lunch --code mt.10")
            print("  plan search \"afternoon snack\" --cal max=300")
            print()
            return

        # Parse options
        history_count = 10  # default
        constraints = {}
        code_filter = None
        
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
            if arg in ("--code", "--codes"):
                if i + 1 < len(args):
                    code_filter = args[i + 1]
                    i += 2
                    continue

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
        if code_filter:
            print(f"Code filter: {code_filter}")

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

                if code_filter:
                    if not self._meal_matches_code_filter(meal_items, code_filter):
                        continue  # Skip meals that don't match code filter

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
        self.ctx.save_workspace()
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
        meals_by_type = {}
        for c in ws['candidates']:
            meal_type = c.get('meal_name', 'unknown')
            if meal_type not in meals_by_type:
                meals_by_type[meal_type] = []
            meals_by_type[meal_type].append(c)  
        
        print("\n=== Planning Workspace ===\n")
        
        for meal_type in sorted(meals_by_type.keys()):
            candidates = meals_by_type[meal_type]
            print(f"{meal_type.upper()}:")
            
            for c in candidates:
                c_id = c['id']
                items = c.get('items', [])
                totals = c.get('totals', {})
                
                # Get source info for display
                source_date = c.get('source_date', '')
                source_info = f"from {source_date}" if source_date else ""
                if c.get('type') == 'invented':
                    source_info = "invented"
                elif c.get('parent_id'):
                    parent = c.get('parent_id')
                    source_info = f"from {parent}"
                
                # Immutable indicator
                immutable = c.get('immutable', False)
                mut_indicator = "-" if immutable else "✓"
                
                # Format line
                cal = totals.get('cal', 0)
                prot = totals.get('prot_g', 0)
                item_count = len(items)
                
                desc = c.get('description', '')
                desc_str = f' - {desc}' if desc else ''
                
                print(f"  {c_id:<6} {mut_indicator}  {source_info:20}  "
                    f"{item_count} items  {cal:.0f} cal  {prot:.0f}g prot{desc_str}")
                    
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
        desc = candidate.get("description")
        if desc:
            print(f"Description: {desc}")
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

        if self.ctx.workspace_mgr:
            self.ctx.save_workspace()

        print(f"\nCleared {count} candidate(s) from planning workspace.\n")
        print("(Command history preserved)\n")
    
    def _rename(self, args: List[str]) -> None:
        """
        Rename a workspace meal (change its ID).
        
        Args:
            args: [from_id, to_id]
        
        Examples:
            plan rename breakfast-old breakfast-new
            plan rename 123a lunch-final
        """
        if len(args) != 2:
            print("\nUsage: plan rename <from_id> <to_id>")
            print("\nExamples:")
            print("  plan rename breakfast-old breakfast-new")
            print("  plan rename 123a lunch-final")
            print("  plan rename N1 dinner-v2")
            print()
            return
        
        from_id = args[0]
        to_id = args[1]
        
        # Find the source meal
        ws = self.ctx.planning_workspace
        source_meal = None
        
        for candidate in ws['candidates']:
            if candidate['id'].upper() == from_id.upper():
                source_meal = candidate
                break
        
        if not source_meal:
            print(f"\nWorkspace meal '{from_id}' not found.")
            print("Use 'plan show' to see available meals.\n")
            return
        
        # Check if target ID already exists
        for candidate in ws['candidates']:
            if candidate['id'].upper() == to_id.upper():
                print(f"\nError: Workspace meal '{to_id}' already exists.")
                print("Choose a different target ID.\n")
                return
        
        # Update the ID
        old_id = source_meal['id']
        source_meal['id'] = to_id
        
        # Update parent_id and ancestor_id references in ALL meals
        # (in case this meal is a parent or ancestor of others)
        for candidate in ws['candidates']:
            if candidate.get('parent_id') == old_id:
                candidate['parent_id'] = to_id
            if candidate.get('ancestor_id') == old_id:
                candidate['ancestor_id'] = to_id
        
        # Save workspace
        self.ctx.save_workspace()
        
        print(f"\nRenamed '{old_id}' → '{to_id}'\n")


    # =========================================================================
    # Helper methods
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
        candidate_copy['immutable'] = True  # NEW: Search results are immutable
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        source_date = candidate_copy.get('source_date', 'unknown')
        meal_name = candidate_copy.get('meal_name', 'meal')
        
        candidate_copy['history'] = [{
            'timestamp': timestamp,
            'command': 'plan search',  # Will be updated by caller if needed
            'note': f'created plan {id_str} from {source_date} {meal_name}'
        }]

        ws['candidates'].append(candidate_copy)

        self.ctx.save_workspace()

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
        Add items to candidate.
        
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
        new_items = expand_aliases(codes_str, self.ctx.aliases)
        if not new_items:
            print("No valid codes found.")
            return

        # Build command and note
        command_str = f"add {candidate_id} {codes_str}"
        edit_note = f"added {len(new_items)} item(s) to plan {candidate_id}"
        
        # Check if invented - modify in-place regardless
        if candidate.get('type') == 'invented':
            candidate['items'].extend(new_items)
            if 'modification_log' not in candidate:
                candidate['modification_log'] = []
            candidate['modification_log'].append(f"Added {len(new_items)} item(s)")
            candidate['totals'] = self._calculate_totals(candidate['items'])
            
            # Append to history
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            if 'history' not in candidate:
                candidate['history'] = []
            candidate['history'].append({
                'timestamp': timestamp,
                'command': command_str,
                'note': edit_note
            })
            
            self.ctx.save_workspace()
            print(f"Updated #{candidate['id']} (added {len(new_items)} item(s))")
            self._show_detail(candidate['id'])
            return

        # Check mutability and auto-copy if needed
        target, was_copied, new_id = self._ensure_mutable(candidate, command_str, edit_note)
        
        # Modify the target (whether it's a new copy or existing mutable)
        target['items'].extend(new_items)
        if 'modification_log' not in target:
            target['modification_log'] = []
        target['modification_log'].append(f"Added {len(new_items)} item(s)")
        target['totals'] = self._calculate_totals(target['items'])
        
        # If not copied, need to add history entry (copied already has it)
        if not was_copied:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            if 'history' not in target:
                target['history'] = []
            target['history'].append({
                'timestamp': timestamp,
                'command': command_str,
                'note': edit_note
            })
        
        self.ctx.save_workspace()
        
        if was_copied:
            print(f"Created {new_id} from {candidate_id} and added {len(new_items)} item(s)")
        else:
            print(f"Updated #{target['id']} (added {len(new_items)} item(s))")
        
        self._show_detail(target['id'])

    
    def _rm(self, args: List[str]) -> None:
        """
        Remove candidates from workspace OR items from a candidate.
        
        Usage: 
        plan rm <ids>              Remove candidates from workspace
        plan rm <id> <indices>     Remove items from candidate
        
        Examples:
        plan rm 7                  Remove candidate #7
        plan rm 7,8,9              Remove candidates #7, #8, #9
        plan rm 7-10               Remove candidates #7 through #10
        plan rm 2 3,5              Remove items at positions 3,5 from candidate #2
        """
        if len(args) == 0:
            print("Usage:")
            print("  plan rm <ids>              Remove candidates from workspace")
            print("  plan rm <id> <indices>     Remove items from candidate")
            print("\nExamples:")
            print("  plan rm 7                  Remove candidate #7")
            print("  plan rm 7,8,9              Remove candidates #7, #8, #9")
            print("  plan rm 7-10               Remove candidates #7 through #10")
            print("  plan rm 2 3,5              Remove items at positions 3,5 from candidate #2")
            return
        
        if len(args) == 1:
            # Remove entire candidate(s) from workspace
            self._rm_candidates(args[0])
        elif len(args) == 2:
            # Remove items from within a candidate (existing behavior)
            self._rm_items_from_candidate(args[0], args[1])
        else:
            print("Error: Too many arguments")
            print("Usage: plan rm <ids> OR plan rm <id> <indices>")

    def _rm_candidates(self, ids_str: str) -> None:
        """Remove entire candidates from workspace."""
        
        # Parse IDs
        ids_to_remove = self._parse_candidate_ids(ids_str)
        
        if not ids_to_remove:
            print("No valid IDs provided")
            return
        
        # Find candidates
        ws = self.ctx.planning_workspace
        found_candidates = []
        not_found = []
        
        for candidate_id in ids_to_remove:
            candidate = self._find_candidate(candidate_id)
            if candidate:
                found_candidates.append(candidate)
            else:
                not_found.append(candidate_id)
        
        if not_found:
            print(f"Not found: {', '.join(not_found)}")
        
        if not found_candidates:
            print("No candidates to remove")
            return
        
        # Confirm if removing multiple
        if len(found_candidates) > 1:
            print(f"Remove {len(found_candidates)} candidates from workspace?")
            for c in found_candidates:
                desc = c.get("description", "")
                desc_str = f" - {desc}" if desc else ""
                print(f"  #{c['id']} ({c.get('meal_name', 'meal')}){desc_str}")
            
            response = input("Continue? (y/n): ").strip().lower()
            if response not in ('y', 'yes'):
                print("Cancelled")
                return
        
        # Remove candidates
        removed_ids = []
        for candidate in found_candidates:
            ws["candidates"].remove(candidate)
            removed_ids.append(candidate["id"])
        
        # Auto-save
        self.ctx.save_workspace()
        
        if len(removed_ids) == 1:
            print(f"Removed candidate #{removed_ids[0]}")
        else:
            print(f"Removed {len(removed_ids)} candidates: {', '.join(f'#{id}' for id in removed_ids)}")

    def _rm_items_from_candidate(self, candidate_id: str, indices_str: str) -> None:
        """
        Remove items from candidate (creates variant or modifies in-place for invented).
        
        This is the existing _rm behavior - moved to separate method.
        """
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

        # Build command and note
        command_str = f"rm {candidate_id} {indices_str}"
        edit_note = f"Removed {len(indices)} item(s) on plan {candidate_id}"

        # Check if invented - modify in-place
        if candidate.get('type') == 'invented':
            # Remove items in reverse order
            for idx in reversed(sorted(indices)):
                del candidate['items'][idx]
            candidate['modification_log'].append(f"Removed {len(indices)} item(s)")
            candidate['totals'] = self._calculate_totals(candidate['items'])
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            if 'history' not in candidate:
                candidate['history'] = []
            candidate['history'].append({
                'timestamp': timestamp,
                'command': command_str,
                'note': edit_note
            })
    
            self.ctx.save_workspace()
            
            print(f"Updated #{candidate['id']} (removed {len(indices)} item(s))")
            self._show_detail(candidate['id'])
            return
        
        target, was_copied, new_id = self._ensure_mutable(candidate, command_str, edit_note)
        
        # Remove items in reverse order
        for idx in reversed(sorted(indices)):
            del target['items'][idx]
        
        # Track modification
        target['parent_id'] = candidate['id']
        target['ancestor_id'] = candidate.get('ancestor_id', candidate['id'])
        if 'modification_log' not in target:
            target['modification_log'] = []
        target['modification_log'].append(f"Removed {len(indices)} item(s)")
        
        # Recalculate totals
        target['totals'] = self._calculate_totals(target['items'])

        if not was_copied:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            if 'history' not in target:
                target['history'] = []
            target['history'].append({
                'timestamp': timestamp,
                'command': command_str,
                'note': edit_note
            })
        
        self.ctx.save_workspace()
        
        if was_copied:
            print(f"Created {new_id} from {candidate_id} and removed {len(indices)} item(s)")
        else:
            print(f"Updated #{target['id']} (removed {len(indices)} item(s))")
        
        self._show_detail(target['id'])

    def _parse_candidate_ids(self, ids_str: str) -> List[str]:
        """
        Parse candidate IDs from string.
        
        Supports:
        - Single: "7"
        - Comma-separated: "7,8,9" or "123a,N1,2b"
        - Numeric ranges: "7-10" (expands to 7,8,9,10)
        
        Returns:
            List of candidate ID strings
        """
        ids = []
        
        for part in ids_str.split(","):
            part = part.strip()
            
            if "-" in part and not part.startswith("N"):
                # Potential range (e.g., "7-10")
                sides = part.split("-", 1)
                if len(sides) == 2:
                    left = sides[0].strip()
                    right = sides[1].strip()
                    
                    # Check if both sides are pure numeric (no letter suffixes)
                    if left.isdigit() and right.isdigit():
                        start = int(left)
                        end = int(right)
                        # Expand range
                        for i in range(start, end + 1):
                            ids.append(str(i))
                        continue
            
            # Not a valid range, treat as literal ID
            ids.append(part)
        
        return ids
    
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
        
        # Build command and note
        command_str = f"move {candidate_id} {from_idx} {to_idx}"
        edit_note = f"Moved {from_idx} to {to_idx} on plan {candidate_id}"

        # Check if invented - modify in-place
        if candidate.get('type') == 'invented':
            # Convert to 0-based and move
            from_idx -= 1
            to_idx -= 1
        
            item = candidate['items'].pop(from_idx)
            candidate['items'].insert(to_idx, item)
            candidate['modification_log'].append(f"Moved item from {from_idx+1} to {to_idx+1}")
            candidate['totals'] = self._calculate_totals(candidate['items'])

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            if 'history' not in candidate:
                candidate['history'] = []
            candidate['history'].append({
                'timestamp': timestamp,
                'command': command_str,
                'note': edit_note
            })
            
            self.ctx.save_workspace()
            
            print(f"Updated #{candidate['id']} (moved item)")
            self._show_detail(candidate['id'])
            return
        
        target, was_copied, new_id = self._ensure_mutable(candidate, command_str, edit_note)
        
        # Convert to 0-based and move
        from_idx -= 1
        to_idx -= 1
        
        item = target['items'].pop(from_idx)
        target['items'].insert(to_idx, item)
        
        # Track modification
        if 'modification_log' not in target:
            target['modification_log'] = []
        target['modification_log'].append(f"Moved item from {from_idx+1} to {to_idx+1}")
        
        # Recalculate totals
        target['totals'] = self._calculate_totals(target['items'])

        if not was_copied:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            if 'history' not in target:
                target['history'] = []
            target['history'].append({
                'timestamp': timestamp,
                'command': command_str,
                'note': edit_note
            })

        self.ctx.save_workspace()
        
        if was_copied:
            print(f"Created {new_id} from {candidate_id} and moved item in #{target['id']}")
        else:
            print(f"Updated #{target['id']} (moved item in #{target['id']})")

        self._show_detail(target['id'])
    
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

        # Build command and note
        command_str = f"setmult {candidate_id} {idx} {mult_str}"
        edit_note = f"Set multiplier {idx} to {mult_str} on plan {candidate_id}"

        # Check if invented - modify in-place
        if candidate.get('type') == 'invented':
            # Set multiplier
            old_mult = candidate['items'][idx].get('mult', 1.0)
            candidate['items'][idx]['mult'] = mult
            candidate['modification_log'].append(f"Changed item {idx+1} mult from {old_mult:g} to {mult:g}")
            candidate['totals'] = self._calculate_totals(candidate['items'])
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            if 'history' not in candidate:
                candidate['history'] = []
            candidate['history'].append({
                'timestamp': timestamp,
                'command': command_str,
                'note': edit_note
            })

            self.ctx.save_workspace()

            print(f"Updated #{candidate['id']} (changed mult on item)")
            self._show_detail(candidate['id'])
            return
        
        target, was_copied, new_id = self._ensure_mutable(candidate, command_str, edit_note)
        
        # Set multiplier
        old_mult = target['items'][idx].get('mult', 1.0)
        target['items'][idx]['mult'] = mult
        
        # Track modification
        target['parent_id'] = candidate['id']
        target['ancestor_id'] = candidate.get('ancestor_id', candidate['id'])
        if 'modification_log' not in target:
            target['modification_log'] = []
        target['modification_log'].append(f"Changed item {idx+1} mult from {old_mult:g} to {mult:g}")
               
        # Recalculate totals
        target['totals'] = self._calculate_totals(target['items'])

        if not was_copied:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            if 'history' not in target:
                target['history'] = []
            target['history'].append({
                'timestamp': timestamp,
                'command': command_str,
                'note': edit_note
            })

        self.ctx.save_workspace()
        
        if was_copied:
            print(f"Created {new_id} from {candidate_id} and set multiplier in #{target['id']}")
        else:
            print(f"Updated #{target['id']} (set multiplier in #{target['id']})")

        self._show_detail(target['id'])
    
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
        new_items = expand_aliases(codes_str, self.ctx.aliases)
        if not new_items:
            print("No valid codes found.")
            return
        
        n = len(candidate['items'])
        
        # Clamp position (1-based, can be n+1 to append)
        pos = max(1, min(pos, n + 1))

        # Build command and note
        command_str = f"ins {candidate_id} {pos} {codes_str}"
        edit_note = f"Insert {new_items} at {pos} on plan {candidate_id}"

        # Check if invented - modify in-place
        if candidate.get('type') == 'invented':
            # Convert to 0-based and insert
            pos -= 1
            for i, item in enumerate(new_items):
                candidate['items'].insert(pos + i, item)
            candidate['modification_log'].append(f"Inserted {len(new_items)} item(s) at position {pos+1}")
            candidate['totals'] = self._calculate_totals(candidate['items'])

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            if 'history' not in candidate:
                candidate['history'] = []
            candidate['history'].append({
                'timestamp': timestamp,
                'command': command_str,
                'note': edit_note
            })

            self.ctx.save_workspace()

            print(f"Updated #{candidate['id']} (inserted {len(new_items)} item(s))")
            self._show_detail(candidate['id'])
            return
        
        target, was_copied, new_id = self._ensure_mutable(candidate, command_str, edit_note)
        
        # Convert to 0-based and insert
        pos -= 1
        for i, item in enumerate(new_items):
            target['items'].insert(pos + i, item)
        
        # Track modification
        target['parent_id'] = candidate['id']
        target['ancestor_id'] = candidate.get('ancestor_id', candidate['id'])
        if 'modification_log' not in target:
            target['modification_log'] = []
        target['modification_log'].append(f"Inserted {len(new_items)} item(s) at position {pos+1}")
        
        # Recalculate totals
        target['totals'] = self._calculate_totals(target['items'])

        if not was_copied:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            if 'history' not in target:
                target['history'] = []
            target['history'].append({
                'timestamp': timestamp,
                'command': command_str,
                'note': edit_note
            })

        self.ctx.save_workspace()
        
        if was_copied:
            print(f"Created {new_id} from {candidate_id} and inserted in #{target['id']}")
        else:
            print(f"Updated #{target['id']} (insert in #{target['id']})")

        self._show_detail(target['id'])
    
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
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')

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
            'modification_log': [],
            'created': datetime.now().isoformat(),
            'immutable': False,  # NEW: Invented plans are mutable
            'history': [{  # NEW: Add history
                'timestamp': timestamp,
                'command': f'plan invent {meal_name}',
                'note': f'created plan {invented_id} (invented)'
            }]
        }
        
        ws['candidates'].append(candidate)

        self.ctx.save_workspace()
        
        print(f"Created blank candidate #{invented_id} for {meal_name}")
        print("Use 'plan add {0} <codes>' to add items".format(invented_id))

    def _promote(self, args: List[str]) -> None:
        """
        Promote candidate to pending file.
        
        Usage: plan promote <id> <HH:MM> [meal_name] [--force]
        Example: plan promote 2a 12:30
                plan promote 2a 11:00 lunch
                plan promote 2a 11:00 "afternoon snack"
        """
        if len(args) < 2:
            print("Usage: plan promote <id> <HH:MM> [meal_name] [--force]")
            print("Example: plan promote 2a 12:30")
            print("         plan promote 2a 11:00 lunch")
            return
        
        candidate_id = args[0]
        time_str = args[1]
        
        # Check for flags
        force = '--force' in args or '-f' in args
        
        # Extract optional meal name (third positional arg, if not a flag)
        meal_name_override = None
        if len(args) >= 3 and not args[2].startswith('--') and args[2] not in ['-f']:
            meal_input = args[2]
            meal_name_override = normalize_meal_name(meal_input)
            
            # Validate meal name
            if meal_name_override not in MEAL_NAMES:
                print(f"Invalid meal name: {meal_input}")
                print(f"Valid names: {', '.join(MEAL_NAMES)}")
                return
        
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
        
        # Create time marker with optional meal override
        time_marker = {"time": time_str}
        if meal_name_override:
            time_marker["meal_override"] = meal_name_override
        
        # Deep copy candidate items
        items_to_add = [time_marker] + copy.deepcopy(candidate['items'])
        
        # Append to pending
        pending['items'].extend(items_to_add)
        
        # Save
        self.ctx.pending_mgr.save(pending)
        
        # Build output message
        meal_label = candidate.get('meal_name', 'meal')
        if meal_name_override:
            print(f"Promoted #{candidate['id']} ({meal_label}) to pending at {time_str} as '{meal_name_override}'")
        else:
            print(f"Promoted #{candidate['id']} ({meal_label}) to pending at {time_str}")
        print(f"Added {len(candidate['items'])} item(s) to pending")

    def _report(self, args: List[str]) -> None:
        """
        Show detailed report for candidate.
        
        Usage: plan report <id> [--recipes] [--nutrients] [--verbose] [--stage]
        Example: plan report 2a --nutrients
        """
        if len(args) < 1:
            print("Usage: plan report <id> [--recipes] [--nutrients] [--verbose] [--stage]")
            print("Example: plan report 2a --nutrients")
            return
        
        candidate_id = args[0]
        show_recipes = '--recipes' in args or '--recipe' in args
        show_nutrients = '--nutrients' in args or '--nutrient' in args or '--micro' in args
        verbose = "--verbose" in args
        stage = "--stage" in args
        
        # --stage auto-enables verbose
        if stage:
            verbose = True

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
        
        if stage:
            self._stage_workspace_report(report, candidate_id, candidate)

        # Show main report (abbreviated if staging, normal otherwise)
        if stage:
            # Show abbreviated format
            lines = report.format_abbreviated()
            for line in lines:
                print(line)
        else:
            # Normal display
            report.print(verbose=verbose)        

        if not stage:
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

   
    def _describe(self, args: List[str]) -> None:
        """
        Set description for workspace meal.
        
        Usage: plan describe <id> "description"
        Example: plan describe N1 "Monday breakfast - high protein"
        """
        if len(args) < 2:
            print('Usage: plan describe <id> "description"')
            print('Example: plan describe N1 "Monday breakfast"')
            return
        
        candidate_id = args[0]
        description = ' '.join(args[1:])
        
        # Remove quotes if present
        if description.startswith('"') and description.endswith('"'):
            description = description[1:-1]
        elif description.startswith("'") and description.endswith("'"):
            description = description[1:-1]
        
        # Find candidate
        candidate = self._find_candidate(candidate_id)
        if not candidate:
            print(f"Candidate '{candidate_id}' not found.")
            return
        
        # Set description
        candidate["description"] = description
        
        # Auto-save
        self.ctx.save_workspace()
        
        print(f"Description set for {candidate_id}")

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
    
    def _meal_matches_code_filter(self, meal_items: List[Dict], code_filter: str) -> bool:
        """
        Check if meal's codes match the boolean code filter.
        
        Args:
            meal_items: List of item dicts with 'code' field
            code_filter: Boolean expression (e.g., "bf.1 and bv.4", "mt.10 or mt.11")
        
        Returns:
            True if meal matches filter, False otherwise
        """
        from meal_planner.utils.search import parse_search_query
        
        # Get meal's codes (uppercase, ignore multipliers for matching)
        meal_codes = {item['code'].upper() for item in meal_items if 'code' in item}
        
        # Parse the code filter into clauses
        try:
            clauses = parse_search_query(code_filter)
        except Exception:
            # If parsing fails, treat as simple code check
            simple_code = code_filter.upper().strip()
            return any(code.startswith(simple_code) for code in meal_codes)
        
        if not clauses:
            return True  # Empty filter matches all
        
        # Check if any clause matches (OR between clauses)
        for clause in clauses:
            # All positive terms must be present (AND within clause)
            all_pos_match = all(
                any(code.startswith(term.upper()) for code in meal_codes)
                for term in clause['pos']
            )
            
            if all_pos_match:
                # No negative terms can be present (NOT)
                no_neg_match = not any(
                    any(code.startswith(term.upper()) for code in meal_codes)
                    for term in clause['neg']
                    )
                
                if no_neg_match:
                    return True
        
        return False
    
    def _stage_workspace_report(self, report, ws_id: str, candidate: dict) -> None:
        """
        Stage workspace meal report to buffer.
        
        Args:
            report: Report object
            ws_id: Workspace ID
            candidate: Candidate dictionary
        """
        if not self.ctx.staging_buffer:
            print("\nWarning: Staging buffer not configured, cannot stage.\n")
            return
        
        from meal_planner.data.staging_buffer_manager import StagingBufferManager
        
        # Generate abbreviated output
        content = report.format_abbreviated()
        
        # Generate ID and label
        meal_name = candidate.get('meal_name')
        description = candidate.get('description')
        
        # Use description if provided, otherwise auto-generate
        if description:
            label = description
        elif meal_name:
            label = f"{meal_name} (workspace)"
        else:
            label = f"Workspace meal {ws_id}"
        
        # ID always includes workspace ID
        item_id = StagingBufferManager.generate_workspace_id(ws_id, meal_name)
        
        # Add to buffer
        is_new = self.ctx.staging_buffer.add(item_id, label, content)
        
        if is_new:
            print(f"\n✓ Staged: {label}\n")
        else:
            print(f"\n✓ Replaced staged item: {label}\n")

    def _history(self, args: List[str]) -> None:
        """
        Show history of operations for a plan.
        
        Usage: plan history <plan_id>
        Example: plan history 1a
        """
        if len(args) < 1:
            print("Usage: plan history <plan_id>")
            print("Example: plan history 1a")
            return
        
        plan_id = args[0]
        
        # Find candidate
        candidate = self._find_candidate(plan_id)
        if not candidate:
            print(f"Plan {plan_id} not found")
            return
        
        history = candidate.get('history', [])
        if not history:
            print(f"No history for plan {plan_id}")
            return
        
        # Print each history entry
        for entry in history:
            timestamp = entry['timestamp']
            command = entry['command']
            note = entry['note']
            print(f"{timestamp}  {command:45}  [{note}]")

    def _copy(self, args: List[str]) -> None:
        """
        Copy a plan to a new plan ID (explicit fork).
        
        Usage: plan copy <source_id> [<dest_id>]
        Example: plan copy 1a
        Example: plan copy 1a 1c
        """
        if not args:
            print("Usage: plan copy <source_id> [<dest_id>]")
            print("Example: plan copy 1a")
            print("Example: plan copy 1a 1c")
            return
        
        source_id = args[0]
        dest_id = args[1] if len(args) > 1 else None
        
        # Find source candidate
        source = self._find_candidate(source_id)
        if not source:
            print(f"Plan {source_id} not found")
            return
        
        # Deep copy
        import copy
        variant = copy.deepcopy(source)
        
        # Determine new ID
        if dest_id:
            # Check if dest_id already exists
            if self._find_candidate(dest_id):
                print(f"Error: Plan {dest_id} already exists")
                return
            new_id = dest_id
        else:
            # Auto-generate
            new_id = self._assign_variant_id(source_id)
        
        # Update variant
        variant['id'] = new_id
        variant['parent_id'] = source_id
        variant['ancestor_id'] = source.get('ancestor_id', source_id)
        variant['immutable'] = False  # Copies are always mutable
        
        # Strip analyzed_as (existing behavior)
        if "analyzed_as" in variant:
            del variant["analyzed_as"]
        
        # Update description
        orig_desc = variant.get("description", "")
        if orig_desc:
            variant["description"] = f"{orig_desc} (copy)"
        else:
            variant["description"] = "(copy)"
        
        # Append copy operation to history
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        if 'history' not in variant:
            variant['history'] = []
        variant['history'].append({
            'timestamp': timestamp,
            'command': f'plan copy {source_id} {new_id}',
            'note': f'created plan {new_id} from plan {source_id}'
        })
        
        # Update modification log
        if "modification_log" not in variant:
            variant["modification_log"] = []
        variant["modification_log"].append(f"Copied from #{source_id}")
        
        # Add to workspace
        ws = self.ctx.planning_workspace
        ws["candidates"].append(variant)
        
        # Auto-save
        self.ctx.save_workspace()
        
        print(f"Created {new_id} (copy of {source_id})")
        if variant.get("description"):
            print(f"Description: {variant['description']}")

    def _ensure_mutable(self, candidate: Dict, command_str: str, edit_note: str) -> tuple:
        """
        Ensure candidate is mutable, auto-creating copy if immutable.
        
        Args:
            candidate: The candidate to check
            command_str: The command being executed
            edit_note: Note describing the edit operation
        
        Returns:
            Tuple of (candidate_to_modify, was_copied, new_id_if_copied)
        """
        if not candidate.get('immutable', False):
            # Already mutable, just return it
            return candidate, False, None
        
        # Auto-create mutable copy
        import copy
        
        ws = self.ctx.planning_workspace
        old_id = candidate['id']
        new_id = self._assign_variant_id(old_id)
        
        variant = copy.deepcopy(candidate)
        variant['id'] = new_id
        variant['parent_id'] = old_id
        variant['ancestor_id'] = candidate.get('ancestor_id', old_id)
        variant['immutable'] = False

        # Ensure modification_log exists
        if 'modification_log' not in variant:
            variant['modification_log'] = []

        # Append auto-copy history entry
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        if 'history' not in variant:
            variant['history'] = []
        
        variant['history'].append({
            'timestamp': timestamp,
            'command': command_str,
            'note': f'auto-created plan {new_id} from immutable plan {old_id}'
        })
        
        # Append edit history entry
        edit_note_for_new = edit_note.replace(f'plan {old_id}', f'plan {new_id}')
        variant['history'].append({
            'timestamp': timestamp,
            'command': command_str,          
            'note': edit_note_for_new
        })
        
        # Add to workspace
        ws['candidates'].append(variant)
        
        return variant, True, new_id