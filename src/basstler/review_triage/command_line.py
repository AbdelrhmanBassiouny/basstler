"""
The ``basstler review-triage`` commands: reporting which files of a pull request need
review, and marking the others viewed.
"""

from __future__ import annotations

from pathlib import Path

from cyclopts import App

from basstler.exit_codes import ExitCode
from basstler.github.client import GitHubRestClient
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.repository import PullRequestReference, Repository
from basstler.review_triage.command_names import ReviewTriageCommand
from basstler.review_triage.outputs import MarkdownReport, ViewedMarking
from basstler.review_triage.pull_request import PullRequestReader
from basstler.review_triage.triage import PullRequestTriage, PullRequestTriager
from basstler.review_triage.viewed_request import (
    MarkViewedRequest,
    ViewedMarkingRoutes,
)
from basstler.review_triage.viewed_setup import MarkViewedSetup
from basstler.locations import ClaudeCodeVariable
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its commands print through.
"""

# %% names and exit statuses


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


def named_or_origin(repository: str | None, git: GitCommandRunner) -> Repository:
    """
    :param repository: A repository as ``owner/name``, or ``None``.
    :param git: The current checkout.
    :return: That repository, the checkout's ``origin`` when ``None``.
    """
    if repository:
        return Repository.parse(repository)
    return Repository.from_remote_url(git.run("remote", "get-url", ORIGIN_REMOTE))


def read_triage(
    pull_request: PullRequestReference, git: GitCommandRunner
) -> PullRequestTriage:
    """
    :param pull_request: The pull request.
    :param git: The checkout holding, or fetching, its commits.
    :return: Its triage.
    """
    changes = PullRequestReader(git, GitHubRestClient()).read(
        pull_request.repository, pull_request.number
    )
    return PullRequestTriager().triage(changes)


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
    git = GitCommandRunner(Path.cwd())
    reference = PullRequestReference(named_or_origin(repository, git), pull_request)
    MarkdownReport().publish(read_triage(reference, git))
    return ReviewTriageExitCode.SUCCESS


@review_triage_app.command(name=ReviewTriageCommand.MARK_VIEWED)
def mark_viewed(
    pull_request: int,
    *,
    repository: str | None = None,
    workflow_repository: str | None = None,
    directly: bool = False,
) -> ReviewTriageExitCode:
    """
    Mark a pull request's mechanical files viewed for the logged-in account, or, where
    that fails, ask a repository's Actions to; then print the triage.

    :param pull_request: The pull request's number.
    :param repository: Its repository as ``owner/name``; the checkout's ``origin`` by
        default.
    :param workflow_repository: The repository whose Actions are asked when marking
        directly fails, as ``owner/name``; the checkout's ``origin`` by default.
    :param directly: Only mark them directly, never through Actions, as the workflow
        that marks them does.
    :raises GraphQLMutationRefused: If marking them directly, alone, fails.
    :raises FilesNotMarkedViewed: If neither way marks them.
    """
    git = GitCommandRunner(Path.cwd())
    reference = PullRequestReference(named_or_origin(repository, git), pull_request)
    triage = read_triage(reference, git)
    MarkdownReport().publish(triage)
    routes = ViewedMarkingRoutes(
        ViewedMarking(GitHubRestClient()),
        MarkViewedRequest(named_or_origin(workflow_repository, git), reference),
        GitHubRestClient(),
        ClaudeCodeVariable.REMOTE.is_true(),
        directly,
    )
    logger.info(routes.mark(triage))
    return ReviewTriageExitCode.SUCCESS


@review_triage_app.command(name=ReviewTriageCommand.REQUEST_MARK_VIEWED)
def request_mark_viewed(
    pull_request: int,
    *,
    repository: str | None = None,
    workflow_repository: str | None = None,
) -> ReviewTriageExitCode:
    """
    Ask a repository's mark-viewed workflow to mark a pull request's mechanical files
    viewed, for the account whose token that repository stores.

    :param pull_request: The pull request's number.
    :param repository: Its repository as ``owner/name``; the checkout's ``origin`` by
        default.
    :param workflow_repository: The repository whose workflow marks the files, as
        ``owner/name``; the checkout's ``origin`` by default.
    """
    git = GitCommandRunner(Path.cwd())
    reference = PullRequestReference(named_or_origin(repository, git), pull_request)
    request = MarkViewedRequest(named_or_origin(workflow_repository, git), reference)
    runs = request.send(GitHubRestClient())
    logger.info(
        f"Asked {request.workflow_repository.full_name}'s Actions to mark the "
        f"mechanical files of {reference.url} viewed; the run shows at {runs}"
    )
    return ReviewTriageExitCode.SUCCESS


@review_triage_app.command(name=ReviewTriageCommand.SET_UP_MARK_VIEWED)
def set_up_mark_viewed(
    *,
    workflow_repository: str | None = None,
    repository: str | None = None,
    branch_or_tag: str = "main",
    on_every_pull_request: bool = False,
) -> ReviewTriageExitCode:
    """
    Set a repository's Actions up to mark files viewed, as far as a command can, and
    print what each step came to and the steps left to you.

    :param workflow_repository: The repository whose Actions mark the files, as
        ``owner/name``; the checkout's ``origin`` by default.
    :param repository: The repository the pull requests are opened on; the workflow
        repository's parent, or itself, by default.
    :param branch_or_tag: The basstler branch or tag the installed workflow runs.
    :param on_every_pull_request: Also run it for every pull request opened or updated
        on the workflow repository, which then defaults to the pull requests'.
    """
    git = GitCommandRunner(Path.cwd())
    if on_every_pull_request and workflow_repository is None:
        workflow_repository = repository
    setup = MarkViewedSetup(
        named_or_origin(workflow_repository, git),
        Repository.parse(repository) if repository else None,
        branch_or_tag,
        on_every_pull_request,
    )
    logger.info(setup.run(GitHubRestClient()))
    return ReviewTriageExitCode.SUCCESS
