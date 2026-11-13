"""
Tests for plan/model.py: the statuses a plan's items carry.
"""

from __future__ import annotations

from pathlib import PureWindowsPath
from types import SimpleNamespace
from typing import Any

import pytest

from basstler.locations import ProjectLocation
from basstler.plan import model
from basstler.plan.model import (
    ItemStatus,
    ManifestKey,
    PlanDocument,
    PlanItem,
    PlanManifest,
)
from basstler.repository import Repository

from ..constants.paths import DatasetLocation
from .concurrent_edits import PLAN_IDENTIFIER
from ..fixture_plans import ForeignItemId, FixturePlanId, fixture_item, fixture_manifest
from ..manifest_builders import manifest_item, minimal_plan

# %% stored spelling


@pytest.mark.parametrize("status", list(ItemStatus))
def test_a_status_value_reads_as_words(status):
    """
    The value is what a page shows, so it is spelled as words rather than as an
    identifier.
    """
    assert "_" not in status.value


@pytest.mark.parametrize(
    ("underscore_spelling", "status"),
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


def test_a_manifest_read_from_yaml_text_equals_the_one_read_from_its_file(other_plan):
    """
    Parsing a manifest's text gives what reading its file gives.
    """
    path = DatasetLocation.PLANS / FixturePlanId.OTHER / PlanDocument.MANIFEST
    assert PlanManifest.from_yaml(path.read_text()) == other_plan


def test_an_empty_yaml_text_is_an_empty_manifest():
    """
    An empty ``plan.yaml`` parses to a manifest with no keys.
    """
    assert PlanManifest.from_yaml("") == PlanManifest({})


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


def test_an_item_without_an_id_is_identified_by_its_branch():
    """
    ``plan-schema.md``: an item's id defaults to its branch.
    """
    item = PlanItem({ManifestKey.BRANCH.key: "a-branch"})

    assert item.identifier == item.branch


# %% landed items


def landed_plan(**overrides: Any) -> PlanManifest:
    """
    :param overrides: Top-level keys to replace in the plan.
    :return: A plan with one landed item and one not started.
    """
    return PlanManifest(
        minimal_plan(
            items=[
                manifest_item("landed", status=ItemStatus.DONE.value),
                manifest_item("open"),
            ],
            **overrides,
        )
    )


def test_dropping_landed_items_counts_them():
    manifest = landed_plan()

    assert manifest.without_landed_items().landed_item_count == len(
        manifest.landed_identifiers
    )


def test_dropping_landed_items_adds_to_the_items_landed_before():
    manifest = landed_plan(landed_item_count=3)

    assert manifest.without_landed_items().landed_item_count == 3 + len(
        manifest.landed_identifiers
    )


def test_a_plan_with_nothing_landed_is_left_as_it_is():
    manifest = PlanManifest(minimal_plan())

    assert manifest.without_landed_items() == manifest


# %% paths on the notes branch


@pytest.mark.parametrize("document", list(PlanDocument))
def test_a_plan_document_path_is_slash_separated_on_windows(document, monkeypatch):
    """
    The path names a file in the notes branch's tree, which git spells with ``/`` on
    every platform; the plans directory is given as Windows would build it.
    """
    windows_plans = PureWindowsPath(*ProjectLocation.PLANS.parts)
    monkeypatch.setattr(model, "ProjectLocation", SimpleNamespace(PLANS=windows_plans))

    assert document.path_within_notes_branch(PLAN_IDENTIFIER) == (
        f"{ProjectLocation.PLANS.as_posix()}/{PLAN_IDENTIFIER}/{document}"
    )
