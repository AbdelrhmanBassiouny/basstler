"""
The token the GitHub REST client authenticates with, and where it came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# %% where a token comes from


class CredentialOrigin:
    """
    Where the token a GitHub request authenticates with comes from.
    """

    def describe_credential(self) -> str:
        """
        :return: The token, named by where it came from.
        """
        raise NotImplementedError

    def suggest_renewal(self) -> str:
        """
        :return: How to replace the token with a valid one.
        """
        raise NotImplementedError


class CredentialProvider(CredentialOrigin, StrEnum):
    """
    The origins of a token not read from a
    :class:`basstler.environment.GitHubCredentialVariable`.
    """

    CALLER = "the token the client was given"
    """
    The caller handed the client its token.
    """

    GH_LOGIN = "gh's login"
    """
    ``gh auth token`` printed it.
    """

    def describe_credential(self) -> str:
        """
        :return: :meth:`CredentialOrigin.describe_credential`: this provider's value.
        """
        return self.value

    def suggest_renewal(self) -> str:
        """
        :return: :meth:`CredentialOrigin.suggest_renewal` for this provider.
        """
        match self:
            case CredentialProvider.CALLER:
                return "Give the client a valid token."
            case CredentialProvider.GH_LOGIN:
                return "Log in again with `gh auth login`."


# %% the token


@dataclass(frozen=True)
class GitHubCredential:
    """
    A token the client authenticates with, and where it came from.
    """

    token: str = field(repr=False)
    """
    The token, kept out of the representation so it never reaches a log.
    """

    origin: CredentialOrigin
    """
    Where the token came from.
    """
