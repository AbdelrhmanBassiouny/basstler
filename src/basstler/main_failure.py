"""
The one issue that stays open while the tests on the default branch fail.

Usage:
    "${BASSTLER_PYTHON}" -m basstler.main_failure record --repository <owner/name>
        --run <run id> --commit <sha> --conclusion <conclusion>
    "${BASSTLER_PYTHON}" -m basstler.main_failure show --repository <owner/name>
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from cyclopts import App

from basstler.github.client import (
    GitHubClient,
    GitHubReader,
    GitHubRestClient,
    HttpMethod,
)
from basstler.github.issue import (
    ClosingReason,
    Issue,
    IssueClosing,
    IssueComment,
    IssueListing,
    IssueState,
    NewIssue,
)
from basstler.github.workflow_run import RunJobPage, WorkflowRun
from basstler.github_labels import GitHubLabel
from basstler.repository import Repository
from basstler.standard_streams import StandardStreamHandler
from basstler.upstream_reviews.vocabulary import CheckOutcome

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% what one run of the tests says about the default branch


class TestsRunVerdict(StrEnum):
    """
    What a finished run of the tests says about the default branch.
    """

    FAILING = "failing"
    """
    The run failed, so the tests on the default branch fail.
    """

    PASSING = "passing"
    """
    The run succeeded, so the tests on the default branch pass.
    """

    UNDECIDED = "undecided"
    """
    The run was cancelled, skipped or otherwise proves nothing.
    """

    @classmethod
    def from_run_check(cls, outcome: CheckOutcome) -> TestsRunVerdict:
        """
        :param outcome: How a run or one of its jobs ended.
        :return: What that says about the default branch.
        """
        if outcome in {
            CheckOutcome.FAILURE,
            CheckOutcome.TIMED_OUT,
            CheckOutcome.STARTUP_FAILURE,
        }:
            return cls.FAILING
        if outcome is CheckOutcome.SUCCESS:
            return cls.PASSING
        return cls.UNDECIDED


@dataclass(frozen=True)
class FinishedRun:
    """
    One finished run of the tests on the default branch, with the jobs that failed.
    """

    repository: Repository
    """
    The repository the run tested.
    """

    workflow_run: WorkflowRun
    """
    The run.
    """

    failed_jobs: tuple[str, ...] = ()
    """
    The names of the jobs that failed, as the run lists them.
    """

    @classmethod
    def read(
        cls, repository: Repository, workflow_run: WorkflowRun, github: GitHubReader
    ) -> FinishedRun:
        """
        :param repository: The repository the run tested.
        :param workflow_run: The finished run.
        :param github: What reads a failed run's jobs.
        :return: The run, with its failed jobs when it failed.
        """
        if (
            TestsRunVerdict.from_run_check(workflow_run.outcome)
            is not TestsRunVerdict.FAILING
        ):
            return cls(repository, workflow_run)
        page = RunJobPage.from_json(
            github.get(RunJobPage.path(repository, workflow_run.identifier))
        )
        failed = tuple(
            job.name
            for job in page.jobs
            if TestsRunVerdict.from_run_check(job.outcome) is TestsRunVerdict.FAILING
        )
        return cls(repository, workflow_run, failed)

    @property
    def verdict(self) -> TestsRunVerdict:
        """
        What the run says about the default branch.
        """
        return TestsRunVerdict.from_run_check(self.workflow_run.outcome)

    @property
    def url(self) -> str:
        """
        The run's page on GitHub.
        """
        return self.repository.workflow_run_url(self.workflow_run.identifier)

    def describe(self) -> str:
        """
        :return: The run, its commit and, when it failed, its failed jobs, as Markdown.
        """
        run = f"[This run]({self.url}) on {self.workflow_run.commit}"
        if self.verdict is not TestsRunVerdict.FAILING:
            return f"{run} passed."
        jobs = ", ".join(f"`{job}`" for job in self.failed_jobs)
        return f"{run} failed in {jobs}."


# %% the issue


@dataclass(frozen=True)
class MainFailureTracker:
    """
    Keeps exactly one issue open, labelled :attr:`GitHubLabel.MAIN_RED`, while the
    default branch's tests fail.
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
        listing = IssueListing(GitHubLabel.MAIN_RED, IssueState.OPEN, per_page=1)
        return f"{self.repository.issues_path}?{listing.query}"

    def open_issue(self, github: GitHubReader) -> Issue | None:
        """
        :param github: What reads the issues.
        :return: The open issue, or ``None`` while the tests pass.
        """
        listed = github.get(self.open_issues_path)
        if not listed:
            return None
        return Issue.from_json(listed[0])

    def record(self, run: FinishedRun, github: GitHubClient) -> Issue | None:
        """
        :param run: The run of the tests that just finished.
        :param github: What reads and writes the issues.
        :return: The issue the run opened, commented on or closed, or ``None`` when it
            changed nothing.
        """
        if run.verdict is TestsRunVerdict.UNDECIDED:
            return None
        issue = self.open_issue(github)
        if run.verdict is TestsRunVerdict.FAILING:
            return self.report_failure(run, issue, github)
        if issue is None:
            return None
        self.report_pass(run, issue, github)
        return issue

    def report_failure(
        self, run: FinishedRun, issue: Issue | None, github: GitHubClient
    ) -> Issue:
        """
        Comment on the open issue, or open one when none is.

        :param run: The failed run.
        :param issue: The issue already open, if there is one.
        :param github: What writes the issues.
        :return: The issue now reporting the failure.
        """
        if issue is not None:
            self.comment(issue, run, github)
            return issue
        opened = github.send(
            HttpMethod.POST,
            self.repository.issues_path,
            NewIssue(
                self.title, run.describe(), [GitHubLabel.BUG, GitHubLabel.MAIN_RED]
            ).to_json(),
        )
        return Issue.from_json(opened)

    def report_pass(self, run: FinishedRun, issue: Issue, github: GitHubClient) -> None:
        """
        Comment the passing run on the open issue and close it as completed.

        :param run: The run that passed.
        :param issue: The open issue.
        :param github: What writes the issues.
        """
        self.comment(issue, run, github)
        github.send(
            HttpMethod.PATCH,
            self.repository.issue_path(issue.number),
            IssueClosing(ClosingReason.COMPLETED).to_json(),
        )

    def comment(self, issue: Issue, run: FinishedRun, github: GitHubClient) -> None:
        """
        Post the run's description on the issue.

        :param issue: The issue to comment on.
        :param run: The run the comment describes.
        :param github: What writes the comment.
        """
        github.send(
            HttpMethod.POST,
            self.repository.issue_comments_path(issue.number),
            IssueComment(run.describe()).to_json(),
        )


# %% the command line

app = App(help=__doc__)
"""
The commands recording a run and showing the open issue.
"""


@app.command
def record(repository: str, run: int, commit: str, conclusion: str) -> None:
    """
    Open, comment on or close the issue after a run of the tests on the default branch.

    :param repository: The tested repository, as ``owner/name``.
    :param run: The Actions run's own number.
    :param commit: The commit the run tested.
    :param conclusion: How the run ended, as Actions spells it.
    """
    tested = Repository.parse(repository)
    github = GitHubRestClient()
    workflow_run = WorkflowRun(run, commit, CheckOutcome.from_conclusion(conclusion))
    issue = MainFailureTracker(tested).record(
        FinishedRun.read(tested, workflow_run, github), github
    )
    if issue is not None:
        logger.info(issue.url)


@app.command
def show(repository: str) -> None:
    """
    Print the open issue's page, or nothing while the tests pass.

    :param repository: The repository, as ``owner/name``.
    """
    issue = MainFailureTracker(Repository.parse(repository)).open_issue(
        GitHubRestClient()
    )
    if issue is not None:
        logger.info(issue.url)


if __name__ == "__main__":
    app()
