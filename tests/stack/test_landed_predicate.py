"""
Tests for the predicate that answers whether a fork branch has landed in the upstream
base, read from a real scratch checkout.
"""

from __future__ import annotations

import pytest

from basstler.stack.checkout import CurrentCheckout

from ..constants.stack import RemoteName, StackBranch

from ..maintenance.fork import UPSTREAM_BASE, ForkCheckout, make_configuration

# %% landing a branch


def land(fork_checkout: ForkCheckout, branch: str) -> None:
    """
    Move the upstream base onto a published fork branch, and fetch it.

    :param fork_checkout: The checkout the branch was published from.
    :param branch: The branch to land.
    """
    fork_checkout.run_git(
        "push", "--quiet", RemoteName.UPSTREAM, f"{branch}:{UPSTREAM_BASE}"
    )
    fork_checkout.run_git("fetch", "--quiet", RemoteName.UPSTREAM)


@pytest.fixture
def in_fork_checkout(
    fork_checkout: ForkCheckout, monkeypatch: pytest.MonkeyPatch
) -> ForkCheckout:
    """
    :param fork_checkout: The scratch checkout.
    :param monkeypatch: pytest's monkeypatch fixture.
    :return: The scratch checkout, made the current directory git runs in.
    """
    monkeypatch.chdir(fork_checkout.project_root)
    return fork_checkout


# %% what the predicate answers


def test_a_branch_contained_in_the_upstream_base_has_landed(
    in_fork_checkout: ForkCheckout,
):
    in_fork_checkout.branch_from(StackBranch.LANDED, UPSTREAM_BASE)
    land(in_fork_checkout, StackBranch.LANDED)

    is_merged = CurrentCheckout.merged_predicate(make_configuration())

    assert is_merged(StackBranch.LANDED)


def test_a_branch_with_commits_of_its_own_has_not_landed(
    in_fork_checkout: ForkCheckout,
):
    in_fork_checkout.branch_from(StackBranch.PARENT, UPSTREAM_BASE)

    is_merged = CurrentCheckout.merged_predicate(make_configuration())

    assert not is_merged(StackBranch.PARENT)


def test_a_branch_the_fork_has_no_copy_of_has_not_landed(
    in_fork_checkout: ForkCheckout,
):
    is_merged = CurrentCheckout.merged_predicate(make_configuration())

    assert not is_merged(StackBranch.ON_ANOTHER_FORK)


def test_a_landed_branch_with_a_slash_in_its_name_has_landed(
    in_fork_checkout: ForkCheckout,
):
    in_fork_checkout.branch_from(StackBranch.NAMESPACED, UPSTREAM_BASE)
    land(in_fork_checkout, StackBranch.NAMESPACED)

    is_merged = CurrentCheckout.merged_predicate(make_configuration())

    assert is_merged(StackBranch.NAMESPACED)


# %% one answer per run


def test_the_predicate_answers_from_the_upstream_base_as_it_was_built(
    in_fork_checkout: ForkCheckout,
):
    """
    Every phase of a run asks the same predicate, so a branch landing mid-run must not
    give two phases two answers.
    """
    in_fork_checkout.branch_from(StackBranch.PARENT, UPSTREAM_BASE)
    is_merged = CurrentCheckout.merged_predicate(make_configuration())

    land(in_fork_checkout, StackBranch.PARENT)

    assert not is_merged(StackBranch.PARENT)
