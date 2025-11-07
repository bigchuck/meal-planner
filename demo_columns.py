"""
Demo script to verify column utilities work with actual data.
"""
import pandas as pd
from config import MASTER_FILE, LOG_FILE, verify_data_files
from meal_planner.utils import ColumnResolver, get_column, get_sugar_column

def main():
    # Verify data files exist
    print("Checking data files...")
    verify_data_files()
    print("✓ All data files found\n")
    
    # Load master file
    print("Loading master file...")
    master = pd.read_csv(MASTER_FILE)
    print(f"✓ Loaded {len(master)} rows\n")
    
    # Show original columns
    print("Original columns in master:")
    for col in master.columns:
        print(f"  - {col}")
    print()
    
    # Test column resolver
    print("Testing ColumnResolver:")
    cols = ColumnResolver(master)
    print(f"  Code column: '{cols.code}'")
    print(f"  Option column: '{cols.option}'")
    print(f"  Section column: '{cols.section}'")
    print(f"  Cal column: '{cols.cal}'")
    print(f"  Sugar column: '{cols.sugar_g}'")
    print(f"  GL column: '{cols.gl}'")
    print()
    
    # Test individual functions
    print("Testing individual functions:")
    print(f"  get_column(master, 'code'): '{get_column(master, 'code')}'")
    print(f"  get_sugar_column(master): '{get_sugar_column(master)}'")
    print()
    
    # Load log file and test
    print("Loading log file...")
    log = pd.read_csv(LOG_FILE)
    print(f"✓ Loaded {len(log)} rows\n")
    
    print("Log file columns:")
    for col in log.columns:
        print(f"  - {col}")
    print()
    
    log_cols = ColumnResolver(log)
    print("Log ColumnResolver:")
    print(f"  Date column: '{log_cols.date}'")
    print(f"  Codes column: '{log_cols.codes}'")
    print(f"  Cal column: '{log_cols.cal}'")
    print()
    
    print("✓ All utilities working correctly!")
    
    # Show a sample lookup
    if not master.empty:
        code_col = cols.code
        option_col = cols.option
        first_code = master.iloc[0][code_col]
        first_option = master.iloc[0][option_col]
        print(f"\nSample: First row has code='{first_code}', option='{first_option}'")

if __name__ == "__main__":
    main()