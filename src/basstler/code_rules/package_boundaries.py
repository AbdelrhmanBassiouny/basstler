"""
Finds imports that cross from one distribution into another it does not list.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from basstler.code_rules.checker import CodeRuleChecker, CodeRuleViolation
from basstler.locations import PackageLocation
from basstler.package_map import PACKAGE_MAP, PackageMap

# %% crossings


@dataclass(frozen=True)
class BoundaryCrossing:
    """
    A module importing a module of a distribution its own distribution does not list.
    """

    importing_module: str
    """
    The dotted name, within ``basstler``, of the module holding the import.
    """

    imported_module: str
    """
    The dotted name, within ``basstler``, of the module it imports.
    """


@dataclass(frozen=True)
class KnownBoundaryCrossings:
    """
    The crossings the package held when the boundaries were declared, which are not
    reported until the code is moved.
    """

    crossings: frozenset[BoundaryCrossing]
    """
    The crossings not reported.
    """

    @classmethod
    def from_file(cls, path: Path) -> KnownBoundaryCrossings:
        """
        :param path: A YAML mapping of each importing module to the modules it imports
            across a boundary.
        :return: The crossings it lists.
        """
        listed: dict[str, list[str]] = yaml.safe_load(path.read_text()) or {}
        return cls(
            frozenset(
                BoundaryCrossing(importing_module, imported_module)
                for importing_module, imported_modules in listed.items()
                for imported_module in imported_modules
            )
        )


# %% the checker


@dataclass(frozen=True)
class PackageBoundaryChecker(CodeRuleChecker):
    """
    Reports a module no distribution claims, and an import of a distribution the
    importing module's distribution does not list.
    """

    package_map: PackageMap = PACKAGE_MAP
    """
    The distributions and the modules each one ships.
    """

    package_directory: Path = PackageLocation.DIRECTORY.value
    """
    The ``basstler`` package directory; files outside it are not checked.
    """

    known_crossings: KnownBoundaryCrossings = field(
        default_factory=lambda: KnownBoundaryCrossings.from_file(
            PackageLocation.KNOWN_BOUNDARY_CROSSINGS
        )
    )
    """
    The crossings not reported.
    """

    def violations(self, path: Path) -> Iterator[CodeRuleViolation]:
        module = self.module_name(path)
        if not module:
            return
        if self.package_map.claiming(module) is None:
            yield CodeRuleViolation(
                path,
                1,
                1,
                f"no distribution claims basstler.{module}; add it to the declaration of "
                "the distribution owning its subject in basstler.package_map",
            )
            return
        for crossing, statement in self.crossings(path):
            if crossing in self.known_crossings.crossings:
                continue
            importing = self.package_map.claiming(crossing.importing_module)
            imported = self.package_map.claiming(crossing.imported_module)
            yield CodeRuleViolation(
                path,
                statement.lineno,
                statement.end_lineno or statement.lineno,
                f"{importing.distribution} imports basstler.{crossing.imported_module} "
                f"from {imported.distribution}, which it does not list in "
                "basstler.package_map; move the code or the import",
            )

    def module_name(self, path: Path) -> str | None:
        """
        :param path: A Python source file.
        :return: Its dotted name within ``basstler``, empty for the package's own
            ``__init__``; none for a file outside :attr:`package_directory`.
        """
        source = path.resolve()
        directory = self.package_directory.resolve()
        if not source.is_relative_to(directory):
            return None
        parts = source.relative_to(directory).with_suffix("").parts
        return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)

    def crossings(self, path: Path) -> Iterator[tuple[BoundaryCrossing, ast.stmt]]:
        """
        :param path: A source file of a module some distribution claims.
        :return: Every import in it of a module of a distribution the module's own
            distribution does not list, with the statement holding the import.
        """
        module = self.module_name(path)
        importing = self.package_map.claiming(module)
        allowed = {importing.distribution, *importing.dependencies}
        for imported_module, statement in self.imported_modules(path):
            imported = self.package_map.claiming(imported_module)
            if imported is None or imported.distribution in allowed:
                continue
            yield BoundaryCrossing(module, imported_module), statement

    def imported_modules(self, path: Path) -> Iterator[tuple[str, ast.stmt]]:
        """
        :param path: A Python source file.
        :return: The dotted name within ``basstler`` of every module of the package it
            imports, with the statement importing it.
        """
        for statement in ast.walk(ast.parse(path.read_text())):
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    root, _, module = alias.name.partition(".")
                    if root == PackageLocation.DIRECTORY.name and module:
                        yield module, statement
            if isinstance(statement, ast.ImportFrom) and statement.level == 0:
                root, _, package = (statement.module or "").partition(".")
                if root == PackageLocation.DIRECTORY.name:
                    for alias in statement.names:
                        yield self.imported_name(package, alias.name), statement

    def imported_name(self, package: str, name: str) -> str:
        """
        :param package: The dotted name within ``basstler`` a ``from`` import reads from.
        :param name: A name it imports.
        :return: The module *name* is, when it is one, else *package*.
        """
        candidate = ".".join(part for part in (package, name) if part)
        location = self.package_directory.joinpath(*candidate.split("."))
        if location.is_dir() or location.with_suffix(".py").is_file():
            return candidate
        return package
