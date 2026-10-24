"""
Retargeting a branch whose base has landed, or telling its owner when GitHub refuses.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from basstler.maintenance_board import PullRequestField
from basstler.maintenance_constants import RoutineText
from basstler.maintenance_github import ForkPullRequests
from basstler.stack import Branch, LabelWrite, Reparent, Stack

# %% outcome


@dataclass(frozen=True)
class RetargetOutcome:
    """
    What became of one pending reparent.
    """

    reparent: Reparent
    """
    What :func:`stack.reparents` found.
    """

    retargeted: bool
    """
    Whether this credential's own retarget succeeded.

    ``False`` means GitHub refused it and the branch's owner was labelled and commented
    at instead.
    """


# %% notice


@dataclass(frozen=True)
class ReparentNotice:
    """
    The comment telling a branch's owner that their branch needs retargeting.
    """

    branch: Branch
    """
    The branch whose base has landed.
    """

    reparent: Reparent
    """
    What it must be retargeted at.
    """

    needs_resolution_label: str
    """
    The label the branch is given so later passes do not report it again.
    """

    @property
    def body(self) -> str:
        """:return: The comment body."""
        addressed = self.branch.session or RoutineText.UNADDRESSED_NOTICE
        return (
            f"{RoutineText.NEEDS_RESOLUTION_COMMENT_PREFIX} "
            f"`{self.reparent.current_base}` has landed upstream, so "
            f"`{self.branch.name}` needs to be retargeted at "
            f"`{self.reparent.target_base}`.\n\n"
            f"GitHub refused this pass's own attempt to retarget it - a session must do "
            f"it through the GitHub MCP server. This branch is labelled "
            f"`{self.needs_resolution_label}` so later passes do not re-report the same "
            f"reparent.\n\n{addressed}"
        )


# %% resolution


@dataclass(frozen=True)
class ReparentResolution:
    """
    Retargets every branch a base landed under through one fork, or labels and comments
    where GitHub refuses.
    """

    stack: Stack
    """
    The derived stack the reparents were read from.
    """

    fork: ForkPullRequests
    """
    The fork to retarget through, and to label and comment on when it refuses.
    """

    def resolve(self, reparents: Sequence[Reparent]) -> tuple[RetargetOutcome, ...]:
        """
        :param reparents: What :func:`stack.reparents` found in :attr:`stack`.
        :return: One outcome per reparent, in the order given.
        """
        outcomes = []
        for reparent in reparents:
            retargeted = self.fork.retarget_base(
                reparent.pull_request_number, reparent.target_base
            )
            if not retargeted:
                self.notify(reparent)
            outcomes.append(RetargetOutcome(reparent, retargeted=retargeted))
        return tuple(outcomes)

    def notify(self, reparent: Reparent) -> None:
        """
        Label a refused reparent's pull request and comment the notice on it.

        The labels are read as the pull request carries them now, not as the board was
        exported: an earlier step of the pass can have written one since.

        :param reparent: The reparent GitHub refused.
        """
        number = reparent.pull_request_number
        branch = next(
            branch for branch in self.stack.branches if branch.name == reparent.branch
        )
        label = self.stack.configuration.needs_resolution_label
        current_labels = PullRequestField.LABELS.read(
            self.fork.pull_request(number), number
        )
        self.fork.replace_labels(
            number, LabelWrite.replacing(current_labels, added=[label]).labels
        )
        self.fork.add_comment(number, ReparentNotice(branch, reparent, label).body)
