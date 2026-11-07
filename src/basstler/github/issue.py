"""
A GitHub issue and its comments, and the requests that open, comment on, close and
list issues.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlencode

from basstler.upstream_reviews.vocabulary import JSONModel

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


@dataclass(frozen=True)
class IssueRequest:
    """
    A request to the issues API, whose fields are named as the API names them.
    """

    def to_json(self) -> dict[str, Any]:
        """
        :return: The request as the API reads it.
        """
        return asdict(self)


@dataclass(frozen=True)
class NewIssue(IssueRequest):
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


@dataclass(frozen=True)
class IssueComment(IssueRequest):
    """
    A comment on an issue or pull request, as it is posted.
    """

    body: str
    """
    The comment's Markdown.
    """


@dataclass(frozen=True)
class PostedIssueComment(IssueComment, JSONModel):
    """
    A comment GitHub has recorded, with who posted it and when.
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


@dataclass(frozen=True)
class IssueClosing(IssueRequest):
    """
    The closing of an issue.
    """

    closing_reason: ClosingReason | None = None
    """
    Why it is closed, or ``None`` to leave the reason unset.
    """

    def to_json(self) -> dict[str, Any]:
        return {"state": IssueState.CLOSED, "state_reason": self.closing_reason}


@dataclass(frozen=True)
class IssueListing(IssueRequest):
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
        return urlencode(self.to_json())
