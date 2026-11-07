"""
Tests for an item issue's body: its scope and dependency list, written and read back,
and the issues a pull request's description closes.
"""

from __future__ import annotations

import pytest

from basstler.plan_store.exceptions import MalformedDependencyError
from basstler.plan_store.item_body import (
    ClosingKeyword,
    IssueReference,
    ItemBody,
    ItemBodySection,
)
from basstler.repository import Repository

HOME = Repository("example-owner", "example-repo")
OTHER = Repository("other-owner", "other-repo")

# %% dependency lists


def test_body_round_trips_through_its_text():
    body = ItemBody(
        "Store plans as issues.\n\nREST only.",
        (IssueReference(HOME, 12), IssueReference(OTHER, 7)),
    )
    assert ItemBody.parse(body.render(HOME), HOME) == body


def test_dependency_in_the_same_repository_is_written_by_number_alone():
    body = ItemBody("Scope.", (IssueReference(HOME, 12),))
    assert body.render(HOME).endswith(f"{ItemBodySection.DEPENDS_ON}\n\n- #12")


def test_body_without_dependencies_is_its_scope():
    assert ItemBody("Scope.").render(HOME) == "Scope."


def test_body_without_a_dependency_list_has_no_dependencies():
    assert ItemBody.parse("Scope.\n", HOME) == ItemBody("Scope.")


def test_dependency_list_written_with_windows_line_endings_is_read():
    text = f"Scope.\r\n\r\n{ItemBodySection.DEPENDS_ON}\r\n\r\n- #12\r\n"
    assert ItemBody.parse(text, HOME).dependencies == (IssueReference(HOME, 12),)


def test_dependency_line_that_is_no_reference_is_refused():
    with pytest.raises(MalformedDependencyError):
        ItemBody.parse(f"Scope.\n\n{ItemBodySection.DEPENDS_ON}\n\n- soon", HOME)


# %% closing references


@pytest.mark.parametrize("keyword", list(ClosingKeyword))
def test_every_closing_keyword_closes_the_issue_after_it(keyword):
    assert IssueReference.closed_by(f"{keyword.title()}: #5", HOME) == {
        IssueReference(HOME, 5)
    }


def test_closing_reference_names_another_repository():
    assert IssueReference.closed_by(
        f"{ClosingKeyword.FIXES} other-owner/other-repo#7", HOME
    ) == {IssueReference(OTHER, 7)}


def test_mention_without_a_closing_keyword_closes_nothing():
    assert IssueReference.closed_by("Prepares for #5.", HOME) == set()
