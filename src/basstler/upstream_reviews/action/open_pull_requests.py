"""
Reading the upstream's open pull requests through the fork's own Action, for a session
whose credential cannot reach the upstream's API.

The session pushes an :class:`OpenPullRequestsRequest` on a branch of its own; the run
reads the upstream with the runner's own token and commits an
:class:`OpenPullRequestsAnswer` onto that branch; the session fetches it. Nothing is
ever written to the upstream.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from basstler.class_property import classproperty
from basstler.github.pull_request_record import (
    PullRequestField,
    PullRequestHead,
    PullRequestRecord,
)
from basstler.github.repository import Repository
from basstler.github.repository_access import PullRequestReader
from basstler.upstream_reviews.action.exchange import (
    ActionAnswer,
    ActionRequest,
    ActionRequestKind,
)
from basstler.upstream_reviews.action.recording import ActionJSONKey

# %% vocabulary


class OpenPullRequestsKey(StrEnum):
    """
    The keys of a request and of its answer.
    """

    UPSTREAM = "upstream"
    FORK = "fork"
    UPSTREAM_PULL_REQUESTS = "upstream_pull_requests"


# %% the exchange


@dataclass(frozen=True)
class OpenPullRequestsRequest(ActionRequest):
    """
    A request for the upstream's open pull requests opened from the fork's branches.
    """

    upstream: Repository
    """
    The repository to read.
    """

    fork: Repository
    """
    The fork whose branches to look for.
    """

    @classproperty
    def kind(cls) -> ActionRequestKind:
        """
        The read it asks for, which the run dispatches on.
        """
        return ActionRequestKind.OPEN_PULL_REQUESTS

    @classmethod
    def fresh(cls, upstream: Repository, fork: Repository) -> OpenPullRequestsRequest:
        """
        :param upstream: The repository to read.
        :param fork: The fork whose branches to look for.
        :return: A request with an identifier of its own.
        """
        return cls(secrets.token_hex(8), upstream, fork)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> OpenPullRequestsRequest:
        """
        :param data: A pushed request.
        :return: The parsed request.
        """
        return cls(
            data[ActionJSONKey.REQUEST_IDENTIFIER],
            Repository.parse(data[OpenPullRequestsKey.UPSTREAM]),
            Repository.parse(data[OpenPullRequestsKey.FORK]),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            ActionJSONKey.REQUEST_IDENTIFIER: self.identifier,
            OpenPullRequestsKey.UPSTREAM: self.upstream.full_name,
            OpenPullRequestsKey.FORK: self.fork.full_name,
        }


@dataclass(frozen=True)
class OpenPullRequestsAnswer(ActionAnswer):
    """
    The upstream pull requests the run found opened from the fork's branches.
    """

    upstream_pull_requests: UpstreamPullRequests
    """
    Each fork branch under upstream review, and the pull request reviewing it.
    """

    @classmethod
    def answering(
        cls, request: OpenPullRequestsRequest, upstream: PullRequestReader
    ) -> OpenPullRequestsAnswer:
        """
        :param request: The branch's request.
        :param upstream: What reads the upstream, with the runner's credential.
        :return: What the run commits.
        """
        return cls(
            request.identifier,
            UpstreamPullRequests.from_api_records(
                upstream.open_pull_requests(), request.fork
            ),
        )

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> OpenPullRequestsAnswer:
        """
        :param data: A committed answer.
        :return: The parsed answer.
        """
        return cls(
            data[ActionJSONKey.REQUEST_IDENTIFIER],
            UpstreamPullRequests.from_json(
                data[OpenPullRequestsKey.UPSTREAM_PULL_REQUESTS]
            ),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            ActionJSONKey.REQUEST_IDENTIFIER: self.request_identifier,
            OpenPullRequestsKey.UPSTREAM_PULL_REQUESTS: (
                self.upstream_pull_requests.to_json()
            ),
        }


# %% what the run found


# %% what the export reads beside the fork's pull requests


class UpstreamPullRequestsKey(StrEnum):
    """
    The keys :class:`UpstreamPullRequests` is written to JSON under.
    """

    FORK = "fork"
    PULL_REQUEST_BY_BRANCH = "pull_request_by_branch"


@dataclass(frozen=True)
class UpstreamPullRequests:
    """
    The open upstream pull requests opened from the fork's branches.
    """

    fork: Repository
    """
    The fork whose branches are reviewed.
    """

    pull_request_by_branch: Mapping[str, int]
    """
    Each fork branch under review, and the upstream pull request reviewing it.
    """

    def pull_request_for(self, head: PullRequestHead) -> int | None:
        """:param head: A fork pull request's head.
        :return: The open upstream pull request opened from it, ``None`` when there is
            none or the head lives outside the fork."""
        if head.repository != self.fork.full_name:
            return None
        return self.pull_request_by_branch.get(head.branch)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> UpstreamPullRequests:
        """
        :param data: What :meth:`to_json` wrote.
        :return: The pull requests it holds.
        """
        return cls(
            Repository.parse(data[UpstreamPullRequestsKey.FORK]),
            dict(data[UpstreamPullRequestsKey.PULL_REQUEST_BY_BRANCH]),
        )

    def to_json(self) -> dict[str, Any]:
        """:return: The fork and each of its branches' upstream pull request."""
        return {
            UpstreamPullRequestsKey.FORK: self.fork.full_name,
            UpstreamPullRequestsKey.PULL_REQUEST_BY_BRANCH: dict(
                self.pull_request_by_branch
            ),
        }

    @classmethod
    def from_api_records(
        cls, records: Iterable[PullRequestRecord], fork: Repository
    ) -> UpstreamPullRequests:
        """
        :param records: The upstream's open pull requests.
        :param fork: The fork whose branches to look for.
        :return: The ones whose head is a branch of *fork*.
        :raises MissingPullRequestFieldError: If a record omits its number or its head.
        """
        pull_request_by_branch = {}
        for record in records:
            number = int(PullRequestField.NUMBER.read(record))
            head = PullRequestHead.from_record(record, number)
            if head.repository == fork.full_name:
                pull_request_by_branch[head.branch] = number
        return cls(fork, pull_request_by_branch)
