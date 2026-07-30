"""
Shared scratch-project fixture for the hook scripts' integration tests, plus the
``sys.path`` entry that makes the hooks' Python scripts importable as plain modules.

They are single-file scripts, not an installed package - so their directory is added to
``sys.path`` here rather than requiring an ``__init__.py``/packaging setup just for
tests. Mirrors ``.claude/skills/plan-dashboard/tests/conftest.py``.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

HOOKS_SOURCE_DIRECTORY = Path(__file__).parent.parent
sys.path.insert(0, str(HOOKS_SOURCE_DIRECTORY))

NOTES_BRANCH = "claude/personal-notes"
"""The personal-notes branch name the hook scripts resolve to with no configuration."""


@dataclass
class ScratchProject:
    """
    A throwaway project root carrying the real hook scripts, wired to a local bare
    repository that stands in for the remote hosting the personal-notes branch - so
    every test runs the scripts end to end with no network access.
    """

    root: Path
    """The project root the hook scripts are run from and operate on."""

    notes_repository: Path
    """The bare repository standing in for the remote hosting the personal-notes branch."""

    def run_git(
        self, *arguments: str, cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        """
        Run a git command that is expected to succeed.

        :param arguments: The arguments to pass to git.
        :param cwd: Where to run it, defaulting to the project root.
        :return: The finished subprocess.
        """
        result = subprocess.run(
            ["git", *arguments], cwd=cwd or self.root, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
        return result

    def run_hook(
        self, script_name: str, *arguments: str
    ) -> subprocess.CompletedProcess[str]:
        """
        Run one of the copied hook scripts from the project root.

        :param script_name: File name of the script under ``.claude/hooks``.
        :param arguments: CLI arguments to pass to it.
        :return: The finished subprocess, whether it succeeded or not.
        """
        return subprocess.run(
            ["bash", str(self.root / ".claude" / "hooks" / script_name), *arguments],
            cwd=self.root,
            capture_output=True,
            text=True,
        )

    def read_notes_branch_file(self, path: str) -> str:
        """
        Return the content committed at *path* on the personal-notes branch.

        :param path: Repository-relative path on that branch.
        :return: The file's content as pushed to the stand-in remote.
        """
        return self.run_git(
            "show", f"{NOTES_BRANCH}:{path}", cwd=self.notes_repository
        ).stdout

    def write_notes_branch_file(self, path: str, content: str) -> None:
        """
        Commit *content* at *path* on the personal-notes branch.

        :param path: Repository-relative path on that branch.
        :param content: The content to commit there.
        """
        checkout = self.root.parent / "notes-seed-checkout"
        shutil.rmtree(checkout, ignore_errors=True)
        self.run_git(
            "clone",
            "--quiet",
            "--branch",
            NOTES_BRANCH,
            str(self.notes_repository),
            str(checkout),
            cwd=self.root.parent,
        )
        self.run_git("config", "user.name", "Scratch Repo", cwd=checkout)
        self.run_git("config", "user.email", "scratch-repo@example.com", cwd=checkout)
        destination = checkout / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content)
        self.run_git("add", path, cwd=checkout)
        self.run_git("commit", "--quiet", "-m", f"Set {path}", cwd=checkout)
        self.run_git("push", "--quiet", "origin", NOTES_BRANCH, cwd=checkout)
        shutil.rmtree(checkout)


@pytest.fixture
def scratch_project(tmp_path: Path) -> ScratchProject:
    """
    Build a scratch project root carrying the real hook scripts, with a local
    `git init --bare` fixture standing in for the personal-notes remote (already
    carrying a `claude/personal-notes` branch), pointed at via local git config.

    :param tmp_path: pytest's per-test temporary directory.
    :return: The scratch project, checked out on a throwaway work branch.
    """
    project_root = tmp_path / "project"
    hooks_directory = project_root / ".claude" / "hooks"
    hooks_directory.mkdir(parents=True)
    for script in [
        *HOOKS_SOURCE_DIRECTORY.glob("*.sh"),
        *HOOKS_SOURCE_DIRECTORY.glob("*.py"),
    ]:
        shutil.copy(script, hooks_directory / script.name)

    bare_repository_path = tmp_path / "personal-notes.git"
    scratch_project = ScratchProject(
        root=project_root, notes_repository=bare_repository_path
    )
    scratch_project.run_git("init", "--quiet")
    # A CI runner has no ambient git identity configured - set one locally so
    # the commits below don't depend on the environment already having one.
    scratch_project.run_git("config", "user.name", "Scratch Repo")
    scratch_project.run_git("config", "user.email", "scratch-repo@example.com")
    (project_root / "README.md").write_text("scratch repo\n")
    scratch_project.run_git("add", ".")
    scratch_project.run_git("commit", "--quiet", "-m", "initial commit")

    scratch_project.run_git("init", "--quiet", "--bare", str(bare_repository_path))

    scratch_project.run_git("checkout", "--quiet", "-b", NOTES_BRANCH)
    (project_root / ".claude" / "personal").mkdir(parents=True)
    (project_root / ".claude" / "personal" / "placeholder.md").write_text("notes\n")
    scratch_project.run_git("add", ".claude/personal/placeholder.md")
    scratch_project.run_git("commit", "--quiet", "-m", "bootstrap personal-notes")
    scratch_project.run_git("push", str(bare_repository_path), NOTES_BRANCH)
    scratch_project.run_git("checkout", "--quiet", "-b", "some-work-branch")

    scratch_project.run_git(
        "config", "claude.personalNotesRemote", str(bare_repository_path)
    )
    return scratch_project
