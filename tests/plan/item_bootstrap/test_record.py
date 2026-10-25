"""
Tests for recording an item in its plan.
"""

from __future__ import annotations

import pytest

from basstler.plan.item_bootstrap.exceptions import (
    IncompleteNewItemError,
    PlanSaveRefusedError,
    UnknownPlanError,
)
from basstler.plan.item_bootstrap.vocabulary import PlanItemBootstrapExitCode
from basstler.plan.model import (
    ItemStatus,
    ManifestKey,
    PlanDocument,
)
from basstler.plan.size_limits import (
    Roadmap,
)

from ...scratch_repository import ScratchRepository
from .bootstrap_scenario import (
    NEW_ITEM,
    PLAN_MANIFEST,
    PLAN_ROADMAP,
    an_entry_over_the_length_limit,
    manifest_line,
    published_plan,
    record_request,
    the_length_violation_of,
)

# %% recording an item


def test_recording_an_existing_item_sets_its_status(
    bootstrap_repository: ScratchRepository,
):
    result = record_request(bootstrap_repository).record(
        project_root=bootstrap_repository.project_root
    )

    assert result.exit_code is PlanItemBootstrapExitCode.SUCCESS
    published = published_plan(bootstrap_repository)
    assert (
        manifest_line(ManifestKey.STATUS, ItemStatus.IN_PROGRESS.value)
        in published[PlanDocument.MANIFEST]
    )


def test_recording_leaves_every_other_manifest_line_byte_identical(
    bootstrap_repository: ScratchRepository,
):
    record_request(bootstrap_repository).record(
        project_root=bootstrap_repository.project_root
    )

    expected = PLAN_MANIFEST.replace(
        manifest_line(ManifestKey.STATUS, ItemStatus.NOT_STARTED.value),
        manifest_line(ManifestKey.STATUS, ItemStatus.IN_PROGRESS.value),
        1,
    )
    assert published_plan(bootstrap_repository)[PlanDocument.MANIFEST] == expected


def test_recording_appends_the_roadmap_entry_without_rewriting_the_roadmap(
    bootstrap_repository: ScratchRepository,
):
    entry = "A rule the item settled,\nwritten over two lines."
    record_request(bootstrap_repository, roadmap_entry=entry).record(
        project_root=bootstrap_repository.project_root
    )

    roadmap = published_plan(bootstrap_repository)[PlanDocument.ROADMAP]
    assert roadmap == record_request(
        bootstrap_repository, roadmap_entry=entry
    ).roadmap_after(PLAN_ROADMAP)
    assert Roadmap.from_text(roadmap).entries[-1] == " ".join(entry.split())


def test_recording_without_a_roadmap_entry_leaves_the_roadmap_untouched(
    bootstrap_repository: ScratchRepository,
):
    record_request(bootstrap_repository).record(
        project_root=bootstrap_repository.project_root
    )

    assert published_plan(bootstrap_repository)[PlanDocument.ROADMAP] == PLAN_ROADMAP


def test_a_refused_save_carries_the_reason_the_plan_save_gave(
    bootstrap_repository: ScratchRepository,
):
    entry = an_entry_over_the_length_limit()

    with pytest.raises(PlanSaveRefusedError) as refusal:
        record_request(bootstrap_repository, roadmap_entry=entry).record(
            project_root=bootstrap_repository.project_root
        )

    assert str(the_length_violation_of(entry)) in refusal.value.detail


def test_a_refused_save_leaves_the_published_plan_untouched(
    bootstrap_repository: ScratchRepository,
):
    request = record_request(
        bootstrap_repository, roadmap_entry=an_entry_over_the_length_limit()
    )

    with pytest.raises(PlanSaveRefusedError):
        request.record(project_root=bootstrap_repository.project_root)

    assert published_plan(bootstrap_repository) == {
        PlanDocument.MANIFEST: PLAN_MANIFEST,
        PlanDocument.ROADMAP: PLAN_ROADMAP,
    }


def test_recording_a_new_item_appends_it_to_the_manifest(
    bootstrap_repository: ScratchRepository,
):
    record_request(
        bootstrap_repository,
        item_identifier=NEW_ITEM,
        title="A brand new item",
        track="a-track",
        status=ItemStatus.NOT_STARTED,
    ).record(project_root=bootstrap_repository.project_root)

    manifest = published_plan(bootstrap_repository)[PlanDocument.MANIFEST]
    assert manifest.startswith(PLAN_MANIFEST)
    assert manifest.endswith(
        ManifestKey.IDENTIFIER.render(NEW_ITEM, opening_the_item=True)
        + manifest_line(ManifestKey.TITLE, "A brand new item")
        + manifest_line(ManifestKey.BRANCH, None)
        + manifest_line(ManifestKey.TRACK, "a-track")
        + manifest_line(ManifestKey.DEPENDS_ON, ())
        + manifest_line(ManifestKey.STATUS, ItemStatus.NOT_STARTED.value)
    )


def test_recording_a_new_item_without_a_title_names_the_key_it_needs(
    bootstrap_repository: ScratchRepository,
):
    with pytest.raises(IncompleteNewItemError) as refusal:
        record_request(
            bootstrap_repository,
            item_identifier=NEW_ITEM,
            track="a-track",
            status=ItemStatus.NOT_STARTED,
        ).record(project_root=bootstrap_repository.project_root)

    assert refusal.value.missing_keys == (ManifestKey.TITLE,)


def test_recording_against_an_unknown_plan_is_refused(
    bootstrap_repository: ScratchRepository,
):
    with pytest.raises(UnknownPlanError) as refusal:
        record_request(bootstrap_repository, plan_identifier="no-such-plan").record(
            project_root=bootstrap_repository.project_root
        )

    assert refusal.value.plan_identifier == "no-such-plan"
