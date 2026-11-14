"""
Tests for :class:`GitHubRemoteBranch`: the repository a branch's remote points at.
"""

from __future__ import annotations

from basstler.git.commands import GitCommandRunner
from basstler.github.remote_branch import GitHubRemoteBranch
from basstler.github.repository import Repository

from ..maintenance.fork import ForkCheckout, RemoteName

# %% helpers


def branch_on_fork(checkout: ForkCheckout, name: str) -> GitHubRemoteBranch:
    """
    :return: The branch called *name* on the checkout's fork remote.
    """
    return GitHubRemoteBranch(
        name, GitCommandRunner(checkout.project_root), RemoteName.ORIGIN
    )


# %% the repository


def test_the_branch_names_the_repository_its_remote_points_at(fork_checkout):
    """
    The repository is the one the remote's URL names.
    """
    branch = branch_on_fork(fork_checkout, "first")

    assert branch.repository == Repository.from_remote_url(
        fork_checkout.fork_path.as_uri()
    )


def test_the_branch_is_described_by_its_repository_s_name(fork_checkout):
    """
    A remote naming a repository is described by that repository's full name.
    """
    branch = branch_on_fork(fork_checkout, "first")

    assert branch.description == branch.repository.full_name


def test_a_remote_naming_no_repository_is_described_by_the_remote(tmp_path):
    """
    A remote given as a local path names no repository, so the remote describes it.
    """
    branch = GitHubRemoteBranch("first", GitCommandRunner(tmp_path), str(tmp_path))

    assert branch.repository is None
    assert branch.description == str(tmp_path)
