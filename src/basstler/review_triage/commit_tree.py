"""
The files of one commit, searched for identifiers, files and definitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from enum import IntEnum
from pathlib import PurePosixPath

from basstler.maintenance.git_commands import GitCommandResult, GitCommandRunner
from basstler.review_triage.definitions import DefinitionSearch
from basstler.review_triage.renames import DOTTED_NAME_SEPARATOR

# %% git's answers


class GitGrepExitCode(IntEnum):
    """
    What ``git grep`` exits with.
    """

    MATCH = 0
    """
    At least one line matched.
    """

    NO_MATCH = 1
    """
    Nothing matched.
    """


PYTHON_FILE_PATTERNS = ("*.py", "*.pyi")
"""
The path patterns of the Python files a definition is searched in.
"""

DEFINITION_PATTERN = (
    r"^[[:space:]]*(async[[:space:]]+)?(def|class)[[:space:]]+[A-Za-z_][A-Za-z0-9_]*"
)
"""
Matches the start of a line defining a function, method or class, up to its name.
"""


PACKAGE_INITIALIZER = "__init__.py"
"""
The file that makes a directory a package, its own module the package's.
"""

MODULE_SUFFIX = ".py"
"""
The suffix of a Python module's file.
"""


# %% the commit


@dataclass(frozen=True)
class CommitTree(DefinitionSearch):
    """
    The files of one commit.
    """

    git: GitCommandRunner
    """
    The checkout holding the commit.
    """

    commit: str
    """
    The commit searched.
    """

    def mentions(self, identifier: str) -> bool:
        """
        :param identifier: A name, or a dotted path of names.
        :return: Whether any file of the commit holds it as a whole word.
        :raises GitCommandFailed: If the search itself fails.
        """
        search = self.git.attempt(
            "grep",
            "--quiet",
            "--word-regexp",
            "--fixed-strings",
            "-e",
            identifier,
            self.commit,
        )
        if search.exit_status == GitGrepExitCode.NO_MATCH:
            return False
        return search.raise_if_failed().succeeded

    def holds(self, path: PurePosixPath) -> bool:
        """
        :param path: A path from the commit's root.
        :return: Whether the commit has a file there.
        """
        return self.git.attempt("cat-file", "-e", f"{self.commit}:{path}").succeeded

    def module_path(self, path: PurePosixPath) -> str:
        """
        :param path: A module's file.
        :return: The dotted path the module is imported by, through every enclosing
            directory that is a package.
        """
        components = [] if path.name == PACKAGE_INITIALIZER else [path.stem]
        package = path.parent
        while package != PurePosixPath(".") and self.holds(
            package / PACKAGE_INITIALIZER
        ):
            components.insert(0, package.name)
            package = package.parent
        return DOTTED_NAME_SEPARATOR.join(components)

    @cached_property
    def definition_files(self) -> dict[str, tuple[str, ...]]:
        """
        The files defining a function, method or class of each name, listed by one
        search of the whole commit.

        :raises GitCommandFailed: If the search itself fails.
        """
        search = self.git.attempt(
            "grep",
            "--only-matching",
            "--extended-regexp",
            "-e",
            DEFINITION_PATTERN,
            self.commit,
            "--",
            *PYTHON_FILE_PATTERNS,
        )
        files: dict[str, dict[str, None]] = {}
        for line in self.listed_lines(search):
            file, definition = line.rsplit(":", 1)
            files.setdefault(definition.split()[-1], {})[file] = None
        return {name: tuple(listed) for name, listed in files.items()}

    def files_defining(self, names: frozenset[str]) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                file for name in names for file in self.definition_files.get(name, ())
            )
        )

    def files_mentioning(self, name: str) -> tuple[str, ...]:
        return self.listed_lines(
            self.git.attempt(
                "grep",
                "--name-only",
                "--word-regexp",
                "--fixed-strings",
                "-e",
                name,
                self.commit,
                "--",
                *PYTHON_FILE_PATTERNS,
            )
        )

    def text_of(self, file: str) -> str:
        return self.git.run("show", file)

    @staticmethod
    def listed_lines(search: GitCommandResult) -> tuple[str, ...]:
        """
        :param search: A finished ``git grep``.
        :return: The lines it printed, none when nothing matched.
        :raises GitCommandFailed: If the search itself failed.
        """
        if search.exit_status == GitGrepExitCode.NO_MATCH:
            return ()
        return tuple(search.raise_if_failed().output.splitlines())
