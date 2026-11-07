"""
Models of a pull request's REST responses, each parsed into the same models a GraphQL
read builds.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field
from pydantic.dataclasses import dataclass

from basstler.upstream_reviews.pull_request_models import (
    CheckResult,
)
from basstler.upstream_reviews.review_models import (
    Author,
    BranchPullRequest,
    Review,
    ReviewThread,
    ThreadComment,
)
from basstler.upstream_reviews.vocabulary import (
    CheckOutcome,
    ConclusionOutcome,
    PullRequestState,
    ReviewState,
    ValidatedJSONModel,
)

# %% models mirroring the REST data


class RestPullRequestState(StrEnum):
    """
    The two states REST reports a pull request in; a merged one reads as closed.
    """

    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True)
class RestPullRequestHead(ValidatedJSONModel):
    """
    The branch a pull request was opened from.
    """

    sha: str
    """
    The commit the branch points at, which the checks are reported against.
    """

    owner: Annotated[Author, Field(alias="user")]
    """
    Whoever owns the branch.
    """


@dataclass(frozen=True)
class RestPullRequestSummary(ValidatedJSONModel):
    """
    One pull request as REST describes it, whether listed or read on its own.
    """

    number: int
    """
    Its number on the upstream repository.
    """

    title: str
    """
    Its title.
    """

    url: Annotated[str, Field(alias="html_url")]
    """
    Its web URL.
    """

    state: RestPullRequestState
    """
    Whether it is open or closed.
    """

    merged_at: str | None
    """
    When it merged, as an ISO 8601 timestamp, absent unless it closed by merging.
    """

    head: RestPullRequestHead
    """
    The branch it was opened from.
    """

    @property
    def merged(self) -> bool:
        """:return: Whether it closed by merging."""
        return self.merged_at is not None

    @property
    def branch_pull_request(self) -> BranchPullRequest:
        """
        :return: The summary a branch search compares, in the lifecycle GraphQL names.
        """
        if self.merged:
            state = PullRequestState.MERGED
        else:
            state = PullRequestState[self.state.name]
        return BranchPullRequest(
            number=self.number, state=state, head_owner=self.head.owner
        )


@dataclass(frozen=True)
class RestReview(ValidatedJSONModel):
    """
    One review, as REST lists it, whose body and submission time are null until it is
    submitted.
    """

    author: Annotated[Author, Field(alias="user")]
    """
    Whoever submitted the review.
    """

    state: ReviewState
    """
    The verdict the reviewer submitted.
    """

    body: str | None
    """
    The review's summary text.
    """

    submitted_at: str | None
    """
    When the review was submitted, as an ISO 8601 timestamp.
    """

    @property
    def review(self) -> Review:
        """:return: The review, as the report reads it."""
        return Review(
            author=self.author,
            state=self.state,
            body=self.body or "",
            submitted_at=self.submitted_at or "",
        )


@dataclass(frozen=True)
class RestReviewComment(ValidatedJSONModel):
    """
    One review comment, as REST lists every comment on a pull request.
    """

    identifier: Annotated[int, Field(alias="id")]
    """
    GitHub's numeric identifier, the one that appears in comment permalinks.
    """

    author: Annotated[Author, Field(alias="user")]
    """
    Whoever wrote the comment.
    """

    body: str
    """
    The comment text, exactly as written.
    """

    created_at: str
    """
    When the comment was posted, as an ISO 8601 timestamp.
    """

    url: Annotated[str, Field(alias="html_url")]
    """
    The permalink to this comment.
    """

    @property
    def comment(self) -> ThreadComment:
        """:return: The comment, as the report reads it."""
        return ThreadComment(
            database_identifier=self.identifier,
            author=self.author,
            body=self.body,
            created_at=self.created_at,
            url=self.url,
        )


@dataclass(frozen=True)
class RestReviewThread(ValidatedJSONModel):
    """
    One review thread, as a Claude Code session's proxy reports it: its state and
    location, and the comments in it named by identifier only.
    """

    is_resolved: Annotated[bool, Field(alias="resolved")]
    """
    Whether a reviewer has marked the thread resolved.
    """

    is_outdated: Annotated[bool, Field(alias="outdated")]
    """
    Whether the diff hunk the thread was anchored to has since changed.
    """

    path: str
    """
    The file the thread is attached to.
    """

    line: int | None
    """
    The line the thread is attached to, absent once the hunk is outdated.
    """

    comment_identifiers: Annotated[list[int], Field(alias="comment_ids")]
    """
    The comments in the thread, oldest first.
    """

    def thread(self, comments: dict[int, ThreadComment]) -> ReviewThread:
        """
        Fill the thread in with its comments.

        The route carries no identifier of the thread's own, so its first comment's
        stands in for one. A comment deleted since the comments were listed is left out
        rather than failing the whole read.

        :param comments: Every comment on the pull request, by identifier.
        :return: The thread, as the report reads it.
        """
        return ReviewThread(
            identifier=str(self.comment_identifiers[0]),
            is_resolved=self.is_resolved,
            is_outdated=self.is_outdated,
            path=self.path,
            line=self.line,
            comments=[
                comments[identifier]
                for identifier in self.comment_identifiers
                if identifier in comments
            ],
        )


@dataclass(frozen=True)
class RestCheckRun(ValidatedJSONModel):
    """
    One check run, such as a GitHub Actions job, whose conclusion is null until it
    finishes.
    """

    name: str
    """
    What the check calls itself.
    """

    outcome: Annotated[ConclusionOutcome, Field(alias="conclusion")]
    """
    Where the check stands.
    """

    url: Annotated[str | None, Field(alias="details_url")]
    """
    Where the check's own output is.
    """

    @property
    def result(self) -> CheckResult:
        """:return: The check, as the report reads it."""
        return CheckResult(name=self.name, outcome=self.outcome, url=self.url or "")


@dataclass(frozen=True)
class RestCheckRunPage(ValidatedJSONModel):
    """
    One page of the check runs reported against a commit.
    """

    check_runs: list[RestCheckRun]
    """
    The check runs on this page.
    """


@dataclass(frozen=True)
class RestCommitStatus(ValidatedJSONModel):
    """
    One status posted through the commit-status API.
    """

    name: Annotated[str, Field(alias="context")]
    """
    What the status calls itself.
    """

    outcome: Annotated[CheckOutcome, Field(alias="state")]
    """
    Where the status stands.
    """

    url: Annotated[str | None, Field(alias="target_url")]
    """
    Where the status's own output is.
    """

    @property
    def result(self) -> CheckResult:
        """:return: The check, as the report reads it."""
        return CheckResult(name=self.name, outcome=self.outcome, url=self.url or "")


@dataclass(frozen=True)
class RestCombinedStatusPage(ValidatedJSONModel):
    """
    One page of the statuses posted against a commit.

    Its own combined state is left unread: GitHub reports it pending when nothing has
    posted at all, which would misreport a commit no status applies to.
    """

    statuses: list[RestCommitStatus]
    """
    The statuses on this page.
    """
