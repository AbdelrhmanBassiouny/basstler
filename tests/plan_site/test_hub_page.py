"""
Tests for plan_site/hub_page.py's cards: a plan's progress on its repository's index.
"""

from __future__ import annotations

from typing import Any

from basstler.plan_site.hub_page import PlanSummary, ProgressStage, StageShare


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
        "page_url": None,
    }
    fields.update(overrides)
    return PlanSummary(**fields)


# %% PlanSummary


def test_is_complete_requires_at_least_one_item():
    assert not summary(done=0, total=0).is_complete


def test_is_complete_when_done_equals_total():
    assert summary(done=4, total=4).is_complete


def test_the_share_of_an_empty_plan_is_zero():
    assert summary(done=0, total=0).percentage_of(0) == 0.0


def test_a_share_is_a_fraction_of_total():
    assert summary(total=4).percentage_of(1) == 25.0


def test_the_stage_shares_are_the_started_reviewed_and_done_shares_in_stage_order():
    card = summary(started=3, reviewed=2, done=1, total=4)
    assert card.stage_shares == [
        StageShare(stage=ProgressStage.STARTED, percentage=card.percentage_of(3)),
        StageShare(stage=ProgressStage.REVIEWED, percentage=card.percentage_of(2)),
        StageShare(stage=ProgressStage.DONE, percentage=card.percentage_of(1)),
    ]


def test_the_stage_shares_label_joins_the_started_and_reviewed_shares():
    card = summary(started=3, reviewed=2, done=1, total=4)
    started, reviewed, _ = card.stage_shares
    assert card.stage_shares_label == f"{started.label} · {reviewed.label}"


def test_an_empty_plan_has_no_stage_shares_label():
    assert summary(done=0, total=0).stage_shares_label is None


def test_a_stage_share_label_is_a_whole_percentage_and_its_stage():
    share = StageShare(stage=ProgressStage.STARTED, percentage=40.0)
    assert share.label == f"40% {ProgressStage.STARTED}"


def test_progress_label_for_empty_plan():
    assert summary(done=0, total=0).progress_label == "no items yet"


def test_progress_label_shows_done_over_total():
    assert summary(done=1, total=4).progress_label == "1 / 4 done"


def test_a_stage_share_width_is_formatted_to_one_decimal_place():
    share = StageShare(stage=ProgressStage.DONE, percentage=100 / 3)
    assert share.width == "33.3%"


def test_css_class_is_plain_for_an_incomplete_plan():
    assert summary(done=1, total=4).css_class == "plan-card"


def test_css_class_marks_a_complete_plan():
    assert summary(done=4, total=4).css_class == "plan-card complete"
