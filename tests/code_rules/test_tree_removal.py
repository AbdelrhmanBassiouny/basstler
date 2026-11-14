"""
Tests for :mod:`basstler.code_rules.tree_removal`: reporting directories removed with
:func:`shutil.rmtree`, which stops at the read-only object files git leaves on Windows.
"""

from __future__ import annotations

from pathlib import Path

from basstler import directory_tree
from basstler.code_rules.checker import CodeRulesCheck
from basstler.code_rules.tree_removal import TreeRemovalChecker

from ..constants.paths import TreeRemovalSnippet

# %% removals


def test_every_shutil_rmtree_is_reported():
    """
    Each call is reported, whether or not it ignores errors.
    """
    violations = TreeRemovalChecker().violations(TreeRemovalSnippet.SHUTIL_RMTREE)
    assert [violation.first_line for violation in violations] == [10, 11]


def test_the_module_removing_trees_is_not_reported():
    """
    The one module allowed to call :func:`shutil.rmtree` is left out.
    """
    assert list(TreeRemovalChecker().violations(Path(directory_tree.__file__))) == []


# %% this repository


def test_no_code_in_the_repository_removes_a_directory_with_shutil_rmtree(
    repository_sources,
):
    """
    Every directory the package, its scripts and its suite remove goes through
    :class:`basstler.directory_tree.DirectoryTree`, so the suite passes on Windows too.
    """
    violations = CodeRulesCheck((TreeRemovalChecker(),)).violations(repository_sources)
    assert [violation.render() for violation in violations] == []
