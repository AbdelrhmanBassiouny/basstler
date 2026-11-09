"""
Tests for :mod:`basstler.pull_request_source`: reading the live state of a plan's pull
requests from GitHub.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any

import pytest

from basstler.github.states import CombinedCheckState
from basstler.maintenance.board import PullRequestField, PullRequestHeadKey
from basstler.github.exceptions import GitHubRequestFailed
from basstler.maintenance.github import CommitReport, GitHubRepository, RepositoryPath
from basstler.plan.dependencies import DependencyResolver
from basstler.pull_request_source import GitHubPullRequestSource
from basstler.pull_request_state import PullRequestRecord, PullRequestState

from .constants.paths import RecordedCommitChecks
from .constants.site import SiteSampleText
from .github.pull_request_api import (
    api_pull_request,
    details_of,
    listing_path,
    pull_request_path,
)
from .github.recorded_client import RecordedGitHubClient
from .plan_site.first_plan import (
    ELSEWHERE_PULL_REQUEST,
    FIRST_PLAN,
    OPEN_PULL_REQUEST,
    PLAN_REPOSITORY,
)

# %% reading pull requests


def test_github_source_answers_a_listed_pull_request_from_the_listing():
    listed = api_pull_request(OPEN_PULL_REQUEST, {PullRequestField.DRAFT: True})
    source = GitHubPullRequestSource(
        RecordedGitHubClient(
            responses=details_of(OPEN_PULL_REQUEST.repository),
            pages={listing_path(OPEN_PULL_REQUEST.repository): [[listed]]},
        )
    )
    record = source.pull_request(OPEN_PULL_REQUEST)
    assert record == PullRequestRecord.from_api(listed)


def test_github_source_reads_an_unlisted_pull_request_on_its_own():
    unlisted = api_pull_request(OPEN_PULL_REQUEST, {PullRequestField.DRAFT: True})
    source = GitHubPullRequestSource(
        RecordedGitHubClient(
            responses={
                **details_of(OPEN_PULL_REQUEST.repository),
                pull_request_path(OPEN_PULL_REQUEST): unlisted,
            },
            pages={listing_path(OPEN_PULL_REQUEST.repository): [[]]},
        )
    )
    record = source.pull_request(OPEN_PULL_REQUEST)
    assert record == PullRequestRecord.from_api(unlisted)


def test_github_source_answers_none_for_a_pull_request_that_does_not_exist():
    source = GitHubPullRequestSource(
        RecordedGitHubClient(
            responses=details_of(ELSEWHERE_PULL_REQUEST.repository),
            pages={listing_path(ELSEWHERE_PULL_REQUEST.repository): [[]]},
        )
    )
    assert source.pull_request(ELSEWHERE_PULL_REQUEST) is None


def commit_report_path(report: CommitReport) -> str:
    """
    :param report: Which listing reported against :attr:`SiteSampleText.HEAD_COMMIT`
        to read.
    :return: The path it is listed from.
    """
    return (
        f"/{OPEN_PULL_REQUEST.repository.api_path}{RepositoryPath.COMMITS}/"
        f"{SiteSampleText.HEAD_COMMIT}/{report}?per_page={GitHubRepository.page_size}"
    )


def api_pull_request_at_head(state: PullRequestState) -> dict[str, Any]:
    """
    :param state: Whether the pull request is open or closed.
    :return: The open pull request of the first plan, in that state, with its head at
        :attr:`SiteSampleText.HEAD_COMMIT`.
    """
    return api_pull_request(
        OPEN_PULL_REQUEST,
        {
            PullRequestField.STATE: state.value,
            PullRequestField.HEAD: {
                PullRequestHeadKey.COMMIT: SiteSampleText.HEAD_COMMIT.value
            },
        },
    )


def test_github_source_reads_the_checks_of_an_open_pull_request():
    source = GitHubPullRequestSource(
        RecordedGitHubClient(
            responses=details_of(OPEN_PULL_REQUEST.repository),
            pages={
                listing_path(OPEN_PULL_REQUEST.repository): [
                    [api_pull_request_at_head(PullRequestState.OPEN)]
                ],
                commit_report_path(CommitReport.CHECK_RUNS): [
                    json.loads(
                        RecordedCommitChecks.ONE_CHECK_RUN_FAILING.value.read_text()
                    )
                ],
                commit_report_path(CommitReport.STATUS): [
                    json.loads(RecordedCommitChecks.NO_STATUSES.value.read_text())
                ],
            },
        )
    )
    assert (
        source.pull_request(OPEN_PULL_REQUEST).check_state is CombinedCheckState.FAILURE
    )


def test_github_source_leaves_the_checks_of_a_closed_pull_request_unread():
    source = GitHubPullRequestSource(
        RecordedGitHubClient(
            responses=details_of(OPEN_PULL_REQUEST.repository),
            pages={
                listing_path(OPEN_PULL_REQUEST.repository): [
                    [api_pull_request_at_head(PullRequestState.CLOSED)]
                ]
            },
        )
    )
    assert source.pull_request(OPEN_PULL_REQUEST).check_state is None


def test_github_source_reads_an_issue_url():
    issue_url = PLAN_REPOSITORY.issue_url(FIRST_PLAN.tracking_issue)
    source = GitHubPullRequestSource(
        RecordedGitHubClient(
            responses={
                **details_of(PLAN_REPOSITORY),
                f"/{PLAN_REPOSITORY.api_path}/issues/{FIRST_PLAN.tracking_issue}": {
                    PullRequestField.HTML_URL.key: issue_url
                },
            }
        )
    )
    assert source.issue_url(PLAN_REPOSITORY, FIRST_PLAN.tracking_issue) == issue_url


def test_github_source_reraises_a_refusal_other_than_not_found():
    with pytest.raises(GitHubRequestFailed) as refused:
        GitHubPullRequestSource(
            RecordedGitHubClient(
                responses=details_of(PLAN_REPOSITORY), refusal=HTTPStatus.FORBIDDEN
            )
        ).issue_url(PLAN_REPOSITORY, FIRST_PLAN.tracking_issue)
    assert refused.value.status == HTTPStatus.FORBIDDEN


# %% a repository the source cannot read


def test_github_source_answers_none_for_a_pull_request_on_a_repository_it_cannot_read():
    source = GitHubPullRequestSource(RecordedGitHubClient())
    assert source.pull_request(ELSEWHERE_PULL_REQUEST) is None


def test_github_source_finds_a_repository_whose_details_are_refused_unreadable():
    source = GitHubPullRequestSource(
        RecordedGitHubClient(
            responses=details_of(PLAN_REPOSITORY),
            pages={listing_path(PLAN_REPOSITORY): [[]]},
        )
    )
    live_pull_requests = source.live_pull_requests_of(DependencyResolver(FIRST_PLAN))
    assert list(live_pull_requests.read_failures) == [ELSEWHERE_PULL_REQUEST.repository]


@pytest.mark.parametrize(
    "status", [HTTPStatus.UNAUTHORIZED, HTTPStatus.INTERNAL_SERVER_ERROR]
)
def test_github_source_raises_a_failure_that_is_not_a_refused_repository(
    status: HTTPStatus,
):
    source = GitHubPullRequestSource(RecordedGitHubClient(refusal=status))
    with pytest.raises(GitHubRequestFailed) as failed:
        source.read_failure_of(PLAN_REPOSITORY)
    assert failed.value.status == status


def test_github_source_keeps_why_a_repository_cannot_be_read():
    client = RecordedGitHubClient(refusal=HTTPStatus.FORBIDDEN)
    failure = GitHubPullRequestSource(client).read_failure_of(PLAN_REPOSITORY)
    assert failure.status == client.refusal


def test_github_source_reports_a_repository_it_cannot_read(
    capsys: pytest.CaptureFixture,
):
    source = GitHubPullRequestSource(RecordedGitHubClient())
    failure = source.read_failure_of(PLAN_REPOSITORY)
    assert failure.error_message() in capsys.readouterr().err


def test_github_source_answers_no_issue_url_on_a_repository_it_cannot_read():
    source = GitHubPullRequestSource(RecordedGitHubClient(refusal=HTTPStatus.FORBIDDEN))
    assert source.issue_url(PLAN_REPOSITORY, FIRST_PLAN.tracking_issue) is None
