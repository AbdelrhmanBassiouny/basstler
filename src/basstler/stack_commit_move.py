"""
Whether commits a caller proposes to move onto a branch may be moved there.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from basstler.exit_codes import StackExitCode
from basstler.stack_checkout import CurrentCheckout, GitArgument
from basstler.stack_model import Stack
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% move check


class CommitMoveAction(StrEnum):
    """What a proposed move would do to the destination branch."""

    PUSH = "push"
    """Publish one branch's commits to a remote branch."""

    MERGE = "merge"
    """Bring one branch's commits into another locally."""

    RESTACK = "restack"
    """Integrate a moved parent and publish the result - a merge and a push together."""


@dataclass(frozen=True)
class ProposedCommitMove:
    """Commits a caller proposes to move onto a branch, before anything is run."""

    action: CommitMoveAction
    """What the move would do."""

    source: str
    """The branch whose commits would move."""

    destination: str
    """The branch they would land on."""

    destination_remote: str
    """The remote holding the destination branch."""


class RefusalReason(StrEnum):
    """Why a proposed move must not be made.

    Each names a move that has gone wrong in practice, so a caller can act on which one
    it hit without reading the sentence explaining it.
    """

    NOT_CHECKED_OUT = "not-checked-out"
    """The source is not the branch whose content a push would actually move."""

    MISMATCHED_BRANCH_NAMES = "mismatched-branch-names"
    """The source and the destination of the push are different branches."""

    NOT_THE_FORK = "not-the-fork"
    """The destination remote is not the fork the stack lives on."""

    FALSE_MERGE = "false-merge"
    """A child would become an ancestor of its own parent, which GitHub reads as merged."""


@dataclass(frozen=True)
class CommitMoveRefusal:
    """One reason a proposed move must not be made."""

    reason: RefusalReason
    """Which refusal this is, for a caller deciding what to do about it."""

    explanation: str
    """What is wrong, in terms of the branches the caller named."""


@dataclass(frozen=True)
class CommitMoveChecks:
    """Checks a proposed move against the checkout it would run in.

    Every refusal describes a move that has gone wrong in practice - see
    :class:`RefusalReason`.
    """

    stack: Stack
    """The stack the branches belong to."""

    checked_out_branch: str
    """The branch actually checked out, whose content a push would move."""

    is_ancestor: Callable[[str, str], bool]
    """Maps a candidate ancestor branch and a descendant branch to whether the first is
    contained in the second; injected so the checks are testable without git."""

    @classmethod
    def of_checkout(cls, stack: Stack) -> CommitMoveChecks:
        """:param stack: The stack the branches belong to.
        :return: The checks against the branch this checkout has checked out."""
        return cls(
            stack=stack,
            checked_out_branch=CurrentCheckout.output(
                GitArgument.BRANCH, GitArgument.SHOW_CURRENT
            ),
            is_ancestor=CurrentCheckout.ancestry_predicate(stack.configuration),
        )

    def refusals(self, move: ProposedCommitMove) -> list[CommitMoveRefusal]:
        """Every reason the move must not be made.

        All of them are reported together: fixing one and re-running to discover the next
        is how a move gets half made.

        :param move: The proposed move.
        :return: The refusals, empty when the move is safe.
        """
        found = []
        if move.source != self.checked_out_branch:
            found.append(
                CommitMoveRefusal(
                    RefusalReason.NOT_CHECKED_OUT,
                    f"'{move.source}' is not checked out; '{self.checked_out_branch}' is, "
                    f"and its content is what would move",
                )
            )
        if move.source != move.destination:
            found.append(
                CommitMoveRefusal(
                    RefusalReason.MISMATCHED_BRANCH_NAMES,
                    f"this would move '{move.source}' onto '{move.destination}'; the "
                    f"source and the destination must be the same branch",
                )
            )
        if move.destination_remote != self.stack.configuration.fork_remote:
            found.append(
                CommitMoveRefusal(
                    RefusalReason.NOT_THE_FORK,
                    f"'{move.destination_remote}' is not the fork remote "
                    f"'{self.stack.configuration.fork_remote}'",
                )
            )
        found.extend(self._false_merges(move))
        return found

    def _false_merges(self, move: ProposedCommitMove) -> list[CommitMoveRefusal]:
        """The children of the destination this move would make GitHub call merged.

        :param move: The proposed move.
        :return: One refusal per child already contained in the move's source.
        """
        return [
            CommitMoveRefusal(
                RefusalReason.FALSE_MERGE,
                f"'{child.name}' is already contained in '{move.source}', so this would "
                f"make it an ancestor of its own parent '{move.destination}' and GitHub "
                f"would close pull request #{child.pull_request_number} as merged",
            )
            for child in self.stack.branches
            if child.parent == move.destination
            and self.is_ancestor(child.name, move.source)
        ]

    def print_verdict(self, move: ProposedCommitMove) -> StackExitCode:
        """Print whether a move may be made, and every reason it may not.

        :param move: The proposed move.
        :return: Success when the move is clear, refusal otherwise.
        """
        refusals = self.refusals(move)
        if not refusals:
            logger.info(
                f"{move.action} {move.source} onto "
                f"{move.destination_remote}/{move.destination}: clear"
            )
            return StackExitCode.SUCCESS
        for refusal in refusals:
            logger.error(f"{refusal.reason}: {refusal.explanation}")
        return StackExitCode.MOVE_REFUSED
