"""
The repository the user owns that builds and serves the plan site.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from urllib.parse import urlsplit

from basstler.locations import ProjectLocation, WorkflowLocation
from basstler.maintenance.remote_branch import RemoteBranch
from basstler.plan_site.hub import PlanHub
from basstler.plan_site.workflows import (
    GitHubCommandLineOption,
    PlanSiteJob,
    WorkflowFile,
)
from basstler.repository import Repository

PAGES_HOST_SUFFIX = ".github.io"
"""
What the host of every address GitHub Pages serves a user's site from ends with.
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

    @property
    def site_url(self) -> str:
        """
        :return: The address GitHub Pages serves the repository's site from.
        """
        host = f"{self.repository.owner.lower()}{PAGES_HOST_SUFFIX}"
        if self.repository.name.lower() == host:
            return f"https://{host}/"
        return f"https://{host}/{self.repository.name}/"
