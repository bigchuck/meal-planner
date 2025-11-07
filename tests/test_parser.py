"""
Tests for code parser utilities.
"""
import pytest
from meal_planner.parsers.code_parser import (
    normalize_time,
    eval_multiplier_expression,
    split_top_level,
    parse_one_code_mult,
    parse_selection_to_items,
    items_to_code_string,
    CodeParser,
)


def test_normalize_time():
    """Test time normalization."""
    assert normalize_time(11, 30) == "11:30"
    assert normalize_time(9, 5) == "09:05"
    assert normalize_time(0, 0) == "00:00"
    assert normalize_time(23, 59) == "23:59"


def test_normalize_time_invalid():
    """Test invalid times raise ValueError."""
    with pytest.raises(ValueError):
        normalize_time(24, 0)
    with pytest.raises(ValueError):
        normalize_time(12, 60)
    with pytest.raises(ValueError):
        normalize_time(-1, 0)


def test_eval_multiplier_simple():
    """Test simple multiplier evaluation."""
    assert eval_multiplier_expression("1.5") == 1.5
    assert eval_multiplier_expression("2") == 2.0
    assert eval_multiplier_expression(".5") == 0.5


def test_eval_multiplier_arithmetic():
    """Test arithmetic multiplier expressions."""
    assert eval_multiplier_expression("5.7/4") == pytest.approx(1.425)
    assert eval_multiplier_expression(".5*2") == 1.0
    assert eval_multiplier_expression("3*2/6") == 1.0


def test_eval_multiplier_empty():
    """Test empty expression returns 1.0."""
    assert eval_multiplier_expression("") == 1.0
    assert eval_multiplier_expression("   ") == 1.0


def test_split_top_level():
    """Test splitting by commas outside parentheses."""
    assert split_top_level("B.1, S2.4") == ["B.1", "S2.4"]
    assert split_top_level("B.1, (FR.1, FR.2), L.3") == ["B.1", "(FR.1, FR.2)", "L.3"]
    assert split_top_level("(A, B), (C, D)") == ["(A, B)", "(C, D)"]


def test_parse_one_code_mult_simple():
    """Test parsing single code without multiplier."""
    result = parse_one_code_mult("B.1")
    assert result == {"code": "B.1", "mult": 1.0}


def test_parse_one_code_mult_with_multiplier():
    """Test parsing code with multiplier."""
    result = parse_one_code_mult("B.1 *1.5")
    assert result == {"code": "B.1", "mult": 1.5}
    
    result = parse_one_code_mult("S2.4 x2")
    assert result == {"code": "S2.4", "mult": 2.0}
    
    result = parse_one_code_mult("FI.9 ×.5")
    assert result == {"code": "FI.9", "mult": 0.5}


def test_parse_one_code_mult_arithmetic():
    """Test parsing code with arithmetic multiplier."""
    result = parse_one_code_mult("FI.9 x5.7/4")
    assert result["code"] == "FI.9"
    assert result["mult"] == pytest.approx(1.425)


def test_parse_one_code_mult_time_returns_none():
    """Test that time tokens return None."""
    assert parse_one_code_mult("@11") is None
    assert parse_one_code_mult("@11:30") is None


def test_parse_selection_simple_codes():
    """Test parsing simple code list."""
    result = parse_selection_to_items("B.1, S2.4, L.3")
    assert len(result) == 3
    assert result[0] == {"code": "B.1", "mult": 1.0}
    assert result[1] == {"code": "S2.4", "mult": 1.0}
    assert result[2] == {"code": "L.3", "mult": 1.0}


def test_parse_selection_with_multipliers():
    """Test parsing codes with multipliers."""
    result = parse_selection_to_items("B.1 *1.5, S2.4 x2")
    assert len(result) == 2
    assert result[0] == {"code": "B.1", "mult": 1.5}
    assert result[1] == {"code": "S2.4", "mult": 2.0}


def test_parse_selection_time_markers():
    """Test parsing time markers."""
    result = parse_selection_to_items("@11, @11:30")
    assert len(result) == 2
    assert result[0] == {"time": "11:00"}
    assert result[1] == {"time": "11:30"}


def test_parse_selection_mixed():
    """Test parsing mixed codes and times."""
    result = parse_selection_to_items("B.1, @11, S2.4 *1.5")
    assert len(result) == 3
    assert result[0] == {"code": "B.1", "mult": 1.0}
    assert result[1] == {"time": "11:00"}
    assert result[2] == {"code": "S2.4", "mult": 1.5}


def test_parse_selection_group():
    """Test parsing grouped codes with multiplier."""
    result = parse_selection_to_items("(FR.1, FR.2) *.5")
    assert len(result) == 2
    assert result[0] == {"code": "FR.1", "mult": 0.5}
    assert result[1] == {"code": "FR.2", "mult": 0.5}


def test_parse_selection_subtraction():
    """Test parsing subtraction (D.10-VE.T1)."""
    result = parse_selection_to_items("D.10-VE.T1")
    assert len(result) == 2
    assert result[0] == {"code": "D.10", "mult": 1.0}
    assert result[1] == {"code": "VE.T1", "mult": -1.0}


def test_parse_selection_subtraction_with_mult():
    """Test parsing subtraction with multiplier."""
    result = parse_selection_to_items("D.10 - VE.T1*.5")
    assert len(result) == 2
    assert result[0] == {"code": "D.10", "mult": 1.0}
    assert result[1] == {"code": "VE.T1", "mult": -0.5}


def test_parse_selection_list_input():
    """Test parsing from list input."""
    result = parse_selection_to_items(["B.1", "S2.4", "@11"])
    assert len(result) == 3
    assert result[0] == {"code": "B.1", "mult": 1.0}
    assert result[1] == {"code": "S2.4", "mult": 1.0}
    assert result[2] == {"time": "11:00"}


def test_items_to_code_string_simple():
    """Test formatting items to string."""
    items = [
        {"code": "B.1", "mult": 1.0},
        {"code": "S2.4", "mult": 1.0}
    ]
    result = items_to_code_string(items)
    assert result == "B.1, S2.4"


def test_items_to_code_string_with_multipliers():
    """Test formatting with multipliers."""
    items = [
        {"code": "B.1", "mult": 1.5},
        {"code": "S2.4", "mult": 2.0}
    ]
    result = items_to_code_string(items)
    assert result == "B.1 x1.5, S2.4 x2"


def test_items_to_code_string_with_time():
    """Test formatting with time markers."""
    items = [
        {"code": "B.1", "mult": 1.0},
        {"time": "11:00"},
        {"code": "S2.4", "mult": 1.0}
    ]
    result = items_to_code_string(items)
    assert result == "B.1, @11:00, S2.4"


def test_items_to_code_string_negative():
    """Test formatting negative multipliers (subtractions)."""
    items = [
        {"code": "D.10", "mult": 1.0},
        {"code": "VE.T1", "mult": -0.5}
    ]
    result = items_to_code_string(items)
    assert result == "D.10, -VE.T1 x0.5"


def test_code_parser_class():
    """Test CodeParser convenience class."""
    # Parse
    items = CodeParser.parse("B.1 *1.5, @11")
    assert len(items) == 2
    
    # Format
    result = CodeParser.format(items)
    assert "B.1" in result
    assert "@11" in result
    
    # Filters
    codes_only = CodeParser.get_codes_only(items)
    assert len(codes_only) == 1
    assert codes_only[0]["code"] == "B.1"
    
    times = CodeParser.get_time_markers(items)
    assert len(times) == 1
    assert times[0] == "11:00"


def test_code_parser_is_methods():
    """Test CodeParser type checking methods."""
    code_item = {"code": "B.1", "mult": 1.0}
    time_item = {"time": "11:00"}
    
    assert CodeParser.is_code(code_item)
    assert not CodeParser.is_time_marker(code_item)
    
    assert CodeParser.is_time_marker(time_item)
    assert not CodeParser.is_code(time_item)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])