"""
Tests for :mod:`basstler.plan_validation`: every schema rule a plan.yaml must satisfy.
"""

from typing import Any

import pytest

from basstler.exceptions import (
    DependencyCycle,
    DuplicateItemId,
    InvalidBlockers,
    InvalidDependsOn,
    InvalidManifestRoot,
    InvalidSchemaVersion,
    MalformedDependencyReference,
    MissingPlanDirectory,
    PlanValidationError,
    SelfPlanReference,
    UnknownDependency,
    UnknownDependencyPlan,
    UnknownStatus,
    UnknownTrack,
    UnknownWave,
)
from basstler.plan_dependencies import (
    DependencyReference,
    PlanDirectory,
)
from basstler.plan_model import ItemStatus, ManifestKey
from basstler.plan_validation import PlanValidator

from .constants.paths import DatasetLocation
from .fixture_plans import (
    FixturePlanId,
    ForeignItemId,
    PLAN_UNDER_TEST_ID,
    foreign_reference,
)
from .manifest_builders import manifest_item, minimal_plan


# %% plan validation


def test_validation_accepts_a_well_formed_manifest():
    PlanValidator(minimal_plan()).validate()  # must not raise


def test_validation_rejects_wrong_schema_version():
    with pytest.raises(PlanValidationError) as error:
        PlanValidator(minimal_plan(schema_version=2)).validate()
    assert isinstance(error.value.problems[0], InvalidSchemaVersion)
    assert error.value.problems[0].actual_value == 2


def test_validation_rejects_duplicate_item_ids():
    items = [
        manifest_item("a"),
        manifest_item("a", title="A again", branch="a2"),
    ]
    with pytest.raises(PlanValidationError) as error:
        PlanValidator(minimal_plan(items=items)).validate()
    duplicate_problems = [
        p for p in error.value.problems if isinstance(p, DuplicateItemId)
    ]
    assert duplicate_problems == [DuplicateItemId(["a"])]


def test_validation_rejects_unknown_track():
    items = [manifest_item("a", track="no-such-track")]
    with pytest.raises(PlanValidationError) as error:
        PlanValidator(minimal_plan(items=items)).validate()
    assert any(isinstance(problem, UnknownTrack) for problem in error.value.problems)


def test_validation_rejects_unknown_wave():
    tracks = [
        {
            ManifestKey.IDENTIFIER.key: "track-1",
            ManifestKey.NAME.key: "Track 1",
            ManifestKey.WAVE.key: "no-such-wave",
        }
    ]
    with pytest.raises(PlanValidationError) as error:
        PlanValidator(minimal_plan(tracks=tracks)).validate()
    assert any(isinstance(problem, UnknownWave) for problem in error.value.problems)


def test_validation_rejects_unknown_depends_on():
    items = [manifest_item("a", depends_on=["ghost"])]
    with pytest.raises(PlanValidationError) as error:
        PlanValidator(minimal_plan(items=items)).validate()
    assert any(
        isinstance(problem, UnknownDependency) for problem in error.value.problems
    )


def test_validation_rejects_depends_on_that_is_not_a_list():
    # A plain string is iterable char-by-char - must be rejected outright,
    # not silently misinterpreted as a list of one-character dependencies.
    items = [manifest_item("a", depends_on="b")]
    with pytest.raises(PlanValidationError) as error:
        PlanValidator(minimal_plan(items=items)).validate()
    assert any(
        isinstance(problem, InvalidDependsOn) for problem in error.value.problems
    )


def test_validation_rejects_blockers_that_is_not_a_list():
    # A plain string is iterable char-by-char - must be rejected outright,
    # not silently misinterpreted as one blocker per character.
    items = [manifest_item("a", blockers="some prose describing the blocker")]
    with pytest.raises(PlanValidationError) as error:
        PlanValidator(minimal_plan(items=items)).validate()
    assert any(isinstance(problem, InvalidBlockers) for problem in error.value.problems)


def test_validation_rejects_unknown_status():
    items = [manifest_item("a", status="in-review")]
    with pytest.raises(PlanValidationError) as error:
        PlanValidator(minimal_plan(items=items)).validate()
    assert any(isinstance(problem, UnknownStatus) for problem in error.value.problems)


@pytest.mark.parametrize("status", ["in_progress", ItemStatus.IN_PROGRESS.value])
def test_validation_accepts_a_status_in_either_spelling(status):
    """
    ``in_progress`` is the spelling manifests were written in before the values took
    spaces, and stays readable beside the current one.
    """
    items = [
        {"id": "a", "title": "A", "branch": "a", "track": "track-1", "status": status}
    ]
    PlanValidator(minimal_plan(items=items)).validate()


def test_validation_collects_every_problem_not_just_the_first():
    with pytest.raises(PlanValidationError) as error:
        PlanValidator(minimal_plan(schema_version=2, tracks=[])).validate()
    problem_types = {type(problem) for problem in error.value.problems}
    assert InvalidSchemaVersion in problem_types
    assert UnknownTrack in problem_types


def test_plan_validation_error_message_joins_every_problem_description():
    with pytest.raises(PlanValidationError) as error:
        PlanValidator(minimal_plan(schema_version=2)).validate()
    assert str(error.value) == "schema_version must be 1, got 2"


def test_validation_rejects_an_empty_manifest_instead_of_crashing():
    # yaml.safe_load returns None for an empty file - PlanValidator must
    # report this as a PlanValidationError, not crash with an AttributeError
    # from calling .get() on None.
    with pytest.raises(PlanValidationError) as error:
        PlanValidator(None).validate()
    assert isinstance(error.value.problems[0], InvalidManifestRoot)
    assert error.value.problems[0].actual_value is None


def test_validation_rejects_a_non_mapping_manifest_instead_of_crashing():
    with pytest.raises(PlanValidationError) as error:
        PlanValidator(["not", "a", "mapping"]).validate()
    assert isinstance(error.value.problems[0], InvalidManifestRoot)


def test_validation_rejects_a_same_track_dependency_cycle():
    # A same-track cycle (a depends on b, b depends on a) must not pass
    # validation - without this check the cycle silently drops both items
    # (and anything depending on them) out of the rendered track later, with
    # no indication data was lost.
    items = [
        manifest_item("a", depends_on=["b"]),
        manifest_item("b", depends_on=["a"]),
    ]
    with pytest.raises(PlanValidationError) as error:
        PlanValidator(minimal_plan(items=items)).validate()
    assert error.value.problems == [DependencyCycle(["a", "b", "a"])]


def test_validation_rejects_an_item_depending_on_itself():
    items = [manifest_item("a", depends_on=["a"])]
    with pytest.raises(PlanValidationError) as error:
        PlanValidator(minimal_plan(items=items)).validate()
    assert error.value.problems == [DependencyCycle(["a", "a"])]


def test_validation_reports_a_cycle_from_its_earliest_listed_item():
    # The walk may enter the cycle anywhere; the report starts where the
    # manifest does, so it reads the same however the search ran.
    items = [
        manifest_item("a", depends_on=["c"]),
        manifest_item("b", depends_on=["a"]),
        manifest_item("c", depends_on=["b"]),
    ]
    with pytest.raises(PlanValidationError) as error:
        PlanValidator(minimal_plan(items=items)).validate()
    assert error.value.problems == [DependencyCycle(["a", "c", "b", "a"])]


def test_validation_accepts_a_dependency_chain_without_a_cycle():
    items = [
        manifest_item("a"),
        manifest_item("b", depends_on=["a"]),
        manifest_item("c", depends_on=["a", "b"]),
    ]
    PlanValidator(minimal_plan(items=items)).validate()  # must not raise


# %% cross-plan references - validation


def plan_depending_on(dependency_text: str) -> dict[str, Any]:
    """
    A one-item manifest whose single item depends on *dependency_text*.

    :param dependency_text: The one entry of that item's ``depends_on``.
    """
    return minimal_plan(
        items=[
            manifest_item("a", depends_on=[dependency_text]),
        ]
    )


def test_validation_accepts_a_reference_into_another_plan():
    PlanValidator(
        plan_depending_on(foreign_reference(ForeignItemId.READY)),
        PlanDirectory(DatasetLocation.PLANS),
    ).validate()


def test_validation_rejects_an_unknown_plan():
    with pytest.raises(PlanValidationError) as error:
        PlanValidator(
            plan_depending_on(
                foreign_reference(ForeignItemId.READY, FixturePlanId.ABSENT)
            ),
            PlanDirectory(DatasetLocation.PLANS),
        ).validate()
    assert error.value.problems == [
        UnknownDependencyPlan(
            "a", foreign_reference(ForeignItemId.READY, FixturePlanId.ABSENT)
        )
    ]


def test_validation_rejects_an_unknown_item_in_a_known_plan():
    with pytest.raises(PlanValidationError) as error:
        PlanValidator(
            plan_depending_on(foreign_reference(ForeignItemId.ABSENT)),
            PlanDirectory(DatasetLocation.PLANS),
        ).validate()
    assert error.value.problems == [
        UnknownDependency("a", foreign_reference(ForeignItemId.ABSENT))
    ]


def test_validation_rejects_a_reference_to_the_plans_own_id():
    # One item, one spelling: the bare id already names it, so the qualified
    # form would be a second way to write the same edge. Two items, so the
    # rejected spelling is the only thing wrong with the manifest - an item
    # qualifying its own id would also be a self-dependency.
    own_reference = foreign_reference("a", PLAN_UNDER_TEST_ID)
    plan = minimal_plan(
        items=[
            manifest_item("a"),
            manifest_item("b", depends_on=[own_reference]),
        ]
    )
    with pytest.raises(PlanValidationError) as error:
        PlanValidator(plan, PlanDirectory(DatasetLocation.PLANS)).validate()
    assert error.value.problems == [SelfPlanReference("b", own_reference)]


def test_validation_rejects_a_malformed_reference():
    malformed = DependencyReference.separator.join(
        [FixturePlanId.OTHER, ManifestKey.WAVE.key, ForeignItemId.READY]
    )
    with pytest.raises(PlanValidationError) as error:
        PlanValidator(
            plan_depending_on(malformed),
            PlanDirectory(DatasetLocation.PLANS),
        ).validate()
    assert error.value.problems == [MalformedDependencyReference("a", malformed)]


def test_validation_rejects_a_cross_plan_reference_with_no_plans_directory():
    # Passing it unchecked is the silent-ready fault this feature exists to
    # remove, so an unresolvable reference is refused instead.
    reference = foreign_reference(ForeignItemId.READY)
    with pytest.raises(PlanValidationError) as error:
        PlanValidator(plan_depending_on(reference)).validate()
    assert error.value.problems == [MissingPlanDirectory("a", reference)]


def test_validation_rejects_a_cycle_that_runs_through_another_plan():
    # other-plan's foreign-depending-back depends on test-plan/a, so this
    # closes a loop that neither manifest can see on its own.
    reference = foreign_reference(ForeignItemId.DEPENDING_BACK)
    with pytest.raises(PlanValidationError) as error:
        PlanValidator(
            plan_depending_on(reference),
            PlanDirectory(DatasetLocation.PLANS),
        ).validate()
    assert error.value.problems == [DependencyCycle(["a", reference, "a"])]
