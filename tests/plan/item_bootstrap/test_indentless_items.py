"""
Tests for patching items written flush with their list.
"""

from __future__ import annotations

from basstler.plan.item_bootstrap.manifest_text import ManifestText
from basstler.plan.item_bootstrap.opening import WorkOpener
from basstler.plan.model import (
    ItemStatus,
    ManifestKey,
)

from ...scratch_repository import ScratchRepository
from .bootstrap_scenario import (
    EXISTING_ITEM,
    INDENTLESS_PLAN_MANIFEST,
    NEW_ITEM,
    PLAN_IDENTIFIER,
    PULL_REQUEST_NUMBER,
    SECOND_ITEM,
    STACKED_ITEM,
    RecordingPullRequestOpener,
    item_named,
    open_request,
    opened_item_fields,
    published_items,
    record_request,
    update_request,
)

# %% patching an item written flush with its list


def test_patching_an_item_written_indentless_reads_back_the_fields_it_wrote():
    patched = ManifestText.from_text(INDENTLESS_PLAN_MANIFEST).with_item_fields(
        PLAN_IDENTIFIER, EXISTING_ITEM, opened_item_fields()
    )

    item = item_named(patched, EXISTING_ITEM)
    assert {
        manifest_key: item[manifest_key.key] for manifest_key in opened_item_fields()
    } == opened_item_fields()


def test_patching_an_item_written_indentless_leaves_the_other_items_alone():
    patched = ManifestText.from_text(INDENTLESS_PLAN_MANIFEST).with_item_fields(
        PLAN_IDENTIFIER, EXISTING_ITEM, opened_item_fields()
    )

    assert item_named(patched, SECOND_ITEM) == item_named(
        INDENTLESS_PLAN_MANIFEST, SECOND_ITEM
    )


def test_updating_an_item_whose_dependencies_are_written_out_keeps_the_manifest_parsing(
    indentless_plan_repository: ScratchRepository,
):
    """
    A field inserted after a block sequence has to land at the item's own depth, or YAML
    reads a mapping key inside a scalar and refuses the document.
    """
    update_request(
        item_identifier=STACKED_ITEM,
        values_by_key={ManifestKey.STATUS: ItemStatus.BLOCKED},
    ).update(indentless_plan_repository.project_root)

    written = published_items(indentless_plan_repository)[STACKED_ITEM]
    assert written[ManifestKey.STATUS.key] == ItemStatus.BLOCKED
    assert (
        written[ManifestKey.DEPENDS_ON.key]
        == item_named(INDENTLESS_PLAN_MANIFEST, STACKED_ITEM)[
            ManifestKey.DEPENDS_ON.key
        ]
    )


def test_replacing_written_out_dependencies_replaces_their_entries(
    indentless_plan_repository: ScratchRepository,
):
    """
    Replacing the key's own line alone leaves its entries behind, where YAML reads them
    as a sequence belonging to whatever key replaced it.
    """
    update_request(
        item_identifier=STACKED_ITEM,
        values_by_key={ManifestKey.DEPENDS_ON: [SECOND_ITEM]},
    ).update(indentless_plan_repository.project_root)

    written = published_items(indentless_plan_repository)[STACKED_ITEM]
    assert written[ManifestKey.DEPENDS_ON.key] == [SECOND_ITEM]


def test_opening_an_item_written_indentless_publishes_the_fields_it_wrote(
    indentless_plan_repository: ScratchRepository,
):
    WorkOpener(indentless_plan_repository.project_root).open(
        open_request(),
        pull_request_opener=RecordingPullRequestOpener(number=PULL_REQUEST_NUMBER),
    )

    item = published_items(indentless_plan_repository)[EXISTING_ITEM]
    assert {
        manifest_key: item[manifest_key.key] for manifest_key in opened_item_fields()
    } == opened_item_fields()


def test_recording_a_new_item_in_an_indentless_plan_publishes_it(
    indentless_plan_repository: ScratchRepository,
):
    record_request(
        indentless_plan_repository,
        item_identifier=NEW_ITEM,
        title="A brand new item",
        track="a-track",
        status=ItemStatus.NOT_STARTED,
    ).record(project_root=indentless_plan_repository.project_root)

    item = published_items(indentless_plan_repository)[NEW_ITEM]
    assert item[ManifestKey.TITLE.key] == "A brand new item"
    assert item[ManifestKey.TRACK.key] == "a-track"
    assert item[ManifestKey.STATUS.key] == ItemStatus.NOT_STARTED
