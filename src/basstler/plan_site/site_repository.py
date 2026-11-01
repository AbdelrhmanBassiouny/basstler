"""
The repository the user owns that builds and serves the plan site.
"""

from __future__ import annotations

from dataclasses import dataclass

from basstler.repository import Repository

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

    @property
    def site_url(self) -> str:
        """
        :return: The address GitHub Pages serves the repository's site from.
        """
        host = f"{self.repository.owner.lower()}.github.io"
        if self.repository.name.lower() == host:
            return f"https://{host}/"
        return f"https://{host}/{self.repository.name}/"
