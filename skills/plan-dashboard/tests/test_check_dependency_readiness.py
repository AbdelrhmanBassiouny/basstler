"""
Tests for check_dependency_readiness.py: classifying one item's dependencies as ready or
not-ready to build on, via build_dashboard.py's own live-state rule.
"""

import pytest

from build_dashboard import (
    Item,
    ItemStatus,
    Plan,
    PullRequestRecord,
    PullRequestState,
    Track,
    Wave,
)
from check_dependency_readiness import UnknownItemError, dependency_readiness


def make_plan(items):
    return Plan(
        id="test-plan",
        title="Test Plan",
        description="desc",
        default_repository="owner/repo",
        waves=[Wave(id="wave-1", name="Wave One")],
        tracks=[Track(id="track-1", name="Track One", wave="wave-1")],
        items=items,
    )


def item(identifier, status: ItemStatus, pull_request_number=None, depends_on=None):
    return Item(
        title=identifier,
        branch=identifier,
        track="track-1",
        status=status,
        id=identifier,
        pull_request_number=pull_request_number,
        depends_on=depends_on or [],
    )


def test_raises_for_an_unknown_item():
    plan = make_plan([item("a", ItemStatus.NOT_STARTED)])
    with pytest.raises(UnknownItemError, match="ghost"):
        dependency_readiness(plan, "ghost", {})


def test_empty_list_for_an_item_with_no_dependencies():
    plan = make_plan([item("a", ItemStatus.NOT_STARTED)])
    assert dependency_readiness(plan, "a", {}) == []


def test_done_dependency_is_ready():
    plan = make_plan(
        [
            item("a", ItemStatus.DONE),
            item("b", ItemStatus.NOT_STARTED, depends_on=["a"]),
        ]
    )
    results = dependency_readiness(plan, "b", {})
    assert results == [
        {"identifier": "a", "title": "a", "live_state": "none", "is_ready": True}
    ]


def test_open_ready_dependency_is_ready():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state=PullRequestState.OPEN, draft=False)}
    }
    plan = make_plan(
        [
            item("a", ItemStatus.IN_PROGRESS, pull_request_number=1),
            item("b", ItemStatus.NOT_STARTED, depends_on=["a"]),
        ]
    )
    results = dependency_readiness(plan, "b", pull_requests_by_repository)
    assert results == [
        {
            "identifier": "a",
            "title": "a",
            "live_state": "open_ready",
            "is_ready": True,
        }
    ]


def test_open_draft_dependency_is_not_ready():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state=PullRequestState.OPEN, draft=True)}
    }
    plan = make_plan(
        [
            item("a", ItemStatus.IN_PROGRESS, pull_request_number=1),
            item("b", ItemStatus.NOT_STARTED, depends_on=["a"]),
        ]
    )
    results = dependency_readiness(plan, "b", pull_requests_by_repository)
    assert results == [
        {
            "identifier": "a",
            "title": "a",
            "live_state": "open_draft",
            "is_ready": False,
        }
    ]


def test_unresolvable_dependency_identifier_is_reported_not_ready():
    plan = make_plan([item("b", ItemStatus.NOT_STARTED, depends_on=["ghost"])])
    results = dependency_readiness(plan, "b", {})
    assert results == [
        {"identifier": "ghost", "title": None, "live_state": None, "is_ready": False}
    ]


def test_multiple_dependencies_reported_in_order():
    plan = make_plan(
        [
            item("a", ItemStatus.DONE),
            item("b", ItemStatus.NOT_STARTED),
            item("c", ItemStatus.NOT_STARTED, depends_on=["b", "a"]),
        ]
    )
    results = dependency_readiness(plan, "c", {})
    assert [entry["identifier"] for entry in results] == ["b", "a"]
    assert [entry["is_ready"] for entry in results] == [False, True]
