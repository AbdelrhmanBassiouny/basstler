"""
Where the live state of the pull requests a plan references is read from.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any

from basstler.maintenance.board import PullRequestField
from basstler.github.client import GitHubFullClient, GitHubRestClient
from basstler.github.exceptions import GitHubCallFailed, GitHubRequestFailed
from basstler.maintenance.github import GitHubRepository
from basstler.plan.dependencies import DependencyResolver
from basstler.pull_request_state import PullRequestRecord, PullRequestsByRepository
from basstler.repository import PullRequestReference, Repository
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which reports a repository that cannot be read.
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

    def read_failure_of(self, repository: Repository) -> GitHubCallFailed | None:
        """
        :param repository: A repository a plan's items name.
        :return: Why its pull requests cannot be read, or ``None`` if they can; ``None``
            unless the source finds otherwise.
        """
        return None

    def read_failures_of(
        self, dependencies: DependencyResolver
    ) -> dict[Repository, GitHubCallFailed]:
        """
        :param dependencies: A plan's items, plus the items of other plans it depends
            on.
        :return: Why each repository of those items' pull requests that cannot be read
            cannot be, in the order the items name them.
        """
        failures = {}
        for dependency in dependencies.resolved_dependencies:
            if dependency.item.pull_request_number is None:
                continue
            repository = Repository.parse(dependency.repository)
            failure = self.read_failure_of(repository)
            if failure is not None:
                failures[repository] = failure
        return failures

    def pull_requests_of(
        self, dependencies: DependencyResolver
    ) -> PullRequestsByRepository:
        """
        :param dependencies: A plan's items, plus the items of other plans it depends
            on.
        :return: The live state of every pull request those items name, in the shape
            the plan site renders from; a number the repository does not have is left
            out.
        """
        pull_requests: PullRequestsByRepository = {}
        for dependency in dependencies.resolved_dependencies:
            if dependency.item.pull_request_number is None:
                continue
            reference = PullRequestReference(
                Repository.parse(dependency.repository),
                dependency.item.pull_request_number,
            )
            record = self.pull_request(reference)
            if record is not None:
                pull_requests.setdefault(str(reference.repository), {})[
                    str(reference.number)
                ] = record
        return pull_requests


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

    read_failures: dict[Repository, GitHubCallFailed | None] = field(
        default_factory=dict
    )
    """
    Why each repository asked about so far cannot be read, ``None`` for one that can.
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

    @classmethod
    def from_environment(cls) -> GitHubPullRequestSource:
        """
        :return: A source authenticating with whichever credential the environment
            carries.
        """
        return cls(client=GitHubRestClient())

    def client_for(self, repository: Repository) -> GitHubRepository:
        """
        :param repository: The repository to call.
        :return: A client for it.
        """
        return GitHubRepository(repository, self.client)

    def read_failure_of(self, repository: Repository) -> GitHubCallFailed | None:
        """
        See :meth:`PullRequestSource.read_failure_of`: why the repository's details
        cannot be read, asked once and reported when they cannot.
        """
        if repository in self.read_failures:
            return self.read_failures[repository]
        failure = self.client.attempt_get(f"/{repository.api_path}").failure
        self.read_failures[repository] = failure
        if failure is not None:
            logger.warning(
                f"cannot read {repository}, so its pull requests are left out: "
                f"{failure.error_message()}"
            )
        return failure

    def pull_request(self, reference: PullRequestReference) -> PullRequestRecord | None:
        record = self.listed_or_read(reference)
        if record is None or not record.has_unread_checks:
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
