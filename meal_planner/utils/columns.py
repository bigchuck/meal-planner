"""
Complete CSV fix: Remove trailing commas from ALL rows.

This fixes both:
1. Header: Ensures it doesn't have sugar_g or trailing comma
2. Data rows: Removes trailing commas from every row
"""
import shutil
from datetime import datetime
from pathlib import Path
import pandas as pd


def fix_trailing_commas(master_file: Path):
    """
    Fix CSV by removing trailing commas from all rows.
    """
    print("=" * 70)
    print("Complete CSV Fix - Remove Trailing Commas")
    print("=" * 70)
    
    # Step 1: Backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = master_file.with_name(f"{master_file.stem}.backup.{timestamp}{master_file.suffix}")
    
    print(f"\n[1/7] Creating backup...")
    shutil.copy2(master_file, backup_file)
    print(f"   ✓ Backup: {backup_file.name}")
    
    # Step 2: Read current file
    print(f"\n[2/7] Reading current file...")
    with open(master_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    if not lines:
        print("   ✗ File is empty!")
        return False
    
    print(f"   ✓ Read {len(lines)} lines")
    
    # Step 3: Analyze current state
    print(f"\n[3/7] Analyzing current state...")
    
    header = lines[0].strip()
    print(f"   Header: {header}")
    
    header_cols = header.split(',')
    print(f"   Header columns: {len(header_cols)}")
    
    # Check for trailing comma in header
    if header.endswith(','):
        print(f"   ⚠️  Header has trailing comma")
    
    # Check data rows
    if len(lines) > 1:
        first_data = lines[1].strip()
        data_cols = first_data.split(',')
        print(f"   First data row columns: {len(data_cols)}")
        
        if first_data.endswith(','):
            print(f"   ⚠️  Data rows have trailing comma (empty field)")
        
        # Count how many rows have trailing commas
        trailing_count = sum(1 for line in lines[1:] if line.strip().endswith(','))
        print(f"   Rows with trailing comma: {trailing_count}/{len(lines)-1}")
    
    # Step 4: Fix header
    print(f"\n[4/7] Fixing header...")
    
    # Remove sugar_g if present
    if ',sugar_g' in header:
        header = header.replace(',sugar_g', '')
        print(f"   Removed ',sugar_g' from header")
    
    # Remove trailing comma if present
    header = header.rstrip(',')
    
    new_header_cols = header.split(',')
    print(f"   New header: {header}")
    print(f"   New header columns: {len(new_header_cols)}")
    
    # Verify expected columns
    expected_cols = ['code', 'section', 'option', 'cal', 'prot_g', 
                     'carbs_g', 'fat_g', 'GI', 'GL', 'sugars_g']
    
    if new_header_cols == expected_cols:
        print(f"   ✓ Header matches expected columns")
    else:
        print(f"   ⚠️  Warning: Header doesn't match expected")
        print(f"   Expected: {','.join(expected_cols)}")
        print(f"   Got: {','.join(new_header_cols)}")
    
    # Step 5: Fix all data rows
    print(f"\n[5/7] Fixing data rows...")
    
    fixed_lines = [header + '\n']  # Fixed header
    
    for i, line in enumerate(lines[1:], 1):
        if not line.strip():
            continue  # Skip blank lines
        
        # Remove trailing comma from this row
        fixed_line = line.rstrip()  # Remove trailing whitespace
        fixed_line = fixed_line.rstrip(',')  # Remove trailing commas
        fixed_line += '\n'
        
        fixed_lines.append(fixed_line)
    
    print(f"   ✓ Fixed {len(fixed_lines)-1} data rows")
    
    # Step 6: Write to temp file and validate
    print(f"\n[6/7] Writing and validating...")
    
    temp_file = master_file.with_suffix('.tmp')
    
    with open(temp_file, 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)
    
    print(f"   ✓ Wrote temp file")
    
    # Validate with pandas
    try:
        df = pd.read_csv(temp_file)
        
        print(f"\n   Pandas validation:")
        print(f"   ✓ Loaded successfully")
        print(f"   Rows: {len(df)}")
        print(f"   Columns: {len(df.columns)}")
        
        # Show columns
        print(f"\n   Column names:")
        for i, col in enumerate(df.columns, 1):
            print(f"      {i}. {col}")
        
        # Verify required columns
        required = ['code', 'sugars_g']
        missing = [col for col in required if col not in df.columns]
        
        if missing:
            print(f"   ✗ Missing required columns: {', '.join(missing)}")
            temp_file.unlink()
            return False
        
        print(f"   ✓ Has required columns: {', '.join(required)}")
        
        # Check for unexpected columns
        if 'sugar_g' in df.columns:
            print(f"   ✗ Still has 'sugar_g' column (unexpected)")
            temp_file.unlink()
            return False
        
        # Show sample data
        code_col = [c for c in df.columns if str(c).lower() == 'code'][0]
        print(f"\n   Sample codes:")
        for code in df[code_col].head(3):
            print(f"      - {code}")
        
        print(f"   ✓ All validation checks passed")
        
    except Exception as e:
        print(f"   ✗ Pandas validation failed: {e}")
        if temp_file.exists():
            temp_file.unlink()
        import traceback
        traceback.print_exc()
        return False
    
    # Step 7: Replace original file
    print(f"\n[7/7] Replacing original file...")
    temp_file.replace(master_file)
    print(f"   ✓ Replaced successfully")
    
    print("\n" + "=" * 70)
    print("✓ CSV Fixed Successfully!")
    print("=" * 70)
    
    print(f"\nWhat was fixed:")
    print(f"  - Removed 'sugar_g' from header")
    print(f"  - Removed trailing commas from header")
    print(f"  - Removed trailing commas from all {len(fixed_lines)-1} data rows")
    
    print(f"\nBackup saved: {backup_file.name}")
    
    print(f"\nNext steps:")
    print(f"  1. Verify columns.py is updated (prioritizes sugars_g)")
    print(f"  2. Restart application: python main.py")
    print(f"  3. Test: > find test")
    print(f"  4. Test: > add MT.2")
    
    return True


def main():
    """Main entry point."""
    possible_paths = [
        Path(r"C:\data\mealplan\meal_plan_master.csv"),
        Path("./data/meal_plan_master.csv"),
        Path("./meal_plan_master.csv"),
    ]
    
    master_file = None
    for path in possible_paths:
        if path.exists():
            master_file = path
            break
    
    if master_file is None:
        print("✗ Could not find meal_plan_master.csv")
        print("\nChecked:")
        for p in possible_paths:
            print(f"  - {p}")
        return 1
    
    print(f"Master file: {master_file}\n")
    
    success = fix_trailing_commas(master_file)
    
    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())