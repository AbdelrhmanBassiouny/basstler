"""
The failures of a call to the GitHub REST API.
"""

from __future__ import annotations

from dataclasses import dataclass

from basstler.class_property import classproperty
from basstler.exceptions import DataclassException
from basstler.exit_codes import CommandFailure, StackExitCode
from basstler.maintenance.exceptions import ExternalCallFailed


@dataclass
class GitHubCredentialUnavailableError(CommandFailure, RuntimeError):
    """
    Raised when no token is available to authenticate the API calls with.
    """

    @classproperty
    def exit_code(cls) -> StackExitCode:
        """:return: The status this kind of error ends a command with."""
        return StackExitCode.CREDENTIAL_UNAVAILABLE

    variables: tuple[str, ...]
    """
    The environment variables that were consulted.
    """

    def __str__(self) -> str:
        """:return: What was looked for, so the caller can supply it."""
        return (
            f"no GitHub token: set one of {', '.join(self.variables)}, log in with "
            f"`gh auth login`, or run this with a caller that has one"
        )


@dataclass
class GitHubCallFailed(CommandFailure):
    """
    Base for a call to the API that did not succeed.
    """

    @classproperty
    def exit_code(cls) -> StackExitCode:
        """:return: The status this kind of error ends a command with."""
        return StackExitCode.GITHUB_REQUEST_FAILED

    method: str
    """
    The HTTP method used.
    """
    path: str
    """
    The API path called, without the host.
    """

    @property
    def call(self) -> str:
        """:return: The request line, as issued."""
        return f"{self.method} {self.path}"


@dataclass
class GitHubRequestFailed(GitHubCallFailed, ExternalCallFailed):
    """
    Raised when the API refuses a call.
    """


@dataclass
class GitHubUnreachableError(GitHubCallFailed, DataclassException, ConnectionError):
    """
    Raised when a call gets no answer from the API, such as when the network is down.
    """

    reason: str
    """
    What stopped the call.
    """

    def error_message(self) -> str:
        return f"{self.call} got no answer from GitHub: {self.reason}"

    def suggest_correction(self) -> str:
        return "Check the network connection to GitHub, then run the command again."
