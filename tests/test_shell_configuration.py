"""
Tests for naming files on the branches the shell configuration fetches.
"""

from __future__ import annotations

from pathlib import PureWindowsPath

from basstler.locations import ProjectLocation
from basstler.shell_configuration import FetchedBranchReference

# %% git tree paths


def test_a_file_on_the_fetched_branch_is_named_with_slashes_from_a_windows_path():
    """
    Git names a file in a tree with ``/`` on every platform, so a path Windows built
    with ``\\`` names no file.
    """
    windows_path = PureWindowsPath(*ProjectLocation.PERSONAL_PLAN_ITEM_MODES.parts)

    assert FetchedBranchReference.PERSONAL_NOTES.file_at(windows_path) == (
        f"{FetchedBranchReference.PERSONAL_NOTES}:"
        f"{ProjectLocation.PERSONAL_PLAN_ITEM_MODES.as_posix()}"
    )
