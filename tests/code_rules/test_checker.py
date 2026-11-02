"""
Tests for :mod:`basstler.code_rules.checker`: running checkers over the code a staged
change touches.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from basstler.code_rules.checker import CodeRulesCheck, StagedLines
from basstler.code_rules.prose_length import ProseLengthChecker
from basstler.maintenance.git_commands import GitCommandRunner

from ..constants.paths import ProseSnippet

# %% the staged change


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """
    :return: A git repository whose one commit holds an overlong module docstring.
    """
    for arguments in (
        ["init", "--quiet"],
        ["config", "user.name", "Tester"],
        ["config", "user.email", "tester@example.com"],
    ):
        subprocess.run(["git", *arguments], cwd=tmp_path, check=True)
    shutil.copy(ProseSnippet.OVERLONG_MODULE_DOCSTRING, tmp_path / "module.py")
    subprocess.run(["git", "add", "module.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "Add"], cwd=tmp_path, check=True)
    return tmp_path


def test_only_code_the_staged_change_touches_is_reported(repository):
    """
    The committed overlong module docstring is left alone; the overlong attribute
    docstring the staged change appends is reported.
    """
    path = repository / "module.py"
    committed_lines = len(path.read_text().splitlines())
    with path.open("a") as source:
        source.write(f"\n{ProseSnippet.OVERLONG_ATTRIBUTE_DOCSTRING.read_text()}")
    subprocess.run(["git", "add", "module.py"], cwd=repository, check=True)
    check = CodeRulesCheck(
        (ProseLengthChecker(),), StagedLines(GitCommandRunner(repository))
    )

    violations = check.violations([path])

    assert [violation.first_line > committed_lines for violation in violations] == [
        True
    ]
