"""
Models of a pull request's REST responses, each parsed into the same models a GraphQL
read builds.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

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
    JSONModel,
    PullRequestState,
    ReviewState,
)

# %% models mirroring the REST data


class RestJSONKey(StrEnum):
    """
    Every field name this script reads out of a REST response.

    REST spells its fields apart from GraphQL, so they are named here rather than shared
    with :class:`PullRequestJSONKey`.
    """

    NUMBER = "number"
    TITLE = "title"
    HTML_URL = "html_url"
    STATE = "state"
    MERGED_AT = "merged_at"
    HEAD = "head"
    SHA = "sha"
    USER = "user"
    BODY = "body"
    SUBMITTED_AT = "submitted_at"
    IDENTIFIER = "id"
    CREATED_AT = "created_at"
    RESOLVED = "resolved"
    OUTDATED = "outdated"
    PATH = "path"
    LINE = "line"
    COMMENT_IDENTIFIERS = "comment_ids"
    CHECK_RUNS = "check_runs"
    NAME = "name"
    CONCLUSION = "conclusion"
    DETAILS_URL = "details_url"
    STATUSES = "statuses"
    CONTEXT = "context"
    TARGET_URL = "target_url"


class RestPullRequestState(StrEnum):
    """
    The two states REST reports a pull request in; a merged one reads as closed.
    """

    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True)
class RestPullRequestHead(JSONModel):
    """
    The branch a pull request was opened from.
    """

    sha: str
    """
    The commit the branch points at, which the checks are reported against.
    """

    owner: Author
    """
    Whoever owns the branch.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RestPullRequestHead:
        """
        Read a ``head`` object.

        :param data: The object to read.
        :return: The parsed head.
        """
        return cls(
            sha=data[RestJSONKey.SHA],
            owner=Author.from_json(data[RestJSONKey.USER]),
        )


@dataclass(frozen=True)
class RestPullRequestSummary(JSONModel):
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

    url: str
    """
    Its web URL.
    """

    state: RestPullRequestState
    """
    Whether it is open or closed.
    """

    merged: bool
    """
    Whether it closed by merging.
    """

    head: RestPullRequestHead
    """
    The branch it was opened from.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RestPullRequestSummary:
        """
        Read a pull request object.

        :param data: The object to read.
        :return: The parsed summary.
        """
        return cls(
            number=data[RestJSONKey.NUMBER],
            title=data[RestJSONKey.TITLE],
            url=data[RestJSONKey.HTML_URL],
            state=RestPullRequestState(data[RestJSONKey.STATE]),
            merged=data[RestJSONKey.MERGED_AT] is not None,
            head=RestPullRequestHead.from_json(data[RestJSONKey.HEAD]),
        )

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
class RestReview(JSONModel):
    """
    One submitted review, as REST lists it.
    """

    review: Review
    """
    The review it describes.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RestReview:
        """
        Read a review object, whose body and submission time are null until submitted.

        :param data: The object to read.
        :return: The parsed review.
        """
        return cls(
            Review(
                author=Author.from_json(data[RestJSONKey.USER]),
                state=ReviewState[data[RestJSONKey.STATE]],
                body=data[RestJSONKey.BODY] or "",
                submitted_at=data[RestJSONKey.SUBMITTED_AT] or "",
            )
        )


@dataclass(frozen=True)
class RestReviewComment(JSONModel):
    """
    One review comment, as REST lists every comment on a pull request.
    """

    comment: ThreadComment
    """
    The comment it describes.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RestReviewComment:
        """
        Read a review comment object.

        :param data: The object to read.
        :return: The parsed comment.
        """
        return cls(
            ThreadComment(
                database_identifier=data[RestJSONKey.IDENTIFIER],
                author=Author.from_json(data[RestJSONKey.USER]),
                body=data[RestJSONKey.BODY],
                created_at=data[RestJSONKey.CREATED_AT],
                url=data[RestJSONKey.HTML_URL],
            )
        )


@dataclass(frozen=True)
class RestReviewThread(JSONModel):
    """
    One review thread, as a Claude Code session's proxy reports it: its state and
    location, and the comments in it named by identifier only.
    """

    is_resolved: bool
    """
    Whether a reviewer has marked the thread resolved.
    """

    is_outdated: bool
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

    comment_identifiers: list[int]
    """
    The comments in the thread, oldest first.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RestReviewThread:
        """
        Read a review thread object.

        :param data: The object to read.
        :return: The parsed thread.
        """
        return cls(
            is_resolved=data[RestJSONKey.RESOLVED],
            is_outdated=data[RestJSONKey.OUTDATED],
            path=data[RestJSONKey.PATH],
            line=data[RestJSONKey.LINE],
            comment_identifiers=list(data[RestJSONKey.COMMENT_IDENTIFIERS]),
        )

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
class RestCheckRun(JSONModel):
    """
    One check run, such as a GitHub Actions job.
    """

    result: CheckResult
    """
    The check it describes.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RestCheckRun:
        """
        Read a check run object, whose conclusion is null until it finishes.

        :param data: The object to read.
        :return: The parsed check run.
        """
        conclusion = data[RestJSONKey.CONCLUSION]
        return cls(
            CheckResult(
                name=data[RestJSONKey.NAME],
                outcome=(
                    CheckOutcome[conclusion.upper()]
                    if conclusion
                    else CheckOutcome.PENDING
                ),
                url=data[RestJSONKey.DETAILS_URL] or "",
            )
        )


@dataclass(frozen=True)
class RestCheckRunPage(JSONModel):
    """
    One page of the check runs reported against a commit.
    """

    check_runs: list[RestCheckRun]
    """
    The check runs on this page.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RestCheckRunPage:
        """
        Read one page of the check-runs listing.

        :param data: The page to read.
        :return: The parsed page.
        """
        return cls(
            [RestCheckRun.from_json(run) for run in data[RestJSONKey.CHECK_RUNS]]
        )


@dataclass(frozen=True)
class RestCommitStatus(JSONModel):
    """
    One status posted through the commit-status API.
    """

    result: CheckResult
    """
    The check it describes.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RestCommitStatus:
        """
        Read a commit status object.

        :param data: The object to read.
        :return: The parsed status.
        """
        return cls(
            CheckResult(
                name=data[RestJSONKey.CONTEXT],
                outcome=CheckOutcome[data[RestJSONKey.STATE].upper()],
                url=data[RestJSONKey.TARGET_URL] or "",
            )
        )


@dataclass(frozen=True)
class RestCombinedStatusPage(JSONModel):
    """
    One page of the statuses posted against a commit.

    Its own combined state is left unread: GitHub reports it pending when nothing has
    posted at all, which would misreport a commit no status applies to.
    """

    statuses: list[RestCommitStatus]
    """
    The statuses on this page.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RestCombinedStatusPage:
        """
        Read one page of the combined status.

        :param data: The page to read.
        :return: The parsed page.
        """
        return cls(
            [
                RestCommitStatus.from_json(status)
                for status in data[RestJSONKey.STATUSES]
            ]
        )
