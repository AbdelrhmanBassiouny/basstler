"""
Tests for plan_site/hub_page.py's cards: a plan's progress on its repository's index.
"""

from __future__ import annotations

import dataclasses

from basstler.plan.model import ItemStatus
from basstler.plan_site.hub_page import CountedItem, PlanSummary, StageShare
from basstler.plan_site.plan import Plan, ProgressStage

from ..manifest_builders import minimal_plan


def summary(
    done: int = 1, total: int = 4, started: int = 0, reviewed: int = 0
) -> PlanSummary:
    """
    Build one :class:`PlanSummary` for a test, counting items that reached each stage.

    :param done: How many items are done.
    :param total: How many items there are.
    :param started: How many items have begun.
    :param reviewed: How many items are past their author's review.
    """
    reached_counts = {
        ProgressStage.STARTED: started,
        ProgressStage.REVIEWED: reviewed,
        ProgressStage.DONE: done,
    }
    return PlanSummary(
        id="plan-a",
        title="Plan A",
        description="desc",
        counted_items=[
            CountedItem(
                status=ItemStatus.DONE if position < done else ItemStatus.IN_PROGRESS,
                reached_stages=[
                    stage for stage in ProgressStage if position < reached_counts[stage]
                ],
                listing_url=None,
                number=None,
            )
            for position in range(total)
        ],
    )


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


# %% what a plan's card counts


def test_a_plan_s_card_counts_its_items_and_those_that_landed():
    plan = Plan.from_mapping(minimal_plan(landed_item_count=2))

    card = PlanSummary(
        id=plan.id,
        title=plan.title,
        description=plan.description,
        counted_items=CountedItem.from_plan(plan),
    )

    assert (card.done, card.total) == (
        plan.landed_item_count,
        len(plan.items) + plan.landed_item_count,
    )


# %% the names a script reads counted items by


def test_a_script_reads_each_field_of_a_counted_item_by_its_name():
    assert [member.value for member in CountedItem.field_name] == [
        data_field.name for data_field in dataclasses.fields(CountedItem)
    ]


def test_a_class_builds_its_field_names_once():
    assert CountedItem.field_name is CountedItem.field_name
