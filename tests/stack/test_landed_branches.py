"""
Tests for answering which fork branches the upstream base already contains, against a
real scratch fork.
"""

from __future__ import annotations

import pytest

from basstler.exceptions import UnresolvableReferenceError
from basstler.stack.checkout import CurrentCheckout, LandedBranches

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


def test_a_branch_named_with_a_slash_has_landed(
    fork_checkout: ForkCheckout, monkeypatch: pytest.MonkeyPatch
):
    fork_checkout.branch_from(StackBranch.NAMESPACED, UPSTREAM_BASE)
    monkeypatch.chdir(fork_checkout.project_root)
    land_upstream(fork_checkout, StackBranch.NAMESPACED)

    assert LandedBranches.from_checkout(make_configuration()).contains(
        StackBranch.NAMESPACED
    )


# %% whether one fork branch's commits are in another


def test_a_branch_is_contained_by_the_branch_cut_from_it(
    fork_with_a_branch: ForkCheckout,
):
    fork_with_a_branch.branch_from(StackBranch.CHILD, StackBranch.PARENT)
    is_contained_by = CurrentCheckout.containment_predicate(make_configuration())

    assert is_contained_by(StackBranch.PARENT, StackBranch.CHILD)


def test_a_branch_is_not_contained_by_the_branch_it_was_cut_from(
    fork_with_a_branch: ForkCheckout,
):
    fork_with_a_branch.branch_from(StackBranch.CHILD, StackBranch.PARENT)
    is_contained_by = CurrentCheckout.containment_predicate(make_configuration())

    assert not is_contained_by(StackBranch.CHILD, StackBranch.PARENT)


def test_containment_refuses_a_branch_whose_reference_does_not_resolve(
    fork_with_a_branch: ForkCheckout,
):
    """
    A reference that was never fetched is not evidence that the commits are elsewhere,
    and answering ``False`` for it would hand a branch back as having lost its base.
    """
    is_contained_by = CurrentCheckout.containment_predicate(make_configuration())

    with pytest.raises(UnresolvableReferenceError) as refusal:
        is_contained_by(StackBranch.CHILD, StackBranch.PARENT)

    assert refusal.value.reference == make_configuration().reference_on_fork(
        StackBranch.CHILD
    )
