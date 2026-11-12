"""
Tests for :mod:`basstler.plan.merged_items`: recording an item done once GitHub reports
its pull request merged.
"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from datetime import datetime, UTC
from pathlib import Path

import pytest

from basstler.exit_codes import ManifestToolsExitCode
from basstler.github.client import HttpMethod
from basstler.github.exceptions import GitHubUnreachableError
from basstler.locations import ProjectLocation
from basstler.plan.merged_items import (
    MergedItems,
    MergedItemsInEveryPlan,
    MergedItemsLine,
    MergedItemsSummary,
)
from basstler.plan.model import ItemStatus, ManifestKey, PlanDocument, PlanManifest
from basstler.pull_request_source import GitHubPullRequestSource, PullRequestSource
from basstler.pull_request_state import PullRequestRecord, PullRequestState
from basstler.repository import PullRequestReference, Repository

from ..plan_dataset import LandedItemsPlan
from ..github.pull_request_api import refusal
from ..github.recorded_client import RecordedGitHubClient
from ..recorded_pull_requests import RecordedPullRequestSource

# %% the pull requests GitHub reports


MERGED = PullRequestRecord(
    state=PullRequestState.CLOSED,
    merged_at=datetime(2026, 11, 1, tzinfo=UTC),
)
"""
A pull request GitHub reports merged.
"""

OPEN = PullRequestRecord(state=PullRequestState.OPEN)
"""
A pull request GitHub reports still open.
"""


def reference_of(plan: LandedItemsPlan, status: ItemStatus) -> PullRequestReference:
    """
    :param plan: The dataset plan.
    :param status: The status of the item whose pull request to name.
    :return: That item's pull request.
    """
    item = plan.item_with_status(status)
    return PullRequestReference(
        plan.manifest.repository_of(item), item.pull_request_number
    )


@dataclass
class UnreachablePullRequestSource(PullRequestSource):
    """
    A source whose every read gets no answer from GitHub.
    """

    failure: GitHubUnreachableError
    """
    What every read raises.
    """

    def pull_request(self, reference: PullRequestReference) -> PullRequestRecord | None:
        raise self.failure

    def issue_url(self, repository: Repository, number: int) -> str | None:
        raise self.failure


@pytest.fixture
def plan() -> LandedItemsPlan:
    """
    :return: The plan with one landed item, one in progress and one not started.
    """
    return LandedItemsPlan.read()


# %% which items are recorded done


def test_an_item_whose_pull_request_merged_is_recorded_done(plan: LandedItemsPlan):
    """
    An item GitHub reports merged is recorded done.
    """
    in_progress = plan.item_with_status(ItemStatus.IN_PROGRESS)
    source = RecordedPullRequestSource(
        records={reference_of(plan, ItemStatus.IN_PROGRESS): MERGED}
    )

    recorded = MergedItems(plan.manifest, source).recorded_manifest

    assert recorded == plan.manifest.with_items_done({in_progress.identifier})
    assert recorded.item_named(in_progress.identifier).status is ItemStatus.DONE


def test_an_item_whose_pull_request_is_open_stays_as_it_was(plan: LandedItemsPlan):
    """
    An item whose pull request is still open keeps its status.
    """
    source = RecordedPullRequestSource(
        records={reference_of(plan, ItemStatus.IN_PROGRESS): OPEN}
    )

    assert MergedItems(plan.manifest, source).recorded_manifest == plan.manifest


def test_only_items_not_yet_done_are_looked_up(plan: LandedItemsPlan):
    """
    Neither a done item nor one without a pull request is read from GitHub.
    """
    source = RecordedPullRequestSource()

    MergedItems(plan.manifest, source).recorded_manifest

    assert source.looked_up == [reference_of(plan, ItemStatus.IN_PROGRESS)]


# %% recording them in a manifest file


def test_recording_writes_the_items_recorded_done(
    plan: LandedItemsPlan, tmp_path: Path
):
    """
    Recording rewrites the manifest file with the merged items done.
    """
    manifest_path = tmp_path / PlanDocument.MANIFEST
    plan.manifest.write(manifest_path)
    in_progress = plan.item_with_status(ItemStatus.IN_PROGRESS)
    source = RecordedPullRequestSource(
        records={reference_of(plan, ItemStatus.IN_PROGRESS): MERGED}
    )

    status = MergedItems.record(manifest_path, source)

    assert status == ManifestToolsExitCode.SUCCESS
    assert PlanManifest.from_file(manifest_path) == plan.manifest.with_items_done(
        {in_progress.identifier}
    )


def test_a_failed_read_ends_with_its_own_status_and_changes_nothing(
    plan: LandedItemsPlan, tmp_path: Path
):
    """
    A read GitHub does not answer ends with that failure's status, the file untouched.
    """
    manifest_path = tmp_path / PlanDocument.MANIFEST
    plan.manifest.write(manifest_path)
    written = manifest_path.read_text()
    failure = GitHubUnreachableError(HttpMethod.GET, "repos/owner/repo/pulls", "down")

    status = MergedItems.record(manifest_path, UnreachablePullRequestSource(failure))

    assert status == failure.exit_code
    assert manifest_path.read_text() == written


def test_recording_reports_a_repository_it_cannot_read(
    plan: LandedItemsPlan, tmp_path: Path, capsys: pytest.CaptureFixture
):
    manifest_path = tmp_path / PlanDocument.MANIFEST
    plan.manifest.write(manifest_path)
    source = GitHubPullRequestSource(RecordedGitHubClient())

    MergedItems.record(manifest_path, source)

    repository = reference_of(plan, ItemStatus.IN_PROGRESS).repository
    assert source.read_failure_of(repository).error_message() in capsys.readouterr().err


# %% every plan on a notes branch


def notes_root_holding(plan: LandedItemsPlan, root: Path) -> Path:
    """
    :param plan: The dataset plan.
    :param root: An empty directory standing in for a checkout of the notes branch.
    :return: The plan's manifest there, written with an empty branch index beside it.
    """
    manifest_path = (
        root / ProjectLocation.PLANS / plan.manifest.identifier / PlanDocument.MANIFEST
    )
    manifest_path.parent.mkdir(parents=True)
    plan.manifest.write(manifest_path)
    (root / ProjectLocation.PLAN_BRANCH_INDEX).parent.mkdir(parents=True)
    (root / ProjectLocation.PLAN_BRANCH_INDEX).write_text("")
    return manifest_path


def test_every_plan_drops_its_merged_items_as_a_save_would(
    plan: LandedItemsPlan, tmp_path: Path
):
    manifest_path = notes_root_holding(plan, tmp_path)
    in_progress = plan.item_with_status(ItemStatus.IN_PROGRESS)
    source = RecordedPullRequestSource(
        records={reference_of(plan, ItemStatus.IN_PROGRESS): MERGED}
    )

    MergedItemsInEveryPlan(source).apply(tmp_path)

    assert (
        PlanManifest.from_file(manifest_path)
        == plan.manifest.with_items_done(
            {in_progress.identifier}
        ).without_landed_items()
    )


def test_every_plan_whose_items_all_merged_is_removed(
    plan: LandedItemsPlan, tmp_path: Path
):
    manifest_path = notes_root_holding(plan, tmp_path)
    plan_of_pull_requests = PlanManifest(
        {
            **plan.manifest.content,
            ManifestKey.ITEMS.key: [
                item.content
                for item in plan.manifest.items
                if item.pull_request_number is not None
            ],
        }
    )
    plan_of_pull_requests.write(manifest_path)
    source = RecordedPullRequestSource(
        records={reference_of(plan, ItemStatus.IN_PROGRESS): MERGED}
    )

    MergedItemsInEveryPlan(source).apply(tmp_path)

    assert not manifest_path.parent.exists()


def test_every_plan_regenerates_the_branch_index(plan: LandedItemsPlan, tmp_path: Path):
    """
    The index names the branches of the items left, and no longer the landed ones'.
    """
    manifest_path = notes_root_holding(plan, tmp_path)
    queued = plan.item_with_status(ItemStatus.NOT_STARTED)
    queued_branch = "queued-branch"
    PlanManifest(
        {
            **plan.manifest.content,
            ManifestKey.ITEMS.key: [
                {**item.content, ManifestKey.BRANCH.key: queued_branch}
                if item == queued
                else item.content
                for item in plan.manifest.items
            ],
        }
    ).write(manifest_path)
    source = RecordedPullRequestSource(
        records={reference_of(plan, ItemStatus.IN_PROGRESS): MERGED}
    )

    MergedItemsInEveryPlan(source).apply(tmp_path)

    assert (tmp_path / ProjectLocation.PLAN_BRANCH_INDEX).read_text() == (
        f"{queued_branch}\t{plan.manifest.identifier}\n"
    )


def test_every_plan_leaves_the_branch_index_alone_when_nothing_landed(
    plan: LandedItemsPlan, tmp_path: Path
):
    manifest_path = notes_root_holding(plan, tmp_path)
    unlanded = PlanManifest(
        {
            **plan.manifest.content,
            ManifestKey.ITEMS.key: [
                item.content
                for item in plan.manifest.items
                if item.status is not ItemStatus.DONE
            ],
        }
    )
    unlanded.write(manifest_path)
    index = tmp_path / ProjectLocation.PLAN_BRANCH_INDEX
    index.write_text("some-branch\tsome-plan\n")

    MergedItemsInEveryPlan(RecordedPullRequestSource()).apply(tmp_path)

    assert index.read_text() == "some-branch\tsome-plan\n"


def test_every_plan_changes_nothing_when_a_pull_request_cannot_be_read(
    plan: LandedItemsPlan, tmp_path: Path
):
    manifest_path = notes_root_holding(plan, tmp_path)
    written = manifest_path.read_text()
    failure = GitHubUnreachableError(HttpMethod.GET, "repos/owner/repo/pulls", "down")

    with pytest.raises(GitHubUnreachableError):
        MergedItemsInEveryPlan(UnreachablePullRequestSource(failure)).apply(tmp_path)

    assert manifest_path.read_text() == written


def test_every_plan_names_each_item_it_dropped(plan: LandedItemsPlan, tmp_path: Path):
    notes_root_holding(plan, tmp_path)
    landed = plan.item_with_status(ItemStatus.DONE)
    in_progress = plan.item_with_status(ItemStatus.IN_PROGRESS)
    recording = MergedItemsInEveryPlan(
        RecordedPullRequestSource(
            records={reference_of(plan, ItemStatus.IN_PROGRESS): MERGED}
        )
    )

    recording.apply(tmp_path)

    assert recording.summary == MergedItemsSummary(
        dropped_items=sorted(
            f"{plan.manifest.identifier}/{item.identifier}"
            for item in (landed, in_progress)
        )
    )


def test_every_plan_names_each_repository_it_cannot_read(
    plan: LandedItemsPlan, tmp_path: Path
):
    notes_root_holding(plan, tmp_path)
    repository = plan.manifest.default_repository
    recording = MergedItemsInEveryPlan(
        RecordedPullRequestSource(
            read_failures={repository: refusal(repository, HTTPStatus.NOT_FOUND)}
        )
    )

    recording.apply(tmp_path)

    assert recording.summary.unreadable_repositories == {repository}


# %% the summary line


def test_the_summary_line_says_nothing_was_dropped():
    assert MergedItemsSummary().line == MergedItemsLine.NONE


def test_the_summary_line_names_the_dropped_items_and_unreadable_repositories():
    repository = Repository.parse("owner/private")
    summary = MergedItemsSummary(
        dropped_items=["plan/item"], unreadable_repositories={repository}
    )
    assert summary.line == MergedItemsLine.DROPPED.format(
        items="plan/item"
    ) + MergedItemsLine.UNREADABLE.format(repositories=str(repository))
