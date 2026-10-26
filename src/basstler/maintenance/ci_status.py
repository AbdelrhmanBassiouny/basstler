"""
Where the checks on a pushed branch stand, as one line a caller can stop at.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from basstler.maintenance.github import CheckStatusReader
from basstler.upstream_reviews.pull_request_models import CheckStatus
from basstler.upstream_reviews.vocabulary import RollupState

# %% vocabulary


class UnreportedCheckState(StrEnum):
    """
    What a branch's line says when no check has reported on its head.
    """

    NO_CHECKS = "no-checks"
    """
    Nothing has reported yet, as right after a push.
    """


# %% the checks of one branch


@dataclass(frozen=True)
class BranchChecks:
    """
    Every check reported on one branch's head.
    """

    branch: str
    """
    The branch whose head was checked.
    """

    status: CheckStatus | None
    """
    Its checks and the verdict over them, ``None`` when nothing has reported.
    """

    @classmethod
    def read(cls, reader: CheckStatusReader, branch: str) -> BranchChecks:
        """
        :param reader: The repository holding the branch.
        :param branch: The branch to read the checks of.
        :return: Its checks.
        """
        return cls(branch, reader.check_status(branch))

    @property
    def state(self) -> RollupState | UnreportedCheckState:
        """
        The verdict over the branch's checks, or that none has reported.
        """
        if self.status is None:
            return UnreportedCheckState.NO_CHECKS
        return self.status.state

    @property
    def failing(self) -> tuple[str, ...]:
        """
        The name of every check that failed or reported an error.
        """
        if self.status is None:
            return ()
        return tuple(
            result.name
            for result in self.status.results
            if result.outcome.rolls_up_to.failed
        )

    @property
    def line(self) -> str:
        """
        The branch, its :attr:`state` and its failing checks, tab separated.
        """
        return f"{self.branch}\t{self.state}\t{','.join(self.failing)}"
