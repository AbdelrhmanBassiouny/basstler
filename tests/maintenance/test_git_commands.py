"""
Tests for running git in a checkout.
"""

from __future__ import annotations

from pathlib import Path

from basstler.maintenance.git_commands import GitCommandRunner

from ..constants.paths import DatasetLocation

# %% non-ASCII file contents


def test_file_round_trips_non_ascii_text(tmp_path: Path) -> None:
    git = GitCommandRunner(tmp_path)
    git.run("init", "--quiet")
    git.run("config", "user.name", "Test Author")
    git.run("config", "user.email", "author@example.com")
    text = DatasetLocation.NON_ASCII_TEXT.read_text(encoding="utf-8").rstrip("\n")

    commit = git.commit_files(None, {"notes.txt": text}, "Add notes")

    assert git.file_at(commit, "notes.txt") == text
