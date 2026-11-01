"""
Tests for plan_site/hub_page.py's cards: a plan's progress on its repository's index.
"""

from __future__ import annotations

from typing import Any

from basstler.plan_site.hub_page import PlanSummary


def summary(**overrides: Any) -> PlanSummary:
    """
    Build one :class:`PlanSummary` for a test, with sensible defaults for every field.

    :param overrides: Fields to replace on the returned summary.
    """
    fields = {
        "id": "plan-a",
        "title": "Plan A",
        "description": "desc",
        "done": 1,
        "total": 4,
        "dashboard_url": None,
    }
    fields.update(overrides)
    return PlanSummary(**fields)


# %% PlanSummary


def test_is_complete_requires_at_least_one_item():
    assert not summary(done=0, total=0).is_complete


def test_is_complete_when_done_equals_total():
    assert summary(done=4, total=4).is_complete


def test_completion_percentage_of_empty_plan_is_zero():
    assert summary(done=0, total=0).completion_percentage == 0.0


def test_completion_percentage_is_a_fraction_of_total():
    assert summary(done=1, total=4).completion_percentage == 25.0


def test_progress_label_for_empty_plan():
    assert summary(done=0, total=0).progress_label == "no items yet"


def test_progress_label_shows_done_over_total():
    assert summary(done=1, total=4).progress_label == "1 / 4 done"


def test_completion_percentage_label_is_formatted_to_one_decimal_place():
    assert summary(done=1, total=3).completion_percentage_label == "33.3%"


def test_css_class_is_plain_for_an_incomplete_plan():
    assert summary(done=1, total=4).css_class == "plan-card"


def test_css_class_marks_a_complete_plan():
    assert summary(done=4, total=4).css_class == "plan-card complete"
