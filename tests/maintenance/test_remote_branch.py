"""
Tests for reading and writing any named branch of a remote without a checkout.
"""

from __future__ import annotations

import subprocess

from basstler.maintenance.git_commands import GitCommandRunner
from basstler.maintenance.remote_branch import RemoteBranch
from basstler.repository import Repository

from .fork import ForkCheckout, RemoteName

# %% helpers


def branch_on_fork(checkout: ForkCheckout, name: str) -> RemoteBranch:
    """
    :return: The branch called *name* on the checkout's fork remote.
    """
    return RemoteBranch(
        GitCommandRunner(checkout.project_root), RemoteName.ORIGIN, name
    )


def file_on_remote(checkout: ForkCheckout, branch: str, path: str) -> str:
    """
    :return: The file's text on the fork's bare repository, stripped.
    """
    return subprocess.run(
        ["git", "show", f"{branch}:{path}"],
        cwd=checkout.fork_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


# %% writing and reading a named branch


def test_a_missing_branch_does_not_exist_and_has_no_tip(fork_checkout):
    branch = branch_on_fork(fork_checkout, "notes/someone")

    assert not branch.exists()
    assert branch.fetch() is None


def test_writing_creates_the_named_branch_with_the_given_file(fork_checkout):
    branch = branch_on_fork(fork_checkout, "notes/someone")

    branch.write({"a/file.txt": "content"}, "Write a file")

    assert branch.exists()
    assert file_on_remote(fork_checkout, "notes/someone", "a/file.txt") == "content"


def test_writing_keeps_the_files_already_on_the_branch(fork_checkout):
    branch = branch_on_fork(fork_checkout, "notes/someone")
    branch.write({"first.txt": "one"}, "First")

    branch.write({"second.txt": "two"}, "Second")

    tip = branch.fetch()
    assert branch.git.file_at(tip, "first.txt") == "one"
    assert branch.git.file_at(tip, "second.txt") == "two"


def test_a_file_the_branch_lacks_reads_as_none(fork_checkout):
    branch = branch_on_fork(fork_checkout, "notes/someone")
    branch.write({"first.txt": "one"}, "First")

    assert branch.git.file_at(branch.fetch(), "missing.txt") is None


def test_two_branches_of_one_remote_are_kept_apart(fork_checkout):
    first = branch_on_fork(fork_checkout, "first")
    second = branch_on_fork(fork_checkout, "second")
    first.write({"file.txt": "first"}, "First")
    second.write({"file.txt": "second"}, "Second")

    assert first.git.file_at(first.fetch(), "file.txt") == "first"
    assert second.git.file_at(second.fetch(), "file.txt") == "second"


def test_the_branch_names_the_repository_its_remote_points_at(fork_checkout):
    branch = branch_on_fork(fork_checkout, "first")

    assert branch.repository == Repository.from_remote_url(
        fork_checkout.fork_path.as_uri()
    )


def test_the_latest_file_is_read_from_the_remote_s_current_tip(fork_checkout):
    branch = branch_on_fork(fork_checkout, "notes/someone")
    branch.write({"file.txt": "first"}, "First")
    branch.write({"file.txt": "second"}, "Second")

    assert branch.read_latest("file.txt") == "second"


def test_a_missing_branch_reads_no_latest_file(fork_checkout):
    assert (
        branch_on_fork(fork_checkout, "notes/someone").read_latest("file.txt") is None
    )
