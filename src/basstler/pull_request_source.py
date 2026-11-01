"""
Where the live state of the pull requests a plan references is read from.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any

from basstler.maintenance.board import PullRequestField
from basstler.environment import GitHubCredentialVariable
from basstler.maintenance.github import (
    GitHubCredentialUnavailableError,
    GitHubRepository,
    GitHubRequestFailed,
)
from basstler.plan.dependencies import DependencyResolver
from basstler.pull_request_state import PullRequestRecord, PullRequestsByRepository
from basstler.repository import PullRequestReference, Repository

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
    the listing missed is read on its own.
    """

    token: str
    """
    The credential the requests authenticate with.
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
        :raises GitHubCredentialUnavailableError: If no token is set.
        """
        token = GitHubCredentialVariable.first_token()
        if not token:
            raise GitHubCredentialUnavailableError(tuple(GitHubCredentialVariable))
        return cls(token=token)

    def client_for(self, repository: Repository) -> GitHubRepository:
        """
        :param repository: The repository to call.
        :return: A client for it.
        """
        return GitHubRepository(repository, self.token)

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
            listing missed it, or ``None`` if the repository has no such pull request.
        """
        self.list_pull_requests_of(reference.repository)
        if reference not in self.pull_requests:
            api_record = self.read_if_present(
                lambda client: client.pull_request(reference.number),
                reference.repository,
            )
            if api_record is None:
                return None
            self.pull_requests[reference] = PullRequestRecord.from_api(api_record)
        return self.pull_requests[reference]

    def issue_url(self, repository: Repository, number: int) -> str | None:
        api_record = self.read_if_present(
            lambda client: client.issue(number), repository
        )
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

    def read_if_present(
        self,
        read: Callable[[GitHubRepository], Mapping[str, Any]],
        repository: Repository,
    ) -> Mapping[str, Any] | None:
        """
        Make one read, treating an absent number as an answer rather than a failure.

        :param read: The call to make, given the repository's client.
        :param repository: The repository to call.
        :return: The response, or ``None`` if the API answered that it does not exist.
        :raises GitHubRequestFailed: If the API refused the read for any other reason.
        """
        try:
            return read(self.client_for(repository))
        except GitHubRequestFailed as refused:
            if refused.status != HTTPStatus.NOT_FOUND:
                raise
            return None
