"""
The errors triaging a pull request can end in.
"""

from __future__ import annotations

from dataclasses import dataclass

from basstler.exceptions import DataclassException
from basstler.repository import Repository
from basstler.review_triage.command_names import ReviewTriageCommand

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
        return (
            "Run it where GitHub's GraphQL API is reachable, with a credential of the "
            "account the files are marked viewed for (gh auth status), or have your "
            f"repository's Actions mark them: {ReviewTriageCommand.REQUEST_MARK_VIEWED.invocation}"
        )


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
        return (
            "Set the workflow up as basstler's docs/SETUP.md describes, or run "
            f"{ReviewTriageCommand.MARK_VIEWED.invocation} where gh is logged in"
        )
