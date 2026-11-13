"""
Finds imports that cross from one distribution into another it does not list.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from basstler.code_rules.checker import CodeRuleChecker, CodeRuleViolation
from basstler.json_model import ValidatedJSONModel
from basstler.locations import PackageLocation
from basstler.package_map import PACKAGE_MAP, PackageMap

# %% imports


@dataclass(frozen=True)
class ModuleImport:
    """
    One module of the package that an import statement imports, with the statement.
    """

    imported_module: str
    """
    The dotted name, within ``basstler``, of the module imported.
    """

    statement: ast.Import | ast.ImportFrom
    """
    The import statement.
    """


class BoundaryCrossing(ValidatedJSONModel):
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


class PackageCrossings(ValidatedJSONModel):
    """
    Every boundary crossing of one checkout of the package.
    """

    crossings: tuple[BoundaryCrossing, ...]
    """
    The crossings, each once, ordered by importing and then imported module.
    """

    def added_since(self, base: PackageCrossings) -> tuple[BoundaryCrossing, ...]:
        """
        :param base: The crossings of the checkout this one is compared with.
        :return: The crossings this checkout has and *base* does not.
        """
        return tuple(
            crossing for crossing in self.crossings if crossing not in base.crossings
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
        importing = self.package_map.claiming(module)
        for crossing in self.crossings(path):
            imported = self.package_map.claiming(crossing.imported_module)
            yield CodeRuleViolation(
                path,
                crossing.statement.lineno,
                crossing.statement.end_lineno or crossing.statement.lineno,
                f"{importing.distribution} imports basstler.{crossing.imported_module} "
                f"from {imported.distribution}, which it does not list in "
                "basstler.package_map; move the code or the import",
            )

    def package_crossings(self) -> PackageCrossings:
        """
        :return: The crossings of every module in :attr:`package_directory`.
        """
        crossings = {
            BoundaryCrossing(
                importing_module=module, imported_module=crossing.imported_module
            )
            for path in self.package_directory.rglob("*.py")
            if (module := self.module_name(path))
            and self.package_map.claiming(module) is not None
            for crossing in self.crossings(path)
        }
        return PackageCrossings(
            crossings=tuple(
                sorted(
                    crossings,
                    key=lambda crossing: (
                        crossing.importing_module,
                        crossing.imported_module,
                    ),
                )
            )
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

    def crossings(self, path: Path) -> Iterator[ModuleImport]:
        """
        :param path: A source file of a module some distribution claims.
        :return: Every import in it of a module of a distribution the module's own
            distribution does not list.
        """
        importing = self.package_map.claiming(self.module_name(path))
        allowed = {importing.distribution, *importing.dependencies}
        for module_import in self.module_imports(path):
            imported = self.package_map.claiming(module_import.imported_module)
            if imported is None or imported.distribution in allowed:
                continue
            yield module_import

    def module_imports(self, path: Path) -> Iterator[ModuleImport]:
        """
        :param path: A Python source file.
        :return: Every import in it of a module of the package.
        """
        for statement in ast.walk(ast.parse(path.read_text())):
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    root, _, module = alias.name.partition(".")
                    if root == PackageLocation.DIRECTORY.name and module:
                        yield ModuleImport(module, statement)
            if isinstance(statement, ast.ImportFrom) and statement.level == 0:
                root, _, package = (statement.module or "").partition(".")
                if root == PackageLocation.DIRECTORY.name:
                    for alias in statement.names:
                        yield ModuleImport(
                            self.imported_name(package, alias.name), statement
                        )

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
