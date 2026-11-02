"""
Tests for a git branch, the base of every branch the package handles.
"""

from __future__ import annotations

from basstler.branch import Branch
from basstler.maintenance.remote_branch import RemoteBranch
from basstler.stack.model import StackBranch

# %% the reference a branch is kept under


def test_reference_is_the_branch_under_the_heads_namespace() -> None:
    assert Branch("feature/x").reference == "refs/heads/feature/x"


# %% the branches that are one


def test_a_remote_branch_is_a_branch() -> None:
    assert issubclass(RemoteBranch, Branch)


def test_a_stack_branch_is_a_branch() -> None:
    assert issubclass(StackBranch, Branch)
