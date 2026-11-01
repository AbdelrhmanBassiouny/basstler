"""
Tests for plan/size_limits.py: the limits every plan document and every pull request's
progress notes are held to.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from basstler.plan.model import PlanDocument
from basstler.plan.model import ItemStatus, ManifestKey, PlanManifest
from basstler.plan.size_limits import (
    DocumentLocation,
    DocumentOverLimitError,
    DocumentPart,
    ItemLocation,
    LimitedDocument,
    Measure,
    Plan,
    PlanFiles,
    ProgressNotes,
    Roadmap,
    RoadmapEntryLocation,
    RoadmapFormatViolation,
    RoadmapLine,
    SizeViolation,
    StagedPlan,
    Violation,
    WholePartLocation,
)

from ..constants.paths import DatasetLocation
from ..plan_dataset import LandedItemsPlan


def destination_in(directory: Path) -> PlanFiles:
    """
    :return: Where a staged plan lands inside *directory*.
    """
    plan_directory = directory / "plan"
    return PlanFiles(
        plan_directory / PlanDocument.MANIFEST, plan_directory / PlanDocument.ROADMAP
    )


def manifest_with_open_item_fields(**fields: object) -> PlanManifest:
    """
    :return: The landed-items plan with *fields* set on its open item.
    """
    plan = LandedItemsPlan.read()
    open_item = plan.item_with_status(ItemStatus.IN_PROGRESS)
    items = [
        {**item.content, **fields} if item == open_item else item.content
        for item in plan.manifest.items
    ]
    return PlanManifest({**plan.manifest.content, ManifestKey.ITEMS.key: items})


def manifest_violations(manifest: PlanManifest) -> list[Violation]:
    """
    :return: Every limit *manifest* breaks, measured beside a roadmap that breaks none.
    """
    roadmap = Roadmap.from_text(DatasetLocation.ROADMAP_OF_STANDING_RULES.read_text())
    return Plan(manifest, roadmap).manifest_violations()


def saved_plan_with_over_limit_open_item(directory: Path) -> PlanFiles:
    """
    :return: The files of a plan already saved in *directory*, whose open item is over
        the notes limit.
    """
    saved = destination_in(directory)
    saved.manifest.parent.mkdir(parents=True)
    over_limit = manifest_with_open_item_fields(
        notes="x" * (Measure.NOTE_LENGTH.maximum + 1)
    )
    over_limit.without_landed_items().write(saved.manifest)
    saved.roadmap.write_text(DatasetLocation.ROADMAP_OF_STANDING_RULES.read_text())
    return saved


def edited_copy_of(saved: PlanFiles, directory: Path, **fields: object) -> PlanFiles:
    """
    :param fields: Fields to set on the queued item of the copy.
    :return: The files of *saved* with *fields* set on its not-started item.
    """
    manifest = PlanManifest.from_file(saved.manifest)
    queued = LandedItemsPlan(manifest).item_with_status(ItemStatus.NOT_STARTED)
    items = [
        {**item.content, **fields} if item == queued else item.content
        for item in manifest.items
    ]
    copy = PlanFiles(directory / "plan.yaml", directory / "roadmap.md")
    directory.mkdir()
    PlanManifest({**manifest.content, ManifestKey.ITEMS.key: items}).write(
        copy.manifest
    )
    copy.roadmap.write_text(saved.roadmap.read_text())
    return copy


def open_item_location() -> DocumentLocation:
    """
    :return: Where the open item's quantities are counted.
    """
    open_item = LandedItemsPlan.read().item_with_status(ItemStatus.IN_PROGRESS)
    return ItemLocation(open_item.identifier)


# %% pruning landed items


def test_pruning_removes_only_the_landed_items():
    plan = LandedItemsPlan.read()
    pruned = plan.manifest.without_landed_items()
    assert pruned.items == [
        plan.item_with_status(ItemStatus.IN_PROGRESS).without_dependencies(
            plan.manifest.landed_identifiers
        ),
        plan.item_with_status(ItemStatus.NOT_STARTED).without_dependencies(
            plan.manifest.landed_identifiers
        ),
    ]


def test_pruning_drops_every_dependency_on_a_landed_item():
    plan = LandedItemsPlan.read()
    pruned = plan.manifest.without_landed_items()
    open_item = plan.item_with_status(ItemStatus.IN_PROGRESS)
    assert [item.dependencies for item in pruned.items] == [[], [open_item.identifier]]


def test_pruning_keeps_every_other_field_of_a_remaining_item():
    plan = LandedItemsPlan.read()
    original = plan.item_with_status(ItemStatus.IN_PROGRESS)
    remaining = plan.manifest.without_landed_items().item_named(original.identifier)
    assert {**remaining.content, ManifestKey.DEPENDS_ON.key: None} == {
        **original.content,
        ManifestKey.DEPENDS_ON.key: None,
    }


def test_staging_writes_the_plan_without_its_landed_items(tmp_path):
    destination = destination_in(tmp_path)
    staged = PlanFiles(
        DatasetLocation.PLAN_WITH_LANDED_ITEMS,
        DatasetLocation.ROADMAP_OF_STANDING_RULES,
    ).stage(destination)
    assert staged == StagedPlan.SAVED
    assert PlanManifest.from_file(destination.manifest) == (
        LandedItemsPlan.read().manifest.without_landed_items()
    )
    assert (
        destination.roadmap.read_text()
        == DatasetLocation.ROADMAP_OF_STANDING_RULES.read_text()
    )


def test_staging_a_plan_with_nothing_landed_copies_its_text_unchanged(tmp_path):
    first = destination_in(tmp_path / "first")
    PlanFiles(
        DatasetLocation.PLAN_WITH_LANDED_ITEMS,
        DatasetLocation.ROADMAP_OF_STANDING_RULES,
    ).stage(first)
    second = destination_in(tmp_path / "second")
    PlanFiles(first.manifest, first.roadmap).stage(second)
    assert second.manifest.read_text() == first.manifest.read_text()


def test_staging_a_plan_with_every_item_landed_removes_its_directory(tmp_path):
    destination = destination_in(tmp_path)
    destination.manifest.parent.mkdir()
    destination.manifest.write_text("stale\n")
    staged = PlanFiles(
        DatasetLocation.PLAN_ALL_LANDED, DatasetLocation.ROADMAP_OF_STANDING_RULES
    ).stage(destination)
    assert staged == StagedPlan.REMOVED
    assert not destination.manifest.parent.exists()


def test_staging_refuses_a_plan_over_its_limits_and_writes_nothing(tmp_path):
    destination = destination_in(tmp_path)
    with pytest.raises(DocumentOverLimitError) as raised:
        PlanFiles(
            DatasetLocation.PLAN_WITH_LANDED_ITEMS,
            DatasetLocation.ROADMAP_WITH_DATED_SECTION,
        ).stage(destination)
    assert raised.value.document == LimitedDocument.PLAN
    assert not destination.manifest.parent.exists()


def test_staging_saves_an_edit_to_another_item_when_an_unchanged_item_is_over_its_limit(
    tmp_path,
):
    saved = saved_plan_with_over_limit_open_item(tmp_path / "saved")
    edited = edited_copy_of(saved, tmp_path / "edited", notes="Waits for review.")
    assert edited.stage(saved) == StagedPlan.SAVED
    assert PlanManifest.from_file(saved.manifest) == PlanManifest.from_file(
        edited.manifest
    )


def test_staging_refuses_an_item_over_its_limit_that_the_edit_changes(tmp_path):
    saved = saved_plan_with_over_limit_open_item(tmp_path / "saved")
    stored = PlanManifest.from_file(saved.manifest)
    edited = edited_copy_of(
        saved, tmp_path / "edited", notes="y" * (Measure.NOTE_LENGTH.maximum + 1)
    )
    with pytest.raises(DocumentOverLimitError) as raised:
        edited.stage(saved)
    assert raised.value.document == LimitedDocument.PLAN
    assert PlanManifest.from_file(saved.manifest) == stored


def test_an_unchanged_item_over_its_limit_is_a_warning_not_a_violation():
    stored = manifest_with_open_item_fields(
        notes="x" * (Measure.NOTE_LENGTH.maximum + 1)
    )
    roadmap = Roadmap.from_text(DatasetLocation.ROADMAP_OF_STANDING_RULES.read_text())
    plan = Plan(stored, roadmap, stored_manifest=stored)
    assert plan.violations() == []
    assert plan.warnings() == [
        SizeViolation(
            Measure.NOTE_LENGTH,
            open_item_location(),
            Measure.NOTE_LENGTH.maximum + 1,
        )
    ]


def test_an_item_the_stored_plan_lacks_is_held_to_its_limits():
    measured = Measure.NOTE_LENGTH.maximum + 1
    manifest = manifest_with_open_item_fields(notes="x" * measured)
    roadmap = Roadmap.from_text(DatasetLocation.ROADMAP_OF_STANDING_RULES.read_text())
    plan = Plan(manifest, roadmap, stored_manifest=PlanManifest({}))
    assert plan.warnings() == []
    assert plan.violations() == [
        SizeViolation(Measure.NOTE_LENGTH, open_item_location(), measured)
    ]


# %% manifest limits


def test_a_manifest_within_every_limit_has_no_violations():
    assert manifest_violations(LandedItemsPlan.read().manifest) == []


def test_notes_one_character_over_the_limit_are_a_violation():
    measured = Measure.NOTE_LENGTH.maximum + 1
    manifest = manifest_with_open_item_fields(notes="x" * measured)
    assert manifest_violations(manifest) == [
        SizeViolation(Measure.NOTE_LENGTH, open_item_location(), measured)
    ]


def test_notes_are_measured_with_their_line_folding_undone():
    words = "word " * (Measure.NOTE_LENGTH.maximum // len("word "))
    manifest = manifest_with_open_item_fields(notes=words.replace(" ", "\n   "))
    assert manifest_violations(manifest) == []


def test_too_many_blockers_are_a_violation():
    measured = Measure.BLOCKER_COUNT.maximum + 1
    manifest = manifest_with_open_item_fields(blockers=["waits"] * measured)
    assert manifest_violations(manifest) == [
        SizeViolation(Measure.BLOCKER_COUNT, open_item_location(), measured)
    ]


def test_a_long_blocker_is_a_violation():
    measured = Measure.BLOCKER_LENGTH.maximum + 1
    manifest = manifest_with_open_item_fields(blockers=["x" * measured])
    assert manifest_violations(manifest) == [
        SizeViolation(Measure.BLOCKER_LENGTH, open_item_location(), measured)
    ]


def test_too_many_items_are_a_violation():
    plan = LandedItemsPlan.read()
    template = plan.item_with_status(ItemStatus.NOT_STARTED).content
    measured = Measure.ITEM_COUNT.maximum + 1
    items = [
        {**template, ManifestKey.IDENTIFIER.key: f"item-{number}"}
        for number in range(measured)
    ]
    oversized = PlanManifest({**plan.manifest.content, ManifestKey.ITEMS.key: items})
    assert manifest_violations(oversized) == [
        SizeViolation(
            Measure.ITEM_COUNT, WholePartLocation(DocumentPart.PLAN), measured
        )
    ]


# %% roadmap shape


def test_a_roadmap_of_entries_reads_each_entry_whole():
    text = DatasetLocation.ROADMAP_OF_STANDING_RULES.read_text()
    roadmap = Roadmap.from_text(text)
    entry_lines = [
        line for line in text.splitlines() if re.match(RoadmapLine.ENTRY, line)
    ]
    assert len(roadmap.entries) == len(entry_lines)
    assert roadmap.violations() == []


def test_a_continuation_line_joins_the_entry_above_it():
    text = DatasetLocation.ROADMAP_OF_STANDING_RULES.read_text()
    roadmap = Roadmap.from_text(text)
    assert "\n" not in roadmap.entries[-1]
    assert roadmap.entries[-1].endswith(text.splitlines()[-1].strip())


def test_a_dated_section_is_refused_as_a_format_violation():
    roadmap = Roadmap.from_text(DatasetLocation.ROADMAP_WITH_DATED_SECTION.read_text())
    assert [type(violation) for violation in roadmap.violations()] == [
        RoadmapFormatViolation
    ]


def test_too_many_roadmap_entries_are_a_violation():
    measured = Measure.ROADMAP_ENTRY_COUNT.maximum + 1
    roadmap = Roadmap.from_text("# plan\n" + "- a rule\n" * measured)
    assert roadmap.violations() == [
        SizeViolation(
            Measure.ROADMAP_ENTRY_COUNT,
            WholePartLocation(DocumentPart.ROADMAP),
            measured,
        )
    ]


def test_a_long_roadmap_entry_is_a_violation():
    measured = Measure.ROADMAP_ENTRY_LENGTH.maximum + 1
    roadmap = Roadmap.from_text("# plan\n- " + "x" * measured + "\n")
    assert roadmap.violations() == [
        SizeViolation(
            Measure.ROADMAP_ENTRY_LENGTH,
            RoadmapEntryLocation(1),
            measured,
        )
    ]


# %% progress notes


def test_progress_notes_within_the_limit_have_no_violations():
    assert ProgressNotes("x" * Measure.PROGRESS_LENGTH.maximum).violations() == []


def test_progress_notes_over_the_limit_are_a_violation(tmp_path):
    measured = Measure.PROGRESS_LENGTH.maximum + 1
    progress_path = tmp_path / "progress.md"
    progress_path.write_text("x" * measured)
    with pytest.raises(DocumentOverLimitError) as raised:
        ProgressNotes.from_file(progress_path).check()
    assert raised.value == DocumentOverLimitError(
        LimitedDocument.PROGRESS_NOTES,
        [
            SizeViolation(
                Measure.PROGRESS_LENGTH,
                WholePartLocation(DocumentPart.PROGRESS_NOTES),
                measured,
            )
        ],
    )
