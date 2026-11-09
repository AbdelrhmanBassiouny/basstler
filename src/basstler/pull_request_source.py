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
from basstler.github.exceptions import GitHubRequestFailed
from basstler.maintenance.github import GitHubRepository
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

    def is_readable(self, repository: Repository) -> bool:
        """
        :param repository: A repository a plan's items name.
        :return: Whether its pull requests can be read; true unless the source finds
            otherwise.
        """
        return True

    def unreadable_repositories_of(
        self, dependencies: DependencyResolver
    ) -> frozenset[Repository]:
        """
        :param dependencies: A plan's items, plus the items of other plans it depends
            on.
        :return: The repositories of those items' pull requests that cannot be read.
        """
        return frozenset(
            repository
            for dependency in dependencies.resolved_dependencies
            if dependency.item.pull_request_number is not None
            and not self.is_readable(
                repository := Repository.parse(dependency.repository)
            )
        )

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

    readability: dict[Repository, bool] = field(default_factory=dict)
    """
    Whether each repository asked about so far can be read.
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

    def is_readable(self, repository: Repository) -> bool:
        """
        See :meth:`PullRequestSource.is_readable`: whether the repository's details can
        be read, asked once.
        """
        if repository not in self.readability:
            answer = self.client.attempt_get(f"/{repository.api_path}")
            self.readability[repository] = answer.failure is None
        return self.readability[repository]

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
        if not self.is_readable(reference.repository):
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
        if not self.is_readable(repository):
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
