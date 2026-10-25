"""
Krrood's ``DataclassException``, copied rather than imported, which is the boundary
decision 12 records for this tooling, and the errors built on it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import PurePosixPath

from basstler.class_property import classproperty
from basstler.exit_codes import CommandFailure, StackExitCode
from basstler.locations import PluginLocation


class DataclassException(Exception, ABC):
    """
    A base exception class for dataclass-based exceptions.

    Subclasses implement error_message() and suggest_correction(); both are evaluated at
    construction time and composed into the actual exception message (the args passed to
    Exception). A non-empty suggest_correction() is rendered as a trailing "Suggestion:
    ..." line. Subclasses that override __post_init__ must call super().__post_init__()
    at the end.
    """

    def __post_init__(self):
        # BaseException.__new__ bypasses the usual ABC instantiation check, so enforce it here.
        if getattr(type(self), "__abstractmethods__", None):
            raise TypeError(
                f"Can't instantiate abstract class {type(self).__name__} without an implementation of "
                f"{', '.join(sorted(type(self).__abstractmethods__))}."
            )
        message = self.error_message()
        correction = self.suggest_correction()
        if correction:
            message = f"{message}\nSuggestion: {correction}"
        super().__init__(message)

    def __str__(self) -> str:
        # Stdlib mixins like KeyError override __str__ to repr their args; always render the
        # plain message that __post_init__ baked into the args.
        return Exception.__str__(self)

    @abstractmethod
    def error_message(self) -> str:
        """
        :return: A human-readable description of what went wrong.
        """

    @abstractmethod
    def suggest_correction(self) -> str:
        """
        :return: Advice on how to fix the error, or an empty string if there is no specific advice.
        """


@dataclass
class NotesBranchMissingError(DataclassException, RuntimeError):
    """
    Raised when no remote tried holds the personal-notes branch.
    """

    branch: str
    """
    The personal-notes branch that was looked for.
    """

    attempted_remotes: tuple[str, ...]
    """
    Every remote it was fetched from, in order.
    """

    def error_message(self) -> str:
        return (
            f"branch '{self.branch}' doesn't exist yet (tried: "
            f"{', '.join(self.attempted_remotes)})"
        )

    def suggest_correction(self) -> str:
        return f"run {PluginLocation.PERSONAL_NOTES_BRANCH_CREATION_SCRIPT} first"


@dataclass
class UnsafeNotesPathError(DataclassException, ValueError):
    """
    Raised when a path to write on the personal-notes branch could leave it.
    """

    path: PurePosixPath
    """
    The refused path.
    """

    def error_message(self) -> str:
        return f"{self.path} would be written outside the personal-notes branch's root"

    def suggest_correction(self) -> str:
        return "give a path relative to the branch's root, with no '..' component"


@dataclass
class UnresolvableReferenceError(CommandFailure, DataclassException, LookupError):
    """
    Raised when a git reference a decision depends on names no commit in the checkout.
    """

    @classproperty
    def exit_code(cls) -> StackExitCode:
        """:return: The status this kind of error ends a command with."""
        return StackExitCode.GIT_COMMAND_FAILED

    reference: str
    """
    The reference git could not resolve.
    """

    def error_message(self) -> str:
        return f"git cannot resolve '{self.reference}' to a commit in this checkout"

    def suggest_correction(self) -> str:
        return (
            "fetch the branch it names from its remote, and check that the branch "
            "still exists there"
        )
