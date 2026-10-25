"""
The contract every model of GitHub's data keeps, and the fixed values GitHub's
pull-request data is written in.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeVar

from basstler.class_property import classproperty
from basstler.locations import PackageLocation

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


# %% the fork's Action branch


class ActionBranch(StrEnum):
    """
    Where the Action lives in the fork.
    """

    NAME = "basstler/upstream-reviews"
    """
    The branch, outside both the fork's default branch and the ``claude/`` branches
    stack maintenance owns.
    """

    LOCAL_REFERENCE = "refs/basstler/upstream-reviews"
    """
    Where a fetch of it is kept, so it never moves ``FETCH_HEAD`` under anyone else.
    """

    @classproperty
    def install_command(cls) -> str:
        """
        How a reader is told to install the branch or bring it up to date.
        """
        return (
            "python -m basstler.setup.steps install-upstream-reviews-action "
            "--branch-or-tag <the basstler release the session runs> "
            "(/setup-personal-notes runs it)"
        )


class ActionFile(StrEnum):
    """
    Every file on the branch.
    """

    WORKFLOW = ".github/workflows/upstream-reviews.yml"
    README = "README.md"
    REQUEST = "request.json"
    RESULT = "result.json"

    @property
    def file_name(self) -> str:
        """:return: The file's own name, without its directory."""
        return Path(self.value).name


class BasstlerSource(StrEnum):
    """
    Where the reusable workflow and the package a run installs come from.
    """

    REPOSITORY = "AbdelrhmanBassiouny/basstler"
    REUSABLE_WORKFLOW = ".github/workflows/upstream-reviews-action.yml"
