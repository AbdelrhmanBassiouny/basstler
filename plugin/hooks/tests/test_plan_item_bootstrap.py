"""
Tests for plan_item_bootstrap.py's two operations, recording an item and opening its
work.

Run against the local scratch repository fixture rather than a real remote, and against
a recording pull request opener rather than GitHub, so nothing here needs network access
or credentials.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import plan_item_bootstrap
from plan_item_bootstrap import (
    CreatedPullRequest,
    ExitCode,
    ItemRecordRequest,
    ItemStatus,
    PullRequestRequest,
    UnknownItemError,
    UnknownPlanError,
    WorkOpenRequest,
    open_work,
    record_item,
)
from scratch_repository import WORK_BRANCH, ScratchRepository

PLAN_IDENTIFIER = "test-plan"

PLAN_MANIFEST = """schema_version: 1
id: test-plan
title: "A plan under test"
description: >
  One paragraph.
default_repository: an-owner/a-repository
tracking_issue: 7

waves:
  - id: immediate
    name: "Immediate"

tracks:
  - id: a-track
    name: "A track"
    wave: immediate

items:
  - id: an-existing-item
    branch: null
    title: "An item that has not been started"
    track: a-track
    depends_on: []
    status: not_started
    notes: >
      A folded note whose wrapping must survive untouched, because a full YAML
      round trip re-flows it.

  - id: a-second-item
    branch: some/other-branch
    title: "An item that is already underway"
    pull_request_number: 12
    track: a-track
    depends_on: []
    status: in_progress
    session: https://example.invalid/session_second
"""

PLAN_ROADMAP = """# test-plan — roadmap

Narrative companion to plan.yaml.
"""


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
        raise plan_item_bootstrap.PullRequestRefusedError(
            "the remote refused to create the pull request"
        )


@pytest.fixture
def bootstrap_repository(scratch_repository: ScratchRepository) -> ScratchRepository:
    """
    A scratch repository carrying the hook scripts this module drives, with a plan
    already published on its notes branch.

    :param scratch_repository: The initialized scratch repository and notes remote.
    :return: The same repository, ready to bootstrap an item in.
    """
    scratch_repository.install_hook_scripts(
        "resolve-personal-notes-config.sh",
        "save-plan.sh",
        "plan_manifest_tools.py",
        "plan_item_bootstrap.py",
    )
    scratch_repository.write("README.md", "scratch repo\n")
    scratch_repository.commit_everything("initial commit")
    scratch_repository.publish_notes_branch(
        {
            f".claude/personal/plans/{PLAN_IDENTIFIER}/plan.yaml": PLAN_MANIFEST,
            f".claude/personal/plans/{PLAN_IDENTIFIER}/roadmap.md": PLAN_ROADMAP,
        }
    )
    scratch_repository.resolve_notes_remote_to()
    scratch_repository.add_work_remote()
    return scratch_repository


def published_plan(repository: ScratchRepository) -> tuple[str, str]:
    """
    Read the manifest and roadmap actually on the notes branch, rather than what a run
    reported.

    :param repository: The scratch repository whose notes remote to read.
    :return: The manifest text and the roadmap text.
    """
    checkout = repository.project_root.parent / "published-plan-checkout"
    if checkout.exists():
        subprocess.run(["rm", "-rf", str(checkout)], check=True)
    repository.clone_notes_branch(checkout)
    plan_directory = checkout / ".claude" / "personal" / "plans" / PLAN_IDENTIFIER
    return (
        (plan_directory / "plan.yaml").read_text(),
        (plan_directory / "roadmap.md").read_text(),
    )


def roadmap_section(repository: ScratchRepository, content: str) -> Path:
    """
    Write a roadmap section to a scratch file, the way a caller hands one over.

    :param repository: The scratch repository to write within.
    :param content: The section's markdown.
    :return: The path written to.
    """
    return repository.write("section.md", content)


# %% recording an item


def test_recording_an_existing_item_sets_its_status(
    bootstrap_repository: ScratchRepository,
):
    result = record_item(
        ItemRecordRequest(
            plan_identifier=PLAN_IDENTIFIER,
            item_identifier="an-existing-item",
            status=ItemStatus.IN_PROGRESS,
            roadmap_section_path=roadmap_section(
                bootstrap_repository, "## A new section\n"
            ),
        ),
        project_root=bootstrap_repository.project_root,
    )

    assert result.exit_code is ExitCode.SUCCESS
    manifest, _ = published_plan(bootstrap_repository)
    assert "    status: in_progress\n" in manifest


def test_recording_leaves_every_other_manifest_line_byte_identical(
    bootstrap_repository: ScratchRepository,
):
    record_item(
        ItemRecordRequest(
            plan_identifier=PLAN_IDENTIFIER,
            item_identifier="an-existing-item",
            status=ItemStatus.IN_PROGRESS,
            roadmap_section_path=roadmap_section(bootstrap_repository, "## Section\n"),
        ),
        project_root=bootstrap_repository.project_root,
    )

    manifest, _ = published_plan(bootstrap_repository)
    expected = PLAN_MANIFEST.replace(
        "    status: not_started\n", "    status: in_progress\n", 1
    )
    assert manifest == expected


def test_recording_appends_the_roadmap_section_without_rewriting_the_roadmap(
    bootstrap_repository: ScratchRepository,
):
    record_item(
        ItemRecordRequest(
            plan_identifier=PLAN_IDENTIFIER,
            item_identifier="an-existing-item",
            status=ItemStatus.IN_PROGRESS,
            roadmap_section_path=roadmap_section(
                bootstrap_repository, "## An appended section\n\nIts body.\n"
            ),
        ),
        project_root=bootstrap_repository.project_root,
    )

    _, roadmap = published_plan(bootstrap_repository)
    assert roadmap.startswith(PLAN_ROADMAP)
    assert roadmap.endswith("## An appended section\n\nIts body.\n")


def test_recording_a_new_item_appends_it_to_the_manifest(
    bootstrap_repository: ScratchRepository,
):
    record_item(
        ItemRecordRequest(
            plan_identifier=PLAN_IDENTIFIER,
            item_identifier="a-brand-new-item",
            title="A brand new item",
            track="a-track",
            status=ItemStatus.NOT_STARTED,
            roadmap_section_path=roadmap_section(bootstrap_repository, "## New\n"),
        ),
        project_root=bootstrap_repository.project_root,
    )

    manifest, _ = published_plan(bootstrap_repository)
    assert manifest.startswith(PLAN_MANIFEST)
    assert manifest.endswith(
        "  - id: a-brand-new-item\n"
        '    title: "A brand new item"\n'
        "    branch: null\n"
        "    track: a-track\n"
        "    depends_on: []\n"
        "    status: not_started\n"
    )


def test_recording_a_new_item_without_a_title_is_refused(
    bootstrap_repository: ScratchRepository,
):
    with pytest.raises(plan_item_bootstrap.IncompleteNewItemError):
        record_item(
            ItemRecordRequest(
                plan_identifier=PLAN_IDENTIFIER,
                item_identifier="a-brand-new-item",
                track="a-track",
                status=ItemStatus.NOT_STARTED,
                roadmap_section_path=roadmap_section(bootstrap_repository, "## New\n"),
            ),
            project_root=bootstrap_repository.project_root,
        )


def test_recording_against_an_unknown_plan_is_refused(
    bootstrap_repository: ScratchRepository,
):
    with pytest.raises(UnknownPlanError):
        record_item(
            ItemRecordRequest(
                plan_identifier="no-such-plan",
                item_identifier="an-existing-item",
                status=ItemStatus.IN_PROGRESS,
                roadmap_section_path=roadmap_section(bootstrap_repository, "## S\n"),
            ),
            project_root=bootstrap_repository.project_root,
        )


# %% opening the work


def open_request(**overrides: object) -> WorkOpenRequest:
    """
    Build a work-open request, overriding only what a test cares about.

    :param overrides: Fields to replace on the default request.
    :return: The request.
    """
    defaults = dict(
        plan_identifier=PLAN_IDENTIFIER,
        item_identifier="an-existing-item",
        branch="claude/a-new-branch",
        base_branch=WORK_BRANCH,
        session_url="https://example.invalid/session_first",
        pull_request_title="An item that has not been started",
        pull_request_body="What it does.",
    )
    defaults.update(overrides)
    return WorkOpenRequest(**defaults)


def test_opening_writes_the_branch_pull_request_and_session_onto_the_item(
    bootstrap_repository: ScratchRepository,
):
    opener = RecordingPullRequestOpener(number=143)

    result = open_work(
        open_request(),
        project_root=bootstrap_repository.project_root,
        pull_request_opener=opener,
    )

    assert result.exit_code is ExitCode.SUCCESS
    assert result.pull_request_number == 143
    manifest, _ = published_plan(bootstrap_repository)
    assert "    branch: claude/a-new-branch\n" in manifest
    assert "    pull_request_number: 143\n" in manifest
    assert "    session: https://example.invalid/session_first\n" in manifest
    assert "    status: in_progress\n" in manifest


def test_opening_asks_for_a_draft_pull_request_against_the_plans_repository(
    bootstrap_repository: ScratchRepository,
):
    opener = RecordingPullRequestOpener()

    open_work(
        open_request(),
        project_root=bootstrap_repository.project_root,
        pull_request_opener=opener,
    )

    assert len(opener.requests) == 1
    request = opener.requests[0]
    assert request.draft is True
    assert request.repository == "an-owner/a-repository"
    assert request.head == "claude/a-new-branch"
    assert request.base == WORK_BRANCH


def test_opening_publishes_the_branch_to_the_repositorys_own_remote(
    bootstrap_repository: ScratchRepository,
):
    open_work(
        open_request(),
        project_root=bootstrap_repository.project_root,
        pull_request_opener=RecordingPullRequestOpener(),
    )

    published = bootstrap_repository.run_git(
        "ls-remote",
        "--heads",
        str(bootstrap_repository.work_remote_path),
        "claude/a-new-branch",
    )
    assert "claude/a-new-branch" in published.stdout


def test_opening_an_already_published_branch_is_refused(
    bootstrap_repository: ScratchRepository,
):
    opener = RecordingPullRequestOpener()
    open_work(
        open_request(),
        project_root=bootstrap_repository.project_root,
        pull_request_opener=opener,
    )

    with pytest.raises(plan_item_bootstrap.BranchAlreadyPublishedError):
        open_work(
            open_request(),
            project_root=bootstrap_repository.project_root,
            pull_request_opener=opener,
        )
    assert len(opener.requests) == 1


def test_opening_an_unknown_item_is_refused_before_anything_is_created(
    bootstrap_repository: ScratchRepository,
):
    opener = RecordingPullRequestOpener()

    with pytest.raises(UnknownItemError):
        open_work(
            open_request(item_identifier="no-such-item"),
            project_root=bootstrap_repository.project_root,
            pull_request_opener=opener,
        )

    assert opener.requests == []
    published = bootstrap_repository.run_git(
        "ls-remote", "--heads", str(bootstrap_repository.work_remote_path)
    )
    assert "claude/a-new-branch" not in published.stdout


def test_a_refused_pull_request_leaves_the_manifest_untouched(
    bootstrap_repository: ScratchRepository,
):
    with pytest.raises(plan_item_bootstrap.PullRequestRefusedError):
        open_work(
            open_request(),
            project_root=bootstrap_repository.project_root,
            pull_request_opener=RefusingPullRequestOpener(),
        )

    manifest, _ = published_plan(bootstrap_repository)
    assert manifest == PLAN_MANIFEST


def test_a_refused_pull_request_leaves_the_branch_it_already_published(
    bootstrap_repository: ScratchRepository,
):
    with pytest.raises(plan_item_bootstrap.PullRequestRefusedError):
        open_work(
            open_request(),
            project_root=bootstrap_repository.project_root,
            pull_request_opener=RefusingPullRequestOpener(),
        )

    published = bootstrap_repository.run_git(
        "ls-remote",
        "--heads",
        str(bootstrap_repository.work_remote_path),
        "claude/a-new-branch",
    )
    assert "claude/a-new-branch" in published.stdout


def test_a_supplied_pull_request_number_is_recorded_without_creating_one(
    bootstrap_repository: ScratchRepository,
):
    opener = RecordingPullRequestOpener()

    result = open_work(
        open_request(pull_request_number=57),
        project_root=bootstrap_repository.project_root,
        pull_request_opener=opener,
    )

    assert opener.requests == []
    assert result.pull_request_number == 57
    manifest, _ = published_plan(bootstrap_repository)
    assert "    pull_request_number: 57\n" in manifest


def test_creating_a_pull_request_without_a_title_or_body_is_refused_before_publishing(
    bootstrap_repository: ScratchRepository,
):
    with pytest.raises(plan_item_bootstrap.PullRequestDetailsMissingError):
        open_work(
            open_request(pull_request_title=None, pull_request_body=None),
            project_root=bootstrap_repository.project_root,
            pull_request_opener=RecordingPullRequestOpener(),
        )

    published = bootstrap_repository.run_git(
        "ls-remote", "--heads", str(bootstrap_repository.work_remote_path)
    )
    assert "claude/a-new-branch" not in published.stdout


def test_a_supplied_pull_request_number_adopts_the_branch_its_caller_published(
    bootstrap_repository: ScratchRepository,
):
    open_work(
        open_request(),
        project_root=bootstrap_repository.project_root,
        pull_request_opener=RecordingPullRequestOpener(number=99),
    )

    result = open_work(
        open_request(pull_request_number=57),
        project_root=bootstrap_repository.project_root,
        pull_request_opener=RecordingPullRequestOpener(),
    )

    assert result.pull_request_number == 57


# %% exit statuses


def test_every_exit_code_names_itself_from_its_own_member():
    for exit_code in ExitCode:
        assert exit_code.name_for_a_caller == exit_code.name.lower()


def test_each_refusal_carries_its_own_exit_code():
    codes = {
        UnknownPlanError: ExitCode.UNKNOWN_PLAN,
        UnknownItemError: ExitCode.UNKNOWN_ITEM,
        plan_item_bootstrap.IncompleteNewItemError: ExitCode.INCOMPLETE_NEW_ITEM,
        plan_item_bootstrap.BranchAlreadyPublishedError: ExitCode.BRANCH_ALREADY_PUBLISHED,
        plan_item_bootstrap.PullRequestDetailsMissingError: (
            ExitCode.PULL_REQUEST_DETAILS_MISSING
        ),
        plan_item_bootstrap.PullRequestRefusedError: ExitCode.PULL_REQUEST_REFUSED,
    }
    assert {error: error.exit_code for error in codes} == codes


# %% the command line


def run_bootstrap(
    repository: ScratchRepository, *arguments: str
) -> subprocess.CompletedProcess[str]:
    """
    Run the scratch layout's plan_item_bootstrap.py with *arguments*.

    :param repository: A fixture-built scratch repository.
    :param arguments: CLI arguments to pass.
    :return: The finished subprocess.
    """
    return subprocess.run(
        [
            "python3",
            str(
                repository.project_root / ".claude" / "hooks" / "plan_item_bootstrap.py"
            ),
            *arguments,
        ],
        cwd=repository.project_root,
        capture_output=True,
        text=True,
    )


def test_the_record_subcommand_reports_status_and_exit_code_first(
    bootstrap_repository: ScratchRepository,
):
    section = roadmap_section(bootstrap_repository, "## From the command line\n")

    result = run_bootstrap(
        bootstrap_repository,
        "record",
        "--plan",
        PLAN_IDENTIFIER,
        "--item",
        "an-existing-item",
        "--status",
        "in_progress",
        "--roadmap-section",
        str(section),
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert list(report)[:2] == ["status", "exit_code"]
    assert report["status"] == "success"
    assert report["exit_code"] == 0


def test_the_command_line_names_the_status_it_failed_with(
    bootstrap_repository: ScratchRepository,
):
    section = roadmap_section(bootstrap_repository, "## Section\n")

    result = run_bootstrap(
        bootstrap_repository,
        "record",
        "--plan",
        "no-such-plan",
        "--item",
        "an-existing-item",
        "--status",
        "in_progress",
        "--roadmap-section",
        str(section),
    )

    assert result.returncode == ExitCode.UNKNOWN_PLAN
    assert "unknown_plan" in result.stderr


def test_the_dashboard_republish_is_handed_back_rather_than_attempted(
    bootstrap_repository: ScratchRepository,
):
    section = roadmap_section(bootstrap_repository, "## Section\n")

    result = run_bootstrap(
        bootstrap_repository,
        "record",
        "--plan",
        PLAN_IDENTIFIER,
        "--item",
        "an-existing-item",
        "--status",
        "in_progress",
        "--roadmap-section",
        str(section),
    )

    report = json.loads(result.stdout)
    assert report["dashboard_command"] == f"/plan-dashboard {PLAN_IDENTIFIER}"
