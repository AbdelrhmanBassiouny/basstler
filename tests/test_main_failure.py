"""
The one issue that stays open while the tests on the default branch fail.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pytest
import yaml

from basstler.github.client import GitHubResponse, HttpMethod
from basstler.github_labels import GitHubLabel
from basstler.main_failure import (
    JOBS_PER_PAGE,
    ClosingReason,
    FinishedRun,
    IssueField,
    IssueState,
    JobField,
    MainFailureIssue,
    ReportedIssue,
    RunConclusion,
    RunOutcome,
)
from basstler.repository import Repository

from .constants.paths import DatasetLocation, RepositoryLocation
from .github.recorded_client import RecordedGitHubClient, SentWrite

# %% a repository whose issues are recorded

REPOSITORY = Repository(owner="owner", name="project")
RUN_ID = 42
COMMIT = "0123456789abcdef0123456789abcdef01234567"
RUN_JOBS_PATH = f"{REPOSITORY.workflow_run_path(RUN_ID)}/jobs?per_page={JOBS_PER_PAGE}"


def recorded(location: DatasetLocation) -> Any:
    """
    :param location: A recorded response.
    :return: It, parsed.
    """
    return json.loads(location.read_text())


@dataclass
class IssueOpeningClient(RecordedGitHubClient):
    """
    Records every write, and answers the opening of an issue as GitHub does.
    """

    def attempt_send(
        self, method: HttpMethod, path: str, payload: Mapping[str, Any]
    ) -> GitHubResponse:
        super().attempt_send(method, path, payload)
        if method is HttpMethod.POST and path == REPOSITORY.issues_path:
            return GitHubResponse(recorded(DatasetLocation.MAIN_FAILURE_OPENED_ISSUE))
        return GitHubResponse(payload)


def client_listing(*issues: DatasetLocation) -> IssueOpeningClient:
    """
    :param issues: The open issues the listing answers with.
    :return: A client whose listing of the open issue answers with them, and which
        lists the recorded failed run's jobs.
    """
    return IssueOpeningClient(
        responses={
            MainFailureIssue(REPOSITORY).open_issues_path: [
                recorded(issue) for issue in issues
            ],
            RUN_JOBS_PATH: recorded(DatasetLocation.MAIN_FAILURE_RUN_JOBS),
        }
    )


def finished_run(conclusion: RunConclusion) -> FinishedRun:
    """
    :param conclusion: How the run ended.
    :return: The run on :data:`REPOSITORY` at :data:`COMMIT`, its jobs read from
        :func:`client_listing`.
    """
    return FinishedRun.read(REPOSITORY, RUN_ID, COMMIT, conclusion, client_listing())


def open_issue() -> ReportedIssue:
    """
    :return: The issue the recorded listing holds.
    """
    return ReportedIssue.from_json(recorded(DatasetLocation.MAIN_FAILURE_OPEN_ISSUE))


def comment_on(issue: ReportedIssue, text: str) -> SentWrite:
    """
    :param issue: The issue commented on.
    :param text: The comment's Markdown.
    :return: The write posting the comment.
    """
    return SentWrite(
        HttpMethod.POST,
        f"{REPOSITORY.issue_path(issue.number)}/comments",
        {IssueField.BODY: text},
    )


# %% what a run concludes


@pytest.mark.parametrize(
    ("conclusion", "outcome"),
    [
        (RunConclusion.FAILURE, RunOutcome.FAILED),
        (RunConclusion.TIMED_OUT, RunOutcome.FAILED),
        (RunConclusion.SUCCESS, RunOutcome.PASSED),
        (RunConclusion.CANCELLED, RunOutcome.UNDECIDED),
        (RunConclusion.SKIPPED, RunOutcome.UNDECIDED),
    ],
)
def test_a_conclusion_decides_what_the_run_says_about_main(conclusion, outcome):
    assert conclusion.outcome is outcome


def test_a_failed_run_names_the_jobs_that_failed_or_timed_out():
    jobs = recorded(DatasetLocation.MAIN_FAILURE_RUN_JOBS)[JobField.JOBS]

    run = finished_run(RunConclusion.FAILURE)

    assert run.failed_jobs == (jobs[1][JobField.NAME], jobs[2][JobField.NAME])


def test_a_passed_run_reads_no_jobs():
    run = FinishedRun.read(
        REPOSITORY, RUN_ID, COMMIT, RunConclusion.SUCCESS, RecordedGitHubClient()
    )

    assert run.failed_jobs == ()


# %% recording a run


def test_the_first_failure_opens_the_issue():
    client = client_listing()
    run = finished_run(RunConclusion.FAILURE)
    issue = MainFailureIssue(REPOSITORY)

    recorded_issue = issue.record(run, client)

    assert recorded_issue == ReportedIssue.from_json(
        recorded(DatasetLocation.MAIN_FAILURE_OPENED_ISSUE)
    )
    assert client.writes == [
        SentWrite(
            HttpMethod.POST,
            REPOSITORY.issues_path,
            {
                IssueField.TITLE: issue.title,
                IssueField.BODY: run.describe(),
                IssueField.LABELS: [GitHubLabel.BUG, GitHubLabel.MAIN_RED],
            },
        )
    ]


def test_a_later_failure_comments_on_the_open_issue():
    client = client_listing(DatasetLocation.MAIN_FAILURE_OPEN_ISSUE)
    run = finished_run(RunConclusion.FAILURE)

    recorded_issue = MainFailureIssue(REPOSITORY).record(run, client)

    assert recorded_issue == open_issue()
    assert client.writes == [comment_on(open_issue(), run.describe())]


def test_a_pass_closes_the_open_issue():
    client = client_listing(DatasetLocation.MAIN_FAILURE_OPEN_ISSUE)

    MainFailureIssue(REPOSITORY).record(finished_run(RunConclusion.SUCCESS), client)

    assert client.writes[-1] == SentWrite(
        HttpMethod.PATCH,
        REPOSITORY.issue_path(open_issue().number),
        {
            IssueField.STATE: IssueState.CLOSED,
            IssueField.STATE_REASON: ClosingReason.COMPLETED,
        },
    )


def test_a_pass_with_no_open_issue_writes_nothing():
    client = client_listing()

    recorded_issue = MainFailureIssue(REPOSITORY).record(
        finished_run(RunConclusion.SUCCESS), client
    )

    assert recorded_issue is None
    assert client.writes == []


@pytest.mark.parametrize("conclusion", [RunConclusion.CANCELLED, RunConclusion.SKIPPED])
def test_an_undecided_run_leaves_the_open_issue_alone(conclusion):
    client = client_listing(DatasetLocation.MAIN_FAILURE_OPEN_ISSUE)

    recorded_issue = MainFailureIssue(REPOSITORY).record(
        finished_run(conclusion), client
    )

    assert recorded_issue is None
    assert client.writes == []


# %% showing the open issue


def test_the_open_issue_is_read_from_the_listing():
    client = client_listing(DatasetLocation.MAIN_FAILURE_OPEN_ISSUE)

    assert MainFailureIssue(REPOSITORY).open_issue(client) == open_issue()


def test_no_open_issue_while_the_tests_pass():
    assert MainFailureIssue(REPOSITORY).open_issue(client_listing()) is None


# %% the workflow recording each run


def test_the_issue_follows_the_same_runs_of_the_tests_as_the_release():
    """
    The release follows every finished run of the tests on main, so the issue reports
    exactly the runs the release reads.
    """
    recording, release = (
        yaml.safe_load(location.read_text())[True]
        for location in (
            RepositoryLocation.MAIN_FAILURE_WORKFLOW,
            RepositoryLocation.RELEASE_WORKFLOW,
        )
    )

    assert recording == release
