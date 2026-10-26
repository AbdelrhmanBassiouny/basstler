"""
What the checks on a pushed branch concluded, as one line a caller can stop at.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from basstler.maintenance.github import CommitChecksReader

# %% vocabulary


class CheckState(StrEnum):
    """
    Where the checks on a branch's head stand.
    """

    PENDING = "pending"
    """
    At least one check is still queued or running, and none has failed.
    """

    SUCCESS = "success"
    """
    Every check completed without failing.
    """

    FAILURE = "failure"
    """
    At least one check failed.
    """

    NO_CHECKS = "no-checks"
    """
    No check has been reported for the head yet.
    """


class CheckRunKey(StrEnum):
    """
    The keys of the check-run listing the API returns for one commit.
    """

    CHECK_RUNS = "check_runs"
    """
    The check runs themselves.
    """

    NAME = "name"
    """
    A check run's name.
    """

    STATUS = "status"
    """
    Whether a check run is queued, running or completed.
    """

    CONCLUSION = "conclusion"
    """
    What a completed check run concluded.
    """


class CheckRunStatus(StrEnum):
    """
    The check-run status that means it has finished.
    """

    COMPLETED = "completed"
    """
    The run finished and has a conclusion.
    """


class PassingConclusion(StrEnum):
    """
    The conclusions of a completed check run that are not a failure.
    """

    SUCCESS = "success"
    """
    The run passed.
    """

    NEUTRAL = "neutral"
    """
    The run reported nothing to pass or fail.
    """

    SKIPPED = "skipped"
    """
    The run did not need to run.
    """


class CommitStatusKey(StrEnum):
    """
    The keys of the combined commit status the API returns for one commit.
    """

    STATUSES = "statuses"
    """
    The latest status of each context.
    """

    CONTEXT = "context"
    """
    The name a status is reported under.
    """

    STATE = "state"
    """
    What a status says.
    """


class CommitStatusState(StrEnum):
    """
    The commit-status states that are not a failure.
    """

    PENDING = "pending"
    """
    The status's check is still running.
    """

    SUCCESS = "success"
    """
    The status's check passed.
    """


# %% the checks of one branch


@dataclass(frozen=True)
class Check:
    """
    One check reported on a commit, a check run or a commit status alike.
    """

    name: str
    """
    What the check is called.
    """

    state: CheckState
    """
    Where it stands.
    """

    @classmethod
    def from_check_run(cls, data: Mapping[str, Any]) -> Check:
        """
        :param data: One entry of the check-run listing.
        :return: The check it describes.
        """
        if data[CheckRunKey.STATUS] != CheckRunStatus.COMPLETED:
            state = CheckState.PENDING
        elif data[CheckRunKey.CONCLUSION] in set(PassingConclusion):
            state = CheckState.SUCCESS
        else:
            state = CheckState.FAILURE
        return cls(str(data[CheckRunKey.NAME]), state)

    @classmethod
    def from_commit_status(cls, data: Mapping[str, Any]) -> Check:
        """
        :param data: One entry of the combined commit status.
        :return: The check it describes.
        """
        states = {
            CommitStatusState.PENDING: CheckState.PENDING,
            CommitStatusState.SUCCESS: CheckState.SUCCESS,
        }
        return cls(
            str(data[CommitStatusKey.CONTEXT]),
            states.get(data[CommitStatusKey.STATE], CheckState.FAILURE),
        )


@dataclass(frozen=True)
class BranchChecks:
    """
    Every check reported on one branch's head.
    """

    branch: str
    """
    The branch whose head was checked.
    """

    checks: tuple[Check, ...]
    """
    Its check runs, then its commit statuses.
    """

    @classmethod
    def read(cls, reader: CommitChecksReader, branch: str) -> BranchChecks:
        """
        :param reader: The repository holding the branch.
        :param branch: The branch to read the checks of.
        :return: Its checks.
        """
        return cls.from_json(
            branch, reader.check_runs(branch), reader.commit_status(branch)
        )

    @classmethod
    def from_json(
        cls,
        branch: str,
        check_runs: Mapping[str, Any],
        commit_status: Mapping[str, Any],
    ) -> BranchChecks:
        """
        :param branch: The branch the responses are about.
        :param check_runs: The check-run listing of its head.
        :param commit_status: The combined commit status of its head.
        :return: Its checks.
        """
        return cls(
            branch,
            (
                *(
                    Check.from_check_run(run)
                    for run in check_runs[CheckRunKey.CHECK_RUNS]
                ),
                *(
                    Check.from_commit_status(status)
                    for status in commit_status[CommitStatusKey.STATUSES]
                ),
            ),
        )

    @property
    def failing(self) -> tuple[str, ...]:
        """
        The name of every check that failed.
        """
        return tuple(
            check.name for check in self.checks if check.state is CheckState.FAILURE
        )

    @property
    def state(self) -> CheckState:
        """
        Where the branch's checks stand together: failed if any failed, else pending if
        any is still running.
        """
        if not self.checks:
            return CheckState.NO_CHECKS
        if self.failing:
            return CheckState.FAILURE
        if any(check.state is CheckState.PENDING for check in self.checks):
            return CheckState.PENDING
        return CheckState.SUCCESS

    @property
    def line(self) -> str:
        """
        The branch, its :attr:`state` and its failing checks, tab separated.
        """
        return f"{self.branch}\t{self.state}\t{','.join(self.failing)}"
