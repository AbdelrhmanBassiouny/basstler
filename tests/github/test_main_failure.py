"""
The one issue that stays open while the tests on the default branch fail.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest
import yaml

from basstler.github import main_failure
from basstler.github.client import GitHubResponse, GitHubWrite
from basstler.github.issue import (
    ClosingReason,
    Issue,
    IssueClosing,
    IssueComment,
    NewIssue,
)
from basstler.github.main_failure import FinishedRun, MainFailureTracker
from basstler.github.repository import Repository
from basstler.github.states import CheckOutcome
from basstler.github.tooling_labels import GitHubLabel
from basstler.github.workflow_run import RunJobPage, WorkflowRun

from ..constants.paths import DatasetLocation, RepositoryLocation
from ..github.recorded_client import RecordedGitHubClient

# %% a repository whose issues are recorded

REPOSITORY = Repository(owner="owner", name="project")
RUN_ID = 42
COMMIT = "0123456789abcdef0123456789abcdef01234567"
RUN_JOBS_PATH = RunJobPage.path(REPOSITORY, RUN_ID)


def recorded(location: DatasetLocation) -> Any:
    """
    :param location: A recorded response.
    :return: It, parsed.
    """
    return json.loads(location.read_text(encoding="utf-8"))


@dataclass
class IssueOpeningClient(RecordedGitHubClient):
    """
    Records every write, and answers the opening of an issue as GitHub does.
    """

    def attempt_send(self, write: GitHubWrite) -> GitHubResponse:
        super().attempt_send(write)
        if isinstance(write, NewIssue):
            return GitHubResponse(recorded(DatasetLocation.MAIN_FAILURE_OPENED_ISSUE))
        return GitHubResponse(write.to_json())


def client_listing(*issues: DatasetLocation) -> IssueOpeningClient:
    """
    :param issues: The open issues the listing answers with.
    :return: A client whose listing of the open issue answers with them, and which
        lists the recorded failed run's jobs.
    """
    return IssueOpeningClient(
        responses={
            MainFailureTracker(REPOSITORY).open_issues_path: [
                recorded(issue) for issue in issues
            ],
            RUN_JOBS_PATH: recorded(DatasetLocation.MAIN_FAILURE_RUN_JOBS),
        }
    )


def finished_run(outcome: CheckOutcome) -> FinishedRun:
    """
    :param outcome: How the run ended.
    :return: The run on :data:`REPOSITORY` at :data:`COMMIT`, its jobs read from
        :func:`client_listing`.
    """
    return FinishedRun.read(
        REPOSITORY, WorkflowRun(RUN_ID, COMMIT, outcome), client_listing()
    )


def open_issue() -> Issue:
    """
    :return: The issue the recorded listing holds.
    """
    return Issue.from_json(recorded(DatasetLocation.MAIN_FAILURE_OPEN_ISSUE))


def comment_on(issue: Issue, run: FinishedRun) -> IssueComment:
    """
    :param issue: The issue commented on.
    :param run: The run the comment describes.
    :return: The write posting the comment.
    """
    return IssueComment(REPOSITORY, issue.number, run.describe())


# %% what a run concludes


@pytest.mark.parametrize(
    ("outcome", "verdict"),
    [
        (CheckOutcome.FAILURE, main_failure.TestsRunVerdict.FAILING),
        (CheckOutcome.TIMED_OUT, main_failure.TestsRunVerdict.FAILING),
        (CheckOutcome.STARTUP_FAILURE, main_failure.TestsRunVerdict.FAILING),
        (CheckOutcome.SUCCESS, main_failure.TestsRunVerdict.PASSING),
        (CheckOutcome.CANCELLED, main_failure.TestsRunVerdict.UNDECIDED),
        (CheckOutcome.SKIPPED, main_failure.TestsRunVerdict.UNDECIDED),
    ],
)
def test_an_outcome_decides_what_the_run_says_about_main(outcome, verdict):
    assert main_failure.TestsRunVerdict.from_run_check(outcome) is verdict


def test_a_failed_run_names_the_jobs_that_failed_or_timed_out():
    jobs = RunJobPage.from_json(recorded(DatasetLocation.MAIN_FAILURE_RUN_JOBS)).jobs

    run = finished_run(CheckOutcome.FAILURE)

    assert run.failed_jobs == (jobs[1].name, jobs[2].name)


def test_a_passed_run_reads_no_jobs():
    run = FinishedRun.read(
        REPOSITORY,
        WorkflowRun(RUN_ID, COMMIT, CheckOutcome.SUCCESS),
        RecordedGitHubClient(),
    )

    assert run.failed_jobs == ()


# %% recording a run


def test_the_first_failure_opens_the_issue():
    """
    With no issue open, a failed run opens one labelled as a red main branch.
    """
    client = client_listing()
    run = finished_run(CheckOutcome.FAILURE)
    issue = MainFailureTracker(REPOSITORY)

    recorded_issue = issue.record(run, client)

    assert recorded_issue == Issue.from_json(
        recorded(DatasetLocation.MAIN_FAILURE_OPENED_ISSUE)
    )
    assert client.writes == [
        NewIssue(
            REPOSITORY,
            issue.title,
            run.describe(),
            [GitHubLabel.BUG, GitHubLabel.MAIN_RED],
        )
    ]


def test_a_later_failure_comments_on_the_open_issue():
    client = client_listing(DatasetLocation.MAIN_FAILURE_OPEN_ISSUE)
    run = finished_run(CheckOutcome.FAILURE)

    recorded_issue = MainFailureTracker(REPOSITORY).record(run, client)

    assert recorded_issue == open_issue()
    assert client.writes == [comment_on(open_issue(), run)]


def test_a_pass_closes_the_open_issue():
    """
    A passing run closes the open issue as completed.
    """
    client = client_listing(DatasetLocation.MAIN_FAILURE_OPEN_ISSUE)

    MainFailureTracker(REPOSITORY).record(finished_run(CheckOutcome.SUCCESS), client)

    assert client.writes[-1] == IssueClosing(
        REPOSITORY, open_issue().number, ClosingReason.COMPLETED
    )


def test_a_pass_with_no_open_issue_writes_nothing():
    client = client_listing()

    recorded_issue = MainFailureTracker(REPOSITORY).record(
        finished_run(CheckOutcome.SUCCESS), client
    )

    assert recorded_issue is None
    assert client.writes == []


@pytest.mark.parametrize("conclusion", [CheckOutcome.CANCELLED, CheckOutcome.SKIPPED])
def test_an_undecided_run_leaves_the_open_issue_alone(conclusion):
    client = client_listing(DatasetLocation.MAIN_FAILURE_OPEN_ISSUE)

    recorded_issue = MainFailureTracker(REPOSITORY).record(
        finished_run(conclusion), client
    )

    assert recorded_issue is None
    assert client.writes == []


# %% showing the open issue


def test_the_open_issue_is_read_from_the_listing():
    client = client_listing(DatasetLocation.MAIN_FAILURE_OPEN_ISSUE)

    assert MainFailureTracker(REPOSITORY).open_issue(client) == open_issue()


def test_no_open_issue_while_the_tests_pass():
    assert MainFailureTracker(REPOSITORY).open_issue(client_listing()) is None


# %% the workflow recording each run


def test_the_issue_follows_the_same_runs_of_the_tests_as_the_release():
    """
    The release follows every finished run of the tests on main, so the issue reports
    exactly the runs the release reads.
    """
    recording, release = (
        yaml.safe_load(location.read_text(encoding="utf-8"))[True]
        for location in (
            RepositoryLocation.MAIN_FAILURE_WORKFLOW,
            RepositoryLocation.RELEASE_WORKFLOW,
        )
    )

    assert recording == release
