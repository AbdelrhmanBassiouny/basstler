"""
A stack node's lifecycle position.
"""

from __future__ import annotations

from enum import StrEnum

# %% lifecycle


class BranchStatus(StrEnum):
    """
    A stack node's lifecycle position.
    """

    DRAFT = "draft"
    """
    Its author has not yet reviewed it themselves, so it may not be promoted.
    """

    READY = "ready"
    """Out of draft - reviewed by its author, and promotable once its parent has merged."""

    IN_REVIEW = "in-review"
    """
    Promoted to the upstream, where it waits on that queue rather than on us.
    """

    MERGED = "merged"
    """
    Its own commits are already contained in the upstream base.
    """

    @classmethod
    def derive(cls, draft: bool, merged: bool, in_review: bool) -> BranchStatus:
        """
        Map a pull request's raw facts to a lifecycle status.

        Precedence: a merged branch is ``merged``; a branch under upstream review is
        ``in-review``; an un-drafted branch is ``ready`` (self-approved for promotion);
        otherwise ``draft``.

        :param draft: Whether the pull request is still a draft.
        :param merged: Whether the branch has landed upstream (git ancestry).
        :param in_review: Whether an upstream pull request opened from the branch is
            open.
        :return: The derived status.
        """
        if merged:
            return cls.MERGED
        if in_review:
            return cls.IN_REVIEW
        return cls.DRAFT if draft else cls.READY
