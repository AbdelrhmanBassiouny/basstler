"""
Reading one upstream pull request's checks and review state, through GraphQL or REST.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlencode

from basstler.class_property import classproperty
from basstler.locations import ClaudeCodeVariable
from basstler.repository import Repository
from basstler.upstream_reviews.clients import (
    GitHubCommandLineClient,
    GraphQLClient,
    RestClient,
)
from basstler.upstream_reviews.exceptions import (
    UpstreamPullRequestNotFound,
)
from basstler.upstream_reviews.pull_request_models import (
    CheckStatus,
    PullRequestForBranchResult,
    ReviewThreadsPageResult,
    UpstreamPullRequestSnapshot,
)
from basstler.upstream_reviews.rest_models import (
    RestCheckRunPage,
    RestCombinedStatusPage,
    RestPullRequestSummary,
    RestReview,
    RestReviewComment,
    RestReviewThread,
)
from basstler.upstream_reviews.review_models import (
    BranchPullRequest,
    Review,
    ReviewThread,
)
from basstler.upstream_reviews.vocabulary import (
    GraphQLDocument,
    PullRequestState,
    QueryVariable,
)

# %% reading


class PullRequestSource(ABC):
    """
    Reads one upstream pull request's checks and review state, by whichever API the
    place it runs in can reach.
    """

    upstream_repository: Repository
    """
    The repository the fork's pull requests are opened against.
    """

    fork_owner: str
    """
    The owner whose branches this reader will claim as its own.
    """

    @abstractmethod
    def resolve_pull_request_number(self, branch: str) -> int:
        """
        Find the upstream pull request opened from *branch*.

        :param branch: The fork branch name.
        :return: The upstream pull request number.
        :raises UpstreamPullRequestNotFound: If the fork has no such pull request.
        """

    @abstractmethod
    def read_current_state(
        self, pull_request_number: int
    ) -> UpstreamPullRequestSnapshot:
        """
        Read the checks, reviews and review threads on one upstream pull request.

        :param pull_request_number: The upstream pull request's number.
        :return: The assembled snapshot.
        """

    def choose(self, branch: str, pull_requests: list[BranchPullRequest]) -> int:
        """
        Pick the fork's own pull request out of those a branch search matched.

        Prefers an open pull request, falling back to the most recent closed one so a
        branch under post-merge discussion still resolves.

        :param branch: The fork branch searched for.
        :param pull_requests: Every match, newest first.
        :return: The chosen pull request's number.
        :raises UpstreamPullRequestNotFound: If none of them is the fork's.
        """
        candidates = [
            pull_request
            for pull_request in pull_requests
            if pull_request.head_owner.login == self.fork_owner
        ]
        if not candidates:
            raise UpstreamPullRequestNotFound(
                branch, self.upstream_repository, self.fork_owner
            )
        open_candidates = [
            pull_request
            for pull_request in candidates
            if pull_request.state is PullRequestState.OPEN
        ]
        return (open_candidates or candidates)[0].number


@dataclass
class UpstreamPullRequestReader(PullRequestSource):
    """
    Reads one upstream pull request's checks and review state through GraphQL, which a
    runner reaches and a Claude Code session does not.
    """

    client: GraphQLClient
    """
    How GraphQL queries reach GitHub.
    """

    upstream_repository: Repository
    """
    The repository the fork's pull requests are opened against.
    """

    fork_owner: str
    """
    The owner whose branches this reader will claim as its own.
    """

    @property
    def _repository_variables(self) -> dict[str, Any]:
        """:return: The owner and name every query in this script takes."""
        return {
            QueryVariable.OWNER: self.upstream_repository.owner,
            QueryVariable.NAME: self.upstream_repository.name,
        }

    def resolve_pull_request_number(self, branch: str) -> int:
        """
        See :meth:`PullRequestSource.resolve_pull_request_number`.
        """
        data = self.client.execute(
            GraphQLDocument.PULL_REQUEST_FOR_BRANCH.read(),
            {**self._repository_variables, QueryVariable.HEAD_REF_NAME: branch},
        )
        return self.choose(
            branch, PullRequestForBranchResult.from_json(data).pull_requests
        )

    def read_current_state(
        self, pull_request_number: int
    ) -> UpstreamPullRequestSnapshot:
        """
        See :meth:`PullRequestSource.read_current_state`.
        """
        threads: list[ReviewThread] = []
        cursor: str | None = None
        while True:
            pull_request = ReviewThreadsPageResult.from_json(
                self.client.execute(
                    GraphQLDocument.REVIEW_THREADS_PAGE.read(),
                    {
                        **self._repository_variables,
                        QueryVariable.NUMBER: pull_request_number,
                        QueryVariable.THREAD_CURSOR: cursor,
                    },
                )
            ).pull_request
            page = pull_request.review_threads
            threads.extend(page.threads)
            if not page.page_info.has_next_page:
                break
            cursor = page.page_info.end_cursor
        return UpstreamPullRequestSnapshot.assemble(pull_request, threads)


@dataclass(frozen=True)
class UpstreamRestRoute:
    """
    The REST paths reading one upstream repository's pull requests takes.
    """

    repository: Repository
    """
    The repository the paths are under.
    """

    @classproperty
    def page_size(cls) -> int:
        """
        The most entries GitHub hands back per page, asked for so a long list takes as
        few requests as it can.
        """
        return 100

    def pull_requests_for_head(self, owner: str, branch: str) -> str:
        """
        :param owner: Whose branch to search for.
        :param branch: The branch's name.
        :return: The search for pull requests opened from it, in any state.
        """
        query = urlencode(
            {"head": f"{owner}:{branch}", "state": "all", "per_page": self.page_size},
            safe=":",
        )
        return f"{self.repository.api_path}/pulls?{query}"

    def pull_request(self, number: int) -> str:
        """
        :param number: The pull request's number.
        :return: The pull request itself.
        """
        return f"{self.repository.api_path}/pulls/{number}"

    def reviews(self, number: int) -> str:
        """
        :param number: The pull request's number.
        :return: Its submitted reviews.
        """
        return f"{self.pull_request(number)}/reviews?per_page={self.page_size}"

    def review_comments(self, number: int) -> str:
        """
        :param number: The pull request's number.
        :return: Every review comment on it, across all its threads.
        """
        return f"{self.pull_request(number)}/comments?per_page={self.page_size}"

    def review_threads(self, number: int) -> str:
        """
        The threads with their resolved state - a route of the Claude Code session
        proxy's own, standing in for the GraphQL GitHub keeps that state behind, which
        answers with every thread at once.

        :param number: The pull request's number.
        :return: Its review threads.
        """
        return f"{self.pull_request(number)}/ccr/review_threads"

    def check_runs(self, sha: str) -> str:
        """
        :param sha: The commit.
        :return: The check runs reported against it.
        """
        return (
            f"{self.repository.api_path}/commits/{sha}/check-runs"
            f"?per_page={self.page_size}"
        )

    def commit_status(self, sha: str) -> str:
        """
        :param sha: The commit.
        :return: The statuses posted against it.
        """
        return (
            f"{self.repository.api_path}/commits/{sha}/status?per_page={self.page_size}"
        )


@dataclass
class RestPullRequestReader(PullRequestSource):
    """
    Reads one upstream pull request's checks and review state over REST, which is what a
    Claude Code session's proxy answers once the upstream is attached to it.
    """

    client: RestClient
    """
    How REST requests reach GitHub.
    """

    upstream_repository: Repository
    """
    The repository the fork's pull requests are opened against.
    """

    fork_owner: str
    """
    The owner whose branches this reader will claim as its own.
    """

    @property
    def route(self) -> UpstreamRestRoute:
        """:return: The paths under the upstream."""
        return UpstreamRestRoute(self.upstream_repository)

    def resolve_pull_request_number(self, branch: str) -> int:
        """
        See :meth:`PullRequestSource.resolve_pull_request_number`.
        """
        pages = self.client.get_pages(
            self.route.pull_requests_for_head(self.fork_owner, branch)
        )
        return self.choose(
            branch,
            [
                RestPullRequestSummary.from_json(entry).branch_pull_request
                for page in pages
                for entry in page
            ],
        )

    def read_current_state(
        self, pull_request_number: int
    ) -> UpstreamPullRequestSnapshot:
        """
        See :meth:`PullRequestSource.read_current_state`.
        """
        pull_request = RestPullRequestSummary.from_json(
            self.client.get(self.route.pull_request(pull_request_number))
        )
        return UpstreamPullRequestSnapshot(
            number=pull_request.number,
            title=pull_request.title,
            url=pull_request.url,
            reviews=self._reviews(pull_request_number),
            threads=self._threads(pull_request_number),
            checks=self._checks(pull_request.head.sha),
        )

    def _reviews(self, pull_request_number: int) -> list[Review]:
        """
        :param pull_request_number: The pull request's number.
        :return: Every submitted review, oldest first.
        """
        return [
            RestReview.from_json(entry).review
            for page in self.client.get_pages(self.route.reviews(pull_request_number))
            for entry in page
        ]

    def _threads(self, pull_request_number: int) -> list[ReviewThread]:
        """
        Read the threads, then fill each in from the comments listed separately.

        :param pull_request_number: The pull request's number.
        :return: Every review thread, in the order the route returned them.
        """
        comments = {
            comment.database_identifier: comment
            for comment in (
                RestReviewComment.from_json(entry).comment
                for page in self.client.get_pages(
                    self.route.review_comments(pull_request_number)
                )
                for entry in page
            )
        }
        return [
            RestReviewThread.from_json(entry).thread(comments)
            for entry in self.client.get(self.route.review_threads(pull_request_number))
        ]

    def _checks(self, sha: str) -> CheckStatus | None:
        """
        Read the check runs and the commit statuses, which REST reports apart.

        :param sha: The head commit.
        :return: The checks, or ``None`` when nothing has reported.
        """
        runs = [
            run.result
            for page in self.client.get_pages(self.route.check_runs(sha))
            for run in RestCheckRunPage.from_json(page).check_runs
        ]
        statuses = [
            status.result
            for page in self.client.get_pages(self.route.commit_status(sha))
            for status in RestCombinedStatusPage.from_json(page).statuses
        ]
        return CheckStatus.over(runs + statuses)


class ReadSource(StrEnum):
    """
    The two APIs a pull request can be read through.
    """

    REST = "rest"
    """
    REST, the only one a Claude Code cloud session's proxy answers.
    """

    GRAPHQL = "graphql"
    """
    GraphQL, which a runner or a developer's own machine reaches.
    """

    @classmethod
    def detect(cls) -> ReadSource:
        """
        :return: The API the place this runs in can reach.
        """
        if ClaudeCodeVariable.REMOTE.read() == "true":
            return cls.REST
        return cls.GRAPHQL

    def reader(
        self,
        client: GitHubCommandLineClient,
        upstream_repository: Repository,
        fork_owner: str,
    ) -> PullRequestSource:
        """
        :param client: The client both readers go through.
        :param upstream_repository: The repository to read.
        :param fork_owner: Whose branches to claim.
        :return: The reader for this API.
        """
        if self is ReadSource.REST:
            return RestPullRequestReader(client, upstream_repository, fork_owner)
        return UpstreamPullRequestReader(client, upstream_repository, fork_owner)
