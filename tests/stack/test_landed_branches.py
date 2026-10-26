"""
Tests for answering which fork branches the upstream base already contains, against a
real scratch fork.
"""

from __future__ import annotations

import pytest

from basstler.stack.checkout import LandedBranches

from ..constants.stack import RemoteName, StackBranch
from ..maintenance.fork import UPSTREAM_BASE, ForkCheckout, make_configuration


# %% a parent branch on the fork, and whether the upstream has it


@pytest.fixture
def fork_with_a_branch(
    fork_checkout: ForkCheckout, monkeypatch: pytest.MonkeyPatch
) -> ForkCheckout:
    """
    The scratch fork with :attr:`StackBranch.PARENT` published on it and not yet
    upstream, as the working directory the questions are asked in.

    :param fork_checkout: The scratch fork.
    :param monkeypatch: Moves the working directory into the fork.
    :return: The same fork.
    """
    fork_checkout.branch_from(StackBranch.PARENT, UPSTREAM_BASE)
    monkeypatch.chdir(fork_checkout.project_root)
    return fork_checkout


def land_upstream(checkout: ForkCheckout, branch: str) -> None:
    """
    Publish a fork branch's commit as the upstream base, as a merged pull request does.

    :param checkout: The scratch fork.
    :param branch: The fork branch to land.
    """
    checkout.run_git(
        "push", "--quiet", RemoteName.UPSTREAM, f"{branch}:{UPSTREAM_BASE}"
    )
    checkout.run_git("fetch", "--quiet", RemoteName.UPSTREAM)


def test_a_branch_the_upstream_lacks_has_not_landed(fork_with_a_branch: ForkCheckout):
    landed = LandedBranches.from_checkout(make_configuration())

    assert not landed.contains(StackBranch.PARENT)


def test_a_branch_the_upstream_carries_has_landed(fork_with_a_branch: ForkCheckout):
    land_upstream(fork_with_a_branch, StackBranch.PARENT)

    assert LandedBranches.from_checkout(make_configuration()).contains(
        StackBranch.PARENT
    )


def test_a_branch_the_fork_does_not_have_has_not_landed(
    fork_with_a_branch: ForkCheckout,
):
    landed = LandedBranches.from_checkout(make_configuration())

    assert not landed.contains(StackBranch.CHILD)


def test_an_answer_is_what_the_refs_said_when_the_snapshot_was_taken(
    fork_with_a_branch: ForkCheckout,
):
    landed = LandedBranches.from_checkout(make_configuration())

    land_upstream(fork_with_a_branch, StackBranch.PARENT)

    assert not landed.contains(StackBranch.PARENT)
