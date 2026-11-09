"""
Tests for :mod:`basstler.plan.merged_items`: recording an item done once GitHub reports
its pull request merged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path

import pytest

from basstler.exit_codes import ManifestToolsExitCode
from basstler.github.client import HttpMethod
from basstler.github.exceptions import GitHubUnreachableError
from basstler.plan.merged_items import MergedItems
from basstler.plan.model import ItemStatus, PlanDocument, PlanManifest
from basstler.pull_request_source import PullRequestSource
from basstler.pull_request_state import PullRequestRecord, PullRequestState
from basstler.repository import PullRequestReference, Repository

from ..plan_dataset import LandedItemsPlan
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
