"""
Makes ``upstream_reviews`` importable as a plain module and loads the recorded GraphQL
payloads the tests replay.

It is a single-file script run via ``python3 upstream_reviews.py ...``, not an
installed package - so its directory is added to ``sys.path`` here rather than
requiring an ``__init__.py``/packaging setup just for tests. Mirrors
``.claude/stack/tests/conftest.py`` and
``.claude/skills/plan-dashboard/tests/conftest.py``.
"""

import json
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest  # noqa: E402

from upstream_reviews import GraphQLTransport  # noqa: E402

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"
"""
Where the recorded GraphQL payloads live.
"""


class FixtureName(StrEnum):
    """
    The recorded payloads the tests replay, named by their filename stem.
    """

    PULL_REQUEST_PAGE_ONE = "pull_request_page_one"
    PULL_REQUEST_PAGE_TWO = "pull_request_page_two"
    BRANCH_PULL_REQUESTS = "branch_pull_requests"
    BRANCH_PULL_REQUESTS_FOREIGN_OWNER = "branch_pull_requests_foreign_owner"

    def load(self) -> dict[str, Any]:
        """:return: The recorded ``data`` payload this fixture holds."""
        return json.loads((FIXTURE_DIRECTORY / f"{self}.json").read_text())


@dataclass(frozen=True)
class RecordedCall:
    """
    One query the reader executed, kept so a test can assert on it.
    """

    query: str
    """
    The GraphQL document that was sent.
    """

    variables: dict[str, Any]
    """
    The variables it was sent with.
    """


@dataclass
class ReplayingTransport(GraphQLTransport):
    """
    A transport that returns queued payloads instead of calling GitHub.

    Records every call it was given, so a test can assert the exact request the reader
    made.
    """

    payloads: list[dict[str, Any]]
    """
    The payloads still to be returned, in order.
    """

    calls: list[RecordedCall] = field(default_factory=list)
    """
    Every call the reader executed, oldest first.
    """

    def execute(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """
        Return the next queued payload.

        :param query: The GraphQL document, recorded for assertions.
        :param variables: The GraphQL variables, recorded for assertions.
        :return: The next queued payload.
        """
        self.calls.append(RecordedCall(query, variables))
        return self.payloads.pop(0)


@pytest.fixture
def paginated_transport() -> ReplayingTransport:
    """:return: A transport replaying both pages of the recorded review threads."""
    return ReplayingTransport(
        [
            FixtureName.PULL_REQUEST_PAGE_ONE.load(),
            FixtureName.PULL_REQUEST_PAGE_TWO.load(),
        ]
    )
