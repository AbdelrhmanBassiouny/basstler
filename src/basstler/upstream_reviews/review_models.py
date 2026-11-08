"""
Models of a pull request's reviews and review threads, as GitHub's GraphQL API returns
them.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field, model_validator
from pydantic.dataclasses import dataclass

from basstler.class_property import classproperty
from basstler.upstream_reviews.vocabulary import (
    GraphQLConnection,
    PullRequestState,
    ReviewState,
    ThreadMarker,
    ValidatedJSONModel,
)

# %% models mirroring the data


@dataclass(frozen=True)
class Author(ValidatedJSONModel):
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

    @model_validator(mode="before")
    @classmethod
    def read_deleted_account(cls, data: Any) -> Any:
        """
        :param data: The ``author`` object, which GitHub reports as null for a deleted
            account.
        :return: The object, with :attr:`unknown_login` standing in for a deleted one.
        """
        if data is None:
            return {"login": cls.unknown_login}
        return data


@dataclass(frozen=True)
class ThreadComment(ValidatedJSONModel):
    """
    One comment inside a review thread.
    """

    database_identifier: Annotated[int, Field(alias="databaseId")]
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

    created_at: Annotated[str, Field(alias="createdAt")]
    """
    When the comment was posted, as an ISO 8601 timestamp.
    """

    url: str
    """
    The permalink to this comment.
    """


@dataclass(frozen=True)
class ReviewThread(ValidatedJSONModel):
    """
    A conversation anchored to one location in the pull request's diff.
    """

    identifier: Annotated[str, Field(alias="id")]
    """
    GitHub's node identifier for the thread.
    """

    is_resolved: Annotated[bool, Field(alias="isResolved")]
    """
    Whether a reviewer has marked the thread resolved.
    """

    is_outdated: Annotated[bool, Field(alias="isOutdated")]
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

    comments: GraphQLConnection[ThreadComment]
    """
    Every comment in the thread, oldest first.
    """

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
class Review(ValidatedJSONModel):
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

    submitted_at: Annotated[str, Field(alias="submittedAt")]
    """
    When the review was submitted, as an ISO 8601 timestamp.
    """


@dataclass(frozen=True)
class BranchPullRequest(ValidatedJSONModel):
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

    head_owner: Annotated[Author, Field(alias="headRepositoryOwner")]
    """
    The owner of the repository the head branch lives in.
    """


@dataclass(frozen=True)
class PageInfo(ValidatedJSONModel):
    """
    Where one page of a paged list stands in the whole list.
    """

    has_next_page: Annotated[bool, Field(alias="hasNextPage")]
    """
    Whether another page follows.
    """

    end_cursor: Annotated[str | None, Field(alias="endCursor")]
    """
    The cursor to request that next page with.
    """


@dataclass(frozen=True)
class ReviewThreadPage(ValidatedJSONModel):
    """
    One page of review threads, with where it stands in the whole list.
    """

    threads: Annotated[list[ReviewThread], Field(alias="nodes")]
    """
    The threads on this page.
    """

    page_info: Annotated[PageInfo, Field(alias="pageInfo")]
    """
    Whether another page follows, and the cursor to request it with.
    """
