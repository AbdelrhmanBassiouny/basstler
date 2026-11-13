"""
The ``basstler review-triage`` commands: reporting which files of a pull request need
review, and marking the others viewed.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from cyclopts import App

from basstler.exit_codes import ExitCode
from basstler.github.client import GitHubRestClient
from basstler.locations import PackageLocation
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.repository import Repository
from basstler.review_triage.outputs import MarkdownReport, TriageOutput, ViewedMarking
from basstler.review_triage.pull_request import PullRequestReader
from basstler.review_triage.triage import PullRequestTriager
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its commands print through.
"""

# %% names and exit statuses


class ReviewTriageCommand(StrEnum):
    """
    The ``basstler review-triage`` command group and its commands, by name.
    """

    GROUP = "review-triage"
    """
    The command group itself.
    """

    REPORT = "report"
    """
    Print which files of a pull request need review, as Markdown.
    """

    MARK_VIEWED = "mark-viewed"
    """
    Mark a pull request's mechanical files viewed for the logged-in account.
    """

    @property
    def invocation(self) -> str:
        """
        The command line running this command.
        """
        return f"{PackageLocation.DIRECTORY.name} {ReviewTriageCommand.GROUP} {self}"


class ReviewTriageExitCode(ExitCode):
    """
    What a ``basstler review-triage`` command's exit status means.
    """

    SUCCESS = 0
    """
    The pull request was triaged.
    """


ORIGIN_REMOTE = "origin"
"""
The remote whose repository a pull request is looked up in when none is named.
"""


# %% reading the triage


def publish_triage(
    pull_request: int, repository: str | None, outputs: tuple[TriageOutput, ...]
) -> None:
    """
    Triage a pull request in the current checkout and hand it to each output.

    :param pull_request: The pull request's number.
    :param repository: Its repository as ``owner/name``, the checkout's ``origin`` when
        ``None``.
    :param outputs: Where the triage goes, in order.
    """
    git = GitCommandRunner(Path.cwd())
    resolved = (
        Repository.parse(repository)
        if repository
        else Repository.from_remote_url(git.run("remote", "get-url", ORIGIN_REMOTE))
    )
    changes = PullRequestReader(git, GitHubRestClient()).read(resolved, pull_request)
    triage = PullRequestTriager().triage(changes)
    for output in outputs:
        output.publish(triage)


# %% the commands

review_triage_app = App(
    name=ReviewTriageCommand.GROUP,
    help="Tell a pull request's mechanical files from those a reviewer has to read.",
)
"""
The ``review-triage`` command group.
"""


@review_triage_app.command(name=ReviewTriageCommand.REPORT)
def report(pull_request: int, *, repository: str | None = None) -> ReviewTriageExitCode:
    """
    Print which files of a pull request need review, as Markdown.

    :param pull_request: The pull request's number.
    :param repository: Its repository as ``owner/name``; the checkout's ``origin`` by
        default.
    """
    publish_triage(pull_request, repository, (MarkdownReport(),))
    return ReviewTriageExitCode.SUCCESS


@review_triage_app.command(name=ReviewTriageCommand.MARK_VIEWED)
def mark_viewed(
    pull_request: int, *, repository: str | None = None
) -> ReviewTriageExitCode:
    """
    Mark a pull request's mechanical files viewed for the account whose GitHub
    credential is configured, and print the triage.

    :param pull_request: The pull request's number.
    :param repository: Its repository as ``owner/name``; the checkout's ``origin`` by
        default.
    """
    publish_triage(
        pull_request, repository, (ViewedMarking(GitHubRestClient()), MarkdownReport())
    )
    return ReviewTriageExitCode.SUCCESS
