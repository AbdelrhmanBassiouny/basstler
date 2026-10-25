"""
Tests for basstler.plan.item_bootstrap's operations: recording an item, opening its
work, updating its fields, checking it against local git, and resolving, blocking and
unblocking the items a branch carries.

Run against the local scratch repository fixture rather than a real remote, and against
a recording pull request opener rather than GitHub, so nothing here needs network access
or credentials.

Every manifest line asserted on is rendered by the :class:`ManifestKey` that owns it,
and every path by the :class:`PlanDocument` that lives at it, so a test cannot pin a
second, independently-drifting copy of the manifest's own vocabulary.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

import basstler.plan.item_bootstrap
from basstler.locations import PluginLocation, ProjectLocation
from basstler.plan.item_bootstrap import (
    BootstrapCommand,
    BranchReport,
    CreatedPullRequest,
    ItemCheckRequest,
    ItemRecordRequest,
    ItemStatus,
    ItemUpdateRequest,
    ManifestText,
    OwnedBlocker,
    PlanDocument,
    PlanDocuments,
    PlanItemBootstrapExitCode,
    PullRequestRequest,
    ReportKey,
    UnknownItemError,
    UnknownPlanError,
    WorkOpener,
    WorkOpenRequest,
)
from basstler.plan.model import (
    ItemIndentation,
    ItemLayout,
    KeySpecification,
    ManifestKey,
    Prose,
    ValueStyle,
)
from basstler.plan.size_limits import (
    Measure,
    Roadmap,
    RoadmapEntryLocation,
    SizeViolation,
)

from ..scratch_repository import ScratchRepository
from ..constants.notes import ScratchBranch
from ..constants.paths import DatasetLocation

from ..script_runner import PythonModuleRunner

BOOTSTRAP_MODULE = basstler.plan.item_bootstrap.__name__
"""
The import path the scratch layout's copy of the module under test is run by.

Read off the module rather than spelled out, so a rename cannot leave the tests running
something else - and ``-m`` rather than a file path, since a module run by path would put
the package's own directory on ``sys.path`` in place of the project root.
"""

PLAN_IDENTIFIER = "test-plan"

PLAN_MANIFEST = (DatasetLocation.DIRECTORY / "bootstrap-plan.yaml").read_text()
"""
The manifest every test starts from.
"""

PLAN_ROADMAP = (DatasetLocation.DIRECTORY / "bootstrap-roadmap.md").read_text()
"""
The roadmap every test starts from.
"""

EXISTING_ITEM = "an-existing-item"
"""
The fixture item the plan already tracks, with no branch of its own yet.
"""

NEW_ITEM = "a-brand-new-item"
"""
An item the fixture plan does not track, for the entry-creating path.
"""

NEW_BRANCH = "claude/a-new-branch"
"""
The branch opening the work publishes.
"""

SESSION_URL = "https://example.invalid/session_first"
"""
The session recorded on an item whose work was opened.
"""

INDENTLESS_PLAN_MANIFEST = (
    DatasetLocation.DIRECTORY / "bootstrap-plan-indentless-items.yaml"
).read_text()
"""
The fixture plan written the way a YAML dumper writes it: every item flush with
``items:``, and the fixture's further items - written-out dependencies, a literal note -
beside them.
"""

SECOND_ITEM = "a-second-item"
"""
The fixture item already underway, on a branch of its own.
"""

STACKED_ITEM = "a-stacked-item"
"""
The indentless fixture's item whose dependencies are written out beneath their key.
"""

LITERALLY_NOTED_ITEM = "a-literally-noted-item"
"""
The indentless fixture's item whose note is a literal block.
"""

PULL_REQUEST_NUMBER = 143
"""
The pull request number opening the work records.
"""

OWNER = "a-maintenance-pass"
"""
The automated caller whose blockers the blocking tests write and withdraw.
"""

CONFLICT_REASON = "conflicts with its base in a_file.py"
"""
Why that caller blocks a branch.
"""

HAND_WRITTEN_BLOCKER = "waiting on a decision nobody automated"
"""
A blocker no automated caller owns, which none of them may touch.
"""

NO_PLANS_BRANCH = "claude/belongs-to-nothing"
"""
A branch no plan tracks.
"""


def second_item_branch() -> str:
    """
    :return: The branch the fixture's underway item records, as the fixture states it.
    """
    return item_named(PLAN_MANIFEST, SECOND_ITEM)[ManifestKey.BRANCH.key]


def manifest_line(manifest_key: ManifestKey, value: Any) -> str:
    """
    One manifest line as the key that owns it writes it.

    :param manifest_key: The key the line sets.
    :param value: The value it carries.
    :return: The rendered line.
    """
    return manifest_key.render(value)


# %% fixtures


@dataclass
class RecordingPullRequestOpener:
    """
    Stands in for the GitHub pull request endpoint, recording what it was asked to
    create instead of calling it.
    """

    number: int = 99
    """
    The pull request number handed back to the caller.
    """

    requests: list[PullRequestRequest] = field(default_factory=list)
    """
    Every request this opener was given, in call order.
    """

    def open_pull_request(self, request: PullRequestRequest) -> CreatedPullRequest:
        """
        Record *request* and hand back a pull request as GitHub would.

        :param request: The pull request to create.
        :return: The created pull request.
        """
        self.requests.append(request)
        return CreatedPullRequest(
            number=self.number,
            html_url=f"https://example.invalid/pull/{self.number}",
        )


@dataclass
class RefusingPullRequestOpener:
    """
    Stands in for a GitHub endpoint that refuses the creation.
    """

    def open_pull_request(self, request: PullRequestRequest) -> CreatedPullRequest:
        """
        Refuse the creation the way the real opener does on a non-success response.

        :param request: The pull request that will not be created.
        :raises PullRequestRefusedError: Always.
        """
        raise basstler.plan.item_bootstrap.PullRequestRefusedError(detail="422 refused")


@pytest.fixture
def bootstrap_repository(scratch_repository: ScratchRepository) -> ScratchRepository:
    """
    A scratch repository carrying the hook scripts this module drives, with a plan
    already published on its notes branch.

    :param scratch_repository: The initialized scratch repository and notes remote.
    :return: The same repository, ready to bootstrap an item in.
    """
    scratch_repository.install_hook_scripts(
        PluginLocation.PERSONAL_NOTES_CONFIGURATION_SCRIPT.name,
        PluginLocation.PLAN_SAVING_SCRIPT.name,
    )
    scratch_repository.install_package()
    scratch_repository.write("README.md", "scratch repo\n")
    scratch_repository.commit_everything("initial commit")
    scratch_repository.publish_notes_branch(
        {
            PlanDocument.MANIFEST.path_within_notes_branch(PLAN_IDENTIFIER): (
                PLAN_MANIFEST
            ),
            PlanDocument.ROADMAP.path_within_notes_branch(PLAN_IDENTIFIER): (
                PLAN_ROADMAP
            ),
        }
    )
    scratch_repository.resolve_notes_remote_to()
    scratch_repository.add_work_remote()
    return scratch_repository


def published_plan(repository: ScratchRepository) -> dict[PlanDocument, str]:
    """
    Read the plan's documents as they actually are on the notes branch, rather than what
    a run reported.

    Asks each document where it lives, so this never states a plan's layout
    independently of the code that owns it.

    :param repository: The scratch repository whose notes remote to read.
    :return: Each document's content.
    """
    checkout = repository.project_root.parent / "published-plan-checkout"
    shutil.rmtree(checkout, ignore_errors=True)
    repository.clone_notes_branch(checkout)
    return {
        document: (
            checkout / document.path_within_notes_branch(PLAN_IDENTIFIER)
        ).read_text()
        for document in PlanDocument
    }


def record_request(repository: ScratchRepository, **overrides: object):
    """
    Build a record request, overriding only what a test cares about.

    :param repository: The scratch repository the request is recorded against.
    :param overrides: Fields to replace on the default request.
    :return: The request.
    """
    defaults = dict(
        plan_identifier=PLAN_IDENTIFIER,
        item_identifier=EXISTING_ITEM,
        status=ItemStatus.IN_PROGRESS,
    )
    defaults.update(overrides)
    return ItemRecordRequest(**defaults)


def published_items(repository: ScratchRepository) -> dict[str, dict[str, Any]]:
    """
    Every item as YAML actually parses it off the notes branch, keyed by id.

    Parsing rather than matching text is what catches a write that leaves the manifest
    valid but means something other than it says.

    :param repository: The scratch repository whose notes remote to read.
    :return: Each item's parsed mapping.
    """
    manifest = yaml.safe_load(published_plan(repository)[PlanDocument.MANIFEST])
    return {
        item[ManifestKey.IDENTIFIER.key]: item
        for item in manifest[ManifestKey.ITEMS.key]
    }


def item_named(manifest_text: str, item_identifier: str) -> dict[str, Any]:
    """
    :param manifest_text: The manifest to parse.
    :param item_identifier: The item's id.
    :return: The item's mapping, as a YAML reader sees it.
    """
    items = yaml.safe_load(manifest_text)[ManifestKey.ITEMS.key]
    return next(
        item for item in items if item[ManifestKey.IDENTIFIER.key] == item_identifier
    )


def update_request(**overrides: object) -> ItemUpdateRequest:
    """
    Build an update request, overriding only what a test cares about.

    :param overrides: Fields to replace on the default request.
    :return: The request.
    """
    defaults = dict(
        plan_identifier=PLAN_IDENTIFIER,
        item_identifier=EXISTING_ITEM,
        values_by_key={},
    )
    defaults.update(overrides)
    return ItemUpdateRequest(**defaults)


def opened_item_fields() -> dict[ManifestKey, Any]:
    """
    :return: The value opening an item's work writes to each key.
    """
    return {
        ManifestKey.BRANCH: NEW_BRANCH,
        ManifestKey.PULL_REQUEST_NUMBER: PULL_REQUEST_NUMBER,
        ManifestKey.SESSION: SESSION_URL,
        ManifestKey.STATUS: ItemStatus.IN_PROGRESS,
    }


def publish_the_branch_index(repository: ScratchRepository) -> None:
    """
    Make the generated branch index exist, by running the save path that writes it.

    Only ``save-plan.sh`` writes that index, so a test needing one asks for a real save
    rather than assembling a second copy of its format.

    :param repository: The scratch repository to save within.
    """
    update_request().update(repository.project_root)


def put_both_items_on_one_branch(repository: ScratchRepository) -> None:
    """
    Move the fixture's unstarted item onto the branch its underway one already rides on.

    :param repository: The scratch repository to save within.
    """
    update_request(values_by_key={ManifestKey.BRANCH: second_item_branch()}).update(
        repository.project_root
    )


def publish_new_branch(repository: ScratchRepository) -> None:
    """
    Create :data:`NEW_BRANCH` and push it to the work remote.

    :param repository: The scratch repository to publish from.
    """
    repository.run_git("checkout", "-b", NEW_BRANCH)
    repository.run_git("push", "--quiet", "origin", NEW_BRANCH)


def entry_wrapping_across(unbreakable: str) -> str:
    """
    A blocker long enough that wrapping has to break somewhere inside *unbreakable*.

    Positioned from the writer's own wrap column, so this keeps reproducing the hazard
    if that column ever moves.

    :param unbreakable: The token that has to survive the wrap intact.
    :return: The blocker's text.
    """
    indentation = ManifestText.from_text(PLAN_MANIFEST).item_indentation()
    body_width = Prose.line_width - len(indentation.nested + ItemLayout.NESTING_STEP)
    lead = "word "
    return (
        lead * ((body_width - len(unbreakable) // 2) // len(lead))
        + unbreakable
        + " and there is more text after it."
    )


@pytest.fixture
def indentless_plan_repository(
    scratch_repository: ScratchRepository,
) -> ScratchRepository:
    """
    A scratch repository whose published plan writes its items flush with ``items:``.

    :param scratch_repository: The initialized scratch repository and notes remote.
    :return: The repository, ready to bootstrap an item in.
    """
    scratch_repository.install_hook_scripts(
        PluginLocation.PERSONAL_NOTES_CONFIGURATION_SCRIPT.name,
        PluginLocation.PLAN_SAVING_SCRIPT.name,
    )
    scratch_repository.install_package()
    scratch_repository.write("README.md", "scratch repo\n")
    scratch_repository.commit_everything("initial commit")
    scratch_repository.publish_notes_branch(
        {
            PlanDocument.MANIFEST.path_within_notes_branch(PLAN_IDENTIFIER): (
                INDENTLESS_PLAN_MANIFEST
            ),
            PlanDocument.ROADMAP.path_within_notes_branch(PLAN_IDENTIFIER): (
                PLAN_ROADMAP
            ),
        }
    )
    scratch_repository.resolve_notes_remote_to()
    scratch_repository.add_work_remote()
    return scratch_repository


def open_request(**overrides: object) -> WorkOpenRequest:
    """
    Build a work-open request, overriding only what a test cares about.

    :param overrides: Fields to replace on the default request.
    :return: The request.
    """
    defaults = dict(
        plan_identifier=PLAN_IDENTIFIER,
        item_identifier=EXISTING_ITEM,
        branch=NEW_BRANCH,
        base_branch=ScratchBranch.WORK,
        session_url=SESSION_URL,
        pull_request_title="An item that has not been started",
        pull_request_body="What it does.",
    )
    defaults.update(overrides)
    return WorkOpenRequest(**defaults)


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


def an_entry_over_the_length_limit() -> str:
    """
    :return: A roadmap entry one character longer than the plan's limits allow.
    """
    return "x" * (Measure.ROADMAP_ENTRY_LENGTH.maximum + 1)


def the_length_violation_of(entry: str) -> SizeViolation:
    """
    :param entry: An entry appended to the fixture roadmap.
    :return: The violation the plan save names for it.
    """
    return SizeViolation(
        measure=Measure.ROADMAP_ENTRY_LENGTH,
        location=RoadmapEntryLocation(len(Roadmap.from_text(PLAN_ROADMAP).entries) + 1),
        measured=len(entry),
    )


def test_a_refused_save_carries_the_reason_the_plan_save_gave(
    bootstrap_repository: ScratchRepository,
):
    entry = an_entry_over_the_length_limit()

    with pytest.raises(basstler.plan.item_bootstrap.PlanSaveRefusedError) as refusal:
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

    with pytest.raises(basstler.plan.item_bootstrap.PlanSaveRefusedError):
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
    with pytest.raises(basstler.plan.item_bootstrap.IncompleteNewItemError) as refusal:
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


# %% opening the work


def test_opening_writes_the_branch_pull_request_and_session_onto_the_item(
    bootstrap_repository: ScratchRepository,
):
    opener = RecordingPullRequestOpener(number=143)

    result = WorkOpener(bootstrap_repository.project_root).open(
        open_request(),
        pull_request_opener=opener,
    )

    assert result.exit_code is PlanItemBootstrapExitCode.SUCCESS
    assert result.pull_request_number == 143
    manifest = published_plan(bootstrap_repository)[PlanDocument.MANIFEST]
    for written_key, value in (
        (ManifestKey.BRANCH, NEW_BRANCH),
        (ManifestKey.PULL_REQUEST_NUMBER, 143),
        (ManifestKey.SESSION, SESSION_URL),
        (ManifestKey.STATUS, ItemStatus.IN_PROGRESS.value),
    ):
        assert manifest_line(written_key, value) in manifest


def test_opening_asks_for_a_draft_pull_request_against_the_plans_repository(
    bootstrap_repository: ScratchRepository,
):
    opener = RecordingPullRequestOpener()

    WorkOpener(bootstrap_repository.project_root).open(
        open_request(),
        pull_request_opener=opener,
    )

    assert len(opener.requests) == 1
    request = opener.requests[0]
    assert request.draft is True
    assert request.repository == "an-owner/a-repository"
    assert request.head == NEW_BRANCH
    assert request.base == ScratchBranch.WORK


def test_opening_publishes_the_branch_to_the_repositorys_own_remote(
    bootstrap_repository: ScratchRepository,
):
    WorkOpener(bootstrap_repository.project_root).open(
        open_request(),
        pull_request_opener=RecordingPullRequestOpener(),
    )

    published = bootstrap_repository.run_git(
        "ls-remote",
        "--heads",
        str(bootstrap_repository.work_remote_path),
        NEW_BRANCH,
    )
    assert NEW_BRANCH in published.stdout


def test_opening_an_already_published_branch_is_refused(
    bootstrap_repository: ScratchRepository,
):
    opener = RecordingPullRequestOpener()
    WorkOpener(bootstrap_repository.project_root).open(
        open_request(),
        pull_request_opener=opener,
    )

    with pytest.raises(
        basstler.plan.item_bootstrap.BranchAlreadyPublishedError
    ) as refusal:
        WorkOpener(bootstrap_repository.project_root).open(
            open_request(),
            pull_request_opener=opener,
        )
    assert refusal.value.branch == NEW_BRANCH
    assert len(opener.requests) == 1


def test_opening_an_unknown_item_is_refused_before_anything_is_created(
    bootstrap_repository: ScratchRepository,
):
    opener = RecordingPullRequestOpener()

    with pytest.raises(UnknownItemError):
        WorkOpener(bootstrap_repository.project_root).open(
            open_request(item_identifier="no-such-item"),
            pull_request_opener=opener,
        )

    assert opener.requests == []
    published = bootstrap_repository.run_git(
        "ls-remote", "--heads", str(bootstrap_repository.work_remote_path)
    )
    assert NEW_BRANCH not in published.stdout


def test_a_refused_pull_request_leaves_the_manifest_untouched(
    bootstrap_repository: ScratchRepository,
):
    with pytest.raises(basstler.plan.item_bootstrap.PullRequestRefusedError):
        WorkOpener(bootstrap_repository.project_root).open(
            open_request(),
            pull_request_opener=RefusingPullRequestOpener(),
        )

    assert published_plan(bootstrap_repository)[PlanDocument.MANIFEST] == PLAN_MANIFEST


def test_a_refused_pull_request_leaves_the_branch_it_already_published(
    bootstrap_repository: ScratchRepository,
):
    with pytest.raises(basstler.plan.item_bootstrap.PullRequestRefusedError):
        WorkOpener(bootstrap_repository.project_root).open(
            open_request(),
            pull_request_opener=RefusingPullRequestOpener(),
        )

    published = bootstrap_repository.run_git(
        "ls-remote",
        "--heads",
        str(bootstrap_repository.work_remote_path),
        NEW_BRANCH,
    )
    assert NEW_BRANCH in published.stdout


def test_a_supplied_pull_request_number_is_recorded_without_creating_one(
    bootstrap_repository: ScratchRepository,
):
    opener = RecordingPullRequestOpener()

    result = WorkOpener(bootstrap_repository.project_root).open(
        open_request(pull_request_number=57),
        pull_request_opener=opener,
    )

    assert opener.requests == []
    assert result.pull_request_number == 57
    assert (
        manifest_line(ManifestKey.PULL_REQUEST_NUMBER, 57)
        in published_plan(bootstrap_repository)[PlanDocument.MANIFEST]
    )


def test_creating_a_pull_request_without_a_title_or_body_is_refused_before_publishing(
    bootstrap_repository: ScratchRepository,
):
    with pytest.raises(basstler.plan.item_bootstrap.PullRequestDetailsMissingError):
        WorkOpener(bootstrap_repository.project_root).open(
            open_request(pull_request_title=None, pull_request_body=None),
            pull_request_opener=RecordingPullRequestOpener(),
        )

    published = bootstrap_repository.run_git(
        "ls-remote", "--heads", str(bootstrap_repository.work_remote_path)
    )
    assert NEW_BRANCH not in published.stdout


def test_a_supplied_pull_request_number_adopts_the_branch_its_caller_published(
    bootstrap_repository: ScratchRepository,
):
    WorkOpener(bootstrap_repository.project_root).open(
        open_request(),
        pull_request_opener=RecordingPullRequestOpener(number=99),
    )

    result = WorkOpener(bootstrap_repository.project_root).open(
        open_request(pull_request_number=57),
        pull_request_opener=RecordingPullRequestOpener(),
    )

    assert result.pull_request_number == 57


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

    with pytest.raises(basstler.plan.item_bootstrap.PlanNotWrittenError) as refusal:
        documents.confirm_written(
            {
                PlanDocument.MANIFEST: PLAN_MANIFEST,
                PlanDocument.ROADMAP: "a roadmap that was never saved\n",
            },
            bootstrap_repository.project_root,
        )

    assert refusal.value.documents == (PlanDocument.ROADMAP,)


# %% checking what the manifest claims against local git


def check_existing_item(repository: ScratchRepository) -> object:
    """
    :param repository: The scratch repository to check within.
    :return: What checking the fixture's unstarted item reports.
    """
    return ItemCheckRequest(
        plan_identifier=PLAN_IDENTIFIER, item_identifier=EXISTING_ITEM
    ).check(repository.project_root)


def test_a_recorded_branch_that_was_never_published_is_reported_stale(
    bootstrap_repository: ScratchRepository,
):
    update_request(values_by_key={ManifestKey.BRANCH: NEW_BRANCH}).update(
        bootstrap_repository.project_root
    )

    report = check_existing_item(bootstrap_repository)

    assert [finding.manifest_key for finding in report.findings] == [ManifestKey.BRANCH]
    assert report.findings[0].recorded == NEW_BRANCH
    assert report.exit_code is PlanItemBootstrapExitCode.MANIFEST_IS_STALE


def test_an_item_recording_a_published_branch_reports_nothing_stale(
    bootstrap_repository: ScratchRepository,
):
    publish_new_branch(bootstrap_repository)
    update_request(values_by_key=opened_item_fields()).update(
        bootstrap_repository.project_root
    )

    report = check_existing_item(bootstrap_repository)

    assert report.findings == ()
    assert report.exit_code is PlanItemBootstrapExitCode.SUCCESS


def test_a_published_branch_with_no_session_recorded_is_reported_stale(
    bootstrap_repository: ScratchRepository,
):
    publish_new_branch(bootstrap_repository)
    update_request(
        values_by_key={
            ManifestKey.BRANCH: NEW_BRANCH,
            ManifestKey.STATUS: ItemStatus.IN_PROGRESS,
            ManifestKey.PULL_REQUEST_NUMBER: PULL_REQUEST_NUMBER,
        }
    ).update(bootstrap_repository.project_root)

    report = check_existing_item(bootstrap_repository)

    assert [finding.manifest_key for finding in report.findings] == [
        ManifestKey.SESSION
    ]


def test_a_branch_exists_while_the_item_is_still_not_started(
    bootstrap_repository: ScratchRepository,
):
    publish_new_branch(bootstrap_repository)
    update_request(values_by_key={ManifestKey.BRANCH: NEW_BRANCH}).update(
        bootstrap_repository.project_root
    )

    report = check_existing_item(bootstrap_repository)

    status_finding = next(
        finding
        for finding in report.findings
        if finding.manifest_key is ManifestKey.STATUS
    )
    assert ItemStatus(status_finding.recorded) is ItemStatus.NOT_STARTED


def test_checking_an_unknown_item_is_refused(bootstrap_repository: ScratchRepository):
    with pytest.raises(UnknownItemError):
        ItemCheckRequest(
            plan_identifier=PLAN_IDENTIFIER, item_identifier=NEW_ITEM
        ).check(bootstrap_repository.project_root)


# %% resolving a branch to the items it carries


def test_resolving_a_branch_names_the_plan_that_tracks_it(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)

    resolution = BranchReport.of_branch(
        second_item_branch(), bootstrap_repository.project_root
    )

    assert resolution.plan_identifier == PLAN_IDENTIFIER
    assert [item.item_identifier for item in resolution.items] == [SECOND_ITEM]


def test_resolving_reports_the_status_and_blockers_each_item_records(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)

    resolution = BranchReport.of_branch(
        second_item_branch(), bootstrap_repository.project_root
    )

    recorded = item_named(PLAN_MANIFEST, SECOND_ITEM)
    assert resolution.items[0].status is ItemStatus(recorded[ManifestKey.STATUS.key])
    assert resolution.items[0].blockers == ()


def test_resolving_a_branch_two_items_ride_on_answers_with_both(
    bootstrap_repository: ScratchRepository,
):
    put_both_items_on_one_branch(bootstrap_repository)

    resolution = BranchReport.of_branch(
        second_item_branch(), bootstrap_repository.project_root
    )

    assert [item.item_identifier for item in resolution.items] == [
        EXISTING_ITEM,
        SECOND_ITEM,
    ]


def test_a_branch_no_plan_claims_is_reported_rather_than_refused(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)

    resolution = BranchReport.of_branch(
        NO_PLANS_BRANCH, bootstrap_repository.project_root
    )

    assert resolution.plan_identifier is None
    assert resolution.items == ()
    assert resolution.exit_code is PlanItemBootstrapExitCode.BRANCH_TRACKS_NO_ITEM


# %% owning a blocker on every item a branch carries


def owned_blocker(reason: str = CONFLICT_REASON) -> str:
    """
    :param reason: Why the owner blocked the branch.
    :return: The blocker as :class:`OwnedBlocker` writes it for :data:`OWNER`.
    """
    return f"{OWNER}{OwnedBlocker.owner_separator}{reason}"


def block_second_items_branch(
    repository: ScratchRepository, reason: str = CONFLICT_REASON
) -> BranchReport:
    """
    :param repository: The scratch repository to write within.
    :param reason: Why the branch is blocked.
    :return: What blocking the underway item's branch wrote.
    """
    return OwnedBlocker(branch=second_item_branch(), owner=OWNER, reason=reason).write(
        repository.project_root
    )


def unblock_branch(repository: ScratchRepository, branch: str) -> BranchReport:
    """
    :param repository: The scratch repository to write within.
    :param branch: The branch to withdraw :data:`OWNER`'s blocker from.
    :return: What withdrawing it wrote.
    """
    return OwnedBlocker(branch=branch, owner=OWNER).write(repository.project_root)


def hand_write_blocker_on_second_item(repository: ScratchRepository) -> None:
    """
    Record :data:`HAND_WRITTEN_BLOCKER` on the underway item, the way a person would.

    :param repository: The scratch repository to write within.
    """
    update_request(
        item_identifier=SECOND_ITEM,
        values_by_key={ManifestKey.BLOCKERS: [HAND_WRITTEN_BLOCKER]},
    ).update(repository.project_root)


def test_blocking_a_branch_blocks_every_item_it_carries(
    bootstrap_repository: ScratchRepository,
):
    put_both_items_on_one_branch(bootstrap_repository)

    block_second_items_branch(bootstrap_repository)

    for item in published_items(bootstrap_repository).values():
        assert item[ManifestKey.STATUS.key] == ItemStatus.BLOCKED
        assert item[ManifestKey.BLOCKERS.key] == [owned_blocker()]


def test_blocking_keeps_a_blocker_somebody_else_wrote(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)
    hand_write_blocker_on_second_item(bootstrap_repository)

    block_second_items_branch(bootstrap_repository)

    assert published_items(bootstrap_repository)[SECOND_ITEM][
        ManifestKey.BLOCKERS.key
    ] == [HAND_WRITTEN_BLOCKER, owned_blocker()]


def test_blocking_a_second_time_replaces_its_own_blocker_rather_than_repeating_it(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)
    block_second_items_branch(bootstrap_repository)

    block_second_items_branch(bootstrap_repository, "a different file conflicts now")

    assert published_items(bootstrap_repository)[SECOND_ITEM][
        ManifestKey.BLOCKERS.key
    ] == [owned_blocker("a different file conflicts now")]


def test_unblocking_removes_only_the_blocker_it_owns(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)
    hand_write_blocker_on_second_item(bootstrap_repository)
    block_second_items_branch(bootstrap_repository)

    unblock_branch(bootstrap_repository, second_item_branch())

    assert published_items(bootstrap_repository)[SECOND_ITEM][
        ManifestKey.BLOCKERS.key
    ] == [HAND_WRITTEN_BLOCKER]


def test_an_item_still_carrying_somebody_elses_blocker_stays_blocked(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)
    hand_write_blocker_on_second_item(bootstrap_repository)
    block_second_items_branch(bootstrap_repository)

    unblock_branch(bootstrap_repository, second_item_branch())

    assert (
        published_items(bootstrap_repository)[SECOND_ITEM][ManifestKey.STATUS.key]
        == ItemStatus.BLOCKED
    )


def test_clearing_the_last_blocker_returns_the_item_to_in_progress(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)
    block_second_items_branch(bootstrap_repository)

    unblock_branch(bootstrap_repository, second_item_branch())

    item = published_items(bootstrap_repository)[SECOND_ITEM]
    assert item[ManifestKey.STATUS.key] == ItemStatus.IN_PROGRESS
    assert item[ManifestKey.BLOCKERS.key] == []


def test_withdrawing_a_blocker_an_item_never_carried_leaves_it_alone(
    bootstrap_repository: ScratchRepository,
):
    """
    A pass withdraws its blocker from every branch it finds clean, most of which it
    never blocked, so writing each of those would spread noise across the manifest.
    """
    publish_the_branch_index(bootstrap_repository)
    before = published_plan(bootstrap_repository)[PlanDocument.MANIFEST]

    report = unblock_branch(bootstrap_repository, second_item_branch())

    assert [item.item_identifier for item in report.items] == [SECOND_ITEM]
    assert published_plan(bootstrap_repository)[PlanDocument.MANIFEST] == before


def test_unblocking_a_branch_no_plan_claims_writes_nothing(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)
    before = published_plan(bootstrap_repository)[PlanDocument.MANIFEST]

    report = unblock_branch(bootstrap_repository, NO_PLANS_BRANCH)

    assert report.exit_code is PlanItemBootstrapExitCode.BRANCH_TRACKS_NO_ITEM
    assert published_plan(bootstrap_repository)[PlanDocument.MANIFEST] == before


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


# %% the vocabulary the manifest is written in


def test_a_rendered_field_line_matches_how_a_real_manifest_writes_it():
    """
    The renderer's indentation and spacing have to match a manifest written by hand,
    since every other test compares the two.
    """
    assert (
        manifest_line(ManifestKey.STATUS, ItemStatus.NOT_STARTED.value) in PLAN_MANIFEST
    )
    assert manifest_line(ManifestKey.TRACK, "a-track") in PLAN_MANIFEST


NARROWLY_INDENTED_MANIFEST = (
    DatasetLocation.DIRECTORY / "narrowly-indented-plan.yaml"
).read_text()
"""
A manifest predating this module's own formatting convention: its items list has no
indent before the ``-`` and its fields sit two spaces in, not the four
``ItemLayout.FIELD_INDENT`` assumes.

``icra-mechanism/plan.yaml`` on the personal-notes branch is written exactly this way.
"""


def test_patching_a_field_matches_the_items_own_indentation_rather_than_a_fixed_one():
    """
    A fixed indentation nests a patched field under whichever key happens to precede it.

    instead of beside it, the moment a manifest's own indentation differs from the
    module's assumed one - which stops the result parsing as YAML at all.
    """
    patched = ManifestText.from_text(NARROWLY_INDENTED_MANIFEST).with_item_fields(
        "narrow-plan",
        "an-item",
        {ManifestKey.STATUS: ItemStatus.IN_PROGRESS.value},
    )

    item = yaml.safe_load(patched)[ManifestKey.ITEMS.key][0]
    assert item[ManifestKey.STATUS.key] == ItemStatus.IN_PROGRESS.value
    assert item[ManifestKey.TITLE.key] == "An item indented two spaces, not four"


def test_a_new_item_matches_the_existing_items_indentation_rather_than_a_fixed_one():
    """
    A new item rendered at a fixed indentation lands inside the previous item instead of
    beside it whenever the manifest's own items sit flush with ``items:``, and the
    result stops parsing as YAML at all.
    """
    request = ItemRecordRequest(
        plan_identifier="narrow-plan",
        item_identifier=NEW_ITEM,
        status=ItemStatus.NOT_STARTED,
        title="A brand new item",
        track="a-track",
    )
    manifest = ManifestText.from_text(NARROWLY_INDENTED_MANIFEST)

    extended = manifest.with_item(request.render_new_item(manifest.item_indentation()))

    items = yaml.safe_load(extended)[ManifestKey.ITEMS.key]
    assert [item[ManifestKey.IDENTIFIER.key] for item in items] == ["an-item", NEW_ITEM]
    assert items[1][ManifestKey.TRACK.key] == "a-track"


def test_a_key_quotes_its_own_value_when_its_style_says_to():
    """
    Quoting is the key's to decide, so no caller has to know that a title is prose and a
    track is a bare identifier.
    """
    assert ManifestKey.TITLE.render("A brand new item").endswith(
        ': "A brand new item"\n'
    )
    assert ManifestKey.TRACK.render("a-track").endswith(": a-track\n")
    assert ManifestKey.TITLE.style is ValueStyle.DOUBLE_QUOTED
    assert ManifestKey.TRACK.style is ValueStyle.PLAIN


def test_every_key_is_a_specification_in_its_own_right():
    """
    Mixing the specification into the enum is what lets a key carry its style without a
    lookup beside it, so the relationship is asserted rather than assumed.
    """
    assert issubclass(ManifestKey, KeySpecification)
    assert all(
        isinstance(manifest_key, KeySpecification) for manifest_key in ManifestKey
    )


def test_every_key_was_declared_as_specification_arguments():
    """
    A member declared as a built ``KeySpecification`` rather than as its argument tuple
    is accepted silently by the enum machinery and lands the whole instance in ``key``.

    This is what catches that.
    """
    assert all(isinstance(manifest_key.key, str) for manifest_key in ManifestKey)
    assert all(
        isinstance(manifest_key.style, ValueStyle) for manifest_key in ManifestKey
    )


def test_a_key_indexes_a_parsed_manifest_by_the_string_it_names():
    """
    A key reads parsed YAML through its own ``key``, which is the manifest's own
    spelling of it.
    """
    item = yaml.safe_load(PLAN_MANIFEST)[ManifestKey.ITEMS.key][0]
    assert item[ManifestKey.IDENTIFIER.key] == EXISTING_ITEM
    assert item[ManifestKey.STATUS.key] == ItemStatus.NOT_STARTED


def test_the_plans_directory_matches_the_shell_configuration_that_owns_it(
    bootstrap_repository: ScratchRepository,
):
    """
    ``ProjectLocation.PLANS`` mirrors ``PLANS_DIR`` in the shell configuration, and
    ``ProjectLocation.PLAN_HUB`` mirrors ``PLAN_HUB_PATH``; this is what stops the
    mirrors drifting, since each pair is edited in different files.
    """
    resolved = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{PluginLocation.PERSONAL_NOTES_CONFIGURATION_SCRIPT}" && '
            'printf "%s\\n%s\\n%s\\n" "${PLANS_DIR}" "$(plan_manifest_path "$1")" '
            '"${PLAN_HUB_PATH}"',
            "test",
            PLAN_IDENTIFIER,
        ],
        cwd=bootstrap_repository.project_root,
        capture_output=True,
        text=True,
        check=True,
    )
    plans_directory, manifest_path, hub_path = resolved.stdout.strip().split("\n")
    assert plans_directory == str(ProjectLocation.PLANS)
    assert hub_path == str(ProjectLocation.PLAN_HUB)
    assert manifest_path == PlanDocument.MANIFEST.path_within_notes_branch(
        PLAN_IDENTIFIER
    )


SCALAR_STYLED_KEYS = tuple(
    manifest_key for manifest_key in ManifestKey if not manifest_key.is_block_styled
)
"""
The keys whose value is written on the key's own line, derived from the styles rather
than listed a second time.
"""

VALUES_YAML_READS_BACK_DIFFERENTLY = (
    "opened on #76",
    'a value carrying a "quoted" phrase',
    r"a path like C:\temp",
    "a value ending in a colon:",
)
"""
Values a manifest can legitimately carry that YAML does not read back as written unless
the writer quotes and escapes them.
"""


@pytest.mark.parametrize("hostile_value", VALUES_YAML_READS_BACK_DIFFERENTLY)
@pytest.mark.parametrize("manifest_key", SCALAR_STYLED_KEYS)
def test_a_rendered_scalar_reads_back_as_the_value_it_was_given(
    manifest_key: ManifestKey, hostile_value: str
):
    written = yaml.safe_load(manifest_key.render(hostile_value))

    assert written[manifest_key.key] == hostile_value


def test_a_word_wrapped_at_its_hyphen_is_written_whole():
    """
    A hyphen at the end of a hard-wrapped line is where the author broke a word they
    wrote whole.
    """
    written = Prose("the paragraphs have to be blank-\nline separated").folded("")

    assert written == "the paragraphs have to be blank-line separated\n"


def test_a_suspended_hyphen_typed_on_one_line_keeps_its_space():
    written = Prose("all network- and credential-free tests").folded("")

    assert written == "all network- and credential-free tests\n"


def test_a_paragraph_break_still_separates_paragraphs_after_a_hyphen():
    assert Prose("ends in a-\n\nnew paragraph").paragraphs == [
        "ends in a-",
        "new paragraph",
    ]


def test_only_the_keys_whose_values_run_over_lines_are_block_styled():
    assert ManifestKey.block_styled() == {
        ManifestKey.NOTES,
        ManifestKey.BLOCKERS,
        ManifestKey.DEPENDS_ON,
    }


# %% exit statuses


def test_every_exit_code_names_itself_from_its_own_member():
    for exit_code in PlanItemBootstrapExitCode:
        assert exit_code.name_for_a_caller == exit_code.name.lower()


def test_each_refusal_carries_its_own_exit_code():
    codes = {
        UnknownPlanError: PlanItemBootstrapExitCode.UNKNOWN_PLAN,
        UnknownItemError: PlanItemBootstrapExitCode.UNKNOWN_ITEM,
        basstler.plan.item_bootstrap.IncompleteNewItemError: PlanItemBootstrapExitCode.INCOMPLETE_NEW_ITEM,
        basstler.plan.item_bootstrap.BranchAlreadyPublishedError: (
            PlanItemBootstrapExitCode.BRANCH_ALREADY_PUBLISHED
        ),
        basstler.plan.item_bootstrap.PullRequestDetailsMissingError: (
            PlanItemBootstrapExitCode.PULL_REQUEST_DETAILS_MISSING
        ),
        basstler.plan.item_bootstrap.PullRequestRefusedError: PlanItemBootstrapExitCode.PULL_REQUEST_REFUSED,
        basstler.plan.item_bootstrap.PlanSaveRefusedError: PlanItemBootstrapExitCode.PLAN_SAVE_REFUSED,
        basstler.plan.item_bootstrap.PlanNotWrittenError: PlanItemBootstrapExitCode.PLAN_NOT_WRITTEN,
    }
    assert {error: error.exit_code for error in codes} == codes


def test_a_refusal_composes_its_message_from_its_own_fields():
    refusal = UnknownItemError(
        plan_identifier=PLAN_IDENTIFIER, item_identifier="no-such-item"
    )
    assert refusal.error_message() in str(refusal)
    assert refusal.suggest_correction() in str(refusal)


# %% the command line


def run_bootstrap(
    repository: ScratchRepository, *arguments: str
) -> subprocess.CompletedProcess[str]:
    """
    Run the scratch layout's copy of this module with *arguments*.

    :param repository: A fixture-built scratch repository.
    :param arguments: CLI arguments to pass.
    :return: The finished subprocess.
    """
    return PythonModuleRunner(
        project_root=repository.project_root, module_name=BOOTSTRAP_MODULE
    ).run(*arguments)


def record_arguments(plan: str = PLAN_IDENTIFIER, *extra: str) -> list[str]:
    """
    The command line for recording the existing item.

    :param plan: The plan to record against.
    :param extra: Further arguments, appended as given.
    :return: The arguments.
    """
    return [
        "record",
        "--plan",
        plan,
        "--item",
        EXISTING_ITEM,
        "--status",
        ItemStatus.IN_PROGRESS.value,
        *extra,
    ]


def test_the_record_subcommand_reports_status_and_exit_code_first(
    bootstrap_repository: ScratchRepository,
):

    result = run_bootstrap(bootstrap_repository, *record_arguments())

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert list(report)[:2] == [ReportKey.STATUS, ReportKey.EXIT_CODE]
    assert (
        report[ReportKey.STATUS] == PlanItemBootstrapExitCode.SUCCESS.name_for_a_caller
    )
    assert report[ReportKey.EXIT_CODE] == PlanItemBootstrapExitCode.SUCCESS


def test_the_command_line_names_the_status_it_failed_with(
    bootstrap_repository: ScratchRepository,
):

    result = run_bootstrap(bootstrap_repository, *record_arguments(plan="no-such-plan"))

    assert result.returncode == PlanItemBootstrapExitCode.UNKNOWN_PLAN
    assert PlanItemBootstrapExitCode.UNKNOWN_PLAN.name_for_a_caller in result.stderr


def test_the_command_line_prints_why_the_plan_save_refused(
    bootstrap_repository: ScratchRepository,
):
    entry = an_entry_over_the_length_limit()

    result = run_bootstrap(
        bootstrap_repository,
        *record_arguments(PLAN_IDENTIFIER, "--roadmap-entry", entry),
    )

    assert result.returncode == PlanItemBootstrapExitCode.PLAN_SAVE_REFUSED
    assert str(the_length_violation_of(entry)) in result.stderr


def test_the_dashboard_republish_is_handed_back_rather_than_attempted(
    bootstrap_repository: ScratchRepository,
):

    result = run_bootstrap(bootstrap_repository, *record_arguments())

    report = json.loads(result.stdout)
    assert report[ReportKey.DASHBOARD_COMMAND] == f"/plan-dashboard {PLAN_IDENTIFIER}"


def test_the_update_subcommand_writes_a_note_from_a_file(
    bootstrap_repository: ScratchRepository,
):
    note = bootstrap_repository.write("note.md", "What the run found.\n")

    result = run_bootstrap(
        bootstrap_repository,
        "update",
        "--plan",
        PLAN_IDENTIFIER,
        "--item",
        EXISTING_ITEM,
        "--status",
        ItemStatus.BLOCKED.value,
        "--notes",
        str(note),
    )

    assert result.returncode == PlanItemBootstrapExitCode.SUCCESS, result.stderr
    item = published_items(bootstrap_repository)[EXISTING_ITEM]
    assert item[ManifestKey.NOTES.key] == "What the run found.\n"
    assert item[ManifestKey.STATUS.key] == ItemStatus.BLOCKED


def test_replacing_a_note_and_extending_it_cannot_be_asked_for_at_once(
    bootstrap_repository: ScratchRepository,
):
    note = bootstrap_repository.write("note.md", "Replaces it.\n")
    addition = bootstrap_repository.write("addition.md", "Extends it.\n")

    result = run_bootstrap(
        bootstrap_repository,
        "update",
        "--plan",
        PLAN_IDENTIFIER,
        "--item",
        EXISTING_ITEM,
        "--notes",
        str(note),
        "--append-notes",
        str(addition),
    )

    assert result.returncode == PlanItemBootstrapExitCode.USAGE
    assert "--append-notes" in result.stderr


def test_the_check_subcommand_exits_stale_and_names_the_field(
    bootstrap_repository: ScratchRepository,
):
    update_request(values_by_key={ManifestKey.BRANCH: NEW_BRANCH}).update(
        bootstrap_repository.project_root
    )

    result = run_bootstrap(
        bootstrap_repository,
        "check",
        "--plan",
        PLAN_IDENTIFIER,
        "--item",
        EXISTING_ITEM,
    )

    assert result.returncode == PlanItemBootstrapExitCode.MANIFEST_IS_STALE
    report = json.loads(result.stdout)
    assert list(report)[:2] == [ReportKey.STATUS, ReportKey.EXIT_CODE]
    assert [finding[ReportKey.FIELD] for finding in report[ReportKey.FINDINGS]] == [
        ManifestKey.BRANCH.key
    ]


def test_the_resolve_subcommand_names_the_plan_and_items_a_branch_carries(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)

    result = run_bootstrap(
        bootstrap_repository, "resolve", "--branch", second_item_branch()
    )

    assert result.returncode == PlanItemBootstrapExitCode.SUCCESS
    report = json.loads(result.stdout)
    assert report[ReportKey.PLAN] == PLAN_IDENTIFIER
    assert [item[ReportKey.ITEM] for item in report[ReportKey.ITEMS]] == [SECOND_ITEM]


def test_the_block_subcommand_exits_on_a_branch_that_belongs_to_no_plan(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)
    reason = bootstrap_repository.write("reasons/conflict.md", CONFLICT_REASON)

    result = run_bootstrap(
        bootstrap_repository,
        "block",
        "--branch",
        NO_PLANS_BRANCH,
        "--owner",
        OWNER,
        "--reason",
        str(reason),
    )

    assert result.returncode == PlanItemBootstrapExitCode.BRANCH_TRACKS_NO_ITEM
    assert json.loads(result.stdout)[ReportKey.PLAN] is None


def test_every_command_answers_to_a_word_of_its_own():
    commands = BootstrapCommand.every_command()

    assert {type(command) for command in commands} == set(
        BootstrapCommand.__subclasses__()
    )
    assert len({command.invoked_as for command in commands}) == len(commands)


def test_the_parser_takes_each_command_s_word(
    bootstrap_repository: ScratchRepository,
):
    """
    The parser is built from the commands themselves, so a word a command answers to is
    a word the command line accepts.
    """
    words = [command.invoked_as for command in BootstrapCommand.every_command()]

    refusals = {
        word: run_bootstrap(bootstrap_repository, word, "--help").returncode
        for word in words
    }

    assert refusals == {word: PlanItemBootstrapExitCode.SUCCESS for word in words}
