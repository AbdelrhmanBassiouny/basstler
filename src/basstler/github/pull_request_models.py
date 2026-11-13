"""
Models of a pull request and the checks reported against its head commit, as GitHub's
GraphQL API returns them, and the snapshot a report is rendered from.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Annotated, Any, Literal

from pydantic import AliasPath, Field

from basstler.github.graphql import GraphQLConnection
from basstler.github.review_models import (
    BranchPullRequest,
    Review,
    ReviewThread,
    ReviewThreadPage,
)
from basstler.github.states import CheckOutcome, CombinedCheckState, ConclusionOutcome
from basstler.github.web_page import AbsentAsEmpty
from basstler.json_model import ValidatedJSONModel
from basstler.upstream_reviews.exceptions import (
    GraphQLErrorsReturned,
)

# %% models mirroring the pull request


class CheckResult(ValidatedJSONModel):
    """
    One check reported against the pull request's head commit: a check run, such as a
    GitHub Actions job, or a status posted through the commit-status API.

    Each shape GitHub reports a check in is a subclass naming its own keys.
    """

    name: str
    """
    What the check calls itself.
    """

    outcome: ConclusionOutcome
    """
    Where the check stands.
    """

    target_url: Annotated[str, AbsentAsEmpty()]
    """
    Where the check's own output is, empty when it reported none.
    """

    @property
    def succeeded(self) -> bool:
        """:return: Whether this check reported success."""
        return self.outcome is CheckOutcome.SUCCESS


class GraphQLCheckRun(CheckResult):
    """
    A check run, as GraphQL lists it among a commit's checks.
    """

    kind: Annotated[Literal["CheckRun"], Field(alias="__typename")]
    """
    The GraphQL type a check of this shape carries.
    """

    outcome: Annotated[ConclusionOutcome, Field(alias="conclusion")]
    """
    Where the run stands, pending while it has no conclusion.
    """

    target_url: Annotated[str, AbsentAsEmpty(), Field(alias="detailsUrl")]
    """
    The run's page, empty when it has none.
    """


class GraphQLStatusContext(CheckResult):
    """
    A commit status, as GraphQL lists it among a commit's checks.
    """

    kind: Annotated[Literal["StatusContext"], Field(alias="__typename")]
    """
    The GraphQL type a check of this shape carries.
    """

    name: Annotated[str, Field(alias="context")]
    """
    The context the status was posted under, which names it.
    """

    outcome: Annotated[ConclusionOutcome, Field(alias="state")]
    """
    The state the status was posted with.
    """

    target_url: Annotated[str, AbsentAsEmpty(), Field(alias="targetUrl")]
    """
    The link the status was posted with, empty when it has none.
    """


GraphQLCheck = Annotated[
    GraphQLCheckRun | GraphQLStatusContext, Field(discriminator="kind")
]
"""
One of a commit's checks in GraphQL, read as the shape its GraphQL type names.
"""


class CheckStatus(ValidatedJSONModel):
    """
    Every check reported against the pull request, with GitHub's verdict over them.
    """

    state: CombinedCheckState
    """
    The verdict GitHub computed over all of them.
    """

    results: list[CheckResult]
    """
    Every check, in the order GitHub returned them.
    """

    @classmethod
    def over(cls, results: list[CheckResult]) -> CheckStatus | None:
        """
        Gather checks read one by one, computing the verdict GitHub would give them.

        :param results: Every check, in the order to report them.
        :return: The status, or ``None`` when nothing has reported.
        """
        if not results:
            return None
        return cls(
            state=CombinedCheckState.over([result.outcome for result in results]),
            results=results,
        )

    @property
    def unsuccessful(self) -> list[CheckResult]:
        """:return: The checks that did not report success."""
        return [result for result in self.results if not result.succeeded]


class GraphQLCheckStatus(CheckStatus):
    """
    The checks of a commit, as GitHub's GraphQL API rolls them up.
    """

    results: Annotated[GraphQLConnection[GraphQLCheck], Field(alias="contexts")]
    """
    Every check, in the order GitHub returned them.
    """


class Commit(ValidatedJSONModel):
    """
    A commit, carrying the checks reported against it.
    """

    checks: Annotated[GraphQLCheckStatus | None, Field(alias="statusCheckRollup")]
    """
    The checks reported against this commit, absent when none have reported.
    """


class PullRequestCommit(ValidatedJSONModel):
    """
    One entry of a pull request's commit list, which wraps the commit itself.
    """

    commit: Commit
    """
    The commit this entry stands for.
    """


class PullRequest(ValidatedJSONModel):
    """
    One upstream pull request, as a single page of the review-threads query reads it.
    """

    number: int
    """
    Its number on the upstream repository.
    """

    title: str
    """
    Its title.
    """

    page_url: Annotated[str, Field(alias="url")]
    """
    Its own page on GitHub.
    """

    commits: GraphQLConnection[PullRequestCommit]
    """
    The commits the query selected, which is the head commit alone.
    """

    reviews: GraphQLConnection[Review]
    """
    Every submitted review, oldest first.
    """

    review_threads: Annotated[ReviewThreadPage, Field(alias="reviewThreads")]
    """
    The page of review threads this response carried.
    """

    @property
    def checks(self) -> CheckStatus | None:
        """
        The checks reported against the head commit.

        GitHub hangs the combined checks off the commit rather than the pull request.

        :return: The checks, or ``None`` when nothing has reported.
        """
        if not self.commits:
            return None
        return self.commits[-1].commit.checks


@dataclass(frozen=True)
class UpstreamPullRequestSnapshot:
    """
    Everything read from one upstream pull request in a single run.
    """

    number: int
    """
    The pull request's number on the upstream repository.
    """

    title: str
    """
    The pull request's title.
    """

    page_url: str
    """
    The pull request's own page on GitHub.
    """

    reviews: list[Review]
    """
    Every submitted review, oldest first.
    """

    threads: list[ReviewThread]
    """
    Every review thread, in the order GitHub returned them.
    """

    checks: CheckStatus | None
    """
    The checks reported against the head commit, absent when none have reported.
    """

    @classmethod
    def assemble(
        cls, pull_request: PullRequest, threads: list[ReviewThread]
    ) -> UpstreamPullRequestSnapshot:
        """
        Combine a parsed pull request with every thread its pages carried.

        :param pull_request: The pull request, as the last page read it.
        :param threads: Every thread gathered across the paged reads.
        :return: The assembled snapshot.
        """
        return cls(
            number=pull_request.number,
            title=pull_request.title,
            page_url=pull_request.page_url,
            reviews=pull_request.reviews,
            threads=threads,
            checks=pull_request.checks,
        )

    @property
    def unresolved_threads(self) -> list[ReviewThread]:
        """:return: The threads still awaiting action."""
        return [thread for thread in self.threads if not thread.is_resolved]

    def thread(self, identifier: str) -> ReviewThread:
        """
        Look one thread up by its node identifier.

        :param identifier: The thread's node identifier.
        :return: The matching thread.
        :raises KeyError: If no thread carries that identifier.
        """
        for thread in self.threads:
            if thread.identifier == identifier:
                return thread
        raise KeyError(identifier)


class PullRequestForBranchResult(ValidatedJSONModel):
    """
    What :attr:`GraphQLDocument.PULL_REQUEST_FOR_BRANCH` returns.
    """

    pull_requests: Annotated[
        GraphQLConnection[BranchPullRequest],
        Field(validation_alias=AliasPath("repository", "pullRequests")),
    ]
    """
    Every pull request the head-branch search matched, newest first.
    """


class ReviewThreadsPageResult(ValidatedJSONModel):
    """
    What :attr:`GraphQLDocument.REVIEW_THREADS_PAGE` returns.
    """

    pull_request: Annotated[
        PullRequest, Field(validation_alias=AliasPath("repository", "pullRequest"))
    ]
    """
    The pull request, carrying one page of its review threads.
    """


# %% the GraphQL envelope


@dataclass(frozen=True)
class GraphQLRequest:
    """
    One GraphQL query, whose fields are named as the request body names them.
    """

    query: str
    """
    The GraphQL document.
    """

    variables: dict[str, Any]
    """
    The document's variables.
    """

    def to_json(self) -> dict[str, Any]:
        """
        :return: The request body GitHub's GraphQL endpoint reads.
        """
        return asdict(self)


@dataclass(frozen=True)
class GraphQLResponse:
    """
    A parsed GraphQL response envelope.
    """

    data: dict[str, Any] | None
    """
    The ``data`` data, absent when the query failed outright.
    """

    errors: list[str] = field(default_factory=list)
    """
    Every message from an ``errors`` array, empty on success.
    """

    @classmethod
    def from_json(cls, text: str) -> GraphQLResponse:
        """
        Parse a response body.

        :param text: The raw JSON GitHub returned.
        :return: The parsed envelope.
        """
        body = json.loads(text)
        return cls(
            data=body.get("data"),
            errors=[error["message"] for error in body.get("errors", [])],
        )

    def result(self) -> dict[str, Any]:
        """:return: The query's result.

        :raises GraphQLErrorsReturned: If GitHub reported errors instead.
        """
        if self.errors:
            raise GraphQLErrorsReturned(self.errors)
        return self.data or {}
