"""
The failures of a call to the GitHub REST API.
"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus

from basstler.class_property import classproperty
from basstler.environment import GitHubCredentialVariable
from basstler.exceptions import DataclassException
from basstler.exit_codes import CommandFailure, StackExitCode
from basstler.github.credential import CredentialOrigin
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
class GitHubCallFailed(CommandFailure, DataclassException):
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

    credential_origin: GitHubCredentialVariable | CredentialOrigin
    """
    Where the token the call authenticated with came from.
    """

    @classmethod
    def for_status(
        cls,
        status: int,
        detail: str,
        method: str,
        path: str,
        credential_origin: GitHubCredentialVariable | CredentialOrigin,
    ) -> GitHubRequestFailed:
        """
        :return: The refusal, a :class:`GitHubCredentialRejected` for a 401.
        """
        refusal = GitHubCredentialRejected if status == HTTPStatus.UNAUTHORIZED else cls
        return refusal(
            status=status,
            detail=detail,
            method=method,
            path=path,
            credential_origin=credential_origin,
        )

    @property
    def credential(self) -> str:
        """
        :return: The token the call authenticated with, named by where it came from.
        """
        if isinstance(self.credential_origin, GitHubCredentialVariable):
            return f"the token in {self.credential_origin}"
        return self.credential_origin

    def error_message(self) -> str:
        """
        :return: :meth:`ExternalCallFailed.error_message`, naming the credential.
        """
        return (
            f"{self.call} failed with {self.status} using {self.credential}: "
            f"{self.detail}"
        )


@dataclass
class GitHubCredentialRejected(GitHubRequestFailed):
    """
    Raised when the API rejects the call's token as invalid or expired.
    """

    def error_message(self) -> str:
        """
        :return: That GitHub rejects the credential, unlike
            :meth:`GitHubRequestFailed.error_message`.
        """
        return (
            f"GitHub rejects {self.credential} as invalid or expired: {self.call} "
            f"failed with {self.status}"
        )

    def suggest_correction(self) -> str:
        """
        :return: How to renew the credential, where
            :meth:`ExternalCallFailed.suggest_correction` has no advice.
        """
        return (
            f"Set a valid token in {self.credential_origin} or log in again with "
            "`gh auth login`."
            if isinstance(self.credential_origin, GitHubCredentialVariable)
            else "Log in again with `gh auth login`, or give the client a valid token."
        )


@dataclass
class GitHubUnreachableError(GitHubCallFailed, ConnectionError):
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
