"""
Report docstrings and comment blocks whose prose runs longer than a line limit.

Usage:
    python -m basstler.prose_length [--all] [--docstring-lines <count>] \\
        [--comment-lines <count>] <file>...
"""

from __future__ import annotations

import argparse
import ast
import inspect
import io
import re
import sys
import tokenize
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from basstler.maintenance.git_commands import GitCommandRunner
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% what is measured


class ProseKind(StrEnum):
    """
    The kinds of prose measured.
    """

    DOCSTRING = "docstring"
    COMMENT = "comment block"


FIELD_LIST_ITEM = re.compile(r"^:[^:\s][^:]*:")
"""
A reStructuredText field such as ``:param name:``, which starts a docstring's field list.
"""

SECTION_HEADER = "# %%"
"""
The start of a section header comment, which is a label, not prose.
"""

TOOL_DIRECTIVE = re.compile(r"^#\s*(noqa|type:|pragma|fmt:|ruff:|!|-\*-)")
"""
A comment addressed to a tool rather than a reader.
"""


@dataclass(frozen=True)
class ProseBlock:
    """
    One docstring or run of comment lines in a source file.
    """

    kind: ProseKind

    first_line: int
    """
    The block's first line in the file, counting from one.
    """

    last_line: int
    """
    The block's last line in the file, counting from one.
    """

    prose_lines: int
    """
    How many of its lines are prose: for a docstring, the non-blank lines before its
    field list that are not indented below its own margin, such as a literal block.
    """

    def touches(self, lines: set[int]) -> bool:
        """
        :param lines: Line numbers in the file.
        :return: Whether any of them falls within the block.
        """
        return any(self.first_line <= line <= self.last_line for line in lines)


@dataclass(frozen=True)
class SourceProse:
    """
    The docstrings and comment blocks of one Python source.
    """

    source: str

    @property
    def blocks(self) -> list[ProseBlock]:
        """:return: Every docstring and comment block, in no particular order."""
        return [*self.docstrings(), *self.comment_blocks()]

    def docstrings(self) -> Iterator[ProseBlock]:
        """
        :return: The docstring of the module and of every class and function, and every
            attribute docstring directly below an assignment in a module or class body.
        """
        for node in ast.walk(ast.parse(self.source)):
            if not isinstance(
                node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
            ):
                continue
            for index, statement in enumerate(node.body):
                if not self.is_string(statement):
                    continue
                follows_assignment = index > 0 and isinstance(
                    node.body[index - 1], ast.Assign | ast.AnnAssign
                )
                if index == 0 or (
                    follows_assignment and isinstance(node, ast.Module | ast.ClassDef)
                ):
                    yield self.docstring_block(statement)

    @staticmethod
    def is_string(statement: ast.stmt) -> bool:
        """:return: Whether *statement* is a bare string literal."""
        return (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        )

    @staticmethod
    def docstring_block(statement: ast.Expr) -> ProseBlock:
        """
        :param statement: A bare string literal.
        :return: It, measured as a docstring.
        """
        prose_lines = 0
        for line in inspect.cleandoc(statement.value.value).splitlines():
            if FIELD_LIST_ITEM.match(line):
                break
            if line.strip() and not line[0].isspace():
                prose_lines += 1
        return ProseBlock(
            ProseKind.DOCSTRING, statement.lineno, statement.end_lineno, prose_lines
        )

    def comment_blocks(self) -> Iterator[ProseBlock]:
        """
        :return: Every run of consecutive lines holding only a comment, section headers
            and comments addressed to tools left out.
        """
        lines: list[int] = []
        for token in tokenize.generate_tokens(io.StringIO(self.source).readline):
            if token.type != tokenize.COMMENT or token.line.strip() != token.string:
                continue
            if token.string.startswith(SECTION_HEADER) or TOOL_DIRECTIVE.match(
                token.string
            ):
                continue
            if lines and token.start[0] != lines[-1] + 1:
                yield ProseBlock(ProseKind.COMMENT, lines[0], lines[-1], len(lines))
                lines = []
            lines.append(token.start[0])
        if lines:
            yield ProseBlock(ProseKind.COMMENT, lines[0], lines[-1], len(lines))


# %% the limits


@dataclass(frozen=True)
class ProseLimits:
    """
    The most prose lines each kind of block may hold.
    """

    docstring_lines: int = 4
    comment_lines: int = 3

    def limit_for(self, kind: ProseKind) -> int:
        """:return: The most prose lines a block of *kind* may hold."""
        return (
            self.docstring_lines if kind is ProseKind.DOCSTRING else self.comment_lines
        )


@dataclass(frozen=True)
class OverlongProse:
    """
    A block holding more prose lines than its limit.
    """

    path: Path
    block: ProseBlock
    limit: int

    def render(self) -> str:
        """:return: The finding as it is printed."""
        return (
            f"{self.path}:{self.block.first_line}: {self.block.kind} has "
            f"{self.block.prose_lines} lines of prose, more than {self.limit}; "
            "shorten it"
        )


# %% the check


@dataclass(frozen=True)
class StagedLines:
    """
    The lines a commit being prepared adds or changes.
    """

    git: GitCommandRunner

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


@dataclass(frozen=True)
class ProseLengthCheck:
    """
    Finds the overlong blocks of a set of files.
    """

    limits: ProseLimits = field(default_factory=ProseLimits)

    staged: StagedLines | None = None
    """
    The staged change whose blocks alone are checked, ``None`` to check every block.
    """

    def findings(self, paths: Sequence[Path]) -> list[OverlongProse]:
        """
        :param paths: The Python files to check.
        :return: Their overlong blocks, file by file, top to bottom.
        """
        findings: list[OverlongProse] = []
        for path in paths:
            changed = None if self.staged is None else self.staged.of(path)
            blocks = SourceProse(path.read_text()).blocks
            for block in sorted(blocks, key=lambda block: block.first_line):
                limit = self.limits.limit_for(block.kind)
                if block.prose_lines <= limit:
                    continue
                if changed is None or block.touches(changed):
                    findings.append(OverlongProse(path, block, limit))
        return findings


# %% command line


class ProseLengthOption(StrEnum):
    """
    Every option the command takes.
    """

    ALL = "--all"
    """
    Check every block, not only those the staged change touches.
    """

    DOCSTRING_LINES = "--docstring-lines"
    """
    The most prose lines a docstring may hold.
    """

    COMMENT_LINES = "--comment-lines"
    """
    The most lines a comment block may hold.
    """


def main(argv: list[str] | None = None) -> int:
    """
    Check the given files. See the module docstring.

    :param argv: The arguments to parse, defaulting to the process's own.
    :return: 0 when nothing is overlong, 1 otherwise.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(ProseLengthOption.ALL, action="store_true")
    parser.add_argument(
        ProseLengthOption.DOCSTRING_LINES, type=int, default=ProseLimits.docstring_lines
    )
    parser.add_argument(
        ProseLengthOption.COMMENT_LINES, type=int, default=ProseLimits.comment_lines
    )
    parser.add_argument("paths", nargs="*", type=Path)
    arguments = parser.parse_args(argv)
    check = ProseLengthCheck(
        ProseLimits(arguments.docstring_lines, arguments.comment_lines),
        None if arguments.all else StagedLines(GitCommandRunner(Path.cwd())),
    )
    findings = check.findings(arguments.paths)
    for finding in findings:
        logger.error(finding.render())
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
