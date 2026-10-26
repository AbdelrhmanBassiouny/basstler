"""
Tests for what ``next --context`` prints for each branch ready to be promoted: the
material its upstream summary is written from.
"""

from __future__ import annotations

import pytest

from basstler.stack.report import StackReport

from ..constants.stack import RemoteName, StackBranch
from ..maintenance.fork import (
    UPSTREAM_BASE,
    ForkCheckout,
    PromotionSampleText,
    StackPullRequestNumber,
    a_board_entry,
    a_parent_and_child,
    a_stack,
)

# %% the context of one promotable branch


@pytest.fixture
def printed_context(
    fork_checkout: ForkCheckout,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> str:
    """
    :param fork_checkout: The checkout the two-branch stack is published from.
    :param monkeypatch: Moves the test into the checkout, where the report runs git.
    :param capsys: Captures what the report prints.
    :return: What ``next --context`` prints for the stack, whose parent alone is ready.
    """
    a_parent_and_child(fork_checkout)
    monkeypatch.chdir(fork_checkout.project_root)
    board = [
        a_board_entry(
            StackPullRequestNumber.PARENT,
            StackBranch.PARENT,
            UPSTREAM_BASE,
            title=PromotionSampleText.TITLE,
            description=PromotionSampleText.SUMMARY,
        ),
        a_board_entry(
            StackPullRequestNumber.CHILD, StackBranch.CHILD, StackBranch.PARENT
        ),
    ]

    StackReport(a_stack(fork_checkout, board)).print_next_context()

    return capsys.readouterr().out


def test_the_context_has_the_files_changed_against_the_base_it_is_promoted_onto(
    fork_checkout: ForkCheckout, printed_context: str
):
    statistics = fork_checkout.run_git(
        "diff",
        "--stat",
        f"{RemoteName.UPSTREAM}/{UPSTREAM_BASE}...{RemoteName.ORIGIN}/{StackBranch.PARENT}",
    )

    assert statistics in printed_context


def test_the_context_has_the_commit_subjects_and_the_description(printed_context: str):
    lines = printed_context.splitlines()

    assert f"- write {ForkCheckout.own_file(StackBranch.PARENT)}" in lines
    assert PromotionSampleText.SUMMARY in lines


def test_the_context_names_only_the_branches_ready_to_be_promoted(
    printed_context: str,
):
    assert f"#{StackPullRequestNumber.PARENT} {StackBranch.PARENT}" in printed_context
    assert StackBranch.CHILD not in printed_context
