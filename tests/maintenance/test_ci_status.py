"""
Tests for the one line ``ci-status`` prints per pushed branch.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from dataclasses import field as dataclasses_field

import pytest

from basstler.exit_codes import StackExitCode
from basstler.maintenance.ci_status import BranchChecks, UnreportedCheckState
from basstler.maintenance.commands import CiStatusCommand
from basstler.maintenance.github import CheckStatusReader
from basstler.upstream_reviews.pull_request_models import CheckResult, CheckStatus
from basstler.upstream_reviews.vocabulary import CheckOutcome, RollupState

from ..constants.stack import StackBranch

from .fork import ForkCheckout, a_parent_and_child, the_board
from .recorded_fork import AlreadyResolvedPass, RecordingPullRequests

# %% a fork answering with recorded checks


@dataclass(frozen=True)
class RecordedChecksFork(RecordingPullRequests, CheckStatusReader):
    """
    Answers every branch's checks with the same recorded outcomes.
    """

    outcomes: dict[str, CheckOutcome] = dataclasses_field(default_factory=dict)
    """
    Each check reported on every branch, by name.
    """

    asked_for: list[str] = dataclasses_field(default_factory=list)
    """
    Every reference whose checks were asked for, in order.
    """

    def check_status(self, reference: str) -> CheckStatus | None:
        self.asked_for.append(reference)
        return CheckStatus.over(
            [
                CheckResult(name=name, outcome=outcome, url="")
                for name, outcome in self.outcomes.items()
            ]
        )


def checks_of(**outcomes: CheckOutcome) -> BranchChecks:
    """
    :param outcomes: Each check reported on the parent's head, by name.
    :return: The parent branch's checks.
    """
    return BranchChecks.read(RecordedChecksFork(outcomes=outcomes), StackBranch.PARENT)


# %% the state of one branch


def test_a_check_still_running_with_none_failed_is_pending():
    checks = checks_of(tests=CheckOutcome.PENDING, lint=CheckOutcome.SUCCESS)

    assert checks.state is RollupState.PENDING
    assert checks.failing == ()


def test_every_check_that_failed_or_errored_is_named():
    checks = checks_of(
        tests=CheckOutcome.FAILURE,
        build=CheckOutcome.PENDING,
        legacy=CheckOutcome.ERROR,
        docs=CheckOutcome.SKIPPED,
    )

    assert checks.state.failed
    assert checks.failing == ("tests", "legacy")


def test_a_commit_with_no_check_yet_says_so_rather_than_passing():
    assert checks_of().state is UnreportedCheckState.NO_CHECKS


def test_a_branch_line_names_the_branch_its_state_and_what_failed():
    checks = checks_of(tests=CheckOutcome.FAILURE, lint=CheckOutcome.SUCCESS)

    assert checks.line == f"{StackBranch.PARENT}\t{RollupState.FAILURE}\ttests"


# %% the command


def test_the_command_prints_one_line_per_branch_asked_for(
    fork_checkout: ForkCheckout, capsys: pytest.CaptureFixture[str]
):
    a_parent_and_child(fork_checkout)
    fork = RecordedChecksFork(outcomes={"tests": CheckOutcome.SUCCESS})
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
        f"{StackBranch.PARENT}\t{RollupState.SUCCESS}\t",
        f"{StackBranch.CHILD}\t{RollupState.SUCCESS}\t",
    ]
