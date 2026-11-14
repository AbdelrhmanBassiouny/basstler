"""
GitHub's form for a new fine-grained personal access token, filled in from its address.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlencode

from basstler.repository import GitHubAddress

# %% the form's parameters


class TokenFormParameter(StrEnum):
    """
    The query parameters GitHub fills the form's fields from, other than permissions.
    """

    NAME = "name"
    """
    The token's name, at most 40 characters.
    """

    DESCRIPTION = "description"
    """
    The token's description.
    """

    RESOURCE_OWNER = "target_name"
    """
    The user or organisation whose repositories the token reaches.
    """


class RepositoryPermission(StrEnum):
    """
    The repository permissions the form takes as query parameters.
    """

    CONTENTS = "contents"
    """
    The repository's files and commits.
    """

    PULL_REQUESTS = "pull_requests"
    """
    The repository's pull requests, their reviews and their files' viewed state.
    """


class PermissionLevel(StrEnum):
    """
    The access a fine-grained token's permission grants.
    """

    READ = "read"
    """
    Read only.
    """

    WRITE = "write"
    """
    Read and write.
    """


# %% the filled-in form


@dataclass(frozen=True)
class FineGrainedTokenForm:
    """
    The form with a token's name, description, owner and permissions filled in; the
    repositories it reaches the form cannot be given.
    """

    name: str
    """
    The token's name, at most 40 characters.
    """

    description: str
    """
    What the token is for.
    """

    resource_owner: str
    """
    The user or organisation whose repositories the token reaches.
    """

    permissions: dict[RepositoryPermission, PermissionLevel] = field(
        default_factory=dict
    )
    """
    The access granted on each permission; any other is left without access.
    """

    @property
    def url(self) -> str:
        """
        The form's address with every field filled in.
        """
        query = urlencode(
            {
                TokenFormParameter.NAME: self.name,
                TokenFormParameter.DESCRIPTION: self.description,
                TokenFormParameter.RESOURCE_OWNER: self.resource_owner,
                **self.permissions,
            }
        )
        return f"{GitHubAddress.WEB}/settings/personal-access-tokens/new?{query}"
