"""
Tests for publishing a branch by hand: one command that checks the move and pushes only
when it is clear, against a real scratch fork.
"""

from __future__ import annotations

import argparse

import pytest

from basstler.exit_codes import StackExitCode
from basstler.maintenance.commands import PushCommand
from basstler.maintenance.git_commands import GitCommandFailed

from ..constants.stack import RemoteName, StackBranch

from .fork import FixtureFile, ForkCheckout, a_parent_and_child, the_board
from .recorded_fork import AlreadyResolvedPass

# %% a push the move checks clear


def test_the_checked_out_branch_is_published_to_the_same_branch_on_the_fork(
    fork_checkout: ForkCheckout,
):
    a_parent_and_child(fork_checkout)
    fork_checkout.run_git("checkout", "--quiet", StackBranch.CHILD)
    committed = fork_checkout.commit(FixtureFile.ON_THE_BASE, "a fix\n")

    status = PushCommand().run(
        AlreadyResolvedPass.over(fork_checkout, the_board()), argparse.Namespace()
    )

    assert status is StackExitCode.SUCCESS
    assert fork_checkout.published_commit(RemoteName.ORIGIN, StackBranch.CHILD) == (
        committed
    )


# %% a push that must not be made


def test_a_push_that_would_close_a_child_as_merged_is_refused_and_not_made(
    fork_checkout: ForkCheckout,
):
    """
    A parent that has swallowed its own child would, once pushed, make GitHub close the
    child's pull request as merged.
    """
    a_parent_and_child(fork_checkout)
    before = fork_checkout.published_commit(RemoteName.ORIGIN, StackBranch.PARENT)
    fork_checkout.run_git("checkout", "--quiet", StackBranch.PARENT)
    fork_checkout.run_git("merge", "--quiet", "--no-edit", StackBranch.CHILD)

    status = PushCommand().run(
        AlreadyResolvedPass.over(fork_checkout, the_board()), argparse.Namespace()
    )

    assert status is StackExitCode.MOVE_REFUSED
    assert (
        fork_checkout.published_commit(RemoteName.ORIGIN, StackBranch.PARENT) == before
    )


def test_a_push_the_fork_rejects_is_a_failed_git_command(fork_checkout: ForkCheckout):
    """
    A branch that moved on the fork since this checkout last saw it is never forced.
    """
    a_parent_and_child(fork_checkout)
    published = fork_checkout.commit_on(
        StackBranch.CHILD, FixtureFile.ON_THE_BASE, "pushed elsewhere\n"
    )
    fork_checkout.run_git("reset", "--quiet", "--hard", "HEAD~1")
    fork_checkout.commit(FixtureFile.ON_THE_BASE, "a fix made here\n")

    with pytest.raises(GitCommandFailed):
        PushCommand().run(
            AlreadyResolvedPass.over(fork_checkout, the_board()), argparse.Namespace()
        )

    assert fork_checkout.published_commit(RemoteName.ORIGIN, StackBranch.CHILD) == (
        published
    )
