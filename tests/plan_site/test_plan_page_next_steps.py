"""
Tests for :mod:`basstler.plan_site.plan_page`: which items the page lists as next steps.
"""

from __future__ import annotations

from datetime import datetime

from basstler.plan.model import ItemStatus
from basstler.pull_request_state import (
    LiveState,
    PullRequestRecord,
    PullRequestState,
)

from .plan_page_builders import (
    item,
    make_renderer,
)

# %% ready to start and blocker may be cleared


def test_item_becomes_ready_to_start_once_all_dependencies_are_done():
    items = [
        item("a", ItemStatus.DONE),
        item("b", ItemStatus.NOT_STARTED, depends_on=["a"]),
    ]
    renderer = make_renderer(items)
    summary = renderer.render().overview
    assert summary.ready_to_start == ["b"]


def test_blocked_item_with_partial_dependencies_done_is_recheck_candidate():
    items = [
        item("a", ItemStatus.DONE),
        item("b", ItemStatus.BLOCKED),
        item("c", ItemStatus.BLOCKED, depends_on=["a", "b"]),
    ]
    renderer = make_renderer(items)
    summary = renderer.render().overview
    assert summary.blocker_maybe_cleared == ["c"]
    assert summary.ready_to_start == []


def test_blocked_item_with_every_dependency_done_is_recheck_not_ready_to_start():
    # A blocked item is still blocked even once its dependencies clear -
    # it belongs in "blocker may be cleared" (actionable: resolve it), never
    # in "ready to start" (that implies starting fresh, which is wrong for
    # an item that already has real state).
    items = [
        item("a", ItemStatus.DONE),
        item("b", ItemStatus.BLOCKED, depends_on=["a"]),
    ]
    renderer = make_renderer(items)
    summary = renderer.render().overview
    assert summary.blocker_maybe_cleared == ["b"]
    assert summary.ready_to_start == []


def test_item_becomes_ready_to_start_once_dependency_is_open_and_ready_for_review():
    # Stacking a branch on a same-track dependency that's already open and
    # out of draft is this repo's normal workflow - waiting for a full merge
    # first would be stricter than how the stack is actually built.
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state=PullRequestState.OPEN, draft=False)}
    }
    items = [
        item("a", ItemStatus.IN_PROGRESS, pull_request_number=1),
        item("b", ItemStatus.NOT_STARTED, depends_on=["a"]),
    ]
    renderer = make_renderer(
        items, pull_requests_by_repository=pull_requests_by_repository
    )
    summary = renderer.render().overview
    assert summary.ready_to_start == ["b"]


def test_item_not_ready_to_start_while_dependency_is_still_a_draft():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state=PullRequestState.OPEN, draft=True)}
    }
    items = [
        item("a", ItemStatus.IN_PROGRESS, pull_request_number=1),
        item("b", ItemStatus.NOT_STARTED, depends_on=["a"]),
    ]
    renderer = make_renderer(
        items, pull_requests_by_repository=pull_requests_by_repository
    )
    summary = renderer.render().overview
    assert summary.ready_to_start == []


def test_not_started_item_with_partial_dependencies_is_neither_list():
    items = [
        item("a", ItemStatus.DONE),
        item("b", ItemStatus.BLOCKED),
        item("c", ItemStatus.NOT_STARTED, depends_on=["a", "b"]),
    ]
    renderer = make_renderer(items)
    summary = renderer.render().overview
    assert summary.ready_to_start == []
    assert summary.blocker_maybe_cleared == []


def test_dependency_free_not_started_item_is_ready_to_start():
    items = [item("a", ItemStatus.NOT_STARTED)]
    renderer = make_renderer(items)
    summary = renderer.render().overview
    assert summary.ready_to_start == ["a"]


def test_dependency_free_blocked_item_is_neither_list():
    items = [item("a", ItemStatus.BLOCKED)]
    renderer = make_renderer(items)
    summary = renderer.render().overview
    assert summary.ready_to_start == []
    assert summary.blocker_maybe_cleared == []


# %% ready to review


def test_needs_review_true_for_an_open_draft_pull_request():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state=PullRequestState.OPEN, draft=True)}
    }
    renderer = make_renderer(
        [item("a", ItemStatus.IN_PROGRESS, pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    renderer.render()
    assert renderer.plan.items[0].needs_review


def test_needs_review_false_once_marked_ready_for_review():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state=PullRequestState.OPEN, draft=False)}
    }
    renderer = make_renderer(
        [item("a", ItemStatus.IN_PROGRESS, pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    renderer.render()
    assert not renderer.plan.items[0].needs_review


def test_needs_review_false_with_no_pull_request():
    renderer = make_renderer([item("a", ItemStatus.NOT_STARTED)])
    renderer.render()
    assert not renderer.plan.items[0].needs_review


def test_needs_review_false_for_a_deferred_item_with_an_open_draft_pull_request():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state=PullRequestState.OPEN, draft=True)}
    }
    renderer = make_renderer(
        [item("a", ItemStatus.DEFERRED, pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    renderer.render()
    assert not renderer.plan.items[0].needs_review


def test_has_open_pull_request_true_for_draft_and_ready():
    draft_item = item("a", ItemStatus.IN_PROGRESS, pull_request_number=1)
    draft_item.live_state = LiveState.OPEN_DRAFT
    ready_item = item("b", ItemStatus.IN_PROGRESS, pull_request_number=2)
    ready_item.live_state = LiveState.OPEN_READY
    assert draft_item.has_open_pull_request
    assert ready_item.has_open_pull_request


def test_has_open_pull_request_false_when_merged_or_absent():
    merged_item = item("a", ItemStatus.DONE, pull_request_number=1)
    merged_item.live_state = LiveState.MERGED
    no_pull_request_item = item("b", ItemStatus.NOT_STARTED)
    assert not merged_item.has_open_pull_request
    assert not no_pull_request_item.has_open_pull_request


def test_item_with_no_dependency_and_draft_pull_request_is_ready_to_review():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state=PullRequestState.OPEN, draft=True)}
    }
    renderer = make_renderer(
        [item("a", ItemStatus.IN_PROGRESS, pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    summary = renderer.render().overview
    assert summary.ready_to_review == ["a"]


def test_blocked_item_with_draft_pull_request_is_not_ready_to_review():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state=PullRequestState.OPEN, draft=True)}
    }
    renderer = make_renderer(
        [item("a", ItemStatus.BLOCKED, pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    summary = renderer.render().overview
    assert summary.ready_to_review == []


def test_deferred_item_with_draft_pull_request_is_not_ready_to_review():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state=PullRequestState.OPEN, draft=True)}
    }
    renderer = make_renderer(
        [item("a", ItemStatus.DEFERRED, pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    summary = renderer.render().overview
    assert summary.ready_to_review == []


def test_item_not_ready_to_review_while_dependency_has_no_pull_request():
    pull_requests_by_repository = {
        "owner/repo": {"2": PullRequestRecord(state=PullRequestState.OPEN, draft=True)}
    }
    items = [
        item("a", ItemStatus.NOT_STARTED),
        item("b", ItemStatus.IN_PROGRESS, pull_request_number=2, depends_on=["a"]),
    ]
    renderer = make_renderer(
        items, pull_requests_by_repository=pull_requests_by_repository
    )
    summary = renderer.render().overview
    assert summary.ready_to_review == []


def test_item_ready_to_review_once_dependency_has_an_open_pull_request():
    # The dependency need not itself be past review - it just needs a pull
    # request open, so a whole reviewable stack can surface before its base merges.
    pull_requests_by_repository = {
        "owner/repo": {
            "1": PullRequestRecord(state=PullRequestState.OPEN, draft=True),
            "2": PullRequestRecord(state=PullRequestState.OPEN, draft=True),
        }
    }
    items = [
        item("a", ItemStatus.IN_PROGRESS, pull_request_number=1),
        item("b", ItemStatus.IN_PROGRESS, pull_request_number=2, depends_on=["a"]),
    ]
    renderer = make_renderer(
        items, pull_requests_by_repository=pull_requests_by_repository
    )
    summary = renderer.render().overview
    assert summary.ready_to_review == ["a", "b"]


def test_item_ready_to_review_once_its_dependency_has_merged():
    pull_requests_by_repository = {
        "owner/repo": {
            "1": PullRequestRecord(
                state=PullRequestState.CLOSED, merged_at=datetime(2026, 1, 1)
            ),
            "2": PullRequestRecord(state=PullRequestState.OPEN, draft=True),
        }
    }
    items = [
        item("a", ItemStatus.DONE, pull_request_number=1),
        item("b", ItemStatus.IN_PROGRESS, pull_request_number=2, depends_on=["a"]),
    ]
    renderer = make_renderer(
        items, pull_requests_by_repository=pull_requests_by_repository
    )
    summary = renderer.render().overview
    assert summary.ready_to_review == ["b"]


def test_item_ready_to_review_when_its_dependency_is_done_without_a_pull_request():
    pull_requests_by_repository = {
        "owner/repo": {"2": PullRequestRecord(state=PullRequestState.OPEN, draft=True)}
    }
    items = [
        item("a", ItemStatus.DONE),
        item("b", ItemStatus.IN_PROGRESS, pull_request_number=2, depends_on=["a"]),
    ]
    renderer = make_renderer(
        items, pull_requests_by_repository=pull_requests_by_repository
    )
    summary = renderer.render().overview
    assert summary.ready_to_review == ["b"]


def test_item_not_ready_to_review_while_its_dependency_is_closed_unmerged():
    pull_requests_by_repository = {
        "owner/repo": {
            "1": PullRequestRecord(state=PullRequestState.CLOSED),
            "2": PullRequestRecord(state=PullRequestState.OPEN, draft=True),
        }
    }
    items = [
        item("a", ItemStatus.IN_PROGRESS, pull_request_number=1),
        item("b", ItemStatus.IN_PROGRESS, pull_request_number=2, depends_on=["a"]),
    ]
    renderer = make_renderer(
        items, pull_requests_by_repository=pull_requests_by_repository
    )
    summary = renderer.render().overview
    assert summary.ready_to_review == []
