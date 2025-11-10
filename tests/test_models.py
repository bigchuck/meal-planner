"""
Tests for data models.
"""
import pytest
from meal_planner.models import (
    MealItem, TimeMarker, Item,
    DailyTotals, NutrientRow,
    PendingDay,
    item_from_dict, items_from_dict_list
)


# MealItem tests
def test_meal_item_creation():
    """Test MealItem basic creation."""
    item = MealItem("B.1", 1.5)
    assert item.code == "B.1"
    assert item.multiplier == 1.5


def test_meal_item_uppercase():
    """Test code is normalized to uppercase."""
    item = MealItem("b.1", 2.0)
    assert item.code == "B.1"


def test_meal_item_default_multiplier():
    """Test default multiplier is 1.0."""
    item = MealItem("S2.4")
    assert item.multiplier == 1.0


def test_meal_item_to_dict():
    """Test MealItem serialization."""
    item = MealItem("B.1", 1.5)
    data = item.to_dict()
    assert data == {"code": "B.1", "mult": 1.5}


def test_meal_item_from_dict():
    """Test MealItem deserialization."""
    data = {"code": "b.1", "mult": 1.5}
    item = MealItem.from_dict(data)
    assert item.code == "B.1"
    assert item.multiplier == 1.5


def test_meal_item_format_simple():
    """Test formatting without multiplier."""
    item = MealItem("B.1", 1.0)
    assert item.format_code_string() == "B.1"


def test_meal_item_format_with_multiplier():
    """Test formatting with multiplier."""
    item = MealItem("B.1", 1.5)
    assert item.format_code_string() == "B.1 x1.5"


def test_meal_item_format_negative():
    """Test formatting negative multiplier."""
    item = MealItem("VE.T1", -0.5)
    assert item.format_code_string() == "-VE.T1 x0.5"


# TimeMarker tests
def test_time_marker_creation():
    """Test TimeMarker creation."""
    marker = TimeMarker("11:30")
    assert marker.time == "11:30"


def test_time_marker_invalid():
    """Test invalid time format raises error."""
    with pytest.raises(ValueError):
        TimeMarker("25:00")
    with pytest.raises(ValueError):
        TimeMarker("12:60")
    with pytest.raises(ValueError):
        TimeMarker("invalid")


def test_time_marker_to_dict():
    """Test TimeMarker serialization."""
    marker = TimeMarker("11:30")
    data = marker.to_dict()
    assert data == {"time": "11:30"}


def test_time_marker_from_dict():
    """Test TimeMarker deserialization."""
    data = {"time": "11:30"}
    marker = TimeMarker.from_dict(data)
    assert marker.time == "11:30"


def test_time_marker_str():
    """Test TimeMarker string representation."""
    marker = TimeMarker("11:30")
    assert str(marker) == "@11:30"


# Item conversion tests
def test_item_from_dict_meal():
    """Test creating MealItem from dict."""
    data = {"code": "B.1", "mult": 1.5}
    item = item_from_dict(data)
    assert isinstance(item, MealItem)
    assert item.code == "B.1"


def test_item_from_dict_time():
    """Test creating TimeMarker from dict."""
    data = {"time": "11:30"}
    item = item_from_dict(data)
    assert isinstance(item, TimeMarker)
    assert item.time == "11:30"


def test_item_from_dict_invalid():
    """Test invalid dict returns None."""
    assert item_from_dict({}) is None
    assert item_from_dict({"invalid": "data"}) is None


def test_items_from_dict_list():
    """Test converting list of dicts to items."""
    data = [
        {"code": "B.1", "mult": 1.5},
        {"time": "11:00"},
        {"code": "S2.4", "mult": 1.0}
    ]
    items = items_from_dict_list(data)
    assert len(items) == 3
    assert isinstance(items[0], MealItem)
    assert isinstance(items[1], TimeMarker)
    assert isinstance(items[2], MealItem)


# DailyTotals tests
def test_daily_totals_creation():
    """Test DailyTotals creation."""
    totals = DailyTotals(calories=2000, protein_g=150)
    assert totals.calories == 2000
    assert totals.protein_g == 150


def test_daily_totals_defaults():
    """Test DailyTotals default values."""
    totals = DailyTotals()
    assert totals.calories == 0.0
    assert totals.protein_g == 0.0


def test_daily_totals_to_dict():
    """Test DailyTotals serialization."""
    totals = DailyTotals(calories=500, protein_g=30)
    data = totals.to_dict()
    assert data["cal"] == 500
    assert data["prot_g"] == 30


def test_daily_totals_from_dict():
    """Test DailyTotals deserialization."""
    data = {"cal": 500, "prot_g": 30, "carbs_g": 50}
    totals = DailyTotals.from_dict(data)
    assert totals.calories == 500
    assert totals.protein_g == 30
    assert totals.carbs_g == 50


def test_daily_totals_add():
    """Test adding two DailyTotals."""
    t1 = DailyTotals(calories=500, protein_g=30)
    t2 = DailyTotals(calories=300, protein_g=20)
    t3 = t1.add(t2)
    assert t3.calories == 800
    assert t3.protein_g == 50


def test_daily_totals_add_operator():
    """Test + operator."""
    t1 = DailyTotals(calories=500, protein_g=30)
    t2 = DailyTotals(calories=300, protein_g=20)
    t3 = t1 + t2
    assert t3.calories == 800


def test_daily_totals_scale():
    """Test scaling."""
    totals = DailyTotals(calories=1000, protein_g=50)
    scaled = totals.scale(1.5)
    assert scaled.calories == 1500
    assert scaled.protein_g == 75


def test_daily_totals_multiply_operator():
    """Test * operator."""
    totals = DailyTotals(calories=1000, protein_g=50)
    scaled = totals * 2.0
    assert scaled.calories == 2000


def test_daily_totals_rounded():
    """Test rounding."""
    totals = DailyTotals(calories=1234.56, protein_g=78.9)
    rounded = totals.rounded()
    assert rounded.calories == 1235
    assert rounded.protein_g == 79


def test_daily_totals_format():
    """Test format_summary."""
    totals = DailyTotals(calories=2000, protein_g=150, carbs_g=200)
    summary = totals.format_summary()
    assert "Cal: 2000" in summary
    assert "P: 150g" in summary
    assert "C: 200g" in summary


# PendingDay tests
def test_pending_day_creation():
    """Test PendingDay creation."""
    day = PendingDay("2025-01-15", [])
    assert day.date == "2025-01-15"
    assert len(day.items) == 0


def test_pending_day_with_items():
    """Test PendingDay with items."""
    items = [
        MealItem("B.1", 1.5),
        TimeMarker("11:00"),
        MealItem("S2.4", 1.0)
    ]
    day = PendingDay("2025-01-15", items)
    assert len(day) == 3


def test_pending_day_add_item():
    """Test adding item to PendingDay."""
    day = PendingDay("2025-01-15", [])
    day.add_item(MealItem("B.1", 1.0))
    assert len(day) == 1


def test_pending_day_remove_item():
    """Test removing item from PendingDay."""
    day = PendingDay("2025-01-15", [MealItem("B.1")])
    day.remove_item(0)
    assert len(day) == 0


def test_pending_day_get_meal_items():
    """Test filtering to meal items only."""
    items = [
        MealItem("B.1", 1.5),
        TimeMarker("11:00"),
        MealItem("S2.4", 1.0)
    ]
    day = PendingDay("2025-01-15", items)
    meals = day.get_meal_items()
    assert len(meals) == 2
    assert all(isinstance(m, MealItem) for m in meals)


def test_pending_day_get_time_markers():
    """Test filtering to time markers only."""
    items = [
        MealItem("B.1", 1.5),
        TimeMarker("11:00"),
        TimeMarker("14:30")
    ]
    day = PendingDay("2025-01-15", items)
    times = day.get_time_markers()
    assert len(times) == 2
    assert all(isinstance(t, TimeMarker) for t in times)


def test_pending_day_format_codes():
    """Test formatting codes string."""
    items = [
        MealItem("B.1", 1.5),
        TimeMarker("11:00"),
        MealItem("S2.4", 1.0)
    ]
    day = PendingDay("2025-01-15", items)
    codes = day.format_codes_string()
    assert "B.1 x1.5" in codes
    assert "@11:00" in codes
    assert "S2.4" in codes


def test_pending_day_to_dict():
    """Test PendingDay serialization."""
    items = [MealItem("B.1", 1.5)]
    day = PendingDay("2025-01-15", items)
    data = day.to_dict()
    assert data["date"] == "2025-01-15"
    assert len(data["items"]) == 1


def test_pending_day_from_dict():
    """Test PendingDay deserialization."""
    data = {
        "date": "2025-01-15",
        "items": [
            {"code": "B.1", "mult": 1.5},
            {"time": "11:00"}
        ]
    }
    day = PendingDay.from_dict(data)
    assert day.date == "2025-01-15"
    assert len(day.items) == 2


def test_pending_day_is_empty():
    """Test is_empty method."""
    day = PendingDay("2025-01-15", [])
    assert day.is_empty()
    
    day.add_item(MealItem("B.1"))
    assert not day.is_empty()


def test_pending_day_clear():
    """Test clear method."""
    day = PendingDay("2025-01-15", [MealItem("B.1")])
    day.clear()
    assert day.is_empty()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])