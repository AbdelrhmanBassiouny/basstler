"""
Where the live state of the pull requests a plan references is read from.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any

from basstler.github.client import (
    GitHubFullClient,
    GitHubResponse,
    GitHubRestClient,
)
from basstler.github.exceptions import GitHubRequestFailed
from basstler.github.pull_request_record import (
    PullRequestField,
)
from basstler.github.pull_request_state import LivePullRequests, PullRequestRecord
from basstler.github.repository import PullRequestReference, Repository
from basstler.github.repository_access import GitHubRepository
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which reports a repository that cannot be read.
"""

READ_ACCESS_STATUSES = frozenset({HTTPStatus.NOT_FOUND, HTTPStatus.FORBIDDEN})
"""
What GitHub answers a token that is not granted a repository.
"""

# %% live pull request state


class PullRequestSource(ABC):
    """
    Where the live state of the pull requests a plan references comes from.
    """

    @abstractmethod
    def pull_request(self, reference: PullRequestReference) -> PullRequestRecord | None:
        """
        :param reference: The pull request to look up.
        :return: Its live state, or ``None`` if the repository has no such pull request.
        """

    @abstractmethod
    def issue_url(self, repository: Repository, number: int) -> str | None:
        """
        :param repository: The repository the issue or pull request is opened on.
        :param number: Its number.
        :return: Its web page, or ``None`` if the repository has no such number.
        """

    def read_failure_of(self, repository: Repository) -> GitHubRequestFailed | None:
        """
        :param repository: A repository a plan's items name.
        :return: The refusal of the token's access to it, or ``None`` if it can be read;
            ``None`` unless the source finds otherwise.
        """
        return None

    def live_pull_requests_of(
        self, references: Iterable[PullRequestReference]
    ) -> LivePullRequests:
        """
        :param references: The pull requests to read.
        :return: The live state of each of them, and why each repository that cannot be
            read cannot be; a number the repository does not have is left out.
        """
        live_pull_requests = LivePullRequests()
        for reference in references:
            failure = self.read_failure_of(reference.repository)
            if failure is not None:
                live_pull_requests.read_failures[reference.repository] = failure
                continue
            record = self.pull_request(reference)
            if record is not None:
                live_pull_requests.pull_requests_by_repository.setdefault(
                    str(reference.repository), {}
                )[str(reference.number)] = record
        return live_pull_requests


@dataclass
class GitHubPullRequestSource(PullRequestSource):
    """
    Pull request state read from the GitHub REST API, once per repository.

    A repository's pull requests are listed in bulk on first use and kept, so a site
    covering many plans costs a handful of requests rather than one per item. A number
    the listing missed is read on its own. A repository whose details cannot be read is
    not listed.
    """

    client: GitHubFullClient
    """
    How the requests reach GitHub.
    """

    repository_details: dict[Repository, GitHubResponse] = field(default_factory=dict)
    """
    The answer to the read of each repository's details asked about so far.
    """

    listed_repositories: set[Repository] = field(default_factory=set)
    """
    Every repository whose pull requests have been listed into :attr:`pull_requests`.
    """

    pull_requests: dict[PullRequestReference, PullRequestRecord] = field(
        default_factory=dict
    )
    """
    Every pull request read so far, listed or read on its own.
    """

    reads_check_states: bool = True
    """
    Whether the check state of an open pull request is read; off, it stays unknown.
    """

    @classmethod
    def from_environment(
        cls, reads_check_states: bool = True
    ) -> GitHubPullRequestSource:
        """
        :param reads_check_states: Whether open pull requests' check states are read.
        :return: A source authenticating with whichever credential the environment
            carries.
        """
        return cls(client=GitHubRestClient(), reads_check_states=reads_check_states)

    def client_for(self, repository: Repository) -> GitHubRepository:
        """
        :param repository: The repository to call.
        :return: A client for it.
        """
        return GitHubRepository(repository, self.client)

    def read_failure_of(self, repository: Repository) -> GitHubRequestFailed | None:
        """
        See :meth:`PullRequestSource.read_failure_of`: the refusal of the repository's
        details, asked once and reported when refused.

        :raises GitHubCallFailed: If the read fails other than by a refused access.
        """
        if repository in self.repository_details:
            return self.repository_details[repository].failure
        details = self.client.attempt_get(f"/{repository.api_path}")
        failure = details.failure
        if failure is not None and not (
            isinstance(failure, GitHubRequestFailed)
            and failure.status in READ_ACCESS_STATUSES
        ):
            raise failure
        self.repository_details[repository] = details
        if failure is not None:
            logger.warning(
                f"cannot read {repository}, so its pull requests are left out: "
                f"{failure.error_message()}"
            )
        return failure

    def pull_request(self, reference: PullRequestReference) -> PullRequestRecord | None:
        record = self.listed_or_read(reference)
        if (
            record is None
            or not self.reads_check_states
            or not record.has_unread_checks
        ):
            return record
        record.check_state = self.client_for(reference.repository).check_state(
            record.head_commit
        )
        return record

    def listed_or_read(
        self, reference: PullRequestReference
    ) -> PullRequestRecord | None:
        """
        :param reference: The pull request to look up.
        :return: Its state as its repository's listing gave it, read on its own when the
            listing missed it, or ``None`` if the repository has no such pull request or
            cannot be read.
        """
        if self.read_failure_of(reference.repository) is not None:
            return None
        self.list_pull_requests_of(reference.repository)
        if reference not in self.pull_requests:
            api_record = self.read_if_present(
                f"/{reference.repository.pull_request_path(reference.number)}"
            )
            if api_record is None:
                return None
            self.pull_requests[reference] = PullRequestRecord.from_api(api_record)
        return self.pull_requests[reference]

    def issue_url(self, repository: Repository, number: int) -> str | None:
        """
        See :meth:`PullRequestSource.issue_url`; ``None`` also when the repository
        cannot be read.
        """
        if self.read_failure_of(repository) is not None:
            return None
        api_record = self.read_if_present(f"/{repository.issue_path(number)}")
        if api_record is None:
            return None
        return PullRequestField.HTML_URL.read(api_record, number)

    def list_pull_requests_of(self, repository: Repository) -> None:
        """
        Read every pull request on a repository into :attr:`pull_requests`, once.

        :param repository: The repository to list.
        """
        if repository in self.listed_repositories:
            return
        for api_record in self.client_for(repository).all_pull_requests():
            number = PullRequestField.NUMBER.read(api_record)
            self.pull_requests[PullRequestReference(repository, number)] = (
                PullRequestRecord.from_api(api_record)
            )
        self.listed_repositories.add(repository)

    def read_if_present(self, path: str) -> Mapping[str, Any] | None:
        """
        Make one read, treating an absent resource as an answer rather than a failure.

        :param path: The resource's REST path.
        :return: The response, or ``None`` if the API answered that it does not exist.
        :raises GitHubRequestFailed: If the API refused the read for any other reason.
        """
        answer = self.client.attempt_get(path)
        if (
            isinstance(answer.failure, GitHubRequestFailed)
            and answer.failure.status == HTTPStatus.NOT_FOUND
        ):
            return None
        return answer.raise_if_failed()
