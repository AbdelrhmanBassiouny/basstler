"""
Tests for reading the verdict over a fork commit's checks through the REST client the
maintenance pass calls GitHub with.
"""

from __future__ import annotations

from basstler.maintenance.github import (
    CommitReport,
    GitHubRepository,
    ListingParameter,
    RepositoryPath,
)
from basstler.github.states import CombinedCheckState

from ..github.recorded_client import RecordedGitHubClient
from ..upstream_reviews.replay import RecordedRestResponse
from ..upstream_reviews.test_rest import (
    HEAD_SHA,
    NUMBER,
    make_reader,
    pull_request_responses,
)
from .fork import PullRequestHeadRepository

# %% a client answering from recorded pages


def commit_report_path(repository: GitHubRepository, report: CommitReport) -> str:
    """
    :param repository: The repository client the listing is read through.
    :param report: Which listing of the recorded head commit to read.
    :return: The path it is listed from.
    """
    return (
        f"/{repository.repository.api_path}{RepositoryPath.COMMITS}/{HEAD_SHA}/{report}"
        f"?{ListingParameter.PAGE_SIZE}={repository.page_size}"
    )


def a_repository_reporting(
    check_runs: RecordedRestResponse, status: RecordedRestResponse
) -> GitHubRepository:
    """
    :param check_runs: The recorded check-run pages of the head commit.
    :param status: The recorded commit-status pages of the head commit.
    :return: A repository client answering both listings from their recorded pages,
        the check runs spanning more than one page.
    """
    client = RecordedGitHubClient()
    repository = GitHubRepository(PullRequestHeadRepository.FORK.value, client)
    client.pages = {
        commit_report_path(repository, CommitReport.CHECK_RUNS): check_runs.load(),
        commit_report_path(repository, CommitReport.STATUS): status.load(),
    }
    return repository


# %% reading the verdict


def test_the_verdict_covers_every_page_of_check_runs_and_the_commit_statuses():
    repository = a_repository_reporting(
        RecordedRestResponse.CHECK_RUNS, RecordedRestResponse.STATUS
    )
    expected = make_reader(pull_request_responses()).read_current_state(NUMBER).checks

    assert repository.check_state(HEAD_SHA) is expected.state


def test_a_commit_nothing_reported_on_is_not_reported():
    repository = a_repository_reporting(
        RecordedRestResponse.CHECK_RUNS_NONE, RecordedRestResponse.STATUS_NONE
    )

    assert repository.check_state(HEAD_SHA) is CombinedCheckState.NOT_REPORTED
