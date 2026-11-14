"""
Tests for :mod:`basstler.directory_tree`: removing a directory and everything in it,
read-only entries included, as git leaves its object files on Windows.
"""

from __future__ import annotations

from pathlib import Path

from basstler.directory_tree import DirectoryTree

from .constants.environment import FileMode

# %% removal


def test_a_tree_holding_read_only_entries_is_removed(tmp_path: Path):
    """
    A read-only directory stands in for git's read-only object files: neither can be
    deleted from as it is, on Linux and on Windows respectively.
    """
    tree = tmp_path / "clone"
    objects = tree / ".git" / "objects"
    objects.mkdir(parents=True)
    (objects / "object").write_text("blob", encoding="utf-8")
    objects.chmod(FileMode.READ_ONLY_DIRECTORY)

    DirectoryTree(tree).remove()

    assert not tree.exists()


def test_removing_a_tree_that_is_not_there_does_nothing(tmp_path: Path):
    """
    A missing tree is no error.
    """
    DirectoryTree(tmp_path / "never-made").remove()

    assert list(tmp_path.iterdir()) == []
