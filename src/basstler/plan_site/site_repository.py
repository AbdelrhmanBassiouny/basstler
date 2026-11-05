"""
The repository the user owns that builds and serves the plan site.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlencode, urlsplit

from basstler.class_property import classproperty
from basstler.locations import ProjectLocation, WorkflowLocation
from basstler.maintenance.remote_branch import RemoteBranch
from basstler.plan_site.hub import PlanHub
from basstler.plan_site.workflows import (
    GitHubCommandLineOption,
    PlanSiteJob,
    WorkflowFile,
)
from basstler.repository import GitHubAddress, Repository

PAGES_HOST_SUFFIX = ".github.io"
"""
What the host of every address GitHub Pages serves a user's site from ends with.
"""

# %% the token that starts the build


class TokenFormField(StrEnum):
    """
    The query parameters GitHub fills its new fine-grained token form from.
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

    ACTIONS = "actions"
    """
    The token's access to repositories' Actions workflows and runs.
    """


class PermissionLevel(StrEnum):
    """
    The access a fine-grained token's permission grants.
    """

    WRITE = "write"
    """
    Read and write.
    """


# %% the site repository


@dataclass(frozen=True)
class SiteRepository:
    """
    The repository the user owns that builds and serves the plan site.
    """

    repository: Repository
    """
    The repository on GitHub.
    """

    @classmethod
    def default_for(
        cls, notes_repository: Repository, name: str = "plans"
    ) -> SiteRepository:
        """
        :param notes_repository: The repository whose plans the site publishes.
        :param name: The site repository's name.
        :return: The repository of that name under the same owner.
        """
        return cls(Repository(notes_repository.owner, name))

    @classmethod
    def from_site_url(cls, site_url: str) -> SiteRepository | None:
        """
        The inverse of :attr:`site_url`, with the owner in the lower case its host has.

        :param site_url: The address the site is served from.
        :return: The repository serving it, ``None`` when it is not on GitHub Pages.
        """
        address = urlsplit(site_url)
        if not address.hostname or not address.hostname.endswith(PAGES_HOST_SUFFIX):
            return None
        owner = address.hostname.removesuffix(PAGES_HOST_SUFFIX)
        name = address.path.strip("/") or address.hostname
        return cls(Repository(owner, name))

    @classmethod
    def from_dispatch_workflow(cls, workflow_text: str) -> SiteRepository:
        """
        :param workflow_text: A dispatch workflow as written on a notes branch.
        :return: The site repository it starts the build in.
        """
        (step,) = WorkflowFile.from_text(workflow_text).jobs[PlanSiteJob.DISPATCH].steps
        words = shlex.split(step.command)
        site = words[words.index(GitHubCommandLineOption.REPOSITORY) + 1]
        return cls(Repository.parse(site))

    @classmethod
    def recorded_on(cls, notes_branch: RemoteBranch) -> SiteRepository | None:
        """
        :param notes_branch: The notes branch.
        :return: The site repository its dispatch workflow starts the build in, else the
            one serving the site its hub file names, ``None`` when it records neither.
        """
        dispatch_text = notes_branch.read_latest(WorkflowLocation.PLAN_SITE_DISPATCH)
        if dispatch_text is not None:
            return cls.from_dispatch_workflow(dispatch_text)
        hub = PlanHub.from_text(notes_branch.read_latest(ProjectLocation.PLAN_HUB))
        if hub is None or hub.site_url is None:
            return None
        return cls.from_site_url(hub.site_url)

    @classproperty
    def token_page(cls) -> str:
        """
        Where a fine-grained token is created.
        """
        return f"{GitHubAddress.WEB}/settings/personal-access-tokens/new"

    def token_form_url(self, token_name: str = "basstler plan site") -> str:
        """
        :param token_name: The name the form fills in.
        :return: :attr:`token_page` with everything filled in that starting the build
            needs, except the repository, which the form cannot be given.
        """
        query = urlencode(
            {
                TokenFormField.NAME: token_name,
                TokenFormField.DESCRIPTION: (
                    f"Starts the plan site build in {self.repository.full_name}"
                ),
                TokenFormField.RESOURCE_OWNER: self.repository.owner,
                TokenFormField.ACTIONS: PermissionLevel.WRITE,
            }
        )
        return f"{self.token_page}?{query}"

    @property
    def site_url(self) -> str:
        """
        :return: The address GitHub Pages serves the repository's site from.
        """
        host = f"{self.repository.owner.lower()}{PAGES_HOST_SUFFIX}"
        if self.repository.name.lower() == host:
            return f"https://{host}/"
        return f"https://{host}/{self.repository.name}/"
