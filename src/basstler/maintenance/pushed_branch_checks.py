"""
CI on the branches a pass pushed, read without anybody polling for it.

A branch whose tip on the fork is a restack's own merge was last moved by a pass, so its
checks are the pass's to read and report. Right after a push they are still running, so
they are read on the *next* pass, which finds them finished; a tip somebody pushed since
is its owner's to watch, and is left alone.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

from basstler.maintenance.board import PullRequestField
from basstler.maintenance.check_results import CheckState, CommitChecks
from basstler.maintenance.constants import CommitTrailer, MaintenanceText
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.maintenance.github import ForkPullRequests
from basstler.stack.label_write import LabelWrite
from basstler.stack.model import Branch, Stack

# %% one branch's checks


@dataclass(frozen=True)
class BranchChecks:
    """
    The checks on the tip a pass left one branch at.
    """

    branch: str
    """
    The branch whose tip was checked.
    """

    pull_request_number: int
    """
    Its fork pull request.
    """

    checks: CommitChecks
    """
    The checks reported on that tip.
    """

    reported_at: str | None = None
    """
    URL of the comment telling the branch's owner its checks fail, absent unless this
    pass posted one.
    """

    @property
    def state(self) -> CheckState:
        """
        The verdict on the tip's checks.
        """
        return self.checks.state

    def failure_report(self, session: str | None) -> str:
        """
        :param session: The session the pull request's description names, if any.
        :return: The comment telling the branch's owner which checks fail on the tip.
        """
        names = "\n".join(f"- `{name}`" for name in self.checks.failing_check_names)
        addressed = (
            f"\n\n{session}"
            if session
            else "\n\nThis pull request's description names no session to address."
        )
        return (
            f"{MaintenanceText.NEEDS_RESOLUTION_COMMENT_PREFIX} checks fail on "
            f"`{self.checks.commit}`, the restack merge a maintenance pass pushed to "
            f"`{self.branch}`.\n\nFailing checks:\n{names}\n\nPlease fix and push. The "
            f"branch is labelled `needs-resolution`, which keeps it from being promoted "
            f"until it is green again.{addressed}"
        )


# %% reading them


@dataclass(frozen=True)
class PushedBranchChecks:
    """
    Reads and reports the checks on every branch whose tip a pass pushed.
    """

    stack: Stack
    """
    The derived stack the branches belong to.
    """

    git: GitCommandRunner
    """
    The checkout whose fork references name each branch's tip.
    """

    fork: ForkPullRequests
    """
    The fork, read for checks, labels and comments, and written to when reporting.
    """

    def pushed_by_a_pass(self, branches: Iterable[Branch]) -> list[Branch]:
        """
        :param branches: The branches to consider.
        :return: Those whose tip on the fork is a restack's own merge.
        """
        return [
            branch
            for branch in branches
            if self.git.trailer_value(
                self.stack.configuration.reference_on_fork(branch.name),
                CommitTrailer.RESTACKED_PARENT,
            )
        ]

    def read(self, branches: Iterable[Branch]) -> list[BranchChecks]:
        """
        :param branches: The branches to read, each at its tip on the fork.
        :return: The checks on each one whose tip a pass pushed.
        """
        configuration = self.stack.configuration
        return [
            BranchChecks(
                branch.name,
                branch.pull_request_number,
                self.fork.commit_checks(
                    self.git.commit_at(configuration.reference_on_fork(branch.name))
                ),
            )
            for branch in self.pushed_by_a_pass(branches)
        ]

    def report_failures(self, checks: Sequence[BranchChecks]) -> list[BranchChecks]:
        """
        Label every branch whose checks fail, and comment once per failing tip.

        :param checks: The checks read this pass.
        :return: The same checks, each failing one carrying the comment posted for it,
            if one was.
        """
        return [
            self._report(branch_checks)
            if branch_checks.state is CheckState.FAILING
            else branch_checks
            for branch_checks in checks
        ]

    def _report(self, branch_checks: BranchChecks) -> BranchChecks:
        """
        :param branch_checks: Checks that fail.
        :return: The checks, carrying the comment posted for them if this tip had none.
        """
        number = branch_checks.pull_request_number
        label = self.stack.configuration.needs_resolution_label
        labels = PullRequestField.LABELS.read(self.fork.pull_request(number), number)
        if label not in labels:
            self.fork.replace_labels(
                number, LabelWrite.replacing(labels, added=[label]).labels
            )
        already_reported = any(
            body.startswith(MaintenanceText.NEEDS_RESOLUTION_COMMENT_PREFIX)
            and branch_checks.checks.commit in body
            for body in self.fork.comment_bodies(number)
        )
        if already_reported:
            return branch_checks
        session = next(
            branch.session
            for branch in self.stack.branches
            if branch.name == branch_checks.branch
        )
        return replace(
            branch_checks,
            reported_at=self.fork.add_comment(
                number, branch_checks.failure_report(session)
            ),
        )
