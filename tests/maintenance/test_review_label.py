"""
Tests for keeping the in-review label on each fork pull request in step with its
upstream pull request.
"""

from __future__ import annotations

from dataclasses import replace

from basstler.maintenance.review_label import (
    ReviewLabelAction,
    ReviewLabelChange,
    synchronize_review_labels,
)
from basstler.stack.model import PullRequest

from ..constants.stack import StackBranch, StackLabel

from .fork import (
    ForkCheckout,
    StackPullRequestNumber,
    a_parent_and_child,
    a_stack,
    the_board,
)
from .recorded_fork import RecordedLabelWrite, RecordingPullRequests

# %% the board under test


def a_board_whose_parent(
    upstream_pull_request: int | None, labels: list[str]
) -> list[PullRequest]:
    """
    :param upstream_pull_request: The open upstream pull request opened from the parent.
    :param labels: The labels the board snapshot found on the parent.
    :return: The two-branch board, its parent in that state.
    """
    parent, child = the_board()
    return [
        replace(parent, upstream_pull_request=upstream_pull_request, labels=labels),
        child,
    ]


# %% keeping the label in step


def test_a_branch_under_upstream_review_gains_the_label(fork_checkout: ForkCheckout):
    a_parent_and_child(fork_checkout)
    fork = RecordingPullRequests()
    board = a_board_whose_parent(StackPullRequestNumber.UPSTREAM, labels=[])

    changes = synchronize_review_labels(a_stack(fork_checkout, board), fork)

    assert changes == [
        ReviewLabelChange(
            StackBranch.PARENT, StackPullRequestNumber.PARENT, ReviewLabelAction.ADDED
        )
    ]
    assert fork.label_writes == [
        RecordedLabelWrite(StackPullRequestNumber.PARENT, (StackLabel.IN_REVIEW,))
    ]


def test_a_branch_whose_upstream_pull_request_closed_loses_the_label(
    fork_checkout: ForkCheckout,
):
    a_parent_and_child(fork_checkout)
    fork = RecordingPullRequests(
        labels={StackPullRequestNumber.PARENT: [StackLabel.IN_REVIEW]}
    )
    board = a_board_whose_parent(None, labels=[StackLabel.IN_REVIEW])

    changes = synchronize_review_labels(a_stack(fork_checkout, board), fork)

    assert changes == [
        ReviewLabelChange(
            StackBranch.PARENT, StackPullRequestNumber.PARENT, ReviewLabelAction.REMOVED
        )
    ]
    assert fork.label_writes == [RecordedLabelWrite(StackPullRequestNumber.PARENT, ())]


def test_a_label_already_in_step_is_not_written(fork_checkout: ForkCheckout):
    a_parent_and_child(fork_checkout)
    fork = RecordingPullRequests()
    board = a_board_whose_parent(
        StackPullRequestNumber.UPSTREAM, labels=[StackLabel.IN_REVIEW]
    )

    changes = synchronize_review_labels(a_stack(fork_checkout, board), fork)

    assert changes == []
    assert fork.label_writes == []


def test_the_write_keeps_the_labels_the_pull_request_carries_now(
    fork_checkout: ForkCheckout,
):
    """
    The restack labels a branch between the export and this write, so the board's
    snapshot of its labels is already out of date here.
    """
    a_parent_and_child(fork_checkout)
    fork = RecordingPullRequests(
        labels={StackPullRequestNumber.PARENT: [StackLabel.NEEDS_RESOLUTION]}
    )
    board = a_board_whose_parent(StackPullRequestNumber.UPSTREAM, labels=[])

    synchronize_review_labels(a_stack(fork_checkout, board), fork)

    assert fork.label_writes == [
        RecordedLabelWrite(
            StackPullRequestNumber.PARENT,
            (StackLabel.NEEDS_RESOLUTION, StackLabel.IN_REVIEW),
        )
    ]


def test_a_label_another_writer_already_put_in_step_is_not_written_again(
    fork_checkout: ForkCheckout,
):
    a_parent_and_child(fork_checkout)
    fork = RecordingPullRequests(
        labels={StackPullRequestNumber.PARENT: [StackLabel.IN_REVIEW]}
    )
    board = a_board_whose_parent(StackPullRequestNumber.UPSTREAM, labels=[])

    changes = synchronize_review_labels(a_stack(fork_checkout, board), fork)

    assert changes == []
    assert fork.label_writes == []
