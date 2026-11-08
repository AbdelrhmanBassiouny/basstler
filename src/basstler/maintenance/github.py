"""
Reading and writing a repository's pull requests and labels.

The reading and the writing halves are declared separately, so a caller that must not
write - the board export - can be handed a reader and provably cannot. Every write here
was probed against the live API first: a pull request's *base branch* is the one the
credential a session carries is refused, which is why retargeting is reported for a
caller to perform rather than performed.
"""

from __future__ import annotations

import urllib.parse
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any

from basstler.github.issue import IssueComment
from basstler.github.label import LabelReplacement, RepositoryLabel
from basstler.github.pull_request import PullRequestDescription
from basstler.pull_request_state import PullRequestState
from basstler.github_labels import GitHubLabel
from basstler.locations import PathEnumeration
from basstler.maintenance.board import (
    AccountField,
    CommitChecks,
    PullRequestRecord,
)
from basstler.github.client import GitHubClient, GitHubRestClient, HttpMethod
from basstler.repository import Repository
from basstler.upstream_reviews.pull_request_models import CheckStatus
from basstler.upstream_reviews.rest_models import (
    RestCheckRunPage,
    RestCombinedStatusPage,
)
from basstler.upstream_reviews.vocabulary import CombinedCheckState, WebPage


# %% what a pass reads and writes


@dataclass(frozen=True)
class PullRequestReader(ABC):
    """
    Reading the pull-request state a pass derives from.

    Implementations inherit rather than merely match the shape, so one that omits a read
    is refused when it is constructed rather than when the missing call is first made.
    """

    @abstractmethod
    def open_pull_requests(self) -> list[PullRequestRecord]:
        """:return: Every open pull request on the fork."""

    @abstractmethod
    def pull_request(self, number: int) -> PullRequestRecord:
        """:param number: The pull request to read.
        :return: That pull request."""


@dataclass(frozen=True)
class PullRequestWriter(ABC):
    """
    The three writes a pass makes, each one probed against the live API first.

    Every one of them is available to the credential a session carries; a pull request's
    *base branch* is the single write that is not, which is why reparenting is the
    caller's job and none of this is.
    """

    @abstractmethod
    def replace_labels(self, number: int, labels: Sequence[str]) -> None:
        """:param number: The pull request to write.
        :param labels: The complete label set it must end up with."""

    @abstractmethod
    def add_comment(self, number: int, body: str) -> str:
        """:param number: The pull request to comment on.
        :param body: The comment.
        :return: The comment's URL."""

    @abstractmethod
    def set_description(self, number: int, body: str) -> None:
        """:param number: The pull request to write.
        :param body: The new description."""


@dataclass(frozen=True)
class ForkPullRequests(PullRequestReader, PullRequestWriter, ABC):
    """
    Everything a pass does to the fork's pull requests.

    A pass reads state and writes back to the same fork, so the two halves are named
    together wherever both are needed; the board export takes the reading half alone,
    which is what keeps an export from being able to write.
    """


@dataclass(frozen=True)
class RepositoryLabels(ABC):
    """
    The labels a repository carries, and adding one it lacks.
    """

    @abstractmethod
    def labels(self) -> set[str]:
        """:return: The name of every label the repository carries."""

    @abstractmethod
    def create_label(self, label: GitHubLabel) -> None:
        """:param label: The label to add, described by its purpose."""


@dataclass(frozen=True)
class CredentialHolder(ABC):
    """
    Telling whose credential a client calls GitHub with.
    """

    @abstractmethod
    def authenticated_login(self) -> str:
        """:return: The login of the account the credential belongs to."""


class GitHubPath(PathEnumeration):
    """
    The API paths that are not below a repository.
    """

    AUTHENTICATED_USER = Path("/user")
    """
    The account the request's credential belongs to.
    """


class RepositoryPath(PathEnumeration):
    """
    The API paths below a repository.
    """

    PULL_REQUESTS = Path("/pulls")
    """
    The repository's pull requests.
    """

    LABELS = Path("/labels")
    """
    The labels defined on the repository.
    """

    COMMITS = Path("/commits")
    """
    The repository's commits.
    """


class CommitReport(StrEnum):
    """
    The listings reported against one commit, below :attr:`RepositoryPath.COMMITS`.
    """

    CHECK_RUNS = "check-runs"
    """
    The check runs reported against it.
    """

    STATUS = "status"
    """
    The commit statuses posted against it.
    """


class ListingParameter(StrEnum):
    """
    The query parameters a paged listing takes.
    """

    STATE = "state"
    """
    Which pull requests to list, by state.
    """

    PAGE_SIZE = "per_page"
    """
    How many entries one page holds.
    """


@dataclass(frozen=True)
class PullRequestListingSpecification:
    """
    One filter the pull request list API takes: what it is asked for by, and which
    :class:`PullRequestState` values it lets through.
    """

    query: str
    """
    The value the list API's ``state`` parameter takes for this filter.
    """

    states: tuple[PullRequestState, ...]
    """
    The pull request states this filter lets through.
    """


class PullRequestListState(PullRequestListingSpecification, Enum):
    """
    The pull request states the list API filters on: each :class:`PullRequestState` a
    pull request reports, plus every state at once.

    Each member *is* a :class:`PullRequestListingSpecification`, written as its fields
    in declaration order - ``query``, then ``states`` - which the enum passes straight to
    the dataclass.
    """

    OPEN = PullRequestState.OPEN.value, (PullRequestState.OPEN,)
    """
    Pull requests whose state is :attr:`PullRequestState.OPEN`: drafts and those ready
    for review alike.
    """

    CLOSED = PullRequestState.CLOSED.value, (PullRequestState.CLOSED,)
    """
    Pull requests whose state is :attr:`PullRequestState.CLOSED`: merged and closed
    unmerged alike.
    """

    ALL = "all", tuple(PullRequestState)
    """
    Every pull request, whatever its :class:`PullRequestState`.
    """


# %% the client that makes the calls


@dataclass(frozen=True)
class GitHubRepository(
    ForkPullRequests, CommitChecks, RepositoryLabels, CredentialHolder
):
    """
    Every pull-request and label call this tooling makes, against one repository.
    """

    repository: Repository
    """
    The repository to read and write.
    """

    client: GitHubClient
    """
    How the calls reach GitHub.
    """

    page_size: int = 100
    """
    How many pull requests, labels or checks to ask for per page.
    """

    @classmethod
    def from_environment(cls, repository: Repository) -> GitHubRepository:
        """
        Build a client from whichever credential the environment carries.

        :param repository: The repository to read and write.
        :return: The client.
        """
        return cls(repository, GitHubRestClient())

    def open_pull_requests(self) -> list[PullRequestRecord]:
        """:return: Every open pull request on the repository, oldest page first."""
        return self._pull_requests_in_state(PullRequestListState.OPEN)

    def all_pull_requests(self) -> list[PullRequestRecord]:
        """:return: Every pull request on the repository, open or closed."""
        return self._pull_requests_in_state(PullRequestListState.ALL)

    def issue(self, number: int) -> Mapping[str, Any]:
        """:param number: The issue or pull request to read.
        :return: It, as the issues API describes it."""
        return self.client.get(self._path(f"/issues/{number}"))

    def _pull_requests_in_state(
        self, state: PullRequestListState
    ) -> list[PullRequestRecord]:
        """
        Read every page of pull requests in one state.

        :param state: Which pull requests to list.
        :return: Them, oldest page first.
        """
        return self._every_entry(
            RepositoryPath.PULL_REQUESTS, {ListingParameter.STATE: state.query}
        )

    def labels(self) -> set[str]:
        return {
            RepositoryLabel.from_json(label).name
            for label in self._every_entry(RepositoryPath.LABELS, {})
        }

    def create_label(self, label: GitHubLabel) -> None:
        self.client.send(
            HttpMethod.POST,
            self._path(str(RepositoryPath.LABELS)),
            RepositoryLabel(label, label.purpose),
        )

    def check_state(self, commit: str) -> CombinedCheckState:
        runs = [
            run
            for page in self.client.get_pages(
                self._listing(self._commit_report(commit, CommitReport.CHECK_RUNS), {})
            )
            for run in RestCheckRunPage.from_json(page).check_runs
        ]
        statuses = [
            status
            for page in self.client.get_pages(
                self._listing(self._commit_report(commit, CommitReport.STATUS), {})
            )
            for status in RestCombinedStatusPage.from_json(page).statuses
        ]
        checks = CheckStatus.over(runs + statuses)
        return CombinedCheckState.NOT_REPORTED if checks is None else checks.state

    @staticmethod
    def _commit_report(commit: str, report: CommitReport) -> str:
        """:param commit: The commit reported against.
        :param report: Which of its listings to read.
        :return: The listing's path below the repository."""
        return f"{RepositoryPath.COMMITS}/{commit}/{report}"

    def authenticated_login(self) -> str:
        account = self.client.get(str(GitHubPath.AUTHENTICATED_USER))
        return str(account[AccountField.LOGIN])

    def _every_entry(
        self, path: RepositoryPath, filters: Mapping[ListingParameter, str]
    ) -> list[Any]:
        """
        Read a listing below the repository whose pages are lists, to its end.

        :param path: The listing's path below the repository.
        :param filters: The query parameters narrowing the listing.
        :return: Every entry, first page first.
        """
        return [
            entry
            for page in self.client.get_pages(self._listing(str(path), filters))
            for entry in page
        ]

    def _listing(self, path: str, filters: Mapping[ListingParameter, str]) -> str:
        """
        :param path: A listing's path below the repository.
        :param filters: The query parameters narrowing it.
        :return: Its path below the API root, asking for full pages.
        """
        query = urllib.parse.urlencode(
            {**filters, ListingParameter.PAGE_SIZE: self.page_size}
        )
        return self._path(f"{path}?{query}")

    def _path(self, path: str) -> str:
        """
        :param path: A path below the repository, starting with a slash.
        :return: It below the API root.
        """
        return f"/{self.repository.api_path}{path}"

    def pull_request(self, number: int) -> PullRequestRecord:
        """:param number: The pull request to read.
        :return: That pull request."""
        return self.client.get(self._path(f"{RepositoryPath.PULL_REQUESTS}/{number}"))

    def replace_labels(self, number: int, labels: Sequence[str]) -> None:
        """
        Write a pull request's complete label set.

        :param number: The pull request to write.
        :param labels: The complete set it must end up with, computed by
            :meth:`stack.LabelWrite.replacing` - this call replaces rather than adds.
        """
        self.client.send(
            HttpMethod.PUT,
            self._path(f"/issues/{number}/labels"),
            LabelReplacement(list(labels)),
        )

    def add_comment(self, number: int, body: str) -> str:
        """:param number: The pull request to comment on.
        :param body: The comment.
        :return: The comment's URL."""
        created = self.client.send(
            HttpMethod.POST,
            self._path(f"/issues/{number}/comments"),
            IssueComment(body),
        )
        return WebPage.from_json(created).page_url

    def set_description(self, number: int, body: str) -> None:
        """
        Rewrite a pull request's description and nothing else.

        :param number: The pull request to write.
        :param body: The new description.
        """
        self.client.send(
            HttpMethod.PATCH,
            self._path(f"{RepositoryPath.PULL_REQUESTS}/{number}"),
            PullRequestDescription(body),
        )
