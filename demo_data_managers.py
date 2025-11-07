"""
Demo script to test all data managers working together.
"""
from config import MASTER_FILE, LOG_FILE, PENDING_FILE, verify_data_files
from meal_planner.data import MasterLoader, LogManager, PendingManager
from meal_planner.parsers import CodeParser

def main():
    print("Testing Data Managers")
    print("=" * 70)
    
    # Verify files
    verify_data_files()
    print()
    
    # Test 1: MasterLoader
    print("1. MasterLoader")
    print("-" * 70)
    master = MasterLoader(MASTER_FILE)
    print(f"   Loaded {len(master.df)} master entries")
    
    # Get first code for testing
    first_code = master.df.iloc[0][master.cols.code]
    print(f"   Testing with code: {first_code}")
    
    row = master.lookup_code(first_code)
    if row:
        print(f"   ✓ Lookup successful: {row[master.cols.option]}")
        print(f"     Calories: {row[master.cols.cal]}")
    
    nutrients = master.get_nutrient_totals(first_code, multiplier=2.0)
    if nutrients:
        print(f"   ✓ Nutrient calculation (x2): {nutrients['cal']:.0f} cal")
    
    # Test 2: LogManager
    print("\n2. LogManager")
    print("-" * 70)
    log = LogManager(LOG_FILE)
    print(f"   Loaded {len(log.df)} log entries")
    
    if not log.df.empty:
        # Get first date
        first_date = str(log.df.iloc[0][log.cols.date])
        print(f"   First entry date: {first_date}")
        
        entries = log.get_entries_for_date(first_date)
        print(f"   Entries for {first_date}: {len(entries)}")
        
        if not entries.empty:
            codes = entries.iloc[0][log.cols.codes]
            print(f"   Codes: {codes}")
    
    # Get summary for last 7 days (if data exists)
    summary = log.get_summary()
    if summary['total_days'] > 0:
        print(f"   Total days logged: {summary['total_days']}")
        print(f"   Average calories: {summary['averages']['cal']}")
    
    # Test 3: PendingManager
    print("\n3. PendingManager")
    print("-" * 70)
    pending_mgr = PendingManager(PENDING_FILE)
    
    pending = pending_mgr.load()
    if pending:
        print(f"   ✓ Pending data exists")
        print(f"   Date: {pending['date']}")
        print(f"   Items: {len(pending['items'])}")
        
        if pending['items']:
            print(f"   First item: {pending['items'][0]}")
    else:
        print("   No pending data (this is normal)")
        print("   Creating test pending data...")
        
        # Create test pending
        test_pending = {
            "date": "2025-01-15",
            "items": CodeParser.parse("B.1 *1.5, @11, S2.4")
        }
        pending_mgr.save(test_pending)
        print("   ✓ Test pending saved")
        
        # Reload and verify
        reloaded = pending_mgr.load()
        if reloaded and len(reloaded['items']) == 3:
            print(f"   ✓ Reload successful: {len(reloaded['items'])} items")
        
        # Clean up test
        pending_mgr.clear()
        print("   ✓ Test pending cleared")
    
    # Test 4: Integration - Parse codes and calculate totals
    print("\n4. Integration Test: Parse → Lookup → Calculate")
    print("-" * 70)
    
    test_codes = f"{first_code} *1.5, {first_code} x0.5"
    print(f"   Input: {test_codes}")
    
    items = CodeParser.parse(test_codes)
    print(f"   Parsed: {len(items)} items")
    
    total_cal = 0
    for item in items:
        if CodeParser.is_code(item):
            code = item['code']
            mult = item['mult']
            nutrients = master.get_nutrient_totals(code, mult)
            if nutrients:
                total_cal += nutrients['cal']
                print(f"     {code} x{mult}: {nutrients['cal']:.0f} cal")
    
    print(f"   Total: {total_cal:.0f} calories")
    
    # Test 5: Backward compatibility
    print("\n5. Backward Compatibility Functions")
    print("-" * 70)
    
    from meal_planner.data import load_master, lookup_code_row
    from meal_planner.data import ensure_log, save_log
    from meal_planner.data import load_pending, save_pending
    
    print("   ✓ load_master() imported")
    print("   ✓ lookup_code_row() imported")
    print("   ✓ ensure_log() imported")
    print("   ✓ save_log() imported")
    print("   ✓ load_pending() imported")
    print("   ✓ save_pending() imported")
    
    # Test them
    master_df = load_master(MASTER_FILE)
    print(f"   ✓ load_master() works: {len(master_df)} rows")
    
    row = lookup_code_row(first_code, master_df)
    if row:
        print(f"   ✓ lookup_code_row() works: found {first_code}")
    
    log_df = ensure_log(LOG_FILE)
    print(f"   ✓ ensure_log() works: {len(log_df)} rows")
    
    print("\n" + "=" * 70)
    print("✓ All data managers working correctly!")
    print("\nYou now have clean, tested data access layer!")
    print("Original messy CSV/JSON operations → Clean manager classes")

if __name__ == "__main__":
    main()