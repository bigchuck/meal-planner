"""
Data management commands: addcode, addnutrient, addrecipe.

These commands support adding/updating entries in the CSV files with
intelligent conflict detection and helpful error messages.
"""
from typing import Optional
import pandas as pd
from datetime import datetime
from pathlib import Path
from .base import Command, register_command, CommandContext


def natural_sort_key(code: str):
    """Generate sort key for natural code ordering (SO.2 before SO.10)."""
    import re
    
    match = re.match(r'^([A-Za-z]+)\.(.+)$', code, re.IGNORECASE)
    if not match:
        return (code.upper(), 0, '')
    
    prefix = match.group(1).upper()
    rest = match.group(2)
    
    num_match = re.match(r'^(\d+)(.*)$', rest)
    if num_match:
        num = int(num_match.group(1))
        suffix = num_match.group(2).upper()
        return (prefix, num, suffix)
    else:
        return (prefix, 0, rest.upper())


def create_backup(filepath: Path, ctx: CommandContext) -> Optional[Path]:
    """
    Create timestamped backup of file (once per session per file).
    
    Args:
        filepath: File to back up
        ctx: Command context (tracks session state)
    
    Returns:
        Backup path if created, None if already backed up or doesn't exist
    """
    # Already backed up this session
    if filepath in ctx.backed_up_files:
        return None
    
    if not filepath.exists():
        return None
    
    # Create backups subdirectory if needed
    backup_dir = filepath.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    
    # Use session start time for all backups in this session
    timestamp = ctx.session_start.strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{filepath.stem}_backup_{timestamp}{filepath.suffix}"
    
    import shutil
    shutil.copy2(filepath, backup_path)
    
    # Mark as backed up this session
    ctx.backed_up_files.add(filepath)
    
    return backup_path

def parse_csv_line(line: str, expected_columns: list) -> dict:
    """Parse CSV line into dictionary, handling quoted values."""
    import csv
    import io
    
    # Use csv.reader to properly handle quoted values
    reader = csv.reader(io.StringIO(line))
    try:
        parts = next(reader)
    except StopIteration:
        parts = []
    
    # Strip whitespace from each part
    parts = [p.strip() for p in parts]
    
    if len(parts) != len(expected_columns):
        raise ValueError(
            f"Expected {len(expected_columns)} columns, got {len(parts)}\n"
            f"Expected: {', '.join(expected_columns)}"
        )
    
    return dict(zip(expected_columns, parts))


def format_csv_line(row: pd.Series, columns: list) -> str:
    """Format DataFrame row as CSV line with proper quoting."""
    import csv
    import io
    
    values = [str(row[col]) if col in row and pd.notna(row[col]) else '' for col in columns]
    
    # Use csv.writer to properly quote values with commas
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(values)
    return output.getvalue().strip()


def show_current_values(code: str, df: pd.DataFrame, columns: list, file_label: str):
    """Display current values for existing code with headers."""
    code_col = columns[0]
    match = df[df[code_col].str.upper() == code.upper()]
    
    if match.empty:
        return
    
    row = match.iloc[0]
    
    print(f"\nCode '{code}' already exists in {file_label}.")
    print("Current values (CSV format):")
    print("  " + ','.join(columns))
    print("  " + format_csv_line(row, columns))
    print(f"\nTo update, copy and modify the line above, then add --force:")
    print(f"  (command) {format_csv_line(row, columns)} --force")
    print()


@register_command
class AddCodeCommand(Command):
    """Add or update master code entry."""
    
    name = "addcode"
    category = "DB Update"
    help_text = "Add/update master entry (addcode CODE or CODE,section,... [--force])"
    overview_help = (
        "addcode  —  Add or update a master-database entry's core macros\n"
        "\n"
        "Usage:\n"
        "  addcode CODE                                     Look up CODE, print its current values as a CSV line\n"
        "  addcode CODE,section,option,cal,prot_g,carbs_g,fat_g,GI,GL,sugar_g\n"
        "                                                    Create CODE (fails if it already exists)\n"
        "  addcode CODE,... --force                         Update CODE (required if it already exists)\n"
        "\n"
        "A backup of master.json is created automatically before any write."
    )
    detailed_help = (
        "addcode  —  Add or update a master-database entry's core macros\n"
        "\n"
        "Two modes:\n"
        "  Lookup (no commas):  addcode CODE\n"
        "    Prints the existing entry's values already formatted as a CSV line,\n"
        "    ready to copy, edit, and resubmit with --force.\n"
        "\n"
        "  Write (comma-separated):  addcode CODE,section,option,cal,prot_g,carbs_g,fat_g,GI,GL,sugar_g\n"
        "    Creates a new entry. Add --force to overwrite an existing one.\n"
        "\n"
        "Columns:\n"
        "  code      Food code, e.g. SO.99\n"
        "  section   Category, e.g. Soup, Vegetable, Fish\n"
        "  option    Description/name (quote it if it contains a comma)\n"
        "  cal, prot_g, carbs_g, fat_g, GI, GL, sugar_g   Numeric macro fields\n"
        "\n"
        "Examples:\n"
        "  addcode VE.38                                     Look up VE.38\n"
        "  addcode SO.99,Soup,New soup,150,8,20,3,40,10,5     Create SO.99\n"
        "  addcode SO.99,Soup,New soup,150,8,20,3,40,10,5 --force   Update SO.99\n"
        "\n"
        "See also: addnutrient (micronutrients), addrecipe (ingredients), delcode."
    )


    def execute(self, args: str) -> None:
        """Add or update master code."""
        if not args.strip():
            print("Usage: addcode CODE  (to check existing)")
            print("   or: addcode CODE,section,option,cal,prot_g,carbs_g,fat_g,GI,GL,sugar_g [--force]")
            print("\nExample:")
            print("  addcode VE.38")
            print("  addcode SO.99,Soup,New soup,150,8,20,3,40,10,5")
            return
        
        force = args.strip().endswith('--force')
        if force:
            args = args.strip()[:-7].strip()
        
        columns = ['code', 'section', 'option', 'cal', 'prot_g', 'carbs_g', 'fat_g', 'GI', 'GL', 'sugar_g']
        
        # If no commas, treat as lookup
        if ',' not in args:
            code = args.strip().upper()
            existing = self.ctx.master.get_entry_structured(code)
            
            if not existing:
                print(f"\nCode '{code}' not found in master.json.")
                print("To add it, use:")
                print(f"  addcode {code},section,option,cal,prot_g,carbs_g,fat_g,GI,GL,sugar_g")
            else:
                # Show current values in CSV format for easy editing
                print(f"\nCode '{code}' already exists in master.json.")
                print("Current values (CSV format):")
                print("  code,section,option,cal,prot_g,carbs_g,fat_g,GI,GL,sugar_g")
                
                # Build CSV line from entry
                section = existing.get('section', '')
                option = existing.get('description', existing.get('option', ''))
                macros = existing.get('macros', {})
                # Format values
                values = [
                    code,
                    section,
                    f'"{option}"' if ',' in option else option,
                    str(macros.get('cal', 0.0)),
                    str(macros.get('prot_g', 0.0)),
                    str(macros.get('carbs_g', 0.0)),
                    str(macros.get('fat_g', 0.0)),
                    str(macros.get('GI', 0.0)),
                    str(macros.get('GL', 0.0)),
                    str(macros.get('sugar_g', 0.0)),
                ]
                
                csv_line = ','.join(values)
                print(f"  {csv_line}")
                print(f"\nTo update, copy and modify the line above, then add --force:")
                print(f"  addcode {csv_line} --force")
            
            print()
            return
        
        # Parse CSV line
        try:
            data = parse_csv_line(args, columns)
        except ValueError as e:
            print(f"Error: {e}")
            return
        
        code = data['code'].upper()
        existing = self.ctx.master.lookup_code(code)
        
        if existing and not force:
            print(f"\nCode '{code}' already exists.")
            print("Use --force to update.")
            print()
            return
        
        # Create backup
        backup_path = create_backup(self.ctx.master.filepath, self.ctx)
        if backup_path:
            print(f"Created backup: {backup_path.name}")
        
        # Build macros dict
        macros = {
            'cal': float(data['cal']) if data['cal'] else 0.0,
            'prot_g': float(data['prot_g']) if data['prot_g'] else 0.0,
            'carbs_g': float(data['carbs_g']) if data['carbs_g'] else 0.0,
            'fat_g': float(data['fat_g']) if data['fat_g'] else 0.0,
            'GI': float(data['GI']) if data['GI'] else 0.0,
            'GL': float(data['GL']) if data['GL'] else 0.0,
            'sugar_g': float(data['sugar_g']) if data['sugar_g'] else 0.0,
        }
        
        # Add/update entry
        is_new = self.ctx.master.add_or_update_entry(
            code=code,
            section=data['section'],
            option=data['option'],
            macros=macros
        )
        
        # Save
        self.ctx.master.save()
        
        action = "Added" if is_new else "Updated"
        print(f"✓ {action} {code} in master.json")

@register_command
class AddNutrientCommand(Command):
    """Add or update nutrient entry."""
    
    name = "addnutrient"
    category = "DB Update"
    help_text = "Add/update nutrients (addnutrient CODE or CODE,fiber_g,... [--force])"
    overview_help = (
        "addnutrient  —  Add or update a master entry's micronutrients\n"
        "\n"
        "Usage:\n"
        "  addnutrient CODE                                              Look up CODE's current nutrient values\n"
        "  addnutrient CODE,fiber_g,sodium_mg,potassium_mg,vitA_mcg,vitC_mg,iron_mg\n"
        "                                                                 Add nutrients (fails if already present)\n"
        "  addnutrient CODE,... --force                                  Update existing nutrients\n"
        "\n"
        "CODE must already exist in master.json (add it first with addcode)."
    )
    detailed_help = (
        "addnutrient  —  Add or update a master entry's micronutrients\n"
        "\n"
        "Two modes:\n"
        "  Lookup (no commas):  addnutrient CODE\n"
        "    Prints existing nutrient values as a CSV line, ready to edit and resubmit.\n"
        "\n"
        "  Write (comma-separated):  addnutrient CODE,fiber_g,sodium_mg,potassium_mg,vitA_mcg,vitC_mg,iron_mg\n"
        "    Add --force to overwrite nutrients that already exist.\n"
        "\n"
        "CODE must already have a master.json entry (via addcode) before nutrients can be attached.\n"
        "\n"
        "Examples:\n"
        "  addnutrient VE.38\n"
        "  addnutrient VE.38,3.2,45,210,120,8,1.1\n"
        "  addnutrient VE.38,3.2,45,210,120,8,1.1 --force\n"
        "\n"
        "See also: addcode, addrecipe."
    )


    def execute(self, args: str) -> None:
        """Add or update nutrient data."""
        if not args.strip():
            print(f"Usage: addnutrient CODE  (to check existing)")
            print(f"   or: addnutrient CODE,fiber_g,sodium_mg,potassium_mg,vitA_mcg,vitC_mg,iron_mg [--force]")
            return
        
        force = args.strip().endswith('--force')
        if force:
            args = args.strip()[:-7].strip()
        
        columns = ['code', 'fiber_g', 'sodium_mg', 'potassium_mg', 'vitA_mcg', 'vitC_mg', 'iron_mg']
        
        # If no commas, treat as lookup
        if ',' not in args:
            code = args.strip().upper()
            existing = self.ctx.master.get_entry_structured(code)
            
            if not existing:
                print(f"\nCode '{code}' not found in master.json.")
                print("To add nutrients, first add the code with:")
                print(f"  addcode {code},section,option,cal,prot_g,carbs_g,fat_g,GI,GL,sugar_g")
            else:
                nutrients = existing.get('nutrients', {}) # check one to see if they are there
                if nutrients:
                    # Show current values in CSV format for easy editing
                    print(f"\nCode '{code}' already has nutrients in master.json.")
                    print("Current values (CSV format):")
                    print("  code,fiber_g,sodium_mg,potassium_mg,vitA_mcg,vitC_mg,iron_mg")
                    
                    values = [
                        code,
                        str(nutrients.get('fiber_g', 0.0)),
                        str(nutrients.get('sodium_mg', 0.0)),
                        str(nutrients.get('potassium_mg', 0.0)),
                        str(nutrients.get('vitA_mcg', 0.0)),
                        str(nutrients.get('vitC_mg', 0.0)),
                        str(nutrients.get('iron_mg', 0.0)),
                    ]
                    
                    csv_line = ','.join(values)
                    print(f"  {csv_line}")
                    print(f"\nTo update, copy and modify the line above, then add --force:")
                    print(f"  addnutrient {csv_line} --force")
                else:
                    print(f"\nCode '{code}' has no nutrients defined.")
                    print("To add nutrients, use:")
                    print(f"  addnutrient {code},fiber_g,sodium_mg,potassium_mg,vitA_mcg,vitC_mg,iron_mg")
            print()
            return
        
        # Parse
        try:
            data = parse_csv_line(args, columns)
        except ValueError as e:
            print(f"Error: {e}")
            return
        
        code = data['code'].upper()
        existing = self.ctx.master.lookup_code(code)
        
        if not existing:
            print(f"\nError: Code '{code}' not found in master.json.")
            print("Add the code first with: addcode")
            print()
            return
        
        has_nutrients = 'nutrients' in existing and existing['nutrients']
        if has_nutrients and not force:
            print(f"\nCode '{code}' already has nutrients.")
            print("Use --force to update.")
            print()
            return
        
        # Create backup
        backup_path = create_backup(self.ctx.master.filepath, self.ctx)
        if backup_path:
            print(f"Created backup: {backup_path.name}")
        
        # Build nutrients dict
        nutrients = {
            'fiber_g': float(data['fiber_g']) if data['fiber_g'] else 0.0,
            'sodium_mg': float(data['sodium_mg']) if data['sodium_mg'] else 0.0,
            'potassium_mg': float(data['potassium_mg']) if data['potassium_mg'] else 0.0,
            'vitA_mcg': float(data['vitA_mcg']) if data['vitA_mcg'] else 0.0,
            'vitC_mg': float(data['vitC_mg']) if data['vitC_mg'] else 0.0,
            'iron_mg': float(data['iron_mg']) if data['iron_mg'] else 0.0,
        }
        
        # Update
        self.ctx.master.update_nutrients(code, nutrients)
        self.ctx.master.save()
        
        action = "Updated" if has_nutrients else "Added"
        print(f"✓ {action} nutrients for {code}")

@register_command
class AddRecipeCommand(Command):
    """Add or update recipe entry."""
    
    name = "addrecipe"
    category = "DB Update"
    help_text = "Add/update recipe (addrecipe CODE or CODE,ingredients [--force])"
    overview_help = (
        "addrecipe  —  Add or update a master entry's ingredient list\n"
        "\n"
        "Usage:\n"
        "  addrecipe CODE                            Look up CODE's current recipe\n"
        "  addrecipe CODE,\"ingredients list\"          Add a recipe (fails if one already exists)\n"
        "  addrecipe CODE,\"ingredients list\" --force  Update an existing recipe\n"
        "\n"
        "CODE must already exist in master.json (add it first with addcode).\n"
        "View a saved recipe with the 'recipe' command."
    )
    detailed_help = (
        "addrecipe  —  Add or update a master entry's ingredient list\n"
        "\n"
        "Two modes:\n"
        "  Lookup (no commas):  addrecipe CODE\n"
        "    Prints the existing recipe as a CSV line, ready to edit and resubmit.\n"
        "\n"
        "  Write (comma-separated):  addrecipe CODE,\"ingredients list\"\n"
        "    Quote the ingredients if the list itself contains commas.\n"
        "    Add --force to overwrite a recipe that already exists.\n"
        "\n"
        "CODE must already have a master.json entry (via addcode).\n"
        "\n"
        "Example:\n"
        "  addrecipe SO.11,\"16oz lean steak, 1 lb dry beans, 11oz okra\"\n"
        "\n"
        "See also: addcode, addnutrient, recipe (to view a saved recipe)."
    )


    def execute(self, args: str) -> None:
        """Add or update recipe."""
        if not args.strip():
            print("Usage: addrecipe CODE  (to check existing)")
            print('   or: addrecipe CODE,"ingredients list" [--force]')
            print("\nNote: Use quotes around ingredients if they contain commas")
            print("\nExample:")
            print('  addrecipe SO.11,"16oz lean steak, 1 lb dry beans, 11oz okra"')
            return
        
        force = args.strip().endswith('--force')
        if force:
            args = args.strip()[:-7].strip()
        
        columns = ['code', 'ingredients']
        
        # If no commas, treat as lookup
        if ',' not in args:
            code = args.strip().upper()
            existing = self.ctx.master.lookup_code(code)
            
            if not existing:
                print(f"\nCode '{code}' not found in master.json.")
            else:
                recipe = existing.get('recipe', '')
                if recipe:
                    # Show current values in CSV format for easy editing
                    print(f"\nCode '{code}' already has a recipe in master.json.")
                    print("Current values (CSV format):")
                    print("  code,ingredients")
                    
                    # Quote recipe if it contains commas
                    quoted_recipe = f'"{recipe}"' if ',' in recipe else recipe
                    csv_line = f"{code},{quoted_recipe}"
                    
                    print(f"  {csv_line}")
                    print(f"\nTo update, copy and modify the line above, then add --force:")
                    print(f"  addrecipe {csv_line} --force")
                else:
                    print(f"\nCode '{code}' has no recipe defined.")
                    print("To add recipe, use:")
                    print(f'  addrecipe {code},"ingredient list"')
            print()
            return
        
        # Parse
        try:
            data = parse_csv_line(args, columns)
        except ValueError as e:
            print(f"Error: {e}")
            return
        
        code = data['code'].upper()
        existing = self.ctx.master.lookup_code(code)
        
        if not existing:
            print(f"\nError: Code '{code}' not found in master.json.")
            print("Add the code first with: addcode")
            print()
            return
        
        has_recipe = 'recipe' in existing and existing['recipe']
        if has_recipe and not force:
            print(f"\nCode '{code}' already has a recipe.")
            print("Use --force to update.")
            print()
            return
        
        # Create backup
        backup_path = create_backup(self.ctx.master.filepath, self.ctx)
        if backup_path:
            print(f"Created backup: {backup_path.name}")
        
        # Update
        self.ctx.master.update_recipe(code, data['ingredients'])
        self.ctx.master.save()
        
        action = "Updated" if has_recipe else "Added"
        print(f"✓ {action} recipe for {code}")

@register_command
class ValidateCommand(Command):
    """Validate master data integrity."""
    
    name = "validate"
    category = "DB Interrogation"
    help_text = "Check data integrity (validate or validate CODE)"
    overview_help = (
        "validate  —  Check master-database integrity\n"
        "\n"
        "Usage:\n"
        "  validate       Check the whole master database: entry/section counts, how many\n"
        "                 entries have nutrients/recipes/portions, and any structural issues\n"
        "  validate CODE  Check one entry for issues\n"
        "\n"
        "Read-only — this never modifies data."
    )


    def execute(self, args: str) -> None:
        """Validate master data or specific code."""
        args = args.strip()
        
        if not args:
            # Check overall integrity
            print("Checking master data integrity...\n")
            stats = self.ctx.master.check_integrity()
            
            print(f"Total entries: {stats['total_entries']}")
            print(f"Sections: {stats['sections']}")
            print(f"With nutrients: {stats['with_nutrients']}")
            print(f"With recipes: {stats['with_recipes']}")
            print(f"With portions: {stats['with_portions']}")
            
            if stats['issues']:
                print(f"\nFound {len(stats['issues'])} issues:")
                for issue in stats['issues'][:20]:  # Limit output
                    print(f"  • {issue}")
                
                if len(stats['issues']) > 20:
                    print(f"  ... and {len(stats['issues']) - 20} more")
            else:
                print("\n✓ No issues found")
            
            print()
        else:
            # Validate specific code
            code = args.upper()
            result = self.ctx.master.validate_entry(code)
            
            if result['valid']:
                print(f"\n✓ {code} is valid")
            else:
                print(f"\n✗ {code} has issues:")
                for issue in result['issues']:
                    print(f"  • {issue}")
            
            print()

@register_command
class DeleteCodeCommand(Command):
    """Delete a code from master."""
    
    name = "delcode"
    category = "DB Update"
    help_text = "Delete code from master (delcode CODE [--force])"
    overview_help = (
        "delcode  —  Permanently delete a code from master.json\n"
        "\n"
        "Usage:\n"
        "  delcode CODE          Preview: show what would be deleted (no change made)\n"
        "  delcode CODE --force  Actually delete it (a backup is created first)\n"
        "\n"
        "This cannot be undone except by restoring from the backup."
    )


    def execute(self, args: str) -> None:
        """Delete a code from master."""
        if not args.strip():
            print("Usage: delcode CODE [--force]")
            print("Example: delcode SO.99 --force")
            print("\nWarning: This permanently removes the code from master.json")
            return
        
        force = args.strip().endswith('--force')
        if force:
            args = args.strip()[:-7].strip()
        
        code = args.strip().upper()
        
        # Check if exists
        existing = self.ctx.master.lookup_code(code)
        if not existing:
            print(f"\nCode '{code}' not found in master.json")
            print()
            return
        
        # Show what will be deleted
        print(f"\nCode '{code}' found:")
        print(f"  Section: {existing.get('section', '')}")
        print(f"  Option: {existing.get('option', '')}")
        
        if not force:
            print("\nUse --force to confirm deletion")
            print("Warning: This action cannot be undone (except via backup)")
            print()
            return
        
        # Create backup
        backup_path = create_backup(self.ctx.master.filepath, self.ctx)
        if backup_path:
            print(f"Created backup: {backup_path.name}")
        
        # Delete
        self.ctx.master.delete_entry(code)
        self.ctx.master.save()
        
        print(f"✓ Deleted {code} from master.json")
        print()

