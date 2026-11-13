"""
The base every code rule checker extends, and the violations checkers report.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
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
            changes.
        """
        diff = self.git.run(
            "diff", "--cached", "--unified=0", "--no-color", "--", str(path)
        )
        lines: set[int] = set()
        for hunk in re.finditer(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", diff, re.MULTILINE):
            start = int(hunk[1])
            count = 1 if hunk[2] is None else int(hunk[2])
            lines.update(range(start, start + count))
        return lines


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
