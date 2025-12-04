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
    help_text = "Add/update master entry (addcode CODE or CODE,section,... [--force])"
    
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
            master_df = self.ctx.master.df
            code_col = self.ctx.master.cols.code
            existing = master_df[master_df[code_col].str.upper() == code]
            
            if existing.empty:
                print(f"\nCode '{code}' not found in master.csv.")
                print("To add it, use:")
                print(f"  addcode {code},section,option,cal,prot_g,carbs_g,fat_g,GI,GL,sugar_g")
            else:
                show_current_values(code, master_df, columns, "master.csv")
            return
        
        # Parse CSV line
        try:
            data = parse_csv_line(args, columns)
        except ValueError as e:
            print(f"Error: {e}")
            return
        
        code = data['code'].upper()
        master_df = self.ctx.master.df.copy()
        code_col = self.ctx.master.cols.code
        existing = master_df[master_df[code_col].str.upper() == code]
        
        if not existing.empty and not force:
            show_current_values(code, master_df, columns, "master.csv")
            return
        
        backup_path = create_backup(self.ctx.master.filepath, self.ctx)
        if backup_path:
            print(f"Created backup: {backup_path.name}")
        
        if not existing.empty:
            idx = existing.index[0]
            for col, value in data.items():
                actual_col = col if col in master_df.columns else self.ctx.master.cols.__dict__.get(col, col)
                if actual_col in master_df.columns:
                    # Convert to proper dtype to avoid warnings
                    if master_df[actual_col].dtype in ['float64', 'int64']:
                        try:
                            master_df.at[idx, actual_col] = float(value) if value else 0.0
                        except (ValueError, TypeError):
                            master_df.at[idx, actual_col] = value
                    else:
                        master_df.at[idx, actual_col] = value
            action = "Updated"
        else:
            # Convert numeric columns to proper types
            typed_data = {}
            for col, value in data.items():
                actual_col = col if col in master_df.columns else self.ctx.master.cols.__dict__.get(col, col)
                if actual_col in master_df.columns:
                    if master_df[actual_col].dtype in ['float64', 'int64']:
                        try:
                            typed_data[col] = float(value) if value else 0.0
                        except (ValueError, TypeError):
                            typed_data[col] = value
                    else:
                        typed_data[col] = value
                else:
                    typed_data[col] = value
            
            new_row = pd.DataFrame([typed_data])
            master_df = pd.concat([master_df, new_row], ignore_index=True)
            action = "Added"
        
        # Sort naturally
        code_col = self.ctx.master.cols.code
        master_df['_sort_key'] = master_df[code_col].apply(natural_sort_key)
        master_df = master_df.sort_values('_sort_key').drop('_sort_key', axis=1)
        master_df = master_df.reset_index(drop=True)
        
        master_df.to_csv(self.ctx.master.filepath, index=False)
        self.ctx.master.reload()
        
        print(f"✓ {action} {code} in master.csv")


@register_command
class AddNutrientCommand(Command):
    """Add or update nutrient entry."""
    
    name = "addnutrient"
    help_text = "Add/update nutrients (addnutrient CODE or CODE,fiber_g,... [--force])"
    
    def execute(self, args: str) -> None:
        """Add or update nutrient data."""
        if not self.ctx.nutrients:
            print("Nutrients file not configured.")
            return
        
        if not args.strip():
            available = self.ctx.nutrients.get_available_nutrients()
            cols_str = ','.join(['code'] + available) if available else 'code,...'
            print(f"Usage: addnutrient CODE  (to check existing)")
            print(f"   or: addnutrient {cols_str} [--force]")
            return
        
        force = args.strip().endswith('--force')
        if force:
            args = args.strip()[:-7].strip()
        
        nutrients_df = self.ctx.nutrients.df
        if nutrients_df.empty:
            print("Nutrients file is empty.")
            return
        
        columns = list(nutrients_df.columns)
        
        # If no commas, treat as lookup
        if ',' not in args:
            code = args.strip().upper()
            existing = nutrients_df[nutrients_df['code'].str.upper() == code]
            
            if existing.empty:
                print(f"\nCode '{code}' not found in nutrients.csv.")
                print("To add it, use:")
                print(f"  addnutrient {code},{','.join(['...']*len(columns[1:]))}")
            else:
                show_current_values(code, nutrients_df, columns, "nutrients.csv")
            return
        
        try:
            data = parse_csv_line(args, columns)
        except ValueError as e:
            print(f"Error: {e}")
            return
        
        code = data['code'].upper()
        existing = nutrients_df[nutrients_df['code'].str.upper() == code]
        
        if not existing.empty and not force:
            show_current_values(code, nutrients_df, columns, "nutrients.csv")
            return
        
        backup_path = create_backup(self.ctx.nutrients.filepath, self.ctx)
        if backup_path:
            print(f"Created backup: {backup_path.name}")
        
        if not existing.empty:
            idx = existing.index[0]
            for col, value in data.items():
                if col in nutrients_df.columns:
                    # Convert to proper dtype
                    if nutrients_df[col].dtype in ['float64', 'int64']:
                        try:
                            nutrients_df.at[idx, col] = float(value) if value else 0.0
                        except (ValueError, TypeError):
                            nutrients_df.at[idx, col] = value
                    else:
                        nutrients_df.at[idx, col] = value
            action = "Updated"
        else:
            # Convert numeric columns to proper types
            typed_data = {}
            for col, value in data.items():
                if col in nutrients_df.columns:
                    if nutrients_df[col].dtype in ['float64', 'int64']:
                        try:
                            typed_data[col] = float(value) if value else 0.0
                        except (ValueError, TypeError):
                            typed_data[col] = value
                    else:
                        typed_data[col] = value
                else:
                    typed_data[col] = value
            
            new_row = pd.DataFrame([typed_data])
            nutrients_df = pd.concat([nutrients_df, new_row], ignore_index=True)
            action = "Added"
        
        nutrients_df['_sort_key'] = nutrients_df['code'].apply(natural_sort_key)
        nutrients_df = nutrients_df.sort_values('_sort_key').drop('_sort_key', axis=1)
        nutrients_df = nutrients_df.reset_index(drop=True)
        
        nutrients_df.to_csv(self.ctx.nutrients.filepath, index=False)
        self.ctx.nutrients.load()
        
        print(f"✓ {action} {code} in nutrients.csv")


@register_command
class AddRecipeCommand(Command):
    """Add or update recipe entry."""
    
    name = "addrecipe"
    help_text = "Add/update recipe (addrecipe CODE or CODE,ingredients [--force])"
    
    def execute(self, args: str) -> None:
        """Add or update recipe."""
        if not self.ctx.recipes:
            print("Recipes file not configured.")
            return
        
        if not args.strip():
            print("Usage: addrecipe CODE  (to check existing)")
            print('   or: addrecipe CODE,"ingredients list" [--force]')
            print("\nNote: Use quotes around ingredients if they contain commas")
            print("\nExample:")
            print('  addrecipe SO.11,"16oz lean steak, 1 lb dry beans, 11oz okra"')
            print('  addrecipe ZZ.1,"dirt, mud, rocks, oak leaves, slugs" --force')
            return
        
        force = args.strip().endswith('--force')
        if force:
            args = args.strip()[:-7].strip()
        
        columns = ['code', 'ingredients']
        
        # If no commas, treat as lookup
        if ',' not in args:
            code = args.strip().upper()
            recipes_df = self.ctx.recipes.df
            existing = recipes_df[recipes_df['code'].str.upper() == code]
            
            if existing.empty:
                print(f"\nCode '{code}' not found in recipes.csv.")
                print("To add it, use:")
                print(f"  addrecipe {code},ingredient list here")
            else:
                show_current_values(code, recipes_df, columns, "recipes.csv")
            return
        
        try:
            data = parse_csv_line(args, columns)
        except ValueError as e:
            print(f"Error: {e}")
            return
        
        code = data['code'].upper()
        recipes_df = self.ctx.recipes.df.copy()
        existing = recipes_df[recipes_df['code'].str.upper() == code]
        
        if not existing.empty and not force:
            show_current_values(code, recipes_df, columns, "recipes.csv")
            return
        
        backup_path = create_backup(self.ctx.recipes.filepath, self.ctx)
        if backup_path:
            print(f"Created backup: {backup_path.name}")
        
        if not existing.empty:
            idx = existing.index[0]
            for col, value in data.items():
                if col in recipes_df.columns:
                    # Recipes are all strings, but check dtype for consistency
                    if recipes_df[col].dtype in ['float64', 'int64']:
                        try:
                            recipes_df.at[idx, col] = float(value) if value else 0.0
                        except (ValueError, TypeError):
                            recipes_df.at[idx, col] = value
                    else:
                        recipes_df.at[idx, col] = value
            action = "Updated"
        else:
            # Convert to proper types if needed
            typed_data = {}
            for col, value in data.items():
                if col in recipes_df.columns:
                    if recipes_df[col].dtype in ['float64', 'int64']:
                        try:
                            typed_data[col] = float(value) if value else 0.0
                        except (ValueError, TypeError):
                            typed_data[col] = value
                    else:
                        typed_data[col] = value
                else:
                    typed_data[col] = value
            
            new_row = pd.DataFrame([typed_data])
            recipes_df = pd.concat([recipes_df, new_row], ignore_index=True)
            action = "Added"
        
        recipes_df['_sort_key'] = recipes_df['code'].apply(natural_sort_key)
        recipes_df = recipes_df.sort_values('_sort_key').drop('_sort_key', axis=1)
        recipes_df = recipes_df.reset_index(drop=True)
        
        recipes_df.to_csv(self.ctx.recipes.filepath, index=False)
        self.ctx.recipes.load()
        
        print(f"✓ {action} {code} in recipes.csv")