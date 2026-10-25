"""
Tests for :mod:`basstler.plan_dependencies`: parsing a ``depends_on`` entry and
resolving it through a plans directory.
"""

import pytest

from basstler.plan_dependencies import (
    DependencyReference,
    PlanDirectory,
    UnresolvedDependency,
)
from basstler.plan_model import ManifestKey

from .constants.paths import DatasetLocation
from .fixture_plans import (
    FixturePlanId,
    ForeignItemId,
    fixture_manifest,
    fixture_repository,
    foreign_reference,
)


# %% cross-plan references - parsing


def test_dependency_reference_reads_a_bare_item_id():
    reference = DependencyReference.from_text("a")
    assert reference == DependencyReference(item_identifier="a")
    assert reference.names_another_plan is False


def test_dependency_reference_reads_a_plan_qualified_id():
    reference = DependencyReference.from_text(foreign_reference(ForeignItemId.READY))
    assert reference == DependencyReference(
        item_identifier=ForeignItemId.READY, plan_id=FixturePlanId.OTHER
    )
    assert reference.names_another_plan is True


@pytest.mark.parametrize(
    "reference",
    [
        DependencyReference(item_identifier="a"),
        DependencyReference(
            item_identifier=ForeignItemId.READY, plan_id=FixturePlanId.OTHER
        ),
    ],
)
def test_dependency_reference_text_round_trips(reference: DependencyReference):
    assert DependencyReference.from_text(reference.text) == reference


def test_dependency_reference_is_malformed_with_a_second_separator():
    # A third segment would have to mean something - a plan inside a plan - and
    # it means nothing, so it is refused rather than read as part of an id.
    reference = DependencyReference.from_text(
        DependencyReference.separator.join(
            [FixturePlanId.OTHER, ManifestKey.WAVE.key, ForeignItemId.READY]
        )
    )
    assert reference.is_well_formed is False


@pytest.mark.parametrize(
    "text",
    [
        f"{DependencyReference.separator}{ForeignItemId.READY}",
        f"{FixturePlanId.OTHER}{DependencyReference.separator}",
    ],
)
def test_dependency_reference_is_malformed_with_an_empty_half(text: str):
    assert DependencyReference.from_text(text).is_well_formed is False


# %% cross-plan references - the plans directory


def test_plan_directory_reads_one_plans_manifest_by_id():
    directory = PlanDirectory(DatasetLocation.PLANS)
    plan = directory.plan(FixturePlanId.OTHER)
    manifest = fixture_manifest(FixturePlanId.OTHER)
    assert plan.title == manifest[ManifestKey.TITLE.key]
    assert plan.default_repository == manifest[ManifestKey.DEFAULT_REPOSITORY.key]


def test_plan_directory_reads_no_manifest_nothing_has_named():
    # One plan's dashboard pulling in every other plan's contents is what the
    # per-plan size budget exists to prevent, so a plan nothing references is
    # never opened.
    directory = PlanDirectory(DatasetLocation.PLANS)
    directory.plan(FixturePlanId.OTHER)
    assert set(directory.plans_by_id) == {FixturePlanId.OTHER}


def test_plan_directory_resolves_an_item_by_reference():
    directory = PlanDirectory(DatasetLocation.PLANS)
    resolved = directory.resolve(
        DependencyReference.from_text(foreign_reference(ForeignItemId.READY))
    )
    assert resolved.item.identifier == ForeignItemId.READY
    assert resolved.plan.id == FixturePlanId.OTHER
    assert resolved.repository == fixture_repository(FixturePlanId.OTHER)


@pytest.mark.parametrize(
    "text",
    [
        foreign_reference(ForeignItemId.READY, FixturePlanId.ABSENT),
        foreign_reference(ForeignItemId.ABSENT),
    ],
)
def test_plan_directory_does_not_resolve_an_unknown_reference(text: str):
    directory = PlanDirectory(DatasetLocation.PLANS)
    resolved = directory.resolve(DependencyReference.from_text(text))
    assert resolved == UnresolvedDependency(
        reference=DependencyReference.from_text(text)
    )
