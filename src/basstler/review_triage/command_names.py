"""
The names of the ``basstler review-triage`` commands.
"""

from __future__ import annotations

from enum import StrEnum

from basstler.locations import PackageLocation

# %% the commands


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

    REQUEST_MARK_VIEWED = "request-mark-viewed"
    """
    Ask a repository's Actions to mark a pull request's mechanical files viewed.
    """

    @property
    def invocation(self) -> str:
        """
        The command line running this command.
        """
        return f"{PackageLocation.DIRECTORY.name} {ReviewTriageCommand.GROUP} {self}"
