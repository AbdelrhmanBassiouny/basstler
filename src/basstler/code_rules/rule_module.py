"""
The modules that declare sections of ``AGENTS.md``.

Copied from krrood :cite:`krrood` (``krrood.development_tools.agents.rule_module``)
until krrood's light core is released.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from types import ModuleType

from basstler.code_rules.checker import CodeRuleChecker
from basstler.code_rules.rule import Section


@dataclass(frozen=True)
class RuleModule:
    """
    A module, or a package with all of its modules, declaring sections of ``AGENTS.md``.
    """

    module: ModuleType
    """
    The module or package.
    """

    @property
    def modules(self) -> list[ModuleType]:
        """
        The module itself and, for a package, every module in it, imported.
        """
        if self.module.__spec__.submodule_search_locations is None:
            return [self.module]
        return [self.module] + [
            importlib.import_module(submodule.name)
            for submodule in pkgutil.walk_packages(
                self.module.__path__, f"{self.module.__name__}."
            )
        ]

    @property
    def sections(self) -> list[type[Section]]:
        """
        The top-level sections defined in :attr:`modules`, in alphabetical order of
        their titles.

        Sections a module only imports are not among them.
        """
        sections = [
            value
            for module in self.modules
            for value in vars(module).values()
            if isinstance(value, type)
            and issubclass(value, Section)
            and value.__module__ == module.__name__
            and value.parent is None
        ]
        return sorted(sections, key=lambda section: section.title)

    @property
    def checkers(self) -> tuple[CodeRuleChecker, ...]:
        """
        The checker of every rule in :attr:`sections` and the sections nested in them.
        """
        return tuple(
            rule.checker
            for top_level_section in self.sections
            for section in top_level_section.descendants
            for rule in section
            if rule.checker is not None
        )
