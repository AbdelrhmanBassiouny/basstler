"""
A ``pyproject.toml``'s ``[project]`` table, read or written by a test, and the build
backend's version source, read by one.

The suites both read the package's own declaration back and write declarations of their
own into a scratch clone, so the table's keys and its access path live here once rather
than at every use site.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from basstler.dependencies import PyprojectKey
from basstler.locations import PackageLocation

from .constants import HatchVersionKey, ProjectTableKey, RepositoryLocation


@dataclass(frozen=True)
class ProjectDeclaration:
    """
    The parts of a ``[project]`` table the suites read or write.
    """

    name: str
    """
    The distribution name.
    """

    dependencies: tuple[str, ...] = ()
    """
    The requirement specifiers, in the order the table states them.
    """

    requires_python: str | None = None
    """
    The interpreters the project supports, when the table states them.
    """

    dynamic: tuple[str, ...] = ()
    """
    The keys left for the build backend to resolve.
    """

    @classmethod
    def read(cls, path: Path) -> ProjectDeclaration:
        """
        :param path: A ``pyproject.toml``.
        :return: Its ``[project]`` table.
        """
        table = tomllib.loads(path.read_text())[PyprojectKey.PROJECT]
        return cls(
            name=table[PyprojectKey.NAME],
            dependencies=tuple(table.get(PyprojectKey.DEPENDENCIES, ())),
            requires_python=table.get(ProjectTableKey.REQUIRES_PYTHON),
            dynamic=tuple(table.get(ProjectTableKey.DYNAMIC, ())),
        )

    @classmethod
    def of_this_package(cls) -> ProjectDeclaration:
        """
        :return: The package's own ``[project]`` table, read straight from its source.
        """
        return cls.read(PackageLocation.DEPENDENCY_DECLARATION.value)

    def as_toml(self) -> str:
        """
        :return: A ``pyproject.toml`` holding this table's name, dependencies and
            interpreter requirement.
        """
        # A JSON string or list of strings is also a TOML one.
        lines = [
            f"[{PyprojectKey.PROJECT}]",
            f"{PyprojectKey.NAME} = {json.dumps(self.name)}",
            f"{PyprojectKey.DEPENDENCIES} = {json.dumps(list(self.dependencies))}",
        ]
        if self.requires_python is not None:
            lines.append(
                f"{ProjectTableKey.REQUIRES_PYTHON} = "
                f"{json.dumps(self.requires_python)}"
            )
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class HatchVersionSource:
    """
    Where a ``pyproject.toml`` tells hatchling to read the version from.
    """

    path: Path
    """
    The file the version is read out of.
    """

    pattern: str
    """
    The regular expression whose ``version`` group is the version.
    """

    @classmethod
    def read(cls, path: Path, root: Path) -> HatchVersionSource:
        """
        :param path: A ``pyproject.toml``.
        :param root: The directory the source's path is relative to.
        :return: Its ``[tool.hatch.version]`` table.
        """
        table = HatchVersionKey.version_table(tomllib.loads(path.read_text()))
        return cls(
            path=root / table[HatchVersionKey.PATH],
            pattern=table[HatchVersionKey.PATTERN],
        )

    @classmethod
    def of_this_package(cls) -> HatchVersionSource:
        """
        :return: The package's own version source, read straight from its source.
        """
        return cls.read(
            PackageLocation.DEPENDENCY_DECLARATION.value, RepositoryLocation.ROOT
        )

    def version(self) -> str | None:
        """
        :return: The version the build reads, or ``None`` if the pattern matches nothing.
        """
        found = re.search(self.pattern, self.path.read_text())
        return found.group(HatchVersionKey.VERSION) if found else None
