"""
Data management commands: addcode, addnutrient, addrecipe.

Allows adding new entries to CSV files from the command line.

Field order for addcode: CODE,SECTION,OPTION,CAL,PROT_G,CARBS_G,FAT_G,GI,GL,SUGARS_G
Example: addcode VE.T2,Vegetable,"Tomato, beefsteak (182 g)",33,1.5,7,0,15.0,1.5,4.7
"""
import csv
import shutil
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .base import Command, register_command


def parse_csv_input(input_str: str) -> List[str]:
    """
    Parse CSV string handling quotes: 'A,"B,C",D' → ['A', 'B,C', 'D']
    
    Args:
        input_str: CSV-formatted string
    
    Returns:
        List of field values
    """
    return next(csv.reader([input_str]))


def extract_section(code: str) -> str:
    """
    Extract section prefix from code: 'SO.11' → 'SO'
    
    Args:
        code: Meal code
    
    Returns:
        Section prefix (empty string if no dot)
    """
    return code.split('.')[0] if '.' in code else ''


def create_timestamped_backup(filepath: Path) -> Path:
    """
    Create timestamped backup: meal_plan_master-2025-12-01-10-15-00.csv.bak
    
    Args:
        filepath: Path to file to backup
    
    Returns:
        Path to backup file
    """
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    stem = filepath.stem
    backup = filepath.with_name(f"{stem}-{timestamp}.csv.bak")
    shutil.copy2(filepath, backup)
    return backup


def atomic_write_csv(df: pd.DataFrame, filepath: Path) -> None:
    """
    Write DataFrame to CSV atomically (via temp file + rename).
    
    Args:
        df: DataFrame to write
        filepath: Destination path
    """
    temp = filepath.with_suffix('.tmp')
    df.to_csv(temp, index=False)
    temp.replace(filepath)  # Atomic rename


def validate_numeric(value: str, field_name: str) -> float:
    """
    Validate that a value is numeric.
    
    Args:
        value: String value to validate
        field_name: Field name for error messages
    
    Returns:
        Float value
    
    Raises:
        ValueError: If not a valid number
    """
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"Field '{field_name}' must be numeric, got: '{value}'")


def validate_code_format(code: str) -> None:
    """
    Validate code format (must contain at least one dot).
    
    Args:
        code: Code to validate
    
    Raises:
        ValueError: If invalid format
    """
    if '.' not in code:
        raise ValueError(f"Code '{code}' must contain at least one dot (e.g., 'SO.11')")


@register_command
class AddCodeCommand(Command):
    """Add new food code to master.csv"""
    
    name = "addcode"
    help_text = "Add food code to master (addcode CODE,SECTION,OPTION,CAL,PROT,CARBS,FAT,GI,GL,SUGAR [--force])"
    
    def execute(self, args: str) -> None:
        """
        Add new code to master.csv
        
        Args:
            args: CSV input with optional --force flag
        
        Format: CODE,SECTION,OPTION,CAL,PROT_G,CARBS_G,FAT_G,GI,GL,SUGARS_G
        Example: VE.T2,Vegetable,"Tomato, beefsteak (182 g)",33,1.5,7,0,15.0,1.5,4.7
        """
        if not args.strip():
            print("Usage: addcode CODE,SECTION,OPTION,CAL,PROT,CARBS,FAT,GI,GL,SUGAR [--force]")
            print('Example: addcode VE.T2,Vegetable,"Tomato, beefsteak (182 g)",33,1.5,7,0,15.0,1.5,4.7')
            return
        
        # Check for --force flag
        force = '--force' in args
        input_str = args.replace('--force', '').strip()
        
        # Parse CSV input
        try:
            fields = parse_csv_input(input_str)
        except Exception as e:
            print(f"Error parsing CSV input: {e}")
            return
        
        # Validate field count
        if len(fields) != 10:
            print(f"Error: Expected 10 fields, got {len(fields)}")
            print("Required: CODE,SECTION,OPTION,CAL,PROT_G,CARBS_G,FAT_G,GI,GL,SUGARS_G")
            return
        
        # Extract fields
        code = fields[0].strip().upper()
        section_input = fields[1].strip()  # User's input (may be ignored)
        option = fields[2].strip()
        
        # Validate code format
        try:
            validate_code_format(code)
        except ValueError as e:
            print(f"Error: {e}")
            return
        
        # Validate numeric fields (correct order: CAL,PROT,CARBS,FAT,GI,GL,SUGAR)
        try:
            cal = validate_numeric(fields[3], 'CAL')
            prot_g = validate_numeric(fields[4], 'PROT_G')
            carbs_g = validate_numeric(fields[5], 'CARBS_G')
            fat_g = validate_numeric(fields[6], 'FAT_G')
            gi = validate_numeric(fields[7], 'GI')
            gl = validate_numeric(fields[8], 'GL')
            sugars_g = validate_numeric(fields[9], 'SUGARS_G')
        except ValueError as e:
            print(f"Error: {e}")
            return
        
        # Load master
        master_df = self.ctx.master.df.copy()
        cols = self.ctx.master.cols
        
        # Determine correct section name based on code prefix
        section_prefix = extract_section(code)
        
        # Look up existing entries with this prefix to get consistent section name
        matching_prefix = master_df[
            master_df[cols.code].astype(str).apply(extract_section) == section_prefix
        ]
        
        if not matching_prefix.empty:
            # Use section name from existing entries with this prefix
            section = matching_prefix.iloc[0][cols.section]
            if section_input.lower() != section.lower():
                print(f"Note: Using section name '{section}' (from existing {section_prefix}.* codes)")
        else:
            # New section - capitalize first letter of user input
            section = section_input[0].upper() + section_input[1:] if len(section_input) > 1 else section_input.upper()
        
        # Check if code exists
        existing = master_df[master_df[cols.code].str.upper() == code]
        if not existing.empty:
            if not force:
                print(f"Error: Code '{code}' already exists in master.csv")
                current = existing.iloc[0]
                # Extract values explicitly to show in INPUT format order: CAL,PROT,CARBS,FAT,GI,GL,SUGARS
                curr_code = current[cols.code]
                curr_section = current[cols.section]
                curr_option = current[cols.option]
                curr_cal = current[cols.cal]
                curr_prot = current[cols.prot_g]
                curr_carbs = current[cols.carbs_g]
                curr_fat = current[cols.fat_g]
                curr_gi = current[cols.gi] if cols.gi and cols.gi in current.index else 0
                curr_gl = current[cols.gl] if cols.gl and cols.gl in current.index else 0
                curr_sugar = current[cols.sugar_g] if cols.sugar_g and cols.sugar_g in current.index else 0
                print(f"  Current: {curr_code},{curr_section},\"{curr_option}\","
                      f"{curr_cal},{curr_prot},{curr_carbs},{curr_fat},"
                      f"{curr_gi},{curr_gl},{curr_sugar}")
                print("Use --force to replace")
                return
            else:
                # Remove existing entry (will be replaced)
                master_df = master_df[master_df[cols.code].str.upper() != code]
                print(f"Replacing existing entry for {code}")
        
        # Check if this is a new section (already determined above)
        if matching_prefix.empty:
            # No existing codes with this prefix
            if not force:
                print(f"Warning: Section '{section_prefix}' does not exist in master.csv")
                print(f"This appears to be a new section. Section name will be: '{section}'")
                print("Use --force to create it.")
                return
            else:
                print(f"Creating new section: {section_prefix} ('{section}')")
        
        # Create backup
        backup_path = create_timestamped_backup(self.ctx.master.filepath)
        print(f"Backup: {backup_path.name}")
        
        # Create new row (column order: code,section,option,cal,prot_g,carbs_g,fat_g,GI,GL,sugars_g)
        new_row = {
            cols.code: code,
            cols.section: section,
            cols.option: option,
            cols.cal: cal,
            cols.prot_g: prot_g,
            cols.carbs_g: carbs_g,
            cols.fat_g: fat_g,
        }
        
        # Add optional columns if they exist
        if cols.gi:
            new_row[cols.gi] = gi
        if cols.gl:
            new_row[cols.gl] = gl
        if cols.sugar_g:
            new_row[cols.sugar_g] = sugars_g
        
        # Add row
        master_df = pd.concat([master_df, pd.DataFrame([new_row])], ignore_index=True)
        
        # Sort by section prefix, then code
        master_df['_section'] = master_df[cols.code].astype(str).apply(extract_section)
        master_df = master_df.sort_values(['_section', cols.code]).reset_index(drop=True)
        master_df = master_df.drop('_section', axis=1)
        
        # Atomic write
        atomic_write_csv(master_df, self.ctx.master.filepath)
        
        # Reload master
        self.ctx.master.reload()
        
        print(f"✓ Added code {code} to master.csv")


@register_command
class AddNutrientCommand(Command):
    """Add micronutrient data for a code"""
    
    name = "addnutrient"
    help_text = "Add nutrients for code (addnutrient CODE,FIBER,SODIUM,POTASSIUM,VITA,VITC,IRON [--force])"
    
    def execute(self, args: str) -> None:
        """
        Add nutrient data for a code.
        
        Args:
            args: CSV input with optional --force flag
        
        Format: CODE,FIBER_G,SODIUM_MG,POTASSIUM_MG,VITA_MCG,VITC_MG,IRON_MG
        Example: OT.28,0.0,5,5,0,0.0,0.0
        """
        if not args.strip():
            print("Usage: addnutrient CODE,FIBER_G,SODIUM_MG,POTASSIUM_MG,VITA_MCG,VITC_MG,IRON_MG [--force]")
            print("Example: addnutrient OT.28,0.0,5,5,0,0.0,0.0")
            return
        
        if not self.ctx.nutrients:
            print("Error: Nutrients file not configured")
            return
        
        # Check for --force flag
        force = '--force' in args
        input_str = args.replace('--force', '').strip()
        
        # Parse CSV input
        try:
            fields = parse_csv_input(input_str)
        except Exception as e:
            print(f"Error parsing CSV input: {e}")
            return
        
        # Validate field count
        if len(fields) != 7:
            print(f"Error: Expected 7 fields, got {len(fields)}")
            print("Required: CODE,FIBER_G,SODIUM_MG,POTASSIUM_MG,VITA_MCG,VITC_MG,IRON_MG")
            return
        
        # Extract code
        code = fields[0].strip().upper()
        
        # Check if code exists in master
        if not self.ctx.master.lookup_code(code):
            print(f"Error: Code '{code}' does not exist in master.csv")
            print("Add the code to master first using 'addcode'")
            return
        
        # Validate numeric fields
        try:
            fiber_g = validate_numeric(fields[1], 'FIBER_G')
            sodium_mg = validate_numeric(fields[2], 'SODIUM_MG')
            potassium_mg = validate_numeric(fields[3], 'POTASSIUM_MG')
            vita_mcg = validate_numeric(fields[4], 'VITA_MCG')
            vitc_mg = validate_numeric(fields[5], 'VITC_MG')
            iron_mg = validate_numeric(fields[6], 'IRON_MG')
        except ValueError as e:
            print(f"Error: {e}")
            return
        
        # Load nutrients
        nutrients_df = self.ctx.nutrients.df.copy()
        
        # Check if entry exists
        code_col = None
        for col in nutrients_df.columns:
            if str(col).lower() == 'code':
                code_col = col
                break
        
        if code_col:
            existing = nutrients_df[nutrients_df[code_col].str.upper() == code]
            if not existing.empty:
                if not force:
                    print(f"Error: Nutrient entry for '{code}' already exists")
                    print("Use --force to replace")
                    return
                else:
                    # Remove existing entry
                    nutrients_df = nutrients_df[nutrients_df[code_col].str.upper() != code]
                    print(f"Replacing existing nutrient entry for {code}")
        
        # Create backup
        backup_path = create_timestamped_backup(self.ctx.nutrients.filepath)
        print(f"Backup: {backup_path.name}")
        
        # Create new row
        new_row = {
            'code': code,
            'fiber_g': fiber_g,
            'sodium_mg': sodium_mg,
            'potassium_mg': potassium_mg,
            'vitA_mcg': vita_mcg,
            'vitC_mg': vitc_mg,
            'iron_mg': iron_mg,
        }
        
        # Add row
        nutrients_df = pd.concat([nutrients_df, pd.DataFrame([new_row])], ignore_index=True)
        
        # Sort by code to match master order (optional)
        nutrients_df = nutrients_df.sort_values('code').reset_index(drop=True)
        
        # Atomic write
        atomic_write_csv(nutrients_df, self.ctx.nutrients.filepath)
        
        # Reload nutrients
        self.ctx.nutrients.load()
        
        print(f"✓ Added nutrient data for {code}")


@register_command
class AddRecipeCommand(Command):
    """Add recipe/ingredient list for a code"""
    
    name = "addrecipe"
    help_text = "Add recipe for code (addrecipe CODE,\"INGREDIENTS\" [--force])"
    
    def execute(self, args: str) -> None:
        """
        Add recipe for a code.
        
        Args:
            args: CSV input with optional --force flag
        
        Format: CODE,"INGREDIENTS"
        Example: addrecipe ENT.12,"12oz turkey,1car,6cel,1lg on,1jal,8gar,1Qt K-bone,1Qt BTB,6C water,1 can pinto"
        """
        if not args.strip():
            print("Usage: addrecipe CODE,\"INGREDIENTS\" [--force]")
            print('Example: addrecipe ENT.12,"12oz turkey,1car,6cel"')
            return
        
        if not self.ctx.recipes:
            print("Error: Recipes file not configured")
            return
        
        # Check for --force flag
        force = '--force' in args
        input_str = args.replace('--force', '').strip()
        
        # Parse CSV input
        try:
            fields = parse_csv_input(input_str)
        except Exception as e:
            print(f"Error parsing CSV input: {e}")
            return
        
        # Validate field count
        if len(fields) != 2:
            print(f"Error: Expected 2 fields (CODE,INGREDIENTS), got {len(fields)}")
            return
        
        # Extract code and ingredients
        code = fields[0].strip().upper()
        ingredients = fields[1].strip()
        
        # Check if code exists in master
        if not self.ctx.master.lookup_code(code):
            print(f"Error: Code '{code}' does not exist in master.csv")
            print("Add the code to master first using 'addcode'")
            return
        
        # Load recipes
        recipes_df = self.ctx.recipes.df.copy()
        
        # Check if entry exists
        code_col = None
        for col in recipes_df.columns:
            if str(col).lower() == 'code':
                code_col = col
                break
        
        if code_col:
            existing = recipes_df[recipes_df[code_col].str.upper() == code]
            if not existing.empty:
                if not force:
                    print(f"Error: Recipe for '{code}' already exists")
                    current = existing.iloc[0]
                    ing_col = None
                    for col in recipes_df.columns:
                        if str(col).lower() == 'ingredients':
                            ing_col = col
                            break
                    if ing_col:
                        print(f"  Current: {current[ing_col]}")
                    print("Use --force to replace")
                    return
                else:
                    # Remove existing entry
                    recipes_df = recipes_df[recipes_df[code_col].str.upper() != code]
                    print(f"Replacing existing recipe for {code}")
        
        # Create backup
        backup_path = create_timestamped_backup(self.ctx.recipes.filepath)
        print(f"Backup: {backup_path.name}")
        
        # Create new row
        new_row = {
            'code': code,
            'ingredients': ingredients,
        }
        
        # Add row
        recipes_df = pd.concat([recipes_df, pd.DataFrame([new_row])], ignore_index=True)
        
        # Sort by code to match master order (optional)
        recipes_df = recipes_df.sort_values('code').reset_index(drop=True)
        
        # Atomic write
        atomic_write_csv(recipes_df, self.ctx.recipes.filepath)
        
        # Reload recipes
        self.ctx.recipes.load()
        
        print(f"✓ Added recipe for {code}")