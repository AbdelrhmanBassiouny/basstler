"""
Models of the GitHub REST requests and responses the issue-based plan store exchanges.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import ConfigDict, Field, TypeAdapter
from pydantic.dataclasses import dataclass

from basstler.repository import Repository

# %% validating and serializing


class RestModel:
    """
    A REST body, validated against the model when read and serialized by it when sent.
    """

    @classmethod
    def from_response(cls, body: Any) -> Self:
        """
        :param body: A parsed JSON response.
        :return: The response as this model.
        :raises pydantic.ValidationError: If the response does not fit the model.
        """
        return TypeAdapter(cls).validate_python(body)

    @classmethod
    def from_pages(cls, pages: list[Any]) -> list[Self]:
        """
        :param pages: Every page of a listing, each a JSON array.
        :return: Every entry of every page as this model, first page first.
        """
        return [cls.from_response(entry) for page in pages for entry in page]

    def payload(self) -> dict[str, Any]:
        """
        :return: The JSON body this model is sent as, under GitHub's field names.
        """
        return TypeAdapter(type(self)).dump_python(self, mode="json", by_alias=True)


# %% responses


class IssueState(StrEnum):
    """
    The states REST reports an issue or a pull request in; a merged pull request reads
    as closed.
    """

    OPEN = "open"
    """
    Still open.
    """

    CLOSED = "closed"
    """
    Closed, merged or not.
    """


class TimelineEventKind(StrEnum):
    """
    The kinds of issue timeline event the store reads.
    """

    CROSS_REFERENCED = "cross-referenced"
    """
    Another issue or pull request mentioned this one.
    """


@dataclass(frozen=True)
class RestLabel(RestModel):
    """
    A label on an issue.
    """

    name: str
    """
    The label's name.
    """


@dataclass(frozen=True)
class RestPullRequestLink(RestModel):
    """
    What an issue that is a pull request carries about the pull request.
    """

    merged_at: datetime | None = None
    """
    When the pull request was merged, ``None`` while it is not.
    """


@dataclass(frozen=True, kw_only=True, config=ConfigDict(validate_by_name=True))
class RestIssue(RestModel):
    """
    An issue, or a pull request read as an issue.
    """

    identifier: int = Field(alias="id")
    """
    GitHub's own identifier for the issue, which a sub-issue is added by.
    """

    number: int
    """
    The issue's number in its repository.
    """

    title: str
    """
    The issue's title.
    """

    state: IssueState
    """
    Whether the issue is open.
    """

    html_url: str
    """
    The issue's web page.
    """

    repository_url: str
    """
    The REST address of the repository the issue is opened on.
    """

    body: str | None = None
    """
    The issue's description, ``None`` when it has none.
    """

    labels: tuple[RestLabel, ...] = ()
    """
    The labels the issue carries.
    """

    pull_request: RestPullRequestLink | None = None
    """
    The pull request this issue is, ``None`` for a plain issue.
    """

    @property
    def repository(self) -> Repository:
        """
        The repository the issue is opened on.
        """
        return Repository.from_remote_url(self.repository_url)


@dataclass(frozen=True)
class RestTimelineSource(RestModel):
    """
    The issue or pull request a cross-reference was made from.
    """

    issue: RestIssue
    """
    The referencing issue or pull request.
    """


@dataclass(frozen=True)
class RestTimelineEvent(RestModel):
    """
    One event on an issue's timeline.
    """

    event: str
    """
    The event's kind, one of many more than :class:`TimelineEventKind` names.
    """

    source: RestTimelineSource | None = None
    """
    Where a cross-reference came from, ``None`` for any other kind of event.
    """


# %% requests


@dataclass(frozen=True)
class IssueCreation(RestModel):
    """
    The body that opens an issue.
    """

    title: str
    """
    The new issue's title.
    """

    body: str
    """
    The new issue's description.
    """


@dataclass(frozen=True)
class SubIssueAddition(RestModel):
    """
    The body that makes an issue a sub-issue of another.
    """

    sub_issue_identifier: int = Field(serialization_alias="sub_issue_id")
    """
    The :attr:`RestIssue.identifier` of the issue to add.
    """


@dataclass(frozen=True)
class LabelAddition(RestModel):
    """
    The body that adds labels to an issue.
    """

    labels: tuple[str, ...]
    """
    The names of the labels to add.
    """
