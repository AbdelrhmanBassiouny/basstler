"""
Finds commands that start bash by its name instead of through :class:`basstler.bash.Bash`.
"""

from __future__ import annotations

import ast
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import override

from basstler.bash import Bash, LocatedProgram
from basstler.code_rules.checker import CodeRuleChecker, CodeRuleViolation

# %% the check


@dataclass(frozen=True)
class BashByNameChecker(CodeRuleChecker):
    """
    Finds command lines whose program is bash given by its name, which Windows resolves
    to WSL's launcher: those passed to a :mod:`subprocess` function, and those returned.
    """

    @override
    def violations(self, path: Path) -> Iterator[CodeRuleViolation]:
        module = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(module):
            command = self.command_line(node)
            if command is None or not self.starts_bash_by_name(command):
                continue
            yield CodeRuleViolation(
                path,
                command.lineno,
                command.end_lineno,
                f"starts {LocatedProgram.BASH} by its name, which Windows resolves to "
                f"WSL's launcher; build the command with {Bash.__name__}.locate(...)"
                f".{Bash.command.__name__}(...)",
            )

    @staticmethod
    def command_line(node: ast.AST) -> ast.expr | None:
        """
        :return: The command line *node* runs or hands on: the first argument of a call
            to a :mod:`subprocess` function, or a returned value; ``None`` otherwise.
        """
        if isinstance(node, ast.Return):
            return node.value
        if not isinstance(node, ast.Call) or not node.args:
            return None
        function = node.func
        if (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id == subprocess.__name__
        ):
            return node.args[0]
        return None

    @staticmethod
    def starts_bash_by_name(command: ast.expr) -> bool:
        """
        :return: Whether *command* is a list or tuple whose first element is the bare
            name of bash.
        """
        return (
            isinstance(command, ast.List | ast.Tuple)
            and bool(command.elts)
            and isinstance(command.elts[0], ast.Constant)
            and command.elts[0].value == LocatedProgram.BASH
        )
