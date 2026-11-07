"""
Models of a pull request and the checks reported against its head commit, as GitHub's
GraphQL API returns them, and the snapshot a report is rendered from.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Annotated, Any

from pydantic import AliasPath, Field, model_validator
from pydantic.dataclasses import dataclass as validated_dataclass

from basstler.upstream_reviews.exceptions import (
    GraphQLErrorsReturned,
)
from basstler.upstream_reviews.review_models import (
    BranchPullRequest,
    Review,
    ReviewThread,
    ReviewThreadPage,
)
from basstler.upstream_reviews.vocabulary import (
    CheckContextType,
    CheckOutcome,
    Connection,
    RollupState,
    ValidatedJSONModel,
)

# %% models mirroring the pull request


@validated_dataclass(frozen=True)
class CheckResult(ValidatedJSONModel):
    """
    One check reported against the pull request's head commit.
    """

    name: str
    """
    What the check calls itself.
    """

    outcome: CheckOutcome
    """
    Where the check stands.
    """

    url: str
    """
    Where the check's own output is, empty when it reported none.
    """

    @model_validator(mode="before")
    @classmethod
    def read_rollup_context(cls, data: Any) -> Any:
        """
        :param data: A rollup context node, in either shape a rollup can hold, or the
            arguments the check is constructed with.
        :return: The check's own fields.
        :raises ValueError: If the node is neither shape a rollup can hold.
        """
        if not isinstance(data, dict):
            return data
        if CheckContextType(data["__typename"]) is CheckContextType.CHECK_RUN:
            return {
                "name": data["name"],
                "outcome": CheckOutcome.from_conclusion(data["conclusion"]),
                "url": data["detailsUrl"] or "",
            }
        return {
            "name": data["context"],
            "outcome": data["state"],
            "url": data["targetUrl"] or "",
        }

    @property
    def succeeded(self) -> bool:
        """:return: Whether this check reported success."""
        return self.outcome is CheckOutcome.SUCCESS


@validated_dataclass(frozen=True)
class CheckStatus(ValidatedJSONModel):
    """
    Every check reported against the pull request, with GitHub's verdict over them.
    """

    state: RollupState
    """
    The verdict GitHub computed over all of them.
    """

    results: Annotated[Connection[CheckResult], Field(alias="contexts")]
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
            state=RollupState.over([result.outcome for result in results]),
            results=results,
        )

    @property
    def unsuccessful(self) -> list[CheckResult]:
        """:return: The checks that did not report success."""
        return [result for result in self.results if not result.succeeded]


@validated_dataclass(frozen=True)
class Commit(ValidatedJSONModel):
    """
    A commit, carrying the checks reported against it.
    """

    checks: Annotated[CheckStatus | None, Field(alias="statusCheckRollup")]
    """
    The checks reported against this commit, absent when none have reported.
    """


@validated_dataclass(frozen=True)
class PullRequestCommit(ValidatedJSONModel):
    """
    One entry of a pull request's commit list, which wraps the commit itself.
    """

    commit: Commit
    """
    The commit this entry stands for.
    """


@validated_dataclass(frozen=True)
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

    url: str
    """
    Its web URL.
    """

    commits: Connection[PullRequestCommit]
    """
    The commits the query selected, which is the head commit alone.
    """

    reviews: Connection[Review]
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

        GitHub hangs the rollup off the commit rather than the pull request.

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

    url: str
    """
    The pull request's web URL.
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
            url=pull_request.url,
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


@validated_dataclass(frozen=True)
class PullRequestForBranchResult(ValidatedJSONModel):
    """
    What :attr:`GraphQLDocument.PULL_REQUEST_FOR_BRANCH` returns.
    """

    pull_requests: Annotated[
        Connection[BranchPullRequest],
        Field(validation_alias=AliasPath("repository", "pullRequests")),
    ]
    """
    Every pull request the head-branch search matched, newest first.
    """


@validated_dataclass(frozen=True)
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
