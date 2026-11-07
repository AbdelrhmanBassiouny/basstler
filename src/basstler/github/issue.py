"""
A GitHub issue, and the requests that open, comment on, close and list issues.
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

    @property
    def payload(self) -> dict[str, Any]:
        """
        The request as the API reads it.
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
class NewIssueComment(IssueRequest):
    """
    A comment to post on an issue.
    """

    body: str
    """
    The comment's Markdown.
    """


@dataclass(frozen=True)
class IssueStateChange(IssueRequest):
    """
    A change of an issue's state.
    """

    state: IssueState
    """
    The state it is set to.
    """

    state_reason: ClosingReason
    """
    Why it is closed.
    """


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
        return urlencode(self.payload)
