"""
Fixtures shared by the plan site suites: the dataset's plans built into a site.
"""

from __future__ import annotations

import pytest

from basstler.github_labels import GitHubLabel
from basstler.plan_site.__main__ import RepositorySite
from basstler.pull_request_state import PullRequestRecord, PullRequestState
from basstler.repository import PullRequestReference

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
def site(pull_request_source: RecordedPullRequestSource) -> RepositorySite:
    """
    A site over the dataset's plans directory.
    """
    return RepositorySite(
        site_url=SiteSampleText.SITE_URL,
        pull_request_source=pull_request_source,
        repository=NOTES_REPOSITORY,
        plans_directory=DatasetLocation.SITE_PLANS.value,
    )
