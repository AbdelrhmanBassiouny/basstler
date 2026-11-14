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

    CROSSINGS = "crossings"
    """
    List every import that crosses a distribution boundary.
    """

    NEW_CROSSINGS = "new-crossings"
    """
    Report the boundary crossings a base commit does not have.
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
