"""
Tests for plan/model.py: the statuses a plan's items carry.
"""

import pytest

from basstler.plan.model import ItemStatus, ManifestKey, PlanDocument, PlanManifest
from basstler.repository import Repository

from ..constants.paths import DatasetLocation
from ..fixture_plans import ForeignItemId, FixturePlanId, fixture_item, fixture_manifest

# %% stored spelling


@pytest.mark.parametrize("status", list(ItemStatus))
def test_a_status_value_reads_as_words(status):
    """
    The value is what a page shows, so it is spelled as words rather than as an
    identifier.
    """
    assert "_" not in status.value


@pytest.mark.parametrize(
    "underscore_spelling, status",
    [
        ("not_started", ItemStatus.NOT_STARTED),
        ("in_progress", ItemStatus.IN_PROGRESS),
    ],
)
def test_a_manifest_written_with_underscores_still_reads(underscore_spelling, status):
    """
    The literals are the spelling manifests were written in before the values took
    spaces, which is the data this reading exists for.
    """
    assert ItemStatus(underscore_spelling) is status


def test_an_unknown_status_is_still_refused():
    with pytest.raises(ValueError):
        ItemStatus("in-review")


# %% typed accessors


@pytest.fixture
def other_plan() -> PlanManifest:
    return PlanManifest.from_file(
        DatasetLocation.PLANS / FixturePlanId.OTHER / PlanDocument.MANIFEST
    )


def test_the_default_repository_is_parsed_into_a_repository(other_plan):
    declared = fixture_manifest(FixturePlanId.OTHER)[ManifestKey.DEFAULT_REPOSITORY.key]
    assert other_plan.default_repository == Repository.parse(declared)


def test_an_items_pull_request_number_is_the_number_the_manifest_declares(other_plan):
    declared = fixture_item(FixturePlanId.OTHER, ForeignItemId.READY)[
        ManifestKey.PULL_REQUEST_NUMBER.key
    ]
    assert other_plan.item_named(ForeignItemId.READY).pull_request_number == declared


def test_an_item_without_a_pull_request_has_no_pull_request_number(other_plan):
    assert other_plan.item_named(ForeignItemId.NOT_STARTED).pull_request_number is None


@pytest.fixture
def first_plan() -> PlanManifest:
    return PlanManifest.from_file(
        DatasetLocation.SITE_PLANS / "first-plan" / PlanDocument.MANIFEST
    )


def test_an_items_branch_is_the_branch_the_manifest_declares(first_plan):
    declared = [
        entry[ManifestKey.BRANCH.key]
        for entry in first_plan.content[ManifestKey.ITEMS.key]
        if entry[ManifestKey.IDENTIFIER.key] == "open-item"
    ]
    assert [first_plan.item_named("open-item").branch] == declared


def test_an_item_naming_no_repository_uses_the_default_repository(first_plan):
    item = first_plan.item_named("open-item")
    assert first_plan.repository_of(item) == first_plan.default_repository


def test_an_item_naming_its_own_repository_uses_it(first_plan):
    item = first_plan.item_named("elsewhere-item")
    declared = item.content[ManifestKey.REPOSITORY.key]
    assert first_plan.repository_of(item) == Repository.parse(declared)
