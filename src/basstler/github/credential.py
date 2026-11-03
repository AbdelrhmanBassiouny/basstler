"""
The token the GitHub REST client authenticates with, and where it came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from basstler.environment import GitHubCredentialVariable

# %% where a token comes from


class CredentialOrigin(StrEnum):
    """
    Where a token not read from a :class:`GitHubCredentialVariable` came from.
    """

    GIVEN = "the token the client was given"
    """
    The caller handed the client its token.
    """

    GH_LOGIN = "gh's login"
    """
    ``gh auth token`` printed it.
    """


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

    origin: GitHubCredentialVariable | CredentialOrigin
    """
    Where the token came from.
    """
