"""
The names of the ``basstler code-rules`` commands.
"""

from __future__ import annotations

from enum import StrEnum

from basstler.locations import PackageLocation


class CodeRulesCommand(StrEnum):
    """
    The ``basstler code-rules`` command group and its commands, by name.
    """

    GROUP = "code-rules"
    """
    The command group itself.
    """

    CHECK = "check"
    """
    Report the code that breaks a rule a checker enforces.
    """

    AGENTS_MD = "agents-md"
    """
    Generate the repository's ``AGENTS.md`` from its rules.
    """

    @property
    def invocation(self) -> str:
        """
        The command line running this command.
        """
        return f"{PackageLocation.DIRECTORY.name} {CodeRulesCommand.GROUP} {self}"
