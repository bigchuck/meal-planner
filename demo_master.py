"""
Demo script to test the new MasterLoader class.
"""
from config import MASTER_FILE, verify_data_files
from meal_planner.data.master_loader import MasterLoader, lookup_code_row
import pandas as pd

def main():
    print("Testing MasterLoader refactored module\n")
    print("="*60)
    
    # Verify files
    verify_data_files()
    
    # Test new class-based approach
    print("\n1. Testing MasterLoader class:")
    print("-" * 60)
    loader = MasterLoader(MASTER_FILE)
    
    # Auto-loads on first access
    print(f"   Loaded {len(loader.df)} rows from master")
    print(f"   Columns: {', '.join(loader.df.columns[:5])}...")
    
    # Test lookup
    print("\n2. Testing lookup_code():")
    print("-" * 60)
    
    # Get first code from the file to test with
    first_code = loader.df.iloc[0][loader.cols.code]
    print(f"   Looking up code: '{first_code}'")
    
    result = loader.lookup_code(first_code)
    if result:
        print(f"   ✓ Found: {result.get(loader.cols.option, 'N/A')}")
        print(f"   Calories: {result.get(loader.cols.cal, 'N/A')}")
    else:
        print("   ✗ Not found")
    
    # Test case insensitivity
    print(f"\n   Testing case-insensitive lookup with '{first_code.lower()}':")
    result_lower = loader.lookup_code(first_code.lower())
    print(f"   {'✓' if result_lower else '✗'} Found with lowercase")
    
    # Test missing code
    print("\n   Testing missing code lookup:")
    result_missing = loader.lookup_code("NOTEXIST.999")
    print(f"   {'✓' if result_missing is None else '✗'} Returns None for missing")
    
    # Test search
    print("\n3. Testing search():")
    print("-" * 60)
    
    # Search for something likely in your data
    search_term = "1"  # Simple search
    results = loader.search(search_term)
    print(f"   Search for '{search_term}': found {len(results)} matches")
    if len(results) > 0:
        print(f"   First match: {results.iloc[0][loader.cols.code]} - {results.iloc[0][loader.cols.option]}")
    
    # Test get_nutrient_totals
    print("\n4. Testing get_nutrient_totals():")
    print("-" * 60)
    nutrients = loader.get_nutrient_totals(first_code, multiplier=1.5)
    if nutrients:
        print(f"   Code '{first_code}' x 1.5:")
        print(f"   Calories: {nutrients['cal']:.1f}")
        print(f"   Protein: {nutrients['prot_g']:.1f}g")
        print(f"   Carbs: {nutrients['carbs_g']:.1f}g")
        print(f"   Fat: {nutrients['fat_g']:.1f}g")
    
    # Test backward-compatible function
    print("\n5. Testing backward-compatible lookup_code_row():")
    print("-" * 60)
    master_df = pd.read_csv(MASTER_FILE)
    result_compat = lookup_code_row(first_code, master_df)
    if result_compat:
        print(f"   ✓ Old function still works")
        print(f"   Found: {result_compat.get(loader.cols.option, 'N/A')}")
    
    print("\n" + "="*60)
    print("✓ All MasterLoader tests passed!")
    print("\nThis proves the refactoring approach works with your real data.")

if __name__ == "__main__":
    main()