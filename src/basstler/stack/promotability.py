"""
The one rule deciding whether a branch may be promoted to the upstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from basstler.stack.branch_status import BranchStatus

# %% why a branch is not promotable


class PromotionBlocker(StrEnum):
    """
    One reason a branch may not be promoted, worded for the reader it is shown to.
    """

    DRAFT = "its pull request is still a draft"
    """
    Its author has not yet reviewed it.
    """

    IN_REVIEW = "an upstream pull request is already open for it"
    """
    It was promoted already.
    """

    MERGED = "it has already landed upstream"
    """
    Its commits are in the upstream base.
    """

    PARENT_NOT_LANDED = "the branch it is stacked on has not landed upstream yet"
    """
    Promoting it now would carry its parent's commits too.
    """

    WITHHELD = "it is withheld until its conflicts are resolved"
    """
    It carries the label marking a pending conflict resolution.
    """

    CHECKS_FAILED = "the checks on its pull request have failed"
    """
    Its head reports a failing check.
    """


@dataclass(frozen=True)
class PromotionReadiness:
    """
    The facts that decide whether one branch may be promoted, and what they say.
    """

    status: BranchStatus
    """
    The branch's lifecycle position.
    """

    parent_landed: bool
    """
    Whether the branch it is stacked on has landed upstream.
    """

    withheld: bool
    """
    Whether the branch is withheld pending conflict resolution.
    """

    checks_failed: bool
    """
    Whether the checks on its pull request head have failed.
    """

    @property
    def blockers(self) -> list[PromotionBlocker]:
        """
        :return: Every reason the branch may not be promoted, empty when it may.
        """
        return [
            blocker
            for blocker, applies in (
                (PromotionBlocker.DRAFT, self.status is BranchStatus.DRAFT),
                (PromotionBlocker.IN_REVIEW, self.status is BranchStatus.IN_REVIEW),
                (PromotionBlocker.MERGED, self.status is BranchStatus.MERGED),
                (PromotionBlocker.PARENT_NOT_LANDED, not self.parent_landed),
                (PromotionBlocker.WITHHELD, self.withheld),
                (PromotionBlocker.CHECKS_FAILED, self.checks_failed),
            )
            if applies
        ]

    @property
    def is_promotable(self) -> bool:
        """
        :return: Whether nothing holds the branch back.
        """
        return not self.blockers
