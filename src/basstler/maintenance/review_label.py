"""
Keeping the in-review label on each fork pull request in step with its upstream pull
request.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from basstler.maintenance.board import PullRequestField
from basstler.maintenance.github import ForkPullRequests
from basstler.stack.label_write import LabelWrite
from basstler.stack.model import BranchStatus, Stack


class ReviewLabelAction(StrEnum):
    """
    What was done to a pull request's in-review label.
    """

    ADDED = "added"
    """
    Added, because an upstream pull request opened from the branch is open.
    """

    REMOVED = "removed"
    """
    Removed, because no upstream pull request opened from the branch is open.
    """


@dataclass(frozen=True)
class ReviewLabelChange:
    """
    One fork pull request whose in-review label was added or removed.
    """

    branch: str
    """
    The branch whose pull request was written.
    """

    pull_request_number: int
    """
    Its fork pull request.
    """

    action: ReviewLabelAction
    """
    What was done to its label.
    """


def synchronize_review_labels(
    stack: Stack, fork: ForkPullRequests
) -> list[ReviewLabelChange]:
    """
    Add the in-review label to every branch under upstream review that lacks it, and
    remove it from every branch no longer under review.

    A landed branch is left as it is. Each write keeps the labels the pull request
    carries *now*, not the ones the board was exported with.

    :param stack: The derived stack.
    :param fork: The fork to read labels from and write them to.
    :return: One entry per pull request written, in dependency order.
    """
    label = stack.configuration.in_review_label
    changes: list[ReviewLabelChange] = []
    for branch in stack.maintained_branches():
        if branch.status is BranchStatus.MERGED:
            continue
        under_review = branch.status is BranchStatus.IN_REVIEW
        if (label in branch.labels) == under_review:
            continue
        number = branch.pull_request_number
        current = PullRequestField.LABELS.read(fork.pull_request(number), number)
        if (label in current) == under_review:
            continue
        if under_review:
            write = LabelWrite.replacing(current, added=[label])
            action = ReviewLabelAction.ADDED
        else:
            write = LabelWrite.replacing(current, removed=[label])
            action = ReviewLabelAction.REMOVED
        fork.replace_labels(number, write.labels)
        changes.append(ReviewLabelChange(branch.name, number, action))
    return changes
