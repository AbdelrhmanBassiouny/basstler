"""
Tests for :mod:`basstler.code_rules.bash_by_name`: reporting commands that start bash
by its name, which Windows resolves to WSL's launcher instead of Git Bash.
"""

from __future__ import annotations

from pathlib import Path

from basstler.code_rules.bash_by_name import BashByNameChecker
from basstler.code_rules.checker import CodeRulesCheck

from ..constants.paths import BashByNameSnippet

# %% helpers


def violation_lines(path: Path) -> list[int]:
    """
    :return: The first line of each violation the checker reports in *path*.
    """
    return [violation.first_line for violation in BashByNameChecker().violations(path)]


# %% commands


def test_a_subprocess_call_running_bash_by_its_name_is_reported():
    """
    A command line handed to :mod:`subprocess` is reported.
    """
    assert violation_lines(BashByNameSnippet.SUBPROCESS_CALL) == [9]


def test_a_returned_command_running_bash_by_its_name_is_reported():
    """
    A command line returned for a caller to run is reported.
    """
    assert violation_lines(BashByNameSnippet.RETURNED_COMMAND) == [12]


def test_the_located_bash_and_a_tuple_of_names_are_not_reported():
    """
    The located bash is not, and neither is a tuple of names that runs nothing.
    """
    assert violation_lines(BashByNameSnippet.LOCATED_BASH) == []


# %% this repository


def test_no_code_in_the_repository_starts_bash_by_its_name(repository_sources):
    """
    Every bash the package, its scripts and its suite start is the one
    :class:`basstler.bash.Bash` locates, so the suite passes on Windows too.
    """
    violations = CodeRulesCheck((BashByNameChecker(),)).violations(repository_sources)
    assert [violation.render() for violation in violations] == []
