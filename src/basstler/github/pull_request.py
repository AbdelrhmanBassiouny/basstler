"""
The requests GitHub's pull request endpoints read.
"""

from __future__ import annotations

from basstler.class_property import classproperty
from basstler.github.client import HttpMethod, RepositoryWrite
from basstler.github.issue import IssueWrite

# %% opening a pull request


class NewPullRequest(RepositoryWrite):
    """
    A pull request that does not exist yet.
    """

    title: str
    """
    The pull request's title.
    """

    head: str
    """
    The branch carrying the changes.
    """

    base: str
    """
    The branch to merge into.
    """

    body: str = ""
    """
    The pull request's description.
    """

    draft: bool = True
    """
    Whether it opens as a draft, which a pull request stays until its author has
    reviewed it themselves.
    """

    @classproperty
    def method(cls) -> HttpMethod:
        return HttpMethod.POST

    @property
    def path(self) -> str:
        return self.repository.pull_requests_path


# %% editing a pull request


class PullRequestDescription(IssueWrite):
    """
    A pull request's new description, leaving everything else about it unchanged.
    """

    body: str
    """
    The description, in Markdown.
    """

    @classproperty
    def method(cls) -> HttpMethod:
        return HttpMethod.PATCH

    @property
    def path(self) -> str:
        return self.repository.pull_request_path(self.number)
