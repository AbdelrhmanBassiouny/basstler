"""
Tests for setting an item's recorded fields.
"""

from __future__ import annotations

import pytest

from basstler.plan.item_bootstrap.documents import PlanDocuments
from basstler.plan.item_bootstrap.exceptions import (
    PlanNotWrittenError,
    UnknownItemError,
)
from basstler.plan.model import (
    ItemStatus,
    ManifestKey,
    PlanDocument,
)

from ...scratch_repository import ScratchRepository
from .bootstrap_scenario import (
    EXISTING_ITEM,
    LITERALLY_NOTED_ITEM,
    NEW_BRANCH,
    NEW_ITEM,
    PLAN_IDENTIFIER,
    PLAN_MANIFEST,
    PLAN_ROADMAP,
    SECOND_ITEM,
    SESSION_URL,
    entry_wrapping_across,
    published_items,
    published_plan,
    update_request,
)

# %% updating an item's recorded fields


def test_writing_a_note_replaces_the_folded_block_rather_than_its_first_line(
    bootstrap_repository: ScratchRepository,
):
    update_request(values_by_key={ManifestKey.NOTES: "What this run found."}).update(
        bootstrap_repository.project_root
    )

    assert published_items(bootstrap_repository)[EXISTING_ITEM][
        ManifestKey.NOTES.key
    ] == ("What this run found.\n")


def test_appending_to_a_note_keeps_the_recorded_paragraphs_apart(
    bootstrap_repository: ScratchRepository,
):
    """
    The recorded note comes back with one newline between paragraphs where the file a
    caller writes uses a blank line, so appending must restore the blank lines or the
    whole note collapses into a single paragraph.
    """
    update_request(
        values_by_key={ManifestKey.NOTES: "The first.\n\nThe second."}
    ).update(bootstrap_repository.project_root)

    update_request(notes_to_append="The third.\n").update(
        bootstrap_repository.project_root
    )

    assert published_items(bootstrap_repository)[EXISTING_ITEM][
        ManifestKey.NOTES.key
    ] == ("The first.\nThe second.\nThe third.\n")


def test_appending_to_a_literal_note_keeps_its_wrapped_lines_within_their_paragraph(
    indentless_plan_repository: ScratchRepository,
):
    """
    A literal block reads a hard-wrapped line back as a newline and a paragraph break as
    a blank line, the opposite of a folded one, so taking every newline for a paragraph
    break splits each wrapped line into a paragraph of its own.
    """
    update_request(
        item_identifier=LITERALLY_NOTED_ITEM, notes_to_append="The third.\n"
    ).update(indentless_plan_repository.project_root)

    assert published_items(indentless_plan_repository)[LITERALLY_NOTED_ITEM][
        ManifestKey.NOTES.key
    ] == (
        "The first paragraph, which its author wrapped by hand.\n"
        "The second paragraph.\n"
        "The third.\n"
    )


def test_appending_to_an_item_carrying_no_note_records_only_the_addition(
    bootstrap_repository: ScratchRepository,
):
    update_request(
        item_identifier=SECOND_ITEM, notes_to_append="The only paragraph.\n"
    ).update(bootstrap_repository.project_root)

    assert (
        published_items(bootstrap_repository)[SECOND_ITEM][ManifestKey.NOTES.key]
        == "The only paragraph.\n"
    )


def test_writing_a_note_leaves_the_other_items_byte_identical(
    bootstrap_repository: ScratchRepository,
):
    update_request(values_by_key={ManifestKey.NOTES: "What this run found."}).update(
        bootstrap_repository.project_root
    )

    published = published_plan(bootstrap_repository)[PlanDocument.MANIFEST]
    opener = ManifestKey.IDENTIFIER.render(SECOND_ITEM, opening_the_item=True)
    assert (
        published[published.index(opener) :]
        == PLAN_MANIFEST[PLAN_MANIFEST.index(opener) :]
    )


def test_writing_blockers_renders_them_as_a_sequence(
    bootstrap_repository: ScratchRepository,
):
    blockers = [
        "A short one.",
        "A blocker long enough that it has to fold over more than a single line of "
        "the manifest, which is what the sequence rendering has to get right.",
    ]
    update_request(values_by_key={ManifestKey.BLOCKERS: blockers}).update(
        bootstrap_repository.project_root
    )

    assert (
        published_items(bootstrap_repository)[EXISTING_ITEM][ManifestKey.BLOCKERS.key]
        == blockers
    )


@pytest.mark.parametrize(
    "unbreakable",
    [
        "claude/workflow-unification-setup-jgvs53",
        "https://example.invalid/a/single/path/segment/long/enough/that/it/cannot/fit/"
        "on/one/body/line/of/the/manifest/at/all",
    ],
    ids=["hyphenated-branch", "url-longer-than-a-line"],
)
def test_a_folded_entry_parses_back_as_the_text_it_was_given(
    bootstrap_repository: ScratchRepository, unbreakable: str
):
    """
    A line break inside a folded scalar comes back as a space, so wrapping is only
    lossless while it happens between words.
    """
    blocker = entry_wrapping_across(unbreakable)

    update_request(values_by_key={ManifestKey.BLOCKERS: [blocker]}).update(
        bootstrap_repository.project_root
    )

    assert published_items(bootstrap_repository)[EXISTING_ITEM][
        ManifestKey.BLOCKERS.key
    ] == [blocker]


def test_an_emptied_sequence_is_written_as_a_list_rather_than_as_nothing(
    bootstrap_repository: ScratchRepository,
):
    """
    A bare ``blockers:`` parses as null, not as an empty list.
    """
    update_request(values_by_key={ManifestKey.BLOCKERS: ["Something."]}).update(
        bootstrap_repository.project_root
    )

    update_request(values_by_key={ManifestKey.BLOCKERS: []}).update(
        bootstrap_repository.project_root
    )

    assert (
        published_items(bootstrap_repository)[EXISTING_ITEM][ManifestKey.BLOCKERS.key]
        == []
    )


def test_updating_sets_every_plain_field_it_is_given(
    bootstrap_repository: ScratchRepository,
):
    update_request(
        values_by_key={
            ManifestKey.STATUS: ItemStatus.BLOCKED,
            ManifestKey.BRANCH: NEW_BRANCH,
            ManifestKey.PULL_REQUEST_NUMBER: 57,
            ManifestKey.SESSION: SESSION_URL,
        }
    ).update(bootstrap_repository.project_root)

    item = published_items(bootstrap_repository)[EXISTING_ITEM]
    assert item[ManifestKey.STATUS.key] == ItemStatus.BLOCKED
    assert item[ManifestKey.BRANCH.key] == NEW_BRANCH
    assert item[ManifestKey.PULL_REQUEST_NUMBER.key] == 57
    assert item[ManifestKey.SESSION.key] == SESSION_URL


def test_updating_leaves_the_roadmap_untouched(bootstrap_repository: ScratchRepository):
    update_request(values_by_key={ManifestKey.STATUS: ItemStatus.BLOCKED}).update(
        bootstrap_repository.project_root
    )

    assert published_plan(bootstrap_repository)[PlanDocument.ROADMAP] == PLAN_ROADMAP


def test_updating_an_unknown_item_is_refused(bootstrap_repository: ScratchRepository):
    with pytest.raises(UnknownItemError):
        update_request(
            item_identifier=NEW_ITEM,
            values_by_key={ManifestKey.STATUS: ItemStatus.BLOCKED},
        ).update(bootstrap_repository.project_root)

    assert published_plan(bootstrap_repository)[PlanDocument.MANIFEST] == PLAN_MANIFEST


def test_updating_hands_the_dashboard_republish_back(
    bootstrap_repository: ScratchRepository,
):
    report = update_request(
        values_by_key={ManifestKey.STATUS: ItemStatus.BLOCKED}
    ).update(bootstrap_repository.project_root)

    assert report.dashboard_command == f"/plan-dashboard {PLAN_IDENTIFIER}"


def test_a_written_note_reports_how_many_paragraphs_it_became(
    bootstrap_repository: ScratchRepository,
):
    """
    A file's paragraphs are whatever its blank lines say they are, so a caller who meant
    several and wrote none can only find out from the report.
    """
    report = update_request(
        values_by_key={ManifestKey.NOTES: "One.\n\nTwo.\n\nThree."}
    ).update(bootstrap_repository.project_root)

    assert report.note_paragraphs == 3


def test_an_addition_wrapped_without_blank_lines_counts_as_the_one_paragraph_it_is(
    bootstrap_repository: ScratchRepository,
):
    """
    The fixture item already carries a note, so an addition meant as two paragraphs and
    written as one leaves two, not three.
    """
    report = update_request(
        notes_to_append="Meant as two paragraphs\nbut wrapped without a blank line."
    ).update(bootstrap_repository.project_root)

    assert report.note_paragraphs == 2


def test_a_write_that_sets_no_note_reports_no_paragraph_count(
    bootstrap_repository: ScratchRepository,
):
    report = update_request(
        values_by_key={ManifestKey.STATUS: ItemStatus.BLOCKED}
    ).update(bootstrap_repository.project_root)

    assert report.note_paragraphs is None


def test_a_save_the_notes_branch_does_not_carry_is_refused(
    bootstrap_repository: ScratchRepository,
):
    documents = PlanDocuments.load(PLAN_IDENTIFIER, bootstrap_repository.project_root)

    with pytest.raises(PlanNotWrittenError) as refusal:
        documents.confirm_written(
            {
                PlanDocument.MANIFEST: PLAN_MANIFEST,
                PlanDocument.ROADMAP: "a roadmap that was never saved\n",
            },
            bootstrap_repository.project_root,
        )

    assert refusal.value.documents == (PlanDocument.ROADMAP,)


def test_finishing_an_item_saves_the_plan_without_it(
    bootstrap_repository: ScratchRepository,
):
    update_request(values_by_key={ManifestKey.STATUS: ItemStatus.DONE.value}).update(
        bootstrap_repository.project_root
    )

    assert EXISTING_ITEM not in published_items(bootstrap_repository)
