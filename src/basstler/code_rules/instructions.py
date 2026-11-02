"""
Generates the repository's ``AGENTS.md`` from the rules it declares.

Copied from krrood :cite:`krrood` (``krrood.development_tools.agents.instructions``)
until krrood's light core is released.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from basstler.code_rules import rules
from basstler.code_rules.commands import CodeRulesCommand
from basstler.code_rules.rule import Section
from basstler.code_rules.rule_module import RuleModule
from basstler.locations import InstructionsTemplate, ProjectLocation
from basstler.render_common import create_template_environment


@dataclass
class AgentsInstructions:
    """
    The ``AGENTS.md`` of one repository, listing the rules of the given sections.
    """

    repository_root: Path
    """
    The directory holding the repository's ``AGENTS.md``.
    """

    sections: list[type[Section]]
    """
    The top-level sections the file lists, each with the sections nested under it.
    """

    @classmethod
    def of_repository(cls, repository_root: Path) -> AgentsInstructions:
        """
        :param repository_root: The directory holding the repository's ``AGENTS.md``.
        :return: The file listing the sections of :mod:`basstler.code_rules.rules`.
        """
        return cls(repository_root, RuleModule(rules).sections)

    @property
    def path(self) -> Path:
        """
        The path of the repository's ``AGENTS.md``.
        """
        return self.repository_root / ProjectLocation.AGENTS_INSTRUCTIONS

    @property
    def text(self) -> str:
        """
        The content ``AGENTS.md`` must have: the rules of :attr:`sections`, under their
        headings, in the order they are declared.
        """
        template = create_template_environment().get_template(
            InstructionsTemplate.AGENTS.name
        )
        return template.render(
            sections=self.sections,
            generate_command=CodeRulesCommand.AGENTS_MD.invocation,
            check_command=CodeRulesCommand.CHECK.invocation,
        )

    def is_current(self) -> bool:
        """
        :return: Whether ``AGENTS.md`` exists and equals :attr:`text`.
        """
        if not self.path.is_file():
            return False
        return self.path.read_text(encoding="utf-8") == self.text

    def write(self) -> None:
        """
        Write ``AGENTS.md``, replacing whatever it held.
        """
        self.path.write_text(self.text, encoding="utf-8")
