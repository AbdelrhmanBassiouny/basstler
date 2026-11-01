"""
A ``pyproject.toml``'s ``[project]`` table, read or written by a test, and the build
backend's version source, read by one.

The suites both read the package's own declaration back and write declarations of their
own into a scratch clone, so the table's keys and its access path live here once rather
than at every use site.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from basstler.setup.dependencies import PyprojectKey
from basstler.locations import PackageLocation


class ProjectTableKey(StrEnum):
    """
    The ``[project]`` keys the suites read that
    :class:`basstler.setup.dependencies.PyprojectKey` does not name, since the package
    itself never reads them.
    """

    REQUIRES_PYTHON = "requires-python"
    """
    The version specifier an interpreter has to satisfy.
    """

    DYNAMIC = "dynamic"
    """
    The keys the build backend resolves rather than the table stating them.
    """


class HatchVersionKey(StrEnum):
    """
    The path through ``pyproject.toml`` to the build's version source, and that source's
    keys.
    """

    TOOL = "tool"
    """
    The table every tool's settings sit under.
    """

    HATCH = "hatch"
    """
    The build backend's own table.
    """

    VERSION = "version"
    """
    The table telling the backend where the version comes from.
    """

    SOURCE = "source"
    """
    The version source plugin the backend reads the version through.
    """

    FALLBACK_VERSION = "fallback-version"
    """
    The version a source with no git history builds as.
    """

    @classmethod
    def version_table(cls, pyproject: dict[str, Any]) -> dict[str, str]:
        """
        :param pyproject: A parsed ``pyproject.toml``.
        :return: Its ``[tool.hatch.version]`` table.
        """
        return pyproject[cls.TOOL][cls.HATCH][cls.VERSION]


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

    source: str
    """
    The version source plugin, e.g. ``vcs`` for the latest git tag.
    """

    fallback_version: str | None
    """
    The version a source with no git history builds as, if one is set.
    """

    @classmethod
    def read(cls, path: Path) -> HatchVersionSource:
        """
        :param path: A ``pyproject.toml``.
        :return: Its ``[tool.hatch.version]`` table.
        """
        table = HatchVersionKey.version_table(tomllib.loads(path.read_text()))
        return cls(
            source=table[HatchVersionKey.SOURCE],
            fallback_version=table.get(HatchVersionKey.FALLBACK_VERSION),
        )

    @classmethod
    def of_this_package(cls) -> HatchVersionSource:
        """
        :return: The package's own version source, read straight from its source.
        """
        return cls.read(PackageLocation.DEPENDENCY_DECLARATION.value)
