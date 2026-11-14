"""
Tests for :mod:`basstler.plan_site.item_classifier`: what each item's live pull request
state and drift come to.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from basstler.github.pull_request_state import (
    LiveState,
    PullRequestRecord,
    PullRequestState,
)
from basstler.plan.model import ItemStatus

from .plan_page_builders import (
    item,
    make_renderer,
)

# %% live state and drift


def test_item_with_no_pull_request_has_no_pull_request_live_state_and_no_drift():
    renderer = make_renderer([item("a", ItemStatus.NOT_STARTED)])
    summary = renderer.render().overview
    assert renderer.plan.items[0].live_state is LiveState.NO_PULL_REQUEST
    assert summary.drift_items == []


def test_merged_pull_request_shows_a_not_started_item_as_done_without_drift():
    pull_requests_by_repository = {
        "owner/repo": {
            "1": PullRequestRecord(
                state=PullRequestState.CLOSED, merged_at=datetime(2026, 1, 1)
            )
        }
    }
    renderer = make_renderer(
        [item("a", ItemStatus.NOT_STARTED, pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    summary = renderer.render().overview
    assert renderer.plan.items[0].live_state is LiveState.MERGED
    assert renderer.plan.items[0].status is ItemStatus.DONE
    assert summary.drift_items == []


def test_merged_item_counts_as_done():
    pull_requests_by_repository = {
        "owner/repo": {
            "1": PullRequestRecord(
                state=PullRequestState.CLOSED, merged_at=datetime(2026, 1, 1)
            )
        }
    }
    renderer = make_renderer(
        [item("a", ItemStatus.IN_PROGRESS, pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    summary = renderer.render().overview
    assert summary.status_counts[ItemStatus.DONE] == 1
    assert summary.status_counts[ItemStatus.IN_PROGRESS] == 0


def test_closed_pull_request_with_merged_label_is_merged_not_closed_unmerged():
    # merged_at is unset here on purpose - this is the out-of-band-merge case
    # PullRequestRecord.was_merged exists for.
    pull_requests_by_repository = {
        "owner/repo": {
            "1": PullRequestRecord(state=PullRequestState.CLOSED, labels=["merged"])
        }
    }
    renderer = make_renderer(
        [item("a", ItemStatus.IN_PROGRESS, pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    summary = renderer.render().overview
    assert renderer.plan.items[0].live_state is LiveState.MERGED
    assert summary.drift_items == []


def test_open_pull_request_marks_done_item_as_drifted():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state=PullRequestState.OPEN, draft=False)}
    }
    renderer = make_renderer(
        [item("a", ItemStatus.DONE, pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    summary = renderer.render().overview
    assert summary.drift_items == ["a"]


def test_pull_request_missing_from_live_data_is_not_found_and_drifted():
    renderer = make_renderer(
        [item("a", ItemStatus.NOT_STARTED, pull_request_number=999)]
    )
    summary = renderer.render().overview
    assert renderer.plan.items[0].live_state is LiveState.NOT_FOUND
    assert summary.drift_items == ["a"]


def test_closed_unmerged_pull_request_marks_done_item_as_drifted():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state=PullRequestState.CLOSED)}
    }
    renderer = make_renderer(
        [item("a", ItemStatus.DONE, pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    summary = renderer.render().overview
    assert renderer.plan.items[0].live_state is LiveState.CLOSED_UNMERGED
    assert summary.drift_items == ["a"]


@pytest.mark.parametrize("status", [ItemStatus.IN_PROGRESS, ItemStatus.BLOCKED])
def test_closed_unmerged_pull_request_marks_in_progress_or_blocked_item_as_drifted(
    status,
):
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state=PullRequestState.CLOSED)}
    }
    renderer = make_renderer(
        [item("a", status, pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    summary = renderer.render().overview
    assert summary.drift_items == ["a"]


def test_matching_status_and_live_state_is_not_drifted():
    pull_requests_by_repository = {
        "owner/repo": {"1": PullRequestRecord(state=PullRequestState.OPEN, draft=True)}
    }
    renderer = make_renderer(
        [item("a", ItemStatus.IN_PROGRESS, pull_request_number=1)],
        pull_requests_by_repository=pull_requests_by_repository,
    )
    summary = renderer.render().overview
    assert summary.drift_items == []
