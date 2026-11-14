"""
Tests for per-item nutrient contribution (top command / export --top).
"""
from types import SimpleNamespace

import pandas as pd

from meal_planner.reports.report_builder import ReportBuilder
from meal_planner.reports.contributors import (
    resolve_nutrient, resolve_meal, day_contributions,
    period_contributions, group_by_section,
)


class FakeMaster:
    """Minimal stand-in for MasterLoader: lookup_code/get_nutrients/cols."""

    cols = SimpleNamespace(
        code="code", option="option", section="section", cal="cal",
        prot_g="prot_g", carbs_g="carbs_g", fat_g="fat_g",
        sugar_g="sugar_g", gl="gl",
    )
    _rows = {
        "BR.1": {"code": "BR.1", "option": "Bread", "section": "Bread", "cal": 100, "carbs_g": 20},
        "FR.1": {"code": "FR.1", "option": "Apple", "section": "Fruit", "cal": 80, "carbs_g": 15},
        "FR.2": {"code": "FR.2", "option": "Pear", "section": "Fruit", "cal": 90, "carbs_g": 10},
        "MT.1": {"code": "MT.1", "option": "Chicken", "section": "Meat", "cal": 200, "prot_g": 30},
    }

    def lookup_code(self, code):
        return self._rows.get(code.upper())

    def get_nutrients(self, code):
        return None


def _builder():
    return ReportBuilder(FakeMaster())


def test_resolve_nutrient_aliases():
    assert resolve_nutrient("carbs") == "carbs_g"
    assert resolve_nutrient("PROT_G") == "prot_g"
    assert resolve_nutrient("vitc") == "vitC_mg"
    assert resolve_nutrient("bogus") is None


def test_resolve_meal():
    assert resolve_meal("lunch") == "LUNCH"
    assert resolve_meal("nope") is None


def test_day_contributions_applies_multipliers_and_merges_codes():
    items, total = day_contributions(_builder(), "BR.1 x2, FR.1, BR.1 *.5", "carbs_g", entry_date="d1")
    assert total == 20 * 2 + 15 + 20 * 0.5
    assert items["BR.1"].amount == 50
    assert items["BR.1"].servings == 2.5
    assert items["BR.1"].days == {"d1"}
    assert items["FR.1"].amount == 15


def test_day_contributions_subtraction_reduces_amount():
    items, total = day_contributions(_builder(), "BR.1-FR.2", "carbs_g")
    assert items["FR.2"].amount == -10
    assert items["FR.2"].servings == 0  # subtraction isn't a serving eaten
    assert total == 10


def test_day_contributions_meal_filter():
    codes = "@08:00 (BREAKFAST), BR.1, @12:00 (LUNCH), FR.1, MT.1"
    items, total = day_contributions(_builder(), codes, "carbs_g", meal="LUNCH")
    assert set(items) == {"FR.1", "MT.1"}
    assert total == 15


def test_day_contributions_empty_or_nan():
    assert day_contributions(_builder(), "nan", "cal") == ({}, 0.0)
    assert day_contributions(_builder(), "", "cal") == ({}, 0.0)


def test_period_contributions_ranks_and_counts_days():
    log_df = pd.DataFrame({
        "date": ["2025-01-01", "2025-01-02", "2025-01-03"],
        "codes": ["BR.1, FR.1", "FR.1 x3", "nan"],
    })
    ranked, total, logged = period_contributions(_builder(), log_df, "date", "codes", "carbs_g")
    assert [c.code for c in ranked] == ["FR.1", "BR.1"]
    assert ranked[0].amount == 60
    assert len(ranked[0].days) == 2
    assert total == 80
    assert logged == 2


def test_group_by_section():
    log_df = pd.DataFrame({"date": ["d1"], "codes": ["FR.1, FR.2, BR.1"]})
    ranked, _, _ = period_contributions(_builder(), log_df, "date", "codes", "carbs_g")
    groups = group_by_section(ranked)
    assert [(g.section, g.amount, g.code) for g in groups] == [
        ("Fruit", 25, "2 items"), ("Bread", 20, "1 item"),
    ]
