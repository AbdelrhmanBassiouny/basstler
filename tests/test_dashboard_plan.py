"""
Tests for :mod:`basstler.dashboard_plan`: reading a plan's waves, tracks and items, and
what an item answers about itself.
"""

import pytest

from basstler.dashboard_plan import Item, Plan
from basstler.plan_model import ItemStatus, ManifestKey
from basstler.pull_request_state import (
    LiveState,
)
from basstler.locations import PackageLocation

from .manifest_builders import manifest_item, minimal_plan


# %% plan items by identifier


def test_plan_indexes_its_items_by_identifier():
    plan = Plan.from_mapping(
        minimal_plan(items=[manifest_item("a"), manifest_item("b")])
    )
    assert plan.items_by_identifier == {item.identifier: item for item in plan.items}


# %% Item / StackedItem - precomputed template values


def test_status_and_drift_css_class_without_drift():
    plain_item = Item(
        title="A", branch="a", track="track-1", status=ItemStatus.IN_PROGRESS
    )
    assert plain_item.status_and_drift_css_class == "status-in_progress"


def test_status_and_drift_css_class_with_drift():
    drifted_item = Item(title="A", branch="a", track="track-1", status=ItemStatus.DONE)
    drifted_item.drift_description = "marked done, but pull request #1 is still open"
    assert drifted_item.status_and_drift_css_class == "status-done has-drift"


@pytest.mark.parametrize("status", list(ItemStatus))
def test_the_dashboard_styles_every_status_css_class(status):
    """
    A status value holds spaces, so the class is built from the member's name, and the
    stylesheet has to know that name.
    """
    item = Item(title="A", branch="a", track="track-1", status=status)
    template = (PackageLocation.TEMPLATES / "dashboard.html").read_text()
    assert f".item.{item.status_and_drift_css_class} " in template


def test_is_ready_to_unblock_dependents_true_when_done():
    done_item = Item(title="A", branch="a", track="track-1", status=ItemStatus.DONE)
    assert done_item.is_ready_to_unblock_dependents()


def test_is_ready_to_unblock_dependents_true_when_open_and_ready_for_review():
    open_item = Item(
        title="A", branch="a", track="track-1", status=ItemStatus.IN_PROGRESS
    )
    open_item.live_state = LiveState.OPEN_READY
    assert open_item.is_ready_to_unblock_dependents()


def test_is_ready_to_unblock_dependents_false_while_still_a_draft():
    draft_item = Item(
        title="A", branch="a", track="track-1", status=ItemStatus.IN_PROGRESS
    )
    draft_item.live_state = LiveState.OPEN_DRAFT
    assert not draft_item.is_ready_to_unblock_dependents()


def test_is_ready_to_unblock_dependents_false_when_not_started():
    fresh_item = Item(
        title="A", branch="a", track="track-1", status=ItemStatus.NOT_STARTED
    )
    assert not fresh_item.is_ready_to_unblock_dependents()


def test_is_ready_for_dependent_review_true_while_still_a_draft():
    draft_item = Item(
        title="A", branch="a", track="track-1", status=ItemStatus.IN_PROGRESS
    )
    draft_item.live_state = LiveState.OPEN_DRAFT
    assert draft_item.is_ready_for_dependent_review()


def test_is_ready_for_dependent_review_true_when_merged():
    merged_item = Item(
        title="A", branch="a", track="track-1", status=ItemStatus.IN_PROGRESS
    )
    merged_item.live_state = LiveState.MERGED
    assert merged_item.is_ready_for_dependent_review()


def test_is_ready_for_dependent_review_true_when_done_without_a_pull_request():
    done_item = Item(title="A", branch="a", track="track-1", status=ItemStatus.DONE)
    assert done_item.is_ready_for_dependent_review()


def test_is_ready_for_dependent_review_false_when_there_is_no_pull_request():
    fresh_item = Item(
        title="A", branch="a", track="track-1", status=ItemStatus.NOT_STARTED
    )
    assert not fresh_item.is_ready_for_dependent_review()


def test_plan_repository_url():
    plan = Plan(
        id="p",
        title="P",
        description="d",
        default_repository="owner/repo",
        waves=[],
        tracks=[],
        items=[],
    )
    assert plan.repository_url == "https://github.com/owner/repo"


def test_plan_from_mapping_reads_optional_wave_description():
    plan = Plan.from_mapping(
        minimal_plan(
            waves=[
                {
                    ManifestKey.IDENTIFIER.key: "wave-1",
                    ManifestKey.NAME.key: "Wave 1",
                    ManifestKey.DESCRIPTION.key: "why",
                }
            ]
        )
    )
    assert plan.waves[0].description == "why"


def test_plan_from_mapping_defaults_missing_wave_description_to_none():
    plan = Plan.from_mapping(minimal_plan())
    assert plan.waves[0].description is None


def test_plan_from_mapping_ignores_an_unexpected_wave_key_instead_of_crashing():
    plan = Plan.from_mapping(
        minimal_plan(
            waves=[
                {
                    ManifestKey.IDENTIFIER.key: "wave-1",
                    ManifestKey.NAME.key: "Wave 1",
                    "future_field": "unused",
                }
            ]
        )
    )
    assert plan.waves[0].id == "wave-1"


def test_plan_from_mapping_ignores_an_unexpected_track_key_instead_of_crashing():
    plan = Plan.from_mapping(
        minimal_plan(
            tracks=[
                {
                    ManifestKey.IDENTIFIER.key: "track-1",
                    ManifestKey.NAME.key: "Track 1",
                    ManifestKey.WAVE.key: "wave-1",
                    "future_field": "unused",
                }
            ]
        )
    )
    assert plan.tracks[0].id == "track-1"


def test_item_from_mapping_keeps_an_http_session_url():
    plan = Plan.from_mapping(
        minimal_plan(
            items=[manifest_item("a", session="https://claude.ai/code/session/abc")]
        )
    )
    assert plan.items[0].session == "https://claude.ai/code/session/abc"


def test_item_from_mapping_rejects_a_non_http_session_url():
    plan = Plan.from_mapping(
        minimal_plan(items=[manifest_item("a", session="javascript:alert(1)")])
    )
    assert plan.items[0].session is None


def test_item_from_mapping_reads_required_and_optional_fields():
    item_instance = Item.from_mapping(
        manifest_item(
            "a",
            title="Item A",
            status=ItemStatus.IN_PROGRESS.value,
            pull_request_number=7,
            repository="owner/other-repo",
            notes="  some notes  ",
            depends_on=["b"],
            blockers=["waiting on design review"],
        )
    )
    assert item_instance.id == "a"
    assert item_instance.title == "Item A"
    assert item_instance.branch == "a"
    assert item_instance.track == "track-1"
    assert item_instance.status is ItemStatus.IN_PROGRESS
    assert item_instance.pull_request_number == 7
    assert item_instance.repository == "owner/other-repo"
    assert item_instance.notes == "some notes"
    assert item_instance.depends_on == ["b"]
    assert item_instance.blockers == ["waiting on design review"]


def test_item_from_mapping_defaults_every_optional_field_when_omitted():
    item_instance = Item.from_mapping(manifest_item("a", id=None, title="Item A"))
    assert item_instance.id is None
    assert item_instance.pull_request_number is None
    assert item_instance.repository is None
    assert item_instance.session is None
    assert item_instance.notes is None
    assert item_instance.depends_on == []
    assert item_instance.blockers == []
