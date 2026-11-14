"""
The errors triaging a pull request can end in.
"""

from __future__ import annotations

from dataclasses import dataclass

from basstler.class_property import classproperty
from basstler.exceptions import DataclassException
from basstler.locations import BasstlerRepositoryLocation
from basstler.repository import BASSTLER_REPOSITORY, PullRequestReference, Repository
from basstler.review_triage.command_names import ReviewTriageCommand

# %% the routes a correction offers

README_BRANCH = "main"
"""
The branch of basstler's repository whose README a correction links.
"""


class MarkingRoutes:
    """
    The two ways of marking files viewed, as a correction offers them.
    """

    @classproperty
    def readme_url(cls) -> str:
        """
        Where both routes are described, readable from any terminal.
        """
        readme = BasstlerRepositoryLocation.REVIEW_TRIAGE_README.as_posix()
        return f"{BASSTLER_REPOSITORY.url}/blob/{README_BRANCH}/{readme}"

    @classproperty
    def instructions(cls) -> str:
        """
        How to take either route.
        """
        return (
            "Either mark them from a terminal, or a Claude Code session, on your own "
            "computer, where GitHub's GraphQL API is reachable: log gh in as the "
            "account the files are marked viewed for (gh auth login; gh auth refresh "
            "-s repo when its credential may not write pull requests), then run "
            f"{ReviewTriageCommand.MARK_VIEWED.invocation} <number>. Or have a "
            "repository's Actions mark them, from anywhere: run "
            f"{ReviewTriageCommand.SET_UP_MARK_VIEWED.invocation} and take the steps "
            f"it lists. Both are described at {cls.readme_url}"
        )


# %% errors


@dataclass
class GraphQLMutationRefused(DataclassException):
    """
    Raised when GitHub answers a GraphQL mutation with errors.
    """

    messages: tuple[str, ...]
    """
    Every message GitHub reported.
    """

    def error_message(self) -> str:
        return "GitHub refused the mutation: " + "; ".join(self.messages)

    def suggest_correction(self) -> str:
        return MarkingRoutes.instructions


@dataclass
class MarkViewedWorkflowRefused(DataclassException):
    """
    Raised when GitHub refuses to start the workflow marking files viewed.
    """

    workflow_repository: Repository
    """
    The repository whose workflow was to be started.
    """

    reason: str
    """
    What GitHub answered.
    """

    def error_message(self) -> str:
        return (
            f"Could not start the mark-viewed workflow of "
            f"{self.workflow_repository.full_name}: {self.reason}"
        )

    def suggest_correction(self) -> str:
        return MarkingRoutes.instructions


@dataclass
class FilesNotMarkedViewed(DataclassException):
    """
    Raised when neither marking files viewed directly nor through a repository's Actions
    succeeded.
    """

    pull_request: PullRequestReference
    """
    The pull request whose files were to be marked.
    """

    direct_refusal: str
    """
    Why marking them directly failed or was not tried.
    """

    workflow_repository: Repository
    """
    The repository whose Actions were asked next.
    """

    workflow_refusal: str
    """
    Why starting its workflow failed.
    """

    def error_message(self) -> str:
        return (
            f"No file of {self.pull_request.url} was marked viewed. Directly: "
            f"{self.direct_refusal}. Through {self.workflow_repository.full_name}'s "
            f"Actions: {self.workflow_refusal}."
        )

    def suggest_correction(self) -> str:
        return MarkingRoutes.instructions
