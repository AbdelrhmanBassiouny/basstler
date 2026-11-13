"""
The reasons the personal-notes setup stops before it finishes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from basstler.class_property import classproperty
from basstler.exceptions import DataclassException
from basstler.exit_codes import CommandFailure, PersonalNotesSetupExitCode
from basstler.github.repository import Repository

if TYPE_CHECKING:
    from basstler.setup.report import SetupCheck


@dataclass
class ForeignNotesRemoteError(CommandFailure, DataclassException, PermissionError):
    """
    Raised when GitHub says the notes remote belongs to somebody other than the caller.
    """

    @classproperty
    def exit_code(cls) -> PersonalNotesSetupExitCode:
        """:return: The status this kind of error ends a command with."""
        return PersonalNotesSetupExitCode.FOREIGN_NOTES_REMOTE

    repository: Repository
    """
    The repository the notes remote names.
    """

    login: str
    """
    The account the available credential belongs to.
    """

    def error_message(self) -> str:
        return (
            f"refusing to set up personal notes on '{self.repository.full_name}': it "
            f"is owned by '{self.repository.owner}', but the credential belongs to "
            f"'{self.login}'"
        )

    def suggest_correction(self) -> str:
        return "pass --remote naming your own fork"


@dataclass
class HookScriptFailedError(CommandFailure, DataclassException, RuntimeError):
    """
    Raised when a hook script a setup step runs exits with a failure.
    """

    @classproperty
    def exit_code(cls) -> PersonalNotesSetupExitCode:
        """:return: The status this kind of error ends a command with."""
        return PersonalNotesSetupExitCode.HOOK_SCRIPT_FAILED

    script: Path
    """
    The script that failed.
    """

    status: int
    """
    The status it exited with.
    """

    def error_message(self) -> str:
        return f"{self.script.name} exited with status {self.status}"

    def suggest_correction(self) -> str:
        return "its own output above says why; fix that and run the setup again"


@dataclass
class CheckSetupFailedError(CommandFailure, DataclassException, RuntimeError):
    """
    Raised when a check-setup.sh run exits with a status that carries no report, or its
    report lacks a requested check or holds a row this package cannot read.
    """

    @classproperty
    def exit_code(cls) -> PersonalNotesSetupExitCode:
        """:return: The status this kind of error ends a command with."""
        return PersonalNotesSetupExitCode.CHECK_SETUP_FAILED

    status: int
    """
    The status check-setup.sh exited with.
    """

    standard_error: str
    """
    What check-setup.sh printed to its standard error.
    """
    missing_checks: list[SetupCheck]
    """
    The requested checks the report has no row for.
    """

    unreadable_rows: list[str]
    """
    The rows naming a check or a status this package does not declare, or not holding a
    check, a status and a detail.
    """

    def error_message(self) -> str:
        problems = [f"check-setup.sh exited with status {self.status}"]
        if self.missing_checks:
            problems.append(f"reported no row for {', '.join(self.missing_checks)}")
        if self.unreadable_rows:
            problems.append(
                f"printed rows this package cannot read: {self.unreadable_rows}"
            )
        return f"{'; '.join(problems)}\nIts standard error:\n{self.standard_error}"

    def suggest_correction(self) -> str:
        return "fix what its standard error names, then run the setup again"
