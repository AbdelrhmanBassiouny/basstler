"""
The GraphQL documents the upstream reviews are read with, and their variables.
"""

from __future__ import annotations

from enum import StrEnum

from basstler.locations import PackageLocation

# %% the query documents


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
        return (PackageLocation.QUERIES / f"{self}.graphql").read_text(encoding="utf-8")
