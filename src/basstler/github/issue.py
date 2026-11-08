"""
A GitHub issue and its comments, and the requests that open, comment on, close and
list issues.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Annotated, Any, Literal
from urllib.parse import urlencode

from pydantic import Field

from basstler.class_property import classproperty
from basstler.github.client import HttpMethod, RepositoryWrite
from basstler.json_model import JSONModel

# %% the values an issue's state is written in


class IssueState(StrEnum):
    """
    The states an issue is listed or set in.
    """

    OPEN = "open"
    CLOSED = "closed"


class ClosingReason(StrEnum):
    """
    Why an issue is closed.
    """

    COMPLETED = "completed"
    """
    What the issue asked for is done.
    """


# %% an issue as GitHub returns it


@dataclass(frozen=True)
class Issue(JSONModel):
    """
    One issue of a repository.
    """

    number: int
    """
    Its number in the repository.
    """

    url: str
    """
    Its page on GitHub.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Issue:
        return cls(data["number"], data["html_url"])


# %% what is sent to GitHub


class NewIssue(RepositoryWrite):
    """
    An issue to open.
    """

    title: str
    """
    The issue's title.
    """

    body: str
    """
    The issue's description, in Markdown.
    """

    labels: list[str]
    """
    The names of the labels it is opened with.
    """

    @classproperty
    def method(cls) -> HttpMethod:
        return HttpMethod.POST

    @property
    def path(self) -> str:
        return self.repository.issues_path


class IssueWrite(RepositoryWrite, ABC):
    """
    A change to one issue or pull request, which GitHub numbers alike.
    """

    number: Annotated[int, Field(exclude=True)]
    """
    The issue's or pull request's number in the repository.
    """


class IssueComment(IssueWrite):
    """
    A comment on an issue or pull request, as it is posted.
    """

    body: str
    """
    The comment's Markdown.
    """

    @classproperty
    def method(cls) -> HttpMethod:
        return HttpMethod.POST

    @property
    def path(self) -> str:
        return self.repository.issue_comments_path(self.number)


@dataclass(frozen=True)
class PostedIssueComment(JSONModel):
    """
    A comment GitHub has recorded, with who posted it and when.
    """

    body: str
    """
    The comment's Markdown.
    """

    author_login: str
    """
    The GitHub login of whoever posted the comment.
    """

    created_at: str
    """
    When the comment was posted, as GitHub's ISO 8601 timestamp.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PostedIssueComment:
        return cls(data["body"], data["user"]["login"], data["created_at"])

    def to_json(self) -> dict[str, Any]:
        """
        :return: The comment in the shape GitHub's issue-comments API returns it.
        """
        return {
            "body": self.body,
            "user": {"login": self.author_login},
            "created_at": self.created_at,
        }

    def formatted(self) -> str:
        """
        :return: The comment as a ``[<login> @ <created_at>]`` line, then its body.
        """
        return f"[{self.author_login} @ {self.created_at}]\n{self.body}"


class IssueClosing(IssueWrite):
    """
    The closing of an issue.
    """

    closing_reason: Annotated[ClosingReason | None, Field(alias="state_reason")] = None
    """
    Why it is closed, or ``None`` to leave the reason unset.
    """

    state: Literal[IssueState.CLOSED] = IssueState.CLOSED
    """
    The state the issue is set to.
    """

    @classproperty
    def method(cls) -> HttpMethod:
        return HttpMethod.PATCH

    @property
    def path(self) -> str:
        return self.repository.issue_path(self.number)


@dataclass(frozen=True)
class IssueListing:
    """
    The query narrowing a listing of a repository's issues.
    """

    labels: str
    """
    The label every listed issue carries.
    """

    state: IssueState
    """
    The state every listed issue is in.
    """

    per_page: int
    """
    How many issues the listing holds.
    """

    @property
    def query(self) -> str:
        """
        The listing's query string.
        """
        return urlencode(asdict(self))
