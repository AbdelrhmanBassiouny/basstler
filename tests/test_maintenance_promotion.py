"""
Tests for promoting approved, unblocked branches to the upstream review queue.
"""

from __future__ import annotations

import pytest

import basstler.maintenance
import basstler.maintenance_restack_procedure
from basstler.github_labels import GitHubLabel
from basstler.maintenance_constants import MaintenanceText
from basstler.maintenance_promotion import (
    clear_spent_promotion_labels,
    description_with_promotion_link,
    promote,
)
from basstler.maintenance_restack_procedure import restack

from .constants.stack import StackBranch, StackLabel

from .maintenance_fork import (
    StackPullRequestNumber,
    PromotionSampleText,
    make_configuration,
    ForkCheckout,
    a_stack,
    a_parent_and_child,
    the_board,
)
from .recorded_fork import (
    RecordedLabelWrite,
    RecordingPullRequests,
)


# %% promotion


def test_the_promotion_link_goes_into_the_description_and_the_branch_is_labelled(
    fork_checkout: ForkCheckout,
):
    a_parent_and_child(fork_checkout)
    fork = RecordingPullRequests(
        descriptions={
            StackPullRequestNumber.PARENT: (
                f"{PromotionSampleText.SUMMARY}\n\n{PromotionSampleText.DETAIL}\n"
            )
        },
        titles={StackPullRequestNumber.PARENT: PromotionSampleText.TITLE},
    )

    promoted = promote(a_stack(fork_checkout, the_board()), fork)

    assert [entry.branch for entry in promoted] == [StackBranch.PARENT]
    written = fork.description_writes[0]
    assert written.pull_request_number == StackPullRequestNumber.PARENT
    assert MaintenanceText.PROMOTION_HEADING in written.body
    assert promoted[0].url in written.body
    assert PromotionSampleText.SUMMARY in written.body
    assert fork.label_writes == [
        RecordedLabelWrite(
            StackPullRequestNumber.PARENT, (GitHubLabel.PROMOTION_LINK_SENT,)
        )
    ]


def test_a_branch_already_carrying_the_link_label_is_not_promoted_again(
    fork_checkout: ForkCheckout,
):
    a_parent_and_child(fork_checkout)
    fork = RecordingPullRequests(
        labels={StackPullRequestNumber.PARENT: [GitHubLabel.PROMOTION_LINK_SENT]}
    )

    promoted = promote(a_stack(fork_checkout, the_board()), fork)

    assert promoted == []
    assert fork.description_writes == []


def test_a_branch_labelled_needs_resolution_during_this_pass_is_not_promoted(
    fork_checkout: ForkCheckout,
):
    """
    The board is a snapshot taken before the restack runs, so a branch the restack has
    just withheld still looks promotable in it.

    Promotion has to ask the branch, not the snapshot, or a pass promotes what the same
    pass just conflicted on.
    """
    a_parent_and_child(fork_checkout)
    fork = RecordingPullRequests(
        labels={
            StackPullRequestNumber.PARENT: [make_configuration().needs_resolution_label]
        }
    )

    promoted = promote(a_stack(fork_checkout, the_board()), fork)

    assert promoted == []
    assert fork.description_writes == []
    assert fork.label_writes == []


def test_the_promotion_label_write_keeps_a_label_added_since_the_board_was_taken(
    fork_checkout: ForkCheckout,
):
    """
    A label write replaces the whole set, so computing it from the snapshot silently
    strips anything applied since - including the label the restack applies mid-pass.
    """
    a_parent_and_child(fork_checkout)
    fork = RecordingPullRequests(
        labels={StackPullRequestNumber.PARENT: [StackLabel.SOMEBODY_ELSES]}
    )

    promote(a_stack(fork_checkout, the_board()), fork)

    assert fork.label_writes == [
        RecordedLabelWrite(
            StackPullRequestNumber.PARENT,
            (StackLabel.SOMEBODY_ELSES, GitHubLabel.PROMOTION_LINK_SENT),
        )
    ]


def test_a_second_promotion_replaces_the_link_rather_than_appending_another():
    """
    The description is rewritten on every run that rebuilds a link, so the section has to
    be replaced in place - two Promote headings would leave a reader guessing which link
    is current.
    """
    first = description_with_promotion_link(
        f"{PromotionSampleText.PROSE}\n", PromotionSampleText.FIRST_LINK
    )

    second = description_with_promotion_link(first, PromotionSampleText.SECOND_LINK)

    assert second.count(MaintenanceText.PROMOTION_HEADING) == 1
    assert PromotionSampleText.SECOND_LINK in second
    assert PromotionSampleText.FIRST_LINK not in second
    assert second.startswith(PromotionSampleText.PROSE)


def test_a_promoted_branch_that_reached_review_has_its_link_label_removed(
    fork_checkout: ForkCheckout,
):
    """
    The label exists to stop a link being rebuilt; once the branch is in review the link
    has been acted on, so leaving it would misreport the branch forever.
    """
    a_parent_and_child(fork_checkout)
    board = the_board()
    board[0].labels = [
        GitHubLabel.PROMOTION_LINK_SENT,
        make_configuration().in_review_label,
    ]
    fork = RecordingPullRequests()

    cleared = clear_spent_promotion_labels(a_stack(fork_checkout, board), fork)

    assert cleared == (StackBranch.PARENT,)
    assert fork.label_writes == [
        RecordedLabelWrite(
            StackPullRequestNumber.PARENT, (make_configuration().in_review_label,)
        )
    ]


def test_a_branch_no_step_concludes_is_an_error_rather_than_a_silent_pass(
    fork_checkout: ForkCheckout, monkeypatch: pytest.MonkeyPatch
):
    """
    The last step always concludes a branch, so a branch reaching the end of the steps
    means the procedure lost it - which must not read as a branch nothing happened to.
    """
    a_parent_and_child(fork_checkout)
    monkeypatch.setattr(
        basstler.maintenance_restack_procedure, "restack_steps", lambda: ()
    )

    with pytest.raises(
        basstler.maintenance_restack_procedure.RestackConcludedNothingError
    ) as raised:
        restack(
            a_stack(fork_checkout, the_board()),
            fork_checkout.git,
            RecordingPullRequests(),
        )

    assert raised.value.branch in {StackBranch.PARENT, StackBranch.CHILD}
