"""
What GitHub reports about the checks run on one commit, reduced to the verdict a pass acts
on.

A commit is checked two ways - check runs, which GitHub Actions and most apps post, and
commit statuses, which older integrations post - so both are read into the same
:class:`CheckResult` and judged together.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

# %% vocabulary


class CheckState(StrEnum):
    """
    The verdict on a commit's checks, or on one of them.
    """

    PASSING = "passing"
    """
    Every check finished without failing.
    """

    PENDING = "pending"
    """
    No check failed, and at least one has not finished.
    """

    FAILING = "failing"
    """
    At least one check finished with a failure.
    """

    NO_CHECKS = "no-checks"
    """
    Nothing was reported for the commit at all.
    """


class CheckRunStatus(StrEnum):
    """
    The ``status`` a check run reports that this module tells apart from the rest.
    """

    COMPLETED = "completed"
    """
    The run finished, so its ``conclusion`` is final; every other status means it has
    not.
    """


class CheckRunConclusion(StrEnum):
    """
    The ``conclusion`` values of a finished check run that count as a failure.
    """

    FAILURE = "failure"
    """
    The run failed.
    """

    TIMED_OUT = "timed_out"
    """
    The run took longer than it was allowed.
    """

    ACTION_REQUIRED = "action_required"
    """
    The run needs somebody to act before it can pass.
    """

    STARTUP_FAILURE = "startup_failure"
    """
    The run could not start.
    """


class CommitStatusState(StrEnum):
    """
    The ``state`` values of a commit status that this module tells apart from success.
    """

    PENDING = "pending"
    """
    The integration has not reported a result yet.
    """

    FAILURE = "failure"
    """
    The integration reported a failure.
    """

    ERROR = "error"
    """
    The integration could not run.
    """


class CheckField(StrEnum):
    """
    The keys of the check-run and commit-status payloads this module reads.
    """

    CHECK_RUNS = "check_runs"
    """
    The list of check runs in a check-run listing.
    """

    STATUSES = "statuses"
    """
    The list of statuses in a combined commit status.
    """

    NAME = "name"
    """
    A check run's name.
    """

    STATUS = "status"
    """
    Whether a check run has finished.
    """

    CONCLUSION = "conclusion"
    """
    How a finished check run ended.
    """

    CONTEXT = "context"
    """
    A commit status's name.
    """

    STATE = "state"
    """
    A commit status's result.
    """


# %% the results


@dataclass(frozen=True)
class CheckResult:
    """
    One check run or commit status, judged.
    """

    check_name: str
    """
    The check's name as GitHub shows it.
    """

    state: CheckState
    """
    Whether it passed, failed or is still running.
    """

    @classmethod
    def from_check_run(cls, check_run: Mapping[str, Any]) -> CheckResult:
        """
        :param check_run: One check run as the API answers it.
        :return: Its result.
        """
        name = str(check_run[CheckField.NAME])
        if check_run[CheckField.STATUS] != CheckRunStatus.COMPLETED:
            return cls(name, CheckState.PENDING)
        if check_run[CheckField.CONCLUSION] in set(CheckRunConclusion):
            return cls(name, CheckState.FAILING)
        return cls(name, CheckState.PASSING)

    @classmethod
    def from_commit_status(cls, status: Mapping[str, Any]) -> CheckResult:
        """
        :param status: One commit status as the API answers it.
        :return: Its result.
        """
        name = str(status[CheckField.CONTEXT])
        state = status[CheckField.STATE]
        if state == CommitStatusState.PENDING:
            return cls(name, CheckState.PENDING)
        if state in {CommitStatusState.FAILURE, CommitStatusState.ERROR}:
            return cls(name, CheckState.FAILING)
        return cls(name, CheckState.PASSING)


@dataclass(frozen=True)
class CommitChecks:
    """
    Every check reported on one commit, and the verdict they add up to.
    """

    commit: str
    """
    The commit the checks ran on.
    """

    results: tuple[CheckResult, ...] = ()
    """
    Each check run and commit status reported on it.
    """

    @classmethod
    def from_json(
        cls,
        commit: str,
        check_runs: Sequence[Mapping[str, Any]],
        combined_status: Mapping[str, Any],
    ) -> CommitChecks:
        """
        :param commit: The commit the payloads describe.
        :param check_runs: Its check runs, as the check-run listing holds them.
        :param combined_status: Its combined commit status.
        :return: Every check reported on the commit.
        """
        return cls(
            commit,
            (
                *(CheckResult.from_check_run(run) for run in check_runs),
                *(
                    CheckResult.from_commit_status(status)
                    for status in combined_status[CheckField.STATUSES]
                ),
            ),
        )

    @property
    def state(self) -> CheckState:
        """
        Failing when any check failed, else pending when any is still running.
        """
        states = {result.state for result in self.results}
        for verdict in (CheckState.FAILING, CheckState.PENDING, CheckState.PASSING):
            if verdict in states:
                return verdict
        return CheckState.NO_CHECKS

    @property
    def failing_check_names(self) -> tuple[str, ...]:
        """
        The names of the checks that failed, in the order they were reported.
        """
        return tuple(
            result.check_name
            for result in self.results
            if result.state is CheckState.FAILING
        )
