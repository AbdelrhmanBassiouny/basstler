"""
Fixtures shared by the plan site suites: the dataset's plans built into a site.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from basstler.github.pull_request_state import PullRequestRecord, PullRequestState
from basstler.github.repository import PullRequestReference
from basstler.github.tooling_labels import GitHubLabel
from basstler.plan_site.__main__ import RepositorySite
from basstler.plan_site.hub import NotesBranch, SiteAddress
from basstler.setup.steps import PersonalNotesSetting

from ..constants.paths import DatasetLocation
from ..constants.site import SiteSampleText
from ..recorded_pull_requests import RecordedPullRequestSource
from .test_build_site import (
    FIRST_PLAN,
    MERGED_PULL_REQUEST,
    NOTES_REPOSITORY,
    OPEN_PULL_REQUEST,
    PLAN_REPOSITORY,
)
from .test_hub import publish_notes

# %% recorded pull request state


@pytest.fixture
def pull_request_source() -> RecordedPullRequestSource:
    """
    The live state of the first plan's pull requests, all but one of which exist.
    """
    return RecordedPullRequestSource(
        records={
            MERGED_PULL_REQUEST: PullRequestRecord(
                state=PullRequestState.CLOSED, labels=[GitHubLabel.MERGED.value]
            ),
            OPEN_PULL_REQUEST: PullRequestRecord(
                state=PullRequestState.OPEN, draft=True
            ),
        },
        issue_urls={
            PullRequestReference(
                PLAN_REPOSITORY, FIRST_PLAN.tracking_issue
            ): PLAN_REPOSITORY.issue_url(FIRST_PLAN.tracking_issue)
        },
    )


@pytest.fixture
def dataset_remotes(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    A directory standing in for GitHub, where the notes repository's notes branch holds
    the dataset's plans.
    """
    remotes = tmp_path_factory.mktemp("remotes")
    publish_notes(
        remotes,
        NOTES_REPOSITORY,
        {
            path.relative_to(DatasetLocation.SITE_PLANS.value): path.read_text()
            for path in DatasetLocation.SITE_PLANS.value.rglob("*")
            if path.is_file()
        },
    )
    return remotes


@pytest.fixture
def dataset_notes(
    dataset_remotes: Path, tmp_path_factory: pytest.TempPathFactory
) -> NotesBranch:
    """
    The notes branch :func:`dataset_remotes` published, fetched.
    """
    return NotesBranch.fetch(
        NOTES_REPOSITORY,
        PersonalNotesSetting.BRANCH.default,
        str(dataset_remotes),
        tmp_path_factory.mktemp("scratch"),
    )


@pytest.fixture
def site(
    pull_request_source: RecordedPullRequestSource, dataset_notes: NotesBranch
) -> RepositorySite:
    """
    A site over the dataset's plans directory.
    """
    return RepositorySite(
        address=SiteAddress(SiteSampleText.SITE_URL),
        pull_request_source=pull_request_source,
        notes=dataset_notes,
    )
