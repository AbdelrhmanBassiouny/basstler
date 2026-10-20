#!/usr/bin/env python3
"""
Report the checks, failing job logs and review threads a fork's pull request has
collected upstream.

It reads through whichever API the place it runs in can reach. A Claude Code cloud
session's proxy refuses GitHub's GraphQL API but answers REST for the repositories the
session has attached, with a review-threads route of its own carrying the resolved
state GitHub otherwise keeps behind GraphQL; anywhere else - a runner, a developer's
machine - reads through GraphQL. Both readers parse into the same models, so the report
is the same either way. ``gh`` is what talks to GitHub, rather than a hand-rolled client:
runners ship it, ``GITHUB_TOKEN`` or the session proxy authenticates it, so no access
rule is implemented here a fourth time.

Every repository name comes from configuration or the runner's own environment, so the
script works unchanged in any contributor's fork.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlencode


from basstler.class_property import classproperty
from basstler.environment import GitHubActionsVariable
from basstler.locations import ClaudeCodeVariable, PackageLocation
from basstler.maintenance_constants import GitHubClient
from basstler.repository import Repository
from basstler.stack_configuration import (
    CommittedStackConfiguration,
    MissingUpstreamRepositoryError,
)
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% the reading contract


class JSONModel(ABC):
    """
    A dataclass mirroring one object GitHub returns, able to read itself from it.

    Declaring the reader here is what lets :meth:`PullRequestJSONKey.read_list` call
    it on any model. Without it the shared name would be a convention every model
    is trusted to have followed, and a model that spelled it differently would fail
    only when something happened to parse that field.

    Every response is parsed into these models as soon as it arrives, and every
    decision after that is made on their attributes, never on the raw object. A
    reader reads its own object's fields and hands each nested object to that
    object's own model, so no access path into a response is spelled out twice.
    """

    @classmethod
    @abstractmethod
    def from_json(cls, data: dict[str, Any]) -> JSONModel:
        """
        Read one of these out of the object GitHub returned.

        :param data: The object to read.
        :return: The parsed model.
        """


ParsedItem = TypeVar("ParsedItem", bound=JSONModel)
"""
Whatever model a list-valued field is being parsed into.
"""


# %% wire vocabulary


class PullRequestJSONKey(StrEnum):
    """
    Every field name this script reads out of a GraphQL response.

    Named once here so a key is never spelled twice, and so a rename in the query
    document has exactly one place to follow.
    """

    DATA = "data"
    ERRORS = "errors"
    MESSAGE = "message"
    REPOSITORY = "repository"
    PULL_REQUEST = "pullRequest"
    PULL_REQUESTS = "pullRequests"
    NODES = "nodes"
    PAGE_INFO = "pageInfo"
    HAS_NEXT_PAGE = "hasNextPage"
    END_CURSOR = "endCursor"
    IDENTIFIER = "id"
    IS_RESOLVED = "isResolved"
    IS_OUTDATED = "isOutdated"
    PATH = "path"
    LINE = "line"
    COMMENTS = "comments"
    DATABASE_IDENTIFIER = "databaseId"
    AUTHOR = "author"
    LOGIN = "login"
    BODY = "body"
    CREATED_AT = "createdAt"
    URL = "url"
    REVIEWS = "reviews"
    REVIEW_THREADS = "reviewThreads"
    STATE = "state"
    SUBMITTED_AT = "submittedAt"
    NUMBER = "number"
    TITLE = "title"
    HEAD_REPOSITORY_OWNER = "headRepositoryOwner"
    COMMITS = "commits"
    COMMIT = "commit"
    STATUS_CHECK_ROLLUP = "statusCheckRollup"
    CONTEXTS = "contexts"
    TYPE_NAME = "__typename"
    NAME = "name"
    CONCLUSION = "conclusion"
    DETAILS_URL = "detailsUrl"
    CONTEXT = "context"
    TARGET_URL = "targetUrl"
    QUERY = "query"
    VARIABLES = "variables"

    def read_list(
        self, data: dict[str, Any], model: type[ParsedItem]
    ) -> list[ParsedItem]:
        """
        Parse every entry of the list-valued field this key names.

        GitHub returns a list-valued field as an object holding the array under
        ``nodes`` rather than as the array itself, so that step happens here rather
        than at each call site.

        :param data: The object the field belongs to.
        :param model: The model to parse each entry into.
        :return: The parsed entries, in the order GitHub returned them.
        """
        entries = data[self][PullRequestJSONKey.NODES]
        return [model.from_json(entry) for entry in entries]


class QueryVariable(StrEnum):
    """
    The variables the query documents declare.
    """

    OWNER = "owner"
    NAME = "name"
    HEAD_REF_NAME = "headRefName"
    NUMBER = "number"
    THREAD_CURSOR = "threadCursor"


class GraphQLDocument(StrEnum):
    """
    The query documents, stored as ``.graphql`` files beside this script.
    """

    PULL_REQUEST_FOR_BRANCH = "pull_request_for_branch"
    REVIEW_THREADS_PAGE = "review_threads_page"

    def read(self) -> str:
        """:return: The document's text."""
        return (PackageLocation.QUERIES / f"{self}.graphql").read_text()


class ReviewState(StrEnum):
    """
    The verdict a reviewer submitted with a review.

    Members are named as GitHub spells them, so a payload's value is looked up by
    name, and each member's value is how the verdict reads in the report.
    """

    APPROVED = "approved"
    """
    The reviewer approved the changes.
    """

    CHANGES_REQUESTED = "changes requested"
    """
    The reviewer asked for changes before the pull request can merge.
    """

    COMMENTED = "commented"
    """
    The reviewer left comments without a verdict.
    """

    DISMISSED = "dismissed"
    """
    The review was dismissed and no longer counts towards the verdict.
    """

    PENDING = "pending"
    """
    The review was started but not yet submitted.
    """


class PullRequestState(StrEnum):
    """
    The lifecycle state GitHub reports for a pull request.
    """

    OPEN = "OPEN"
    CLOSED = "CLOSED"
    MERGED = "MERGED"


class CheckContextType(StrEnum):
    """
    The two shapes GitHub returns inside a status check rollup.

    A pull request can carry both at once: Actions jobs arrive as check runs, while
    anything reporting through the older commit-status API arrives as a status
    context, and each spells its outcome with its own field.
    """

    CHECK_RUN = "CheckRun"
    """
    A check run, such as a GitHub Actions job, whose outcome is its conclusion.
    """

    STATUS_CONTEXT = "StatusContext"
    """
    A commit status posted through the commit-status API, whose outcome is its state.
    """


class CheckOutcome(StrEnum):
    """
    Where one check stands, over both shapes a rollup can hold.

    Members are named as GitHub spells them, so a payload's value is looked up by
    name, and each member's value is how the outcome reads in the report. A check run
    that has not finished reports no conclusion at all, which reads here as
    :attr:`PENDING` so an unfinished check is never mistaken for a passing one.
    """

    SUCCESS = "success"
    """
    The check passed.
    """

    FAILURE = "failure"
    """
    The check failed.
    """

    ERROR = "error"
    """
    The commit status reported an error.
    """

    CANCELLED = "cancelled"
    """
    The check run was cancelled before it finished.
    """

    TIMED_OUT = "timed out"
    """
    The check run exceeded its time limit.
    """

    ACTION_REQUIRED = "action required"
    """
    The check run needs someone to act before it can conclude.
    """

    NEUTRAL = "neutral"
    """
    The check run finished without passing or failing.
    """

    SKIPPED = "skipped"
    """
    The check run was skipped.
    """

    STALE = "stale"
    """
    GitHub marked the check run stale after it went too long without finishing.
    """

    STARTUP_FAILURE = "startup failure"
    """
    The check run failed before it could start.
    """

    PENDING = "pending"
    """
    The check has not finished yet.
    """

    EXPECTED = "expected"
    """
    A required commit status that has not been reported yet.
    """

    @property
    def rolls_up_to(self) -> RollupState:
        """
        :return: The verdict this outcome alone would give the whole rollup, the way
            GitHub counts it: a neutral or skipped check does not hold a pull request
            back, and everything that ended without passing fails it.
        """
        if self in {CheckOutcome.SUCCESS, CheckOutcome.NEUTRAL, CheckOutcome.SKIPPED}:
            return RollupState.SUCCESS
        if self in {CheckOutcome.ERROR, CheckOutcome.PENDING, CheckOutcome.EXPECTED}:
            return RollupState[self.name]
        return RollupState.FAILURE


class RollupState(StrEnum):
    """
    The verdict GitHub itself computes over all of a pull request's checks.

    Members are named as GitHub spells them, so a payload's value is looked up by
    name, and each member's value is how the verdict reads in the report.
    """

    SUCCESS = "success"
    """
    Every check passed.
    """

    FAILURE = "failure"
    """
    At least one check failed.
    """

    ERROR = "error"
    """
    At least one commit status reported an error.
    """

    PENDING = "pending"
    """
    At least one check has not finished yet.
    """

    EXPECTED = "expected"
    """
    At least one required commit status has not been reported yet.
    """

    @classmethod
    def over(cls, outcomes: list[CheckOutcome]) -> RollupState:
        """
        Compute the verdict GitHub would over a set of checks, for a source that does
        not report one: the worst any single check would give.

        :param outcomes: Every check's outcome, at least one.
        :return: The verdict.
        """
        reached = {outcome.rolls_up_to for outcome in outcomes}
        return next(state for state in cls.severity_order() if state in reached)

    @classmethod
    def severity_order(cls) -> list[RollupState]:
        """
        :return: Every verdict, worst first.
        """
        return [cls.FAILURE, cls.ERROR, cls.PENDING, cls.EXPECTED, cls.SUCCESS]


class ThreadMarker(StrEnum):
    """
    The annotations a thread can carry in the report.
    """

    RESOLVED = "resolved"
    OUTDATED = "outdated"


# %% errors


@dataclass
class UpstreamReadError(Exception, ABC):
    """
    Base class for every failure this script raises.
    """

    def __post_init__(self) -> None:
        Exception.__init__(self, self.describe())

    @abstractmethod
    def describe(self) -> str:
        """:return: The message a caller should see."""


@dataclass
class GitHubCommandFailed(UpstreamReadError):
    """
    Raised when the ``gh`` invocation itself exits non-zero.
    """

    executable: str
    """
    The command that was run.
    """

    exit_code: int
    """
    The status it exited with.
    """

    error_output: str
    """
    Whatever it wrote to standard error.
    """

    def describe(self) -> str:
        """:return: The message a caller should see."""
        return f"{self.executable} exited {self.exit_code}: {self.error_output}"


@dataclass
class GraphQLErrorsReturned(UpstreamReadError):
    """
    Raised when GitHub answers with an ``errors`` array instead of data.
    """

    messages: list[str]
    """
    Every message GitHub reported.
    """

    def describe(self) -> str:
        """:return: The message a caller should see."""
        return "; ".join(self.messages)


@dataclass
class UpstreamPullRequestNotFound(UpstreamReadError):
    """
    Raised when a branch has no pull request open on the upstream.
    """

    branch: str
    """
    The fork branch that was looked up.
    """

    upstream: Repository
    """
    The repository that was searched.
    """

    fork_owner: str
    """
    The owner whose head branches were being claimed.
    """

    def describe(self) -> str:
        """:return: The message a caller should see."""
        return (
            f"no pull request on {self.upstream} has head "
            f"'{self.fork_owner}:{self.branch}' - the branch has most likely not "
            "been promoted upstream yet"
        )


# %% models mirroring the data


@dataclass(frozen=True)
class Author(JSONModel):
    """
    Whoever wrote a comment or submitted a review.
    """

    login: str
    """
    Their GitHub login, or a placeholder when the account is gone.
    """

    @classproperty
    def unknown_login(cls) -> str:
        """
        Stands in for the author of a comment whose account no longer exists.
        """
        return "(unknown)"

    @classmethod
    def from_json(cls, data: dict[str, Any] | None) -> Author:
        """
        Read an author, tolerating the null GitHub returns for deleted users.

        :param data: The ``author`` object, which GitHub may report as null.
        :return: The parsed author.
        """
        if data is None:
            return cls(cls.unknown_login)
        return cls(data[PullRequestJSONKey.LOGIN])


@dataclass(frozen=True)
class ThreadComment(JSONModel):
    """
    One comment inside a review thread.
    """

    database_identifier: int
    """
    GitHub's numeric identifier, the one that appears in comment permalinks.
    """

    author: Author
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

    url: str
    """
    The permalink to this comment.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ThreadComment:
        """
        Build a comment from one ``comments`` node.

        :param data: The node to read.
        :return: The parsed comment.
        """
        return cls(
            database_identifier=data[PullRequestJSONKey.DATABASE_IDENTIFIER],
            author=Author.from_json(data[PullRequestJSONKey.AUTHOR]),
            body=data[PullRequestJSONKey.BODY],
            created_at=data[PullRequestJSONKey.CREATED_AT],
            url=data[PullRequestJSONKey.URL],
        )


@dataclass(frozen=True)
class ReviewThread(JSONModel):
    """
    A conversation anchored to one location in the pull request's diff.
    """

    identifier: str
    """
    GitHub's node identifier for the thread.
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

    comments: list[ThreadComment]
    """
    Every comment in the thread, oldest first.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ReviewThread:
        """
        Build a thread from one ``reviewThreads`` node.

        :param data: The node to read.
        :return: The parsed thread.
        """
        return cls(
            identifier=data[PullRequestJSONKey.IDENTIFIER],
            is_resolved=data[PullRequestJSONKey.IS_RESOLVED],
            is_outdated=data[PullRequestJSONKey.IS_OUTDATED],
            path=data[PullRequestJSONKey.PATH],
            line=data[PullRequestJSONKey.LINE],
            comments=PullRequestJSONKey.COMMENTS.read_list(data, ThreadComment),
        )

    @property
    def location(self) -> str:
        """:return: The thread's ``path:line``, or just its path when it is outdated."""
        if self.line is None:
            return self.path
        return f"{self.path}:{self.line}"

    @property
    def markers(self) -> list[ThreadMarker]:
        """:return: The annotations this thread carries."""
        carried = []
        if self.is_resolved:
            carried.append(ThreadMarker.RESOLVED)
        if self.is_outdated:
            carried.append(ThreadMarker.OUTDATED)
        return carried


@dataclass(frozen=True)
class Review(JSONModel):
    """
    A submitted review, separate from the threads it may have opened.
    """

    author: Author
    """
    Whoever submitted the review.
    """

    state: ReviewState
    """
    The verdict the reviewer submitted.
    """

    body: str
    """
    The review's summary text, which is often empty.
    """

    submitted_at: str
    """
    When the review was submitted, as an ISO 8601 timestamp.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Review:
        """
        Build a review from one ``reviews`` node.

        :param data: The node to read.
        :return: The parsed review.
        """
        return cls(
            author=Author.from_json(data[PullRequestJSONKey.AUTHOR]),
            state=ReviewState[data[PullRequestJSONKey.STATE]],
            body=data[PullRequestJSONKey.BODY],
            submitted_at=data[PullRequestJSONKey.SUBMITTED_AT],
        )


@dataclass(frozen=True)
class BranchPullRequest(JSONModel):
    """
    One pull request found by searching the upstream for a head branch.
    """

    number: int
    """
    Its number on the upstream repository.
    """

    state: PullRequestState
    """
    Its lifecycle state.
    """

    head_owner: Author
    """
    The owner of the repository the head branch lives in.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> BranchPullRequest:
        """
        Build a summary from one ``pullRequests`` node.

        :param data: The node to read.
        :return: The parsed summary.
        """
        return cls(
            number=data[PullRequestJSONKey.NUMBER],
            state=PullRequestState(data[PullRequestJSONKey.STATE]),
            head_owner=Author.from_json(data[PullRequestJSONKey.HEAD_REPOSITORY_OWNER]),
        )


@dataclass(frozen=True)
class PageInfo(JSONModel):
    """
    Where one page of a paged list stands in the whole list.
    """

    has_next_page: bool
    """
    Whether another page follows.
    """

    end_cursor: str | None
    """
    The cursor to request that next page with.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PageInfo:
        """
        Read a ``pageInfo`` object.

        :param data: The object to read.
        :return: The parsed page position.
        """
        return cls(
            has_next_page=data[PullRequestJSONKey.HAS_NEXT_PAGE],
            end_cursor=data[PullRequestJSONKey.END_CURSOR],
        )


@dataclass(frozen=True)
class ReviewThreadPage(JSONModel):
    """
    One page of review threads, with where it stands in the whole list.
    """

    threads: list[ReviewThread]
    """
    The threads on this page.
    """

    page_info: PageInfo
    """
    Whether another page follows, and the cursor to request it with.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ReviewThreadPage:
        """
        Build a page from a ``reviewThreads`` object.

        :param data: The object to read.
        :return: The parsed page.
        """
        return cls(
            threads=[
                ReviewThread.from_json(node) for node in data[PullRequestJSONKey.NODES]
            ],
            page_info=PageInfo.from_json(data[PullRequestJSONKey.PAGE_INFO]),
        )


@dataclass(frozen=True)
class CheckResult(JSONModel):
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

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> CheckResult:
        """
        Read one check out of a rollup context node.

        :param data: The node to read.
        :return: The parsed check.
        :raises ValueError: If the node is neither shape a rollup can hold.
        """
        if (
            CheckContextType(data[PullRequestJSONKey.TYPE_NAME])
            is CheckContextType.CHECK_RUN
        ):
            conclusion = data[PullRequestJSONKey.CONCLUSION]
            return cls(
                name=data[PullRequestJSONKey.NAME],
                outcome=(
                    CheckOutcome[conclusion] if conclusion else CheckOutcome.PENDING
                ),
                url=data[PullRequestJSONKey.DETAILS_URL] or "",
            )
        return cls(
            name=data[PullRequestJSONKey.CONTEXT],
            outcome=CheckOutcome[data[PullRequestJSONKey.STATE]],
            url=data[PullRequestJSONKey.TARGET_URL] or "",
        )

    @property
    def succeeded(self) -> bool:
        """:return: Whether this check reported success."""
        return self.outcome is CheckOutcome.SUCCESS


@dataclass(frozen=True)
class CheckStatus(JSONModel):
    """
    Every check reported against the pull request, with GitHub's verdict over them.
    """

    state: RollupState
    """
    The verdict GitHub computed over all of them.
    """

    results: list[CheckResult]
    """
    Every check, in the order GitHub returned them.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> CheckStatus:
        """
        Read the rollup out of a ``statusCheckRollup`` object.

        :param data: The rollup to read.
        :return: The parsed status.
        """
        return cls(
            state=RollupState[data[PullRequestJSONKey.STATE]],
            results=PullRequestJSONKey.CONTEXTS.read_list(data, CheckResult),
        )

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


@dataclass(frozen=True)
class Commit(JSONModel):
    """
    A commit, carrying the checks reported against it.
    """

    checks: CheckStatus | None
    """
    The checks reported against this commit, absent when none have reported.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Commit:
        """
        Read a ``commit`` object, whose rollup GitHub leaves null while nothing has
        reported against it.

        :param data: The object to read.
        :return: The parsed commit.
        """
        rollup = data[PullRequestJSONKey.STATUS_CHECK_ROLLUP]
        return cls(checks=CheckStatus.from_json(rollup) if rollup else None)


@dataclass(frozen=True)
class PullRequestCommit(JSONModel):
    """
    One entry of a pull request's commit list, which wraps the commit itself.
    """

    commit: Commit
    """
    The commit this entry stands for.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PullRequestCommit:
        """
        Read one ``commits`` node.

        :param data: The node to read.
        :return: The parsed entry.
        """
        return cls(commit=Commit.from_json(data[PullRequestJSONKey.COMMIT]))


@dataclass(frozen=True)
class PullRequest(JSONModel):
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

    commits: list[PullRequestCommit]
    """
    The commits the query selected, which is the head commit alone.
    """

    reviews: list[Review]
    """
    Every submitted review, oldest first.
    """

    review_threads: ReviewThreadPage
    """
    The page of review threads this response carried.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PullRequest:
        """
        Read a ``pullRequest`` object.

        :param data: The object to read.
        :return: The parsed pull request.
        """
        return cls(
            number=data[PullRequestJSONKey.NUMBER],
            title=data[PullRequestJSONKey.TITLE],
            url=data[PullRequestJSONKey.URL],
            commits=PullRequestJSONKey.COMMITS.read_list(data, PullRequestCommit),
            reviews=PullRequestJSONKey.REVIEWS.read_list(data, Review),
            review_threads=ReviewThreadPage.from_json(
                data[PullRequestJSONKey.REVIEW_THREADS]
            ),
        )

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


@dataclass(frozen=True)
class PullRequestForBranchResult(JSONModel):
    """
    What :attr:`GraphQLDocument.PULL_REQUEST_FOR_BRANCH` returns.
    """

    pull_requests: list[BranchPullRequest]
    """
    Every pull request the head-branch search matched, newest first.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PullRequestForBranchResult:
        """
        Read the query's ``data``, whose ``repository`` object selects nothing else.

        :param data: The response's ``data`` object.
        :return: The parsed result.
        """
        return cls(
            pull_requests=PullRequestJSONKey.PULL_REQUESTS.read_list(
                data[PullRequestJSONKey.REPOSITORY], BranchPullRequest
            )
        )


@dataclass(frozen=True)
class ReviewThreadsPageResult(JSONModel):
    """
    What :attr:`GraphQLDocument.REVIEW_THREADS_PAGE` returns.
    """

    pull_request: PullRequest
    """
    The pull request, carrying one page of its review threads.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ReviewThreadsPageResult:
        """
        Read the query's ``data``, whose ``repository`` object selects nothing else.

        :param data: The response's ``data`` object.
        :return: The parsed result.
        """
        return cls(
            pull_request=PullRequest.from_json(
                data[PullRequestJSONKey.REPOSITORY][PullRequestJSONKey.PULL_REQUEST]
            )
        )


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
            data=body.get(PullRequestJSONKey.DATA),
            errors=[
                error[PullRequestJSONKey.MESSAGE]
                for error in body.get(PullRequestJSONKey.ERRORS, [])
            ],
        )

    def result(self) -> dict[str, Any]:
        """:return: The query's result.

        :raises GraphQLErrorsReturned: If GitHub reported errors instead.
        """
        if self.errors:
            raise GraphQLErrorsReturned(self.errors)
        return self.data or {}


# %% models mirroring the REST data


class RestJSONKey(StrEnum):
    """
    Every field name this script reads out of a REST response.

    REST spells its fields apart from GraphQL, so they are named here rather than
    shared with :class:`PullRequestJSONKey`.
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
        stands in for one. A comment deleted since the comments were listed is left
        out rather than failing the whole read.

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


# %% the log behind a failed check


class LogFormatting(Enum):
    """
    What gets written around a log line's text that does not survive being quoted.
    """

    TERMINAL_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
    """
    The colour a test runner writes around its own output.
    """

    TIMESTAMP = re.compile(r"^\S+Z ")
    """
    The timestamp a runner writes in front of every line it records.
    """

    @classmethod
    def remove_from(cls, line: str) -> str:
        """
        :param line: One line of a job log.
        :return: The line's text alone.
        """
        for formatting in cls:
            line = formatting.value.sub("", line)
        return line


class LogMarker(StrEnum):
    """
    The lines in a runner's log that say where a failure is described.
    """

    PYTEST_SUMMARY = "short test summary info"
    """
    Opens pytest's own list of what failed, which is the answer wherever there is one.
    """

    ERROR_ANNOTATION = "##[error]"
    """
    Marks a line the runner itself flagged, which is all a job that died before pytest
    leaves behind.
    """


@dataclass(frozen=True)
class FailedJob:
    """
    The Actions job behind a check that did not pass.
    """

    identifier: int
    """
    The job's own number, which is what a log read asks for.
    """

    @classproperty
    def identifier_group(cls) -> str:
        """
        What the job's number is called inside :attr:`link_pattern`.
        """
        return "identifier"

    @classproperty
    def link_pattern(cls) -> re.Pattern[str]:
        """
        Where a check's own output link carries the job that produced it.
        """
        return re.compile(rf"/actions/runs/\d+/job/(?P<{cls.identifier_group}>\d+)")

    @classmethod
    def behind(cls, result: CheckResult) -> FailedJob | None:
        """
        Find the job a check's output link points at.

        A rollup also carries contexts posted by services that are not Actions at all,
        and those link somewhere with no job behind them.

        :param result: The check to locate.
        :return: The job, or ``None`` where the link names none.
        """
        match = cls.link_pattern.search(result.url)
        if match is None:
            return None
        return cls(int(match.group(cls.identifier_group)))


@dataclass(frozen=True)
class FailureLog:
    """
    The part of a failed job's log that says what went wrong.
    """

    check_name: str
    """
    The check whose job this came from.
    """

    lines: list[str]
    """
    The excerpt, oldest line first, with the runner's timestamps taken off.
    """

    @classproperty
    def line_limit(cls) -> int:
        """
        How many lines of one job's log the report is willing to quote.
        """
        return 40

    @classmethod
    def excerpt(cls, check_name: str, log: str) -> FailureLog:
        """
        Cut one whole job log down to the lines worth reading.

        pytest's own summary is preferred where the job ran that far, the runner's error
        annotations where it did not, and the log's last lines where neither marker
        appears at all. A runner's timestamps and a test runner's colour both come off,
        since neither survives being quoted under the check that produced it.

        :param check_name: The check the job reported for.
        :param log: The job log, exactly as the runner recorded it.
        :return: The excerpt.
        """
        lines = [LogFormatting.remove_from(line) for line in log.splitlines()]
        summary = cls._from_marker(lines, LogMarker.PYTEST_SUMMARY)
        if summary:
            ended = cls._until_marker(summary, LogMarker.ERROR_ANNOTATION)
            return cls(check_name, ended[: cls.line_limit])
        annotations = [line for line in lines if LogMarker.ERROR_ANNOTATION in line]
        if annotations:
            return cls(check_name, annotations[: cls.line_limit])
        return cls(check_name, lines[-cls.line_limit :])

    @staticmethod
    def _from_marker(lines: list[str], marker: LogMarker) -> list[str]:
        """
        :param lines: The log's lines.
        :param marker: What opens the part worth keeping.
        :return: That line and everything after it, empty where it never appears.
        """
        for index, line in enumerate(lines):
            if marker in line:
                return lines[index:]
        return []

    @staticmethod
    def _until_marker(lines: list[str], marker: LogMarker) -> list[str]:
        """
        Stop where the failure has been stated, before the steps that run afterwards.

        :param lines: The lines kept so far.
        :param marker: What the runner writes once the step has failed.
        :return: Everything through that line, or all of them where it never appears.
        """
        for index, line in enumerate(lines):
            if marker in line:
                return lines[: index + 1]
        return lines


# %% client


class JobLogReader(ABC):
    """
    Reads the log one Actions job recorded.
    """

    @abstractmethod
    def read_job_log(self, repository: Repository, job_identifier: int) -> str:
        """
        Read one job's whole log.

        :param repository: The repository the job ran in.
        :param job_identifier: The job to read.
        :return: The log, exactly as the runner recorded it.
        """


class GraphQLClient(ABC):
    """
    Sends a GraphQL document to GitHub and returns its ``data`` data.
    """

    @abstractmethod
    def execute(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """
        Run one GraphQL query.

        :param query: The GraphQL document.
        :param variables: The document's variables.
        :return: The response's ``data`` data.
        """


class RestClient(ABC):
    """
    Reads REST responses from GitHub.
    """

    @abstractmethod
    def get(self, path: str) -> Any:
        """
        Read one response.

        :param path: The REST path, query included.
        :return: The parsed response.
        """

    @abstractmethod
    def get_pages(self, path: str) -> list[Any]:
        """
        Read every page of a paged response.

        :param path: The REST path of the first page, query included.
        :return: Each page's parsed response, in order.
        """


@dataclass
class GitHubCommandLineClient(GraphQLClient, RestClient, JobLogReader):
    """
    A client that shells out to ``gh api``.

    A runner ships ``gh`` and authenticates it from ``GITHUB_TOKEN``, and a Claude Code
    session's proxy authenticates it for the repositories the session has attached, so
    this holds no credential handling of its own.
    """

    executable: str = GitHubClient.COMMAND_LINE
    """
    The command to invoke, overridable for testing.
    """

    @classproperty
    def allow_escape_sequences(cls) -> str:
        """
        What ``gh`` wants before it will print a log at all: a test runner colours its
        own output, and ``gh`` refuses to write terminal escape sequences it was not
        asked for.
        """
        return "--allow-escape-sequences"

    def execute(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """
        Run one GraphQL query through ``gh``.

        :param query: The GraphQL document.
        :param variables: The document's variables.
        :return: The response's ``data`` data.
        :raises GitHubCommandFailed: If ``gh`` exits non-zero.
        :raises GraphQLErrorsReturned: If GitHub answers with errors.
        """
        request = json.dumps(
            {PullRequestJSONKey.QUERY: query, PullRequestJSONKey.VARIABLES: variables}
        )
        return GraphQLResponse.from_json(
            self._run(["api", "graphql", "--input", "-"], request)
        ).result()

    def get(self, path: str) -> Any:
        """
        Read one REST response through ``gh``.

        :param path: The REST path, query included.
        :return: The parsed response.
        :raises GitHubCommandFailed: If ``gh`` exits non-zero.
        """
        return json.loads(self._run(["api", path]))

    def get_pages(self, path: str) -> list[Any]:
        """
        Read every page of a REST response through ``gh``, which follows the pages and
        collects them into one list.

        :param path: The REST path of the first page, query included.
        :return: Each page's parsed response, in order.
        :raises GitHubCommandFailed: If ``gh`` exits non-zero.
        """
        return json.loads(self._run(["api", "--paginate", "--slurp", path]))

    def read_job_log(self, repository: Repository, job_identifier: int) -> str:
        """
        Read one job's log through ``gh``.

        The upstream is a different repository from the one the runner is running in,
        which its token reads as anyone else does.

        :param repository: The repository the job ran in.
        :param job_identifier: The job to read.
        :return: The log, exactly as the runner recorded it.
        :raises GitHubCommandFailed: If ``gh`` exits non-zero.
        """
        return self._run(
            [
                "api",
                self.allow_escape_sequences,
                repository.job_log_path(job_identifier),
            ]
        )

    def _run(self, arguments: list[str], standard_input: str | None = None) -> str:
        """
        Invoke ``gh`` once and hand back what it wrote.

        :param arguments: The arguments to pass.
        :param standard_input: What to write to its standard input, if anything.
        :return: Its standard output.
        :raises GitHubCommandFailed: If it exits non-zero.
        """
        completed = subprocess.run(
            [self.executable, *arguments],
            input=standard_input,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise GitHubCommandFailed(
                self.executable, completed.returncode, completed.stderr.strip()
            )
        return completed.stdout


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
        """See :meth:`PullRequestSource.resolve_pull_request_number`."""
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
        """See :meth:`PullRequestSource.read_current_state`."""
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
        The most entries GitHub hands back per page, asked for so a long list takes
        as few requests as it can.
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
            f"{self.repository.api_path}/commits/{sha}/status"
            f"?per_page={self.page_size}"
        )


@dataclass
class RestPullRequestReader(PullRequestSource):
    """
    Reads one upstream pull request's checks and review state over REST, which is
    what a Claude Code session's proxy answers once the upstream is attached to it.
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
        """See :meth:`PullRequestSource.resolve_pull_request_number`."""
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
        """See :meth:`PullRequestSource.read_current_state`."""
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


@dataclass
class FailureLogReader:
    """
    Reads the log behind every check a pull request did not pass.
    """

    job_logs: JobLogReader
    """
    How one job's log is fetched.
    """

    upstream_repository: Repository
    """
    The repository whose jobs are read.
    """

    def read(self, checks: CheckStatus | None) -> list[FailureLog]:
        """
        Excerpt the log behind each check that failed.

        A check still running has no failure to describe, and one whose link names no
        job has no log to read, so both are left out rather than reported empty.

        :param checks: The head commit's checks, where it reported any.
        :return: One excerpt per failed check with a job behind it.
        """
        if checks is None:
            return []
        excerpts = []
        for result in checks.unsuccessful:
            if result.outcome is CheckOutcome.PENDING:
                continue
            job = FailedJob.behind(result)
            if job is None:
                continue
            excerpts.append(
                FailureLog.excerpt(
                    result.name,
                    self.job_logs.read_job_log(
                        self.upstream_repository, job.identifier
                    ),
                )
            )
        return excerpts


# %% configuration


def resolve_upstream_repository(
    configuration: CommittedStackConfiguration, override: str | None = None
) -> Repository:
    """
    Decide which repository the fork's pull requests are reviewed on.

    Reads the committed settings only. The per-user layer lives on the personal-notes
    branch, which a runner does not check out, so *override* is the escape hatch for a
    checkout whose upstream differs.

    :param configuration: The shipped defaults and the project's committed settings.
    :param override: An ``owner/name`` reference outranking the files.
    :return: The upstream repository.
    :raises MissingUpstreamRepositoryError: If neither names one and no override is given.
    """
    if override:
        return Repository.parse(override)
    return configuration.upstream_repository()


# %% report


class ReportText(StrEnum):
    """
    The fixed lines the report states rather than computes.
    """

    CHECKS_HEADING = "## Checks"
    NO_CHECKS = "No checks have reported."
    FAILURE_LOGS_HEADING = "## The log behind each failed check"
    REVIEWS_HEADING = "## Reviews"
    NO_REVIEWS = "No reviews submitted."
    NO_UNRESOLVED_HEADING = "## No unresolved review threads"
    NOTHING_TO_ACT_ON = "Nothing to act on."


@dataclass
class UpstreamPullRequestReport:
    """
    Renders a pull request's current upstream state as the markdown a session or a phone
    reads.
    """

    snapshot: UpstreamPullRequestSnapshot
    """
    The upstream state to describe.
    """

    include_resolved: bool = False
    """
    Whether threads already marked resolved are shown too.
    """

    failure_logs: list[FailureLog] = field(default_factory=list)
    """
    The excerpts to quote under the checks, empty where none were read.
    """

    def render(self) -> str:
        """:return: The report as markdown."""
        lines = [
            f"# Upstream pull request: #{self.snapshot.number} {self.snapshot.title}",
            "",
            self.snapshot.url,
            "",
        ]
        lines.extend(self._render_checks())
        lines.extend(self._render_failure_logs())
        lines.extend(self._render_reviews())
        lines.extend(self._render_threads())
        return "\n".join(lines)

    def heading(self, shown_count: int) -> str:
        """
        Describe the set actually being listed, not just the unresolved one.

        :param shown_count: How many threads the section goes on to list.
        :return: The section heading.
        """
        unresolved_count = len(self.snapshot.unresolved_threads)
        if not unresolved_count:
            return ReportText.NO_UNRESOLVED_HEADING
        if self.include_resolved:
            return f"## {shown_count} review threads, {unresolved_count} unresolved"
        return f"## {unresolved_count} unresolved review threads"

    @property
    def shown_threads(self) -> list[ReviewThread]:
        """:return: The threads this report lists."""
        if self.include_resolved:
            return self.snapshot.threads
        return self.snapshot.unresolved_threads

    def _render_checks(self) -> list[str]:
        """:return: The checks section."""
        checks = self.snapshot.checks
        if checks is None:
            return [ReportText.CHECKS_HEADING, "", ReportText.NO_CHECKS, ""]
        unsuccessful = checks.unsuccessful
        succeeded = len(checks.results) - len(unsuccessful)
        lines = [
            f"{ReportText.CHECKS_HEADING}: {checks.state} "
            f"({succeeded}/{len(checks.results)} passed)",
            "",
        ]
        for result in unsuccessful:
            location = f" <{result.url}>" if result.url else ""
            lines.append(f"- **{result.name}** — {result.outcome}{location}")
        lines.append("")
        return lines

    def _render_failure_logs(self) -> list[str]:
        """:return: The quoted-log section, empty where nothing was read."""
        if not self.failure_logs:
            return []
        lines = [ReportText.FAILURE_LOGS_HEADING, ""]
        for failure in self.failure_logs:
            lines.extend([f"### {failure.check_name}", "", "```"])
            lines.extend(failure.lines)
            lines.extend(["```", ""])
        return lines

    def _render_reviews(self) -> list[str]:
        """:return: The submitted-reviews section."""
        if not self.snapshot.reviews:
            return [ReportText.REVIEWS_HEADING, "", ReportText.NO_REVIEWS, ""]
        lines = [ReportText.REVIEWS_HEADING, ""]
        for review in self.snapshot.reviews:
            lines.append(
                f"- **{review.author.login}** — {review.state} "
                f"({review.submitted_at})"
            )
            if review.body.strip():
                lines.append(f"  > {review.body.strip()}")
        lines.append("")
        return lines

    def _render_threads(self) -> list[str]:
        """:return: The review-threads section."""
        shown = self.shown_threads
        lines = [self.heading(len(shown)), ""]
        if not shown:
            lines.extend([ReportText.NOTHING_TO_ACT_ON, ""])
            return lines
        for thread in shown:
            lines.extend(self._render_thread(thread))
        return lines

    def _render_thread(self, thread: ReviewThread) -> list[str]:
        """
        Render one thread with every comment in it.

        :param thread: The thread to render.
        :return: The thread's markdown lines.
        """
        markers = thread.markers
        suffix = f" _({', '.join(markers)})_" if markers else ""
        lines = [f"### `{thread.location}`{suffix}", ""]
        for comment in thread.comments:
            lines.append(f"- **{comment.author.login}**: {comment.body.strip()}")
        if thread.comments:
            lines.extend(["", f"<{thread.comments[0].url}>", ""])
        return lines


# %% command line


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    """
    Parse the command line.

    :param argv: The arguments to parse, defaulting to the process's own.
    :return: The parsed arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--pull-request", type=int, help="the upstream pull request number to read"
    )
    target.add_argument(
        "--branch", help="the fork branch whose upstream pull request to read"
    )
    parser.add_argument(
        "--fork-owner",
        default=GitHubActionsVariable.REPOSITORY_OWNER.read() or "",
        help="the owner whose branches to claim, defaulting to the runner's own",
    )
    parser.add_argument(
        "--upstream", help="an owner/name upstream outranking the configured one"
    )
    parser.add_argument(
        "--source",
        type=ReadSource,
        choices=list(ReadSource),
        default=None,
        help="the API to read through, defaulting to the one this place can reach",
    )
    parser.add_argument(
        "--include-resolved",
        action="store_true",
        help="show threads already marked resolved as well",
    )
    parser.add_argument(
        "--failure-logs",
        action="store_true",
        help="quote the log behind each check that failed",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """
    Read one upstream pull request and print its report.

    A branch that was never promoted upstream is an ordinary answer rather than a crash,
    so this boundary turns the script's own errors into a stated reason. Anything else
    still propagates with its traceback intact.

    :param argv: The arguments to parse, defaulting to the process's own.
    :return: The process exit status.
    """
    arguments = _parse_arguments(argv)
    try:
        report = _build_report(arguments)
    except (UpstreamReadError, MissingUpstreamRepositoryError) as failure:
        logger.error(failure)
        return 1
    logger.info(report)
    summary_path = GitHubActionsVariable.STEP_SUMMARY.read()
    if summary_path:
        Path(summary_path).write_text(report)
    return 0


def _build_report(arguments: argparse.Namespace) -> str:
    """
    Read the requested pull request and render its report.

    :param arguments: The parsed command line.
    :return: The rendered markdown.
    """
    client = GitHubCommandLineClient()
    upstream = resolve_upstream_repository(
        CommittedStackConfiguration(), override=arguments.upstream
    )
    source = arguments.source or ReadSource.detect()
    reader = source.reader(client, upstream, arguments.fork_owner)
    number = arguments.pull_request or reader.resolve_pull_request_number(
        arguments.branch
    )
    snapshot = reader.read_current_state(number)
    failure_logs = (
        FailureLogReader(client, upstream).read(snapshot.checks)
        if arguments.failure_logs
        else []
    )
    return UpstreamPullRequestReport(
        snapshot,
        include_resolved=arguments.include_resolved,
        failure_logs=failure_logs,
    ).render()


if __name__ == "__main__":
    sys.exit(main())
