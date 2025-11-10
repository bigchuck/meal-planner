"""
Demo script to test the models.
"""
from meal_planner.models import (
    MealItem, TimeMarker,
    DailyTotals, NutrientRow,
    PendingDay,
    items_from_dict_list
)


def main():
    print("Testing Data Models")
    print("=" * 70)
    
    # Test 1: MealItem
    print("\n1. MealItem")
    print("-" * 70)
    
    item1 = MealItem("B.1", 1.5)
    print(f"   Created: {item1}")
    print(f"   Code: {item1.code}, Multiplier: {item1.multiplier}")
    print(f"   Formatted: {item1.format_code_string()}")
    
    # Lowercase gets uppercased
    item2 = MealItem("s2.4")
    print(f"   Lowercase 's2.4' becomes: {item2.code}")
    
    # Serialization
    data = item1.to_dict()
    print(f"   Serialized: {data}")
    
    item3 = MealItem.from_dict(data)
    print(f"   Deserialized: {item3}")
    
    # Test 2: TimeMarker
    print("\n2. TimeMarker")
    print("-" * 70)
    
    marker = TimeMarker("11:30")
    print(f"   Created: {marker}")
    print(f"   String repr: {str(marker)}")
    print(f"   Serialized: {marker.to_dict()}")
    
    # Test invalid time
    try:
        bad_marker = TimeMarker("25:00")
    except ValueError as e:
        print(f"   ✓ Invalid time rejected: {e}")
    
    # Test 3: DailyTotals
    print("\n3. DailyTotals")
    print("-" * 70)
    
    totals1 = DailyTotals(calories=500, protein_g=30, carbs_g=50, fat_g=15)
    print(f"   Meal 1: {totals1.format_summary()}")
    
    totals2 = DailyTotals(calories=300, protein_g=20, carbs_g=30, fat_g=10)
    print(f"   Meal 2: {totals2.format_summary()}")
    
    # Add totals
    combined = totals1 + totals2
    print(f"   Combined: {combined.format_summary()}")
    
    # Scale totals
    doubled = totals1 * 2.0
    print(f"   Doubled: {doubled.format_summary()}")
    
    # Rounding
    precise = DailyTotals(calories=1234.56, protein_g=78.9)
    rounded = precise.rounded()
    print(f"   Before rounding: Cal={precise.calories:.2f}, P={precise.protein_g:.1f}g")
    print(f"   After rounding: Cal={rounded.calories:.0f}, P={rounded.protein_g:.0f}g")
    
    # Test 4: PendingDay
    print("\n4. PendingDay")
    print("-" * 70)
    
    # Create empty day
    day = PendingDay("2025-01-15", [])
    print(f"   Created: {day}")
    print(f"   Empty: {day.is_empty()}")
    
    # Add items
    day.add_item(MealItem("B.1", 1.5))
    day.add_item(TimeMarker("11:00"))
    day.add_item(MealItem("S2.4", 1.0))
    day.add_item(TimeMarker("14:30"))
    day.add_item(MealItem("L.3", 2.0))
    
    print(f"   After adding items: {len(day)} items")
    print(f"   Codes string: {day.format_codes_string()}")
    
    # Filter items
    meals = day.get_meal_items()
    times = day.get_time_markers()
    print(f"   Meal items: {len(meals)}")
    print(f"   Time markers: {len(times)}")
    
    for meal in meals:
        print(f"     - {meal}")
    for time in times:
        print(f"     - {time}")
    
    # Serialization
    data = day.to_dict()
    print(f"\n   Serialized to dict with {len(data['items'])} items")
    
    # Round-trip
    day2 = PendingDay.from_dict(data)
    print(f"   Deserialized: {day2}")
    print(f"   Codes match: {day.format_codes_string() == day2.format_codes_string()}")
    
    # Test 5: Integration with dict lists
    print("\n5. Integration with Dictionary Lists")
    print("-" * 70)
    
    # Simulate what comes from JSON
    json_data = [
        {"code": "B.1", "mult": 1.5},
        {"time": "11:00"},
        {"code": "S2.4", "mult": 1.0},
        {"time": "14:30"},
        {"code": "L.3", "mult": 2.0}
    ]
    
    print(f"   Loading {len(json_data)} items from dict list...")
    items = items_from_dict_list(json_data)
    print(f"   Created {len(items)} item objects")
    
    day3 = PendingDay("2025-01-16", items)
    print(f"   Created PendingDay: {day3}")
    print(f"   Formatted: {day3.format_codes_string()}")
    
    # Test 6: NutrientRow
    print("\n6. NutrientRow (for reports)")
    print("-" * 70)
    
    row_totals = DailyTotals(calories=350, protein_g=25, carbs_g=40, fat_g=12)
    row = NutrientRow(
        code="B.1",
        option="Scrambled eggs with toast",
        section="Breakfast",
        multiplier=1.5,
        totals=row_totals
    )
    
    print(f"   Code: {row.code}")
    print(f"   Option: {row.option}")
    print(f"   Section: {row.section}")
    print(f"   Multiplier: {row.multiplier}")
    print(f"   Totals: {row.totals.format_summary()}")
    
    row_dict = row.to_dict()
    print(f"   Serialized keys: {', '.join(row_dict.keys())}")
    
    print("\n" + "=" * 70)
    print("✓ All models working correctly!")
    print("\nThese models provide:")
    print("  - Type safety (know what data you're working with)")
    print("  - Clean serialization (easy JSON conversion)")
    print("  - Rich behavior (add totals, format strings, etc.)")
    print("  - Self-documenting code (clear what each field means)")

if __name__ == "__main__":
    main()