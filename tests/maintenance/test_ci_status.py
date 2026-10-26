"""
Tests for the one line ``ci-status`` prints per pushed branch.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, replace
from dataclasses import field as dataclasses_field
from pathlib import Path
from typing import Any

import pytest

from basstler.exit_codes import StackExitCode
from basstler.maintenance.ci_status import BranchChecks, CheckState
from basstler.maintenance.commands import CiStatusCommand
from basstler.maintenance.github import CommitChecksReader

from ..constants.paths import DatasetLocation
from ..constants.stack import StackBranch

from .fork import ForkCheckout, a_parent_and_child, the_board
from .recorded_fork import AlreadyResolvedPass, RecordingPullRequests

# %% a fork answering with recorded responses


@dataclass(frozen=True)
class RecordedChecksFork(RecordingPullRequests, CommitChecksReader):
    """
    Answers every branch's checks with the same recorded responses.
    """

    check_runs_response: Path = DatasetLocation.CHECK_RUNS_NONE.value
    """
    The check-run response every branch answers with.
    """

    status_response: Path = DatasetLocation.STATUS_NONE.value
    """
    The commit-status response every branch answers with.
    """

    asked_for: list[str] = dataclasses_field(default_factory=list)
    """
    Every reference whose check runs were asked for, in order.
    """

    def check_runs(self, reference: str) -> dict[str, Any]:
        self.asked_for.append(reference)
        return json.loads(self.check_runs_response.read_text())

    def commit_status(self, reference: str) -> dict[str, Any]:
        return json.loads(self.status_response.read_text())


def checks_of(check_runs: Path, statuses: Path) -> BranchChecks:
    """
    :param check_runs: The recorded check-run response.
    :param statuses: The recorded commit-status response.
    :return: The parent branch's checks, read from both.
    """
    return BranchChecks.read(
        RecordedChecksFork(check_runs_response=check_runs, status_response=statuses),
        StackBranch.PARENT,
    )


# %% the state of one branch


def test_a_check_still_running_with_none_failed_is_pending():
    checks = checks_of(
        DatasetLocation.CHECK_RUNS_IN_PROGRESS.value, DatasetLocation.STATUS_NONE.value
    )

    assert checks.state is CheckState.PENDING
    assert checks.failing == ()


def test_a_failed_check_run_or_commit_status_is_a_failure_naming_both():
    checks = checks_of(
        DatasetLocation.CHECK_RUNS_FAILING.value, DatasetLocation.STATUS_FAILING.value
    )

    assert checks.state is CheckState.FAILURE
    assert checks.failing == ("tests", "ci/legacy")


def test_every_check_completed_without_failing_is_a_success():
    checks = checks_of(
        DatasetLocation.CHECK_RUNS_PASSING.value, DatasetLocation.STATUS_NONE.value
    )

    assert checks.state is CheckState.SUCCESS


def test_a_commit_with_no_check_yet_says_so_rather_than_passing():
    checks = checks_of(
        DatasetLocation.CHECK_RUNS_NONE.value, DatasetLocation.STATUS_NONE.value
    )

    assert checks.state is CheckState.NO_CHECKS


def test_a_branch_line_names_the_branch_its_state_and_what_failed():
    checks = checks_of(
        DatasetLocation.CHECK_RUNS_FAILING.value, DatasetLocation.STATUS_FAILING.value
    )

    assert checks.line == f"{StackBranch.PARENT}\t{CheckState.FAILURE}\ttests,ci/legacy"


# %% the command


def test_the_command_prints_one_line_per_branch_asked_for(
    fork_checkout: ForkCheckout, capsys: pytest.CaptureFixture[str]
):
    a_parent_and_child(fork_checkout)
    fork = RecordedChecksFork(
        check_runs_response=DatasetLocation.CHECK_RUNS_FAILING.value,
        status_response=DatasetLocation.STATUS_NONE.value,
    )
    maintenance = replace(
        AlreadyResolvedPass.over(fork_checkout, the_board()), recorded_fork=fork
    )

    status = CiStatusCommand().run(
        maintenance,
        argparse.Namespace(branch=[StackBranch.PARENT, StackBranch.CHILD]),
    )

    assert status is StackExitCode.SUCCESS
    assert fork.asked_for == [StackBranch.PARENT, StackBranch.CHILD]
    assert capsys.readouterr().out.splitlines() == [
        BranchChecks.read(fork, StackBranch.PARENT).line,
        BranchChecks.read(fork, StackBranch.CHILD).line,
    ]
