"""
Demo script to test the parser module.
"""
from meal_planner.parsers import CodeParser, parse_selection_to_items, items_to_code_string

def main():
    print("Testing Code Parser Module")
    print("=" * 60)
    
    # Test cases from your original code
    test_cases = [
        "B.1 *1.5, S2.4, L.3x2",
        "(FR.1, FR.2) *.5",
        "D.10-VE.T1",
        "D.10 - VE.T1*.5",
        "FI.9 x5.7/4",
        "@11, B.1, @11:30, S2.4",
        "B.1, (FR.1, FR.2) *.5, @12, L.3",
    ]
    
    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test}")
        print("-" * 60)
        
        # Parse
        items = CodeParser.parse(test)
        print(f"Parsed into {len(items)} items:")
        
        for j, item in enumerate(items, 1):
            if CodeParser.is_time_marker(item):
                print(f"  {j}. Time: @{item['time']}")
            elif CodeParser.is_code(item):
                code = item['code']
                mult = item['mult']
                mult_str = f" x{mult}" if mult != 1.0 else ""
                print(f"  {j}. Code: {code}{mult_str}")
        
        # Format back
        formatted = CodeParser.format(items)
        print(f"Formatted back: {formatted}")
        
        # Show filtering
        codes_only = CodeParser.get_codes_only(items)
        times = CodeParser.get_time_markers(items)
        
        if codes_only:
            print(f"Codes only: {len(codes_only)} codes")
        if times:
            print(f"Times: {', '.join('@' + t for t in times)}")
    
    # Demonstrate round-trip parsing
    print("\n" + "=" * 60)
    print("Round-trip test:")
    print("-" * 60)
    
    original = "B.1 *1.5, @11, S2.4, (FR.1, FR.2) *.5, D.10-VE.T1"
    print(f"Original: {original}")
    
    items = CodeParser.parse(original)
    formatted = CodeParser.format(items)
    print(f"After parse + format: {formatted}")
    
    items2 = CodeParser.parse(formatted)
    formatted2 = CodeParser.format(items2)
    print(f"After second round: {formatted2}")
    
    if formatted == formatted2:
        print("✓ Round-trip successful!")
    else:
        print("✗ Round-trip changed output")
    
    # Special case: FISH easter egg
    print("\n" + "=" * 60)
    print("Testing FISH codes (should trigger easter egg in app):")
    print("-" * 60)
    
    fish_test = "FI.1, FI.9 x5.7/4, B.1"
    items = CodeParser.parse(fish_test)
    
    has_fish = any(
        CodeParser.is_code(it) and it['code'].upper().startswith('FI.')
        for it in items
    )
    
    print(f"Input: {fish_test}")
    print(f"Contains fish code: {has_fish}")
    if has_fish:
        print("🐟 THANKS FOR ALL THE FISH!!!")
    
    print("\n" + "=" * 60)
    print("✓ All parser tests completed successfully!")

if __name__ == "__main__":
    main()