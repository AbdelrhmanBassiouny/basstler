"""
Tests for the overview of every open branch's checks that the ``checks`` command prints.
"""

from __future__ import annotations

import argparse

import pytest

from basstler.maintenance.check_overview import CheckOverview
from basstler.maintenance.commands import ChecksCommand
from basstler.upstream_reviews.vocabulary import CombinedCheckState

from ..constants.stack import StackBranch

from .fork import (
    UPSTREAM_BASE,
    ForkCheckout,
    StackPullRequestNumber,
    a_board_entry,
    a_parent_and_child,
)
from .large_board import LargeBoard, OutputBudget
from .recorded_fork import AlreadyResolvedPass


def test_every_verdict_is_counted_and_every_one_but_success_named():
    board = LargeBoard()
    overview = CheckOverview(board.stack())

    lines = overview.as_lines()

    assert lines[0] == (
        f"checks on {len(overview.open_branches())} open branches: "
        f"{len(overview.branches_in(CombinedCheckState.SUCCESS))} {CombinedCheckState.SUCCESS}, "
        f"{board.failing_checks} {CombinedCheckState.FAILURE}, "
        f"{board.pushed} {CombinedCheckState.PENDING}"
    )
    assert lines[1:] == [
        f"{CombinedCheckState.FAILURE}: {overview.named(CombinedCheckState.FAILURE)}",
        f"{CombinedCheckState.PENDING}: {overview.named(CombinedCheckState.PENDING)}",
    ]


def test_a_verdict_names_its_first_branches_and_counts_the_rest():
    board = LargeBoard()
    overview = CheckOverview(board.stack())

    named = overview.named(CombinedCheckState.FAILURE)

    first = overview.branches_in(CombinedCheckState.FAILURE)[0]
    assert named.startswith(f"#{first.pull_request_number} `{first.name}`")
    assert named.endswith(
        f" and {board.failing_checks - overview.entries_per_state} more"
    )


@pytest.mark.parametrize("board", [LargeBoard(), LargeBoard().doubled().doubled()])
def test_the_overview_of_a_large_board_stays_within_the_summary_budget(
    board: LargeBoard,
):
    text = "\n".join(CheckOverview(board.stack()).as_lines())

    assert len(text.encode()) <= OutputBudget.FINISH_SUMMARY


def test_the_command_names_a_branch_nothing_has_reported_checks_on(
    fork_checkout: ForkCheckout, capsys: pytest.CaptureFixture[str]
):
    a_parent_and_child(fork_checkout)
    maintenance = AlreadyResolvedPass.over(
        fork_checkout,
        [
            a_board_entry(
                StackPullRequestNumber.PARENT,
                StackBranch.PARENT,
                UPSTREAM_BASE,
                check_state=CombinedCheckState.SUCCESS,
            ),
            a_board_entry(
                StackPullRequestNumber.CHILD, StackBranch.CHILD, StackBranch.PARENT
            ),
        ],
    )

    ChecksCommand().run(maintenance, argparse.Namespace())

    printed = capsys.readouterr().out.splitlines()
    assert printed[-1] == (
        f"{CombinedCheckState.NOT_REPORTED}: "
        f"#{StackPullRequestNumber.CHILD} `{StackBranch.CHILD}`"
    )
