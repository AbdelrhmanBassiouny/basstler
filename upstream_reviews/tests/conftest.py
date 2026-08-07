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
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest  # noqa: E402

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    """
    Read one recorded GraphQL ``data`` payload.

    :param name: The fixture's filename stem.
    :return: The parsed payload.
    """
    return json.loads((FIXTURE_DIRECTORY / f"{name}.json").read_text())


class ReplayingTransport:
    """
    A transport that returns queued payloads instead of calling GitHub.

    Records every query and variable set it was given, so a test can assert the exact
    request the reader made.
    """

    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = list(payloads)
        """
        The payloads still to be returned, in order.
        """
        self.calls: list[tuple[str, dict[str, Any]]] = []
        """
        Every ``(query, variables)`` pair the reader executed.
        """

    def execute(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """
        Return the next queued payload.

        :param query: The GraphQL document, recorded for assertions.
        :param variables: The GraphQL variables, recorded for assertions.
        :return: The next queued payload.
        """
        self.calls.append((query, variables))
        return self.payloads.pop(0)


@pytest.fixture
def paginated_transport() -> ReplayingTransport:
    """:return: A transport replaying both pages of the recorded review threads."""
    return ReplayingTransport(
        [load_fixture("pull_request_page_one"), load_fixture("pull_request_page_two")]
    )
