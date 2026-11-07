"""
The one issue that stays open while the tests on the default branch fail.

Usage:
    "${BASSTLER_PYTHON}" -m basstler.main_failure record --repository <owner/name>
        --run <run id> --commit <sha> --conclusion <conclusion>
    "${BASSTLER_PYTHON}" -m basstler.main_failure show --repository <owner/name>
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum
from typing import Any
from urllib.parse import urlencode

from cyclopts import App

from basstler.github.client import (
    GitHubClient,
    GitHubReader,
    GitHubRestClient,
    HttpMethod,
)
from basstler.github_labels import GitHubLabel
from basstler.repository import Repository
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% what the issues API reads and writes


class IssueField(StrEnum):
    """
    The fields of an issue this module writes or reads.
    """

    NUMBER = "number"
    """
    The issue's number in its repository.
    """

    HTML_URL = "html_url"
    """
    The issue's page on GitHub.
    """

    TITLE = "title"
    """
    The issue's title.
    """

    BODY = "body"
    """
    The issue's description, or a comment's text.
    """

    LABELS = "labels"
    """
    The names of the labels it carries.
    """

    STATE = "state"
    """
    Whether it is open or closed.
    """

    STATE_REASON = "state_reason"
    """
    Why it was closed.
    """


class IssueListingParameter(StrEnum):
    """
    The query parameters of the issue listing this module sends.
    """

    LABELS = "labels"
    STATE = "state"
    PER_PAGE = "per_page"


class IssueState(StrEnum):
    """
    The states an issue is listed or set in.
    """

    OPEN = "open"
    CLOSED = "closed"


class ClosingReason(StrEnum):
    """
    Why an issue is closed.
    """

    COMPLETED = "completed"
    """
    The tests pass again.
    """


@dataclass(frozen=True)
class ReportedIssue:
    """
    The issue reporting the failing tests, as GitHub returned it.
    """

    number: int
    """
    Its number in the repository.
    """

    url: str
    """
    Its page on GitHub.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ReportedIssue:
        """
        :param data: An issue as the issues API returns it.
        :return: The parsed issue.
        """
        return cls(data[IssueField.NUMBER], data[IssueField.HTML_URL])


# %% what one run of the tests concluded


class RunConclusion(StrEnum):
    """
    The conclusions Actions reports for a finished run or job.
    """

    SUCCESS = "success"
    FAILURE = "failure"
    TIMED_OUT = "timed_out"
    STARTUP_FAILURE = "startup_failure"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    NEUTRAL = "neutral"
    ACTION_REQUIRED = "action_required"
    STALE = "stale"

    @property
    def outcome(self) -> RunOutcome:
        """
        What a run ending so says about the default branch.
        """
        if self in {self.FAILURE, self.TIMED_OUT, self.STARTUP_FAILURE}:
            return RunOutcome.FAILED
        if self is self.SUCCESS:
            return RunOutcome.PASSED
        return RunOutcome.UNDECIDED


class RunOutcome(Enum):
    """
    What a run of the tests on the default branch says about it.
    """

    FAILED = "failed"
    """
    The run failed.
    """

    PASSED = "passed"
    """
    The run succeeded.
    """

    UNDECIDED = "undecided"
    """
    The run was cancelled, skipped or otherwise proves nothing.
    """


class JobField(StrEnum):
    """
    The fields of a run's job listing this module reads.
    """

    JOBS = "jobs"
    NAME = "name"
    CONCLUSION = "conclusion"


JOBS_PER_PAGE = 100
"""
The most jobs GitHub returns in one page.
"""


@dataclass(frozen=True)
class FinishedRun:
    """
    One finished run of the tests on the default branch.
    """

    repository: Repository
    """
    The repository the run tested.
    """

    run_id: int
    """
    The Actions run's own number.
    """

    commit: str
    """
    The commit the run tested.
    """

    conclusion: RunConclusion
    """
    How the run ended.
    """

    failed_jobs: tuple[str, ...] = ()
    """
    The names of the jobs that failed, as the run lists them.
    """

    @classmethod
    def read(
        cls,
        repository: Repository,
        run_id: int,
        commit: str,
        conclusion: RunConclusion,
        github: GitHubReader,
    ) -> FinishedRun:
        """
        :param repository: The repository the run tested.
        :param run_id: The Actions run's own number.
        :param commit: The commit the run tested.
        :param conclusion: How the run ended.
        :param github: What reads a failed run's jobs.
        :return: The run, with its failed jobs when it failed.
        """
        if conclusion.outcome is not RunOutcome.FAILED:
            return cls(repository, run_id, commit, conclusion)
        listed = github.get(
            f"{repository.workflow_run_path(run_id)}/jobs?per_page={JOBS_PER_PAGE}"
        )
        failed = tuple(
            job[JobField.NAME]
            for job in listed[JobField.JOBS]
            if RunConclusion(job[JobField.CONCLUSION]).outcome is RunOutcome.FAILED
        )
        return cls(repository, run_id, commit, conclusion, failed)

    @property
    def url(self) -> str:
        """
        The run's page on GitHub.
        """
        return self.repository.workflow_run_url(self.run_id)

    def describe(self) -> str:
        """
        :return: The run, its commit and its failed jobs, as an issue's Markdown.
        """
        jobs = ", ".join(f"`{job}`" for job in self.failed_jobs)
        return f"[This run]({self.url}) on {self.commit} failed in {jobs}."


# %% the issue


@dataclass(frozen=True)
class MainFailureIssue:
    """
    Opens, updates and closes the one issue reporting that the default branch's tests
    fail.
    """

    repository: Repository
    """
    The repository whose default branch is tested.
    """

    title: str = "The tests on main are failing"
    """
    The title the issue is opened with.
    """

    @property
    def open_issues_path(self) -> str:
        """
        The listing of the open issue, if there is one.
        """
        query = urlencode(
            {
                IssueListingParameter.LABELS: GitHubLabel.MAIN_RED,
                IssueListingParameter.STATE: IssueState.OPEN,
                IssueListingParameter.PER_PAGE: 1,
            }
        )
        return f"{self.repository.issues_path}?{query}"

    def open_issue(self, github: GitHubReader) -> ReportedIssue | None:
        """
        :param github: What reads the issues.
        :return: The open issue, or ``None`` while the tests pass.
        """
        listed = github.get(self.open_issues_path)
        if not listed:
            return None
        return ReportedIssue.from_json(listed[0])

    def record(self, run: FinishedRun, github: GitHubClient) -> ReportedIssue | None:
        """
        :param run: The run of the tests that just finished.
        :param github: What reads and writes the issues.
        :return: The issue the run opened, commented on or closed, or ``None`` when it
            changed nothing.
        """
        if run.conclusion.outcome is RunOutcome.UNDECIDED:
            return None
        issue = self.open_issue(github)
        if run.conclusion.outcome is RunOutcome.FAILED:
            return self.report_failure(run, issue, github)
        if issue is None:
            return None
        self.report_pass(run, issue, github)
        return issue

    def report_failure(
        self, run: FinishedRun, issue: ReportedIssue | None, github: GitHubClient
    ) -> ReportedIssue:
        """
        :param run: The failed run.
        :param issue: The issue already open, if there is one.
        :param github: What writes the issues.
        :return: The issue now reporting the failure.
        """
        if issue is not None:
            self.comment(issue, run.describe(), github)
            return issue
        opened = github.send(
            HttpMethod.POST,
            self.repository.issues_path,
            {
                IssueField.TITLE: self.title,
                IssueField.BODY: run.describe(),
                IssueField.LABELS: [GitHubLabel.BUG, GitHubLabel.MAIN_RED],
            },
        )
        return ReportedIssue.from_json(opened)

    def report_pass(
        self, run: FinishedRun, issue: ReportedIssue, github: GitHubClient
    ) -> None:
        """
        :param run: The run that passed.
        :param issue: The open issue, which it closes.
        :param github: What writes the issues.
        """
        self.comment(issue, f"[This run]({run.url}) on {run.commit} passed.", github)
        github.send(
            HttpMethod.PATCH,
            self.repository.issue_path(issue.number),
            {
                IssueField.STATE: IssueState.CLOSED,
                IssueField.STATE_REASON: ClosingReason.COMPLETED,
            },
        )

    def comment(self, issue: ReportedIssue, text: str, github: GitHubClient) -> None:
        """
        :param issue: The issue to comment on.
        :param text: The comment's Markdown.
        :param github: What writes the comment.
        """
        github.send(
            HttpMethod.POST,
            f"{self.repository.issue_path(issue.number)}/comments",
            {IssueField.BODY: text},
        )


# %% the command line

app = App(help=__doc__)
"""
The commands recording a run and showing the open issue.
"""


@app.command
def record(repository: str, run: int, commit: str, conclusion: RunConclusion) -> None:
    """
    Open, comment on or close the issue after a run of the tests on the default branch.

    :param repository: The tested repository, as ``owner/name``.
    :param run: The Actions run's own number.
    :param commit: The commit the run tested.
    :param conclusion: How the run ended.
    """
    tested = Repository.parse(repository)
    github = GitHubRestClient()
    issue = MainFailureIssue(tested).record(
        FinishedRun.read(tested, run, commit, conclusion, github), github
    )
    if issue is not None:
        logger.info(issue.url)


@app.command
def show(repository: str) -> None:
    """
    Print the open issue's page, or nothing while the tests pass.

    :param repository: The repository, as ``owner/name``.
    """
    issue = MainFailureIssue(Repository.parse(repository)).open_issue(
        GitHubRestClient()
    )
    if issue is not None:
        logger.info(issue.url)


if __name__ == "__main__":
    app()
