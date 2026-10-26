"""
Tests for keeping each fork pull request's in-review label and upstream link in step
with its upstream pull request.
"""

from __future__ import annotations

from dataclasses import replace

from basstler.maintenance.description import (
    PullRequestDescription,
    UpstreamPullRequestLink,
)
from basstler.maintenance.upstream_pull_request_synchronization import (
    UpstreamPullRequestSynchronizationAction,
    UpstreamPullRequestSynchronizationChange,
    UpstreamPullRequestSynchronization,
)
from basstler.stack.model import PullRequest

from ..constants.stack import StackBranch, StackLabel

from .fork import (
    ForkCheckout,
    PromotionSampleText,
    StackPullRequestNumber,
    a_parent_and_child,
    a_stack,
    make_configuration,
    the_board,
)
from .recorded_fork import (
    RecordedDescription,
    RecordedLabelWrite,
    RecordingPullRequests,
)

# %% the board under test


def the_upstream_link() -> UpstreamPullRequestLink:
    """
    :return: The link to the upstream pull request opened from the parent.
    """
    return UpstreamPullRequestLink(
        make_configuration().upstream_repository, StackPullRequestNumber.UPSTREAM
    )


def a_linked_description() -> str:
    """
    :return: A parent description already linking its upstream pull request.
    """
    return PullRequestDescription(PromotionSampleText.PROSE).with_upstream_link(
        the_upstream_link()
    )


def a_board_whose_parent(
    upstream_pull_request: int | None,
    labels: list[str],
    upstream_link: str | None = None,
) -> list[PullRequest]:
    """
    :param upstream_pull_request: The open upstream pull request opened from the parent.
    :param labels: The labels the board snapshot found on the parent.
    :param upstream_link: The upstream pull request the snapshot found linked.
    :return: The two-branch board, its parent in that state.
    """
    parent, child = the_board()
    return [
        replace(
            parent,
            upstream_pull_request=upstream_pull_request,
            labels=labels,
            upstream_link=upstream_link,
        ),
        child,
    ]


# %% keeping the label in step


def test_a_branch_under_upstream_review_gains_the_label(fork_checkout: ForkCheckout):
    a_parent_and_child(fork_checkout)
    fork = RecordingPullRequests(
        descriptions={StackPullRequestNumber.PARENT: a_linked_description()}
    )
    board = a_board_whose_parent(
        StackPullRequestNumber.UPSTREAM,
        labels=[],
        upstream_link=the_upstream_link().url,
    )

    changes = UpstreamPullRequestSynchronization(
        a_stack(fork_checkout, board), fork
    ).synchronize()

    assert changes == [
        UpstreamPullRequestSynchronizationChange(
            StackBranch.PARENT,
            StackPullRequestNumber.PARENT,
            UpstreamPullRequestSynchronizationAction.LABEL_ADDED,
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

    changes = UpstreamPullRequestSynchronization(
        a_stack(fork_checkout, board), fork
    ).synchronize()

    assert changes == [
        UpstreamPullRequestSynchronizationChange(
            StackBranch.PARENT,
            StackPullRequestNumber.PARENT,
            UpstreamPullRequestSynchronizationAction.LABEL_REMOVED,
        )
    ]
    assert fork.label_writes == [RecordedLabelWrite(StackPullRequestNumber.PARENT, ())]


def test_a_branch_already_in_step_is_not_written(fork_checkout: ForkCheckout):
    a_parent_and_child(fork_checkout)
    fork = RecordingPullRequests()
    board = a_board_whose_parent(
        StackPullRequestNumber.UPSTREAM,
        labels=[StackLabel.IN_REVIEW],
        upstream_link=the_upstream_link().url,
    )

    changes = UpstreamPullRequestSynchronization(
        a_stack(fork_checkout, board), fork
    ).synchronize()

    assert changes == []
    assert fork.label_writes == []
    assert fork.description_writes == []


def test_the_label_write_keeps_the_labels_the_pull_request_carries_now(
    fork_checkout: ForkCheckout,
):
    """
    The restack labels a branch between the export and this write, so the board's
    snapshot of its labels is already out of date here.
    """
    a_parent_and_child(fork_checkout)
    fork = RecordingPullRequests(
        labels={StackPullRequestNumber.PARENT: [StackLabel.NEEDS_RESOLUTION]},
        descriptions={StackPullRequestNumber.PARENT: a_linked_description()},
    )
    board = a_board_whose_parent(StackPullRequestNumber.UPSTREAM, labels=[])

    UpstreamPullRequestSynchronization(
        a_stack(fork_checkout, board), fork
    ).synchronize()

    assert fork.label_writes == [
        RecordedLabelWrite(
            StackPullRequestNumber.PARENT,
            (StackLabel.NEEDS_RESOLUTION, StackLabel.IN_REVIEW),
        )
    ]


def test_a_pull_request_another_writer_already_put_in_step_is_not_written_again(
    fork_checkout: ForkCheckout,
):
    a_parent_and_child(fork_checkout)
    fork = RecordingPullRequests(
        labels={StackPullRequestNumber.PARENT: [StackLabel.IN_REVIEW]},
        descriptions={StackPullRequestNumber.PARENT: a_linked_description()},
    )
    board = a_board_whose_parent(StackPullRequestNumber.UPSTREAM, labels=[])

    changes = UpstreamPullRequestSynchronization(
        a_stack(fork_checkout, board), fork
    ).synchronize()

    assert changes == []
    assert fork.label_writes == []
    assert fork.description_writes == []


# %% keeping the link in step


def test_a_branch_under_upstream_review_gets_its_upstream_pull_request_linked(
    fork_checkout: ForkCheckout,
):
    a_parent_and_child(fork_checkout)
    fork = RecordingPullRequests(
        labels={StackPullRequestNumber.PARENT: [StackLabel.IN_REVIEW]},
        descriptions={StackPullRequestNumber.PARENT: PromotionSampleText.PROSE},
    )
    board = a_board_whose_parent(
        StackPullRequestNumber.UPSTREAM, labels=[StackLabel.IN_REVIEW]
    )

    changes = UpstreamPullRequestSynchronization(
        a_stack(fork_checkout, board), fork
    ).synchronize()

    assert changes == [
        UpstreamPullRequestSynchronizationChange(
            StackBranch.PARENT,
            StackPullRequestNumber.PARENT,
            UpstreamPullRequestSynchronizationAction.LINK_WRITTEN,
        )
    ]
    assert fork.description_writes == [
        RecordedDescription(StackPullRequestNumber.PARENT, a_linked_description())
    ]


def test_a_branch_whose_upstream_pull_request_closed_loses_its_link(
    fork_checkout: ForkCheckout,
):
    a_parent_and_child(fork_checkout)
    fork = RecordingPullRequests(
        descriptions={StackPullRequestNumber.PARENT: a_linked_description()}
    )
    board = a_board_whose_parent(None, labels=[], upstream_link=the_upstream_link().url)

    changes = UpstreamPullRequestSynchronization(
        a_stack(fork_checkout, board), fork
    ).synchronize()

    assert changes == [
        UpstreamPullRequestSynchronizationChange(
            StackBranch.PARENT,
            StackPullRequestNumber.PARENT,
            UpstreamPullRequestSynchronizationAction.LINK_REMOVED,
        )
    ]
    assert fork.description_writes == [
        RecordedDescription(
            StackPullRequestNumber.PARENT,
            PullRequestDescription(a_linked_description()).with_upstream_link(None),
        )
    ]
