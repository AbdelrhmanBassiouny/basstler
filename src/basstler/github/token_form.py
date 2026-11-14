"""
GitHub's form for a new fine-grained personal access token, filled in from its address.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlencode

from basstler.class_property import classproperty
from basstler.locations import GitHubTemplate
from basstler.render_common import TemplatePage
from basstler.repository import GitHubAddress, Repository

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

    ACTIONS = "actions"
    """
    The repository's workflows and their runs.
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

    @classmethod
    def broadest(cls, levels: list[PermissionLevel]) -> PermissionLevel:
        """
        :param levels: The levels several jobs need on one permission, at least one.
        :return: The level that grants all of them.
        """
        return cls.WRITE if cls.WRITE in levels else cls.READ


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


# %% one token for several jobs


@dataclass(frozen=True)
class TokenUse:
    """
    One job a person's fine-grained token does, and the secret it is stored as.
    """

    purpose: str
    """
    What the token does for this job, as a phrase completing "it ...".
    """

    repositories: tuple[Repository, ...]
    """
    The repositories the job reaches, all of one owner.
    """

    permissions: dict[RepositoryPermission, PermissionLevel]
    """
    The access the job needs on each permission.
    """

    secret: str
    """
    The Actions secret the job's workflows read the token from.
    """

    stored_on: tuple[Repository, ...]
    """
    The repositories whose Actions read :attr:`secret`.
    """

    @property
    def resource_owner(self) -> str:
        """
        The user or organisation whose repositories the job reaches.
        """
        return self.repositories[0].owner


@dataclass(frozen=True)
class StoredSecret:
    """
    One Actions secret a token is stored as, on one repository.
    """

    secret: str
    """
    The secret's name.
    """

    repository: Repository
    """
    The repository storing it.
    """


@dataclass(frozen=True)
class SharedToken(TemplatePage):
    """
    One fine-grained token doing several jobs on one owner's repositories.
    """

    name: str
    """
    The token's name, at most 40 characters.
    """

    uses: tuple[TokenUse, ...]
    """
    The jobs, all reaching one owner's repositories; the first is the one asked for.
    """

    @classmethod
    def joining(
        cls, name: str, first: TokenUse, others: tuple[TokenUse, ...]
    ) -> SharedToken:
        """
        :param name: The token's name.
        :param first: The job the token is asked for.
        :param others: Further jobs, joined where they reach the same owner.
        :return: The token doing *first* and every other job one token can do with it.
        """
        return cls(
            name,
            (
                first,
                *(use for use in others if use.resource_owner == first.resource_owner),
            ),
        )

    @classproperty
    def template(cls) -> str:
        return GitHubTemplate.SHARED_TOKEN_STORE_COMMAND.name

    @property
    def form(self) -> FineGrainedTokenForm:
        """
        The form creating the token, granting each permission the broadest level a job
        needs.
        """
        permissions = {
            permission: PermissionLevel.broadest(
                [
                    use.permissions[permission]
                    for use in self.uses
                    if permission in use.permissions
                ]
            )
            for use in self.uses
            for permission in use.permissions
        }
        return FineGrainedTokenForm(
            self.name,
            self.description,
            self.uses[0].resource_owner,
            permissions,
        )

    @property
    def description(self) -> str:
        """
        What the token does, every job's purpose in turn.
        """
        purposes = "; ".join(use.purpose for use in self.uses)
        return f"{purposes[0].upper()}{purposes[1:]}"

    @property
    def selection(self) -> str:
        """
        The repositories to select under the form's repository access, as a phrase.
        """
        names = [repository.full_name for repository in self.repositories]
        if len(names) == 1:
            return names[0]
        return f"{', '.join(names[:-1])} and {names[-1]}"

    @property
    def repositories(self) -> list[Repository]:
        """
        Every repository a job reaches, each once, in the order the jobs name them.
        """
        return list(
            dict.fromkeys(
                repository for use in self.uses for repository in use.repositories
            )
        )

    @property
    def secrets(self) -> list[StoredSecret]:
        """
        Each secret the token is stored as.
        """
        return [
            StoredSecret(use.secret, repository)
            for use in self.uses
            for repository in use.stored_on
        ]

    @property
    def store_command(self) -> str:
        """
        The command storing the token as every secret in :attr:`secrets`, asking for it
        once.
        """
        if len(self.secrets) == 1:
            (stored,) = self.secrets
            return f"gh secret set {stored.secret} --repo {stored.repository.full_name}"
        return self.render_template(secrets=self.secrets).strip()
