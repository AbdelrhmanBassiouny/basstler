"""
The requests GitHub's pull request endpoints read.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from basstler.github.client import RequestBody
from basstler.repository import Repository

# %% opening a pull request


@dataclass(frozen=True)
class NewPullRequest(RequestBody):
    """
    A pull request that does not exist yet.
    """

    repository: Repository
    """
    The repository to open it on.
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

    def to_json(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "body": self.body,
            "head": self.head,
            "base": self.base,
            "draft": self.draft,
        }


# %% editing a pull request


@dataclass(frozen=True)
class PullRequestDescription(RequestBody):
    """
    A pull request's new description, leaving everything else about it unchanged.
    """

    body: str
    """
    The description, in Markdown.
    """

    def to_json(self) -> dict[str, Any]:
        return asdict(self)
