"""
The base every code rule checker extends, and the violations checkers report.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from basstler.git.commands import GitCommandRunner

# %% violations


@dataclass(frozen=True)
class CodeRuleViolation:
    """
    One place in a source file that breaks a rule.
    """

    path: Path
    """
    The file breaking the rule.
    """

    first_line: int
    """
    The first line of the offending code, counting from one.
    """

    last_line: int
    """
    The last line of the offending code, counting from one.
    """

    description: str
    """
    What is wrong and how to fix it, as one sentence fragment.
    """

    def touches(self, lines: set[int]) -> bool:
        """
        :param lines: Line numbers in the file.
        :return: Whether any of them falls within the offending code.
        """
        return any(self.first_line <= line <= self.last_line for line in lines)

    def render(self) -> str:
        """
        :return: The violation as it is printed.
        """
        return f"{self.path}:{self.first_line}: {self.description}"


# %% checkers


class CodeRuleChecker(ABC):
    """
    Finds the code that breaks one agent rule, the rule that names this checker.
    """

    @abstractmethod
    def violations(self, path: Path) -> Iterator[CodeRuleViolation]:
        """
        :param path: A Python source file.
        :return: Every place in it that breaks the rule.
        """


# %% the staged change


@dataclass(frozen=True)
class StagedLines:
    """
    The lines a commit being prepared adds or changes.
    """

    git: GitCommandRunner
    """
    The repository the commit is prepared in.
    """

    def of(self, path: Path) -> set[int]:
        """
        :param path: A file in the repository.
        :return: The line numbers, in the staged file, that the staged change adds or
            changes; none for a file the change only moves.
        """
        return self.lines_by_file.get(path.resolve(), set())

    @cached_property
    def lines_by_file(self) -> dict[Path, set[int]]:
        """
        :return: The lines the staged change adds or changes, by the staged file they
            are in, with moves detected so a moved file keeps its committed lines.
        """
        diff = self.git.run(
            "diff",
            "--cached",
            "--find-renames",
            "--unified=0",
            "--no-color",
            "--relative",
        )
        lines_by_file: dict[Path, set[int]] = {}
        lines: set[int] = set()
        for match in re.finditer(
            r"^diff --git a/.+ b/(.+)$|^@@ -\S+ \+(\d+)(?:,(\d+))? @@",
            diff,
            re.MULTILINE,
        ):
            if match[1] is not None:
                lines = lines_by_file.setdefault(
                    (self.git.working_directory / match[1]).resolve(), set()
                )
                continue
            start = int(match[2])
            count = 1 if match[3] is None else int(match[3])
            lines.update(range(start, start + count))
        return lines_by_file


# %% checking files


@dataclass(frozen=True)
class CodeRulesCheck:
    """
    Runs a set of checkers over a set of files.
    """

    checkers: tuple[CodeRuleChecker, ...]
    """
    The checkers to run.
    """

    staged: StagedLines | None = None
    """
    The staged change whose code alone is checked, ``None`` to check all of it.
    """

    def violations(self, paths: Sequence[Path]) -> list[CodeRuleViolation]:
        """
        :param paths: The Python files to check.
        :return: Their violations, file by file, top to bottom.
        """
        violations: list[CodeRuleViolation] = []
        for path in paths:
            changed = None if self.staged is None else self.staged.of(path)
            found = [
                violation
                for checker in self.checkers
                for violation in checker.violations(path)
                if changed is None or violation.touches(changed)
            ]
            violations.extend(sorted(found, key=lambda violation: violation.first_line))
        return violations
