"""
A branch of a remote, named by the GitHub repository the remote points at.
"""

from __future__ import annotations

from dataclasses import dataclass

from basstler.git.remote_branch import RemoteBranch
from basstler.github.repository import Repository

# %% the branch


@dataclass(frozen=True)
class GitHubRemoteBranch(RemoteBranch):
    """
    A :class:`RemoteBranch` that knows the GitHub repository its remote points at.
    """

    @property
    def repository(self) -> Repository | None:
        """
        :return: The repository the remote points at, ``None`` when it names none - a
            remote given as a local path.
        """
        url = self.url
        if not Repository.names_a_repository(url):
            return None
        return Repository.from_remote_url(url)

    @property
    def description(self) -> str:
        """:return: The repository's name, or the remote's where it names none."""
        repository = self.repository
        return repository.full_name if repository else self.remote
