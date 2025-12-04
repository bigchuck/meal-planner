"""
Tests for column resolution utilities.
"""
import pandas as pd
import pytest
from meal_planner.utils.columns import (
    get_column,
    get_date_column,
    get_codes_column,
    get_sugar_column,
    ColumnResolver,
)


def test_get_column_exact_match():
    """Test exact case match."""
    df = pd.DataFrame(columns=['code', 'option', 'cal'])
    assert get_column(df, 'code') == 'code'
    assert get_column(df, 'option') == 'option'


def test_get_column_case_insensitive():
    """Test case-insensitive matching."""
    df = pd.DataFrame(columns=['Code', 'OPTION', 'Cal'])
    assert get_column(df, 'code') == 'Code'
    assert get_column(df, 'option') == 'OPTION'
    assert get_column(df, 'cal') == 'Cal'


def test_get_column_missing():
    """Test missing column returns None."""
    df = pd.DataFrame(columns=['code', 'option'])
    assert get_column(df, 'missing') is None


def test_get_date_column():
    """Test date column resolution."""
    df1 = pd.DataFrame(columns=['date', 'codes'])
    assert get_date_column(df1) == 'date'
    
    df2 = pd.DataFrame(columns=['Date', 'Codes'])
    assert get_date_column(df2) == 'Date'
    
    df3 = pd.DataFrame(columns=['other'])
    assert get_date_column(df3) == 'date'  # default


def test_get_codes_column():
    """Test codes column resolution."""
    df1 = pd.DataFrame(columns=['date', 'codes'])
    assert get_codes_column(df1) == 'codes'
    
    df2 = pd.DataFrame(columns=['Date', 'Codes'])
    assert get_codes_column(df2) == 'Codes'


def test_get_sugar_column_variants():
    """Test sugar column finds various naming conventions."""
    df1 = pd.DataFrame(columns=['cal', 'sugar_g'])
    assert get_sugar_column(df1) == 'sugar_g'
    
    df2 = pd.DataFrame(columns=['cal', 'sugar_g'])
    assert get_sugar_column(df2) == 'sugar_g'
    
    df3 = pd.DataFrame(columns=['cal', 'sugar'])
    assert get_sugar_column(df3) == 'sugar'
    
    df4 = pd.DataFrame(columns=['cal', 'sugar'])
    assert get_sugar_column(df4) == 'sugar'


def test_get_sugar_column_missing():
    """Test sugar column returns None when not found."""
    df = pd.DataFrame(columns=['cal', 'prot_g'])
    assert get_sugar_column(df) is None


def test_column_resolver_basic():
    """Test ColumnResolver basic functionality."""
    df = pd.DataFrame(columns=['Code', 'Option', 'Cal', 'prot_g'])
    cols = ColumnResolver(df)
    
    assert cols.code == 'Code'
    assert cols.option == 'Option'
    assert cols.cal == 'Cal'
    assert cols.prot_g == 'prot_g'


def test_column_resolver_defaults():
    """Test ColumnResolver returns defaults for missing columns."""
    df = pd.DataFrame(columns=['Code'])
    cols = ColumnResolver(df)
    
    assert cols.code == 'Code'
    assert cols.option == 'option'  # default
    assert cols.cal == 'cal'  # default


def test_column_resolver_sugar_variants():
    """Test ColumnResolver handles sugar column variants."""
    df1 = pd.DataFrame(columns=['cal', 'sugar_g'])
    cols1 = ColumnResolver(df1)
    assert cols1.sugar_g == 'sugar_g'
    
    df2 = pd.DataFrame(columns=['cal', 'sugar'])
    cols2 = ColumnResolver(df2)
    assert cols2.sugar_g == 'sugar'
    
    df3 = pd.DataFrame(columns=['cal'])
    cols3 = ColumnResolver(df3)
    assert cols3.sugar_g is None


def test_column_resolver_caching():
    """Test that ColumnResolver caches results."""
    df = pd.DataFrame(columns=['Code', 'Option'])
    cols = ColumnResolver(df)
    
    # First access
    result1 = cols.code
    # Second access should return cached value
    result2 = cols.code
    
    assert result1 == result2 == 'Code'
    assert 'code' in cols._cache


def test_column_resolver_as_dict():
    """Test ColumnResolver.as_dict() method."""
    df = pd.DataFrame(columns=['Code', 'Option', 'Cal', 'sugar_g'])
    cols = ColumnResolver(df)
    
    d = cols.as_dict()
    
    assert d['code'] == 'Code'
    assert d['option'] == 'Option'
    assert d['cal'] == 'Cal'
    assert d['sugar_g'] == 'sugar_g'
    assert 'prot_g' in d  # should have default values


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])