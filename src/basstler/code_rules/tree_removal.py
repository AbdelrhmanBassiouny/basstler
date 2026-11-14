"""
Finds directories removed with :func:`shutil.rmtree` instead of through
:class:`basstler.directory_tree.DirectoryTree`.
"""

from __future__ import annotations

import ast
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import override

from basstler import directory_tree
from basstler.code_rules.checker import CodeRuleChecker, CodeRuleViolation
from basstler.directory_tree import DirectoryTree

# %% the check


@dataclass(frozen=True)
class TreeRemovalChecker(CodeRuleChecker):
    """
    Finds calls to :func:`shutil.rmtree` outside :mod:`basstler.directory_tree`; they stop
    at the read-only object files git leaves on Windows.
    """

    @override
    def violations(self, path: Path) -> Iterator[CodeRuleViolation]:
        if path.resolve() == Path(directory_tree.__file__).resolve():
            return
        module = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(module):
            if not self.calls_rmtree(node):
                continue
            yield CodeRuleViolation(
                path,
                node.lineno,
                node.end_lineno,
                f"removes a directory with {shutil.__name__}."
                f"{shutil.rmtree.__name__}, which stops at a read-only entry; call "
                f"{DirectoryTree.__name__}(...).{DirectoryTree.remove.__name__}()",
            )

    @staticmethod
    def calls_rmtree(node: ast.AST) -> bool:
        """
        :return: Whether *node* is a call to :func:`shutil.rmtree`.
        """
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == shutil.rmtree.__name__
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == shutil.__name__
        )
