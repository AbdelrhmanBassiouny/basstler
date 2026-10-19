"""
Calls into the plugin's shell configuration, ``resolve-personal-notes-config.sh``.

The shell configuration is where the personal-notes remote and branch precedence is
decided. A module that needs one of its answers sources it and calls its function,
rather than re-deriving the precedence, so the module and the hook scripts can never
disagree. This is the one place that does so.
"""

from __future__ import annotations

import subprocess
from enum import StrEnum
from pathlib import Path

from basstler.locations import PluginLocation


class ShellConfigurationFunction(StrEnum):
    """
    The functions of the shell configuration this package calls.
    """

    FETCH_PERSONAL_NOTES_BRANCH = "fetch_personal_notes_branch"
    """
    Fetches the personal-notes branch, leaving ``FETCH_HEAD`` pointing at it.

    Falls back to the current branch's upstream remote when the configured one does not
    carry the branch.
    """

    BASSTLER_PACKAGE_SOURCE = "basstler_package_source"
    """
    Prints what the package is installed from: the checkout the plugin sits in, else its
    repository at the latest release a session start recorded.
    """

    def run(self, project_root: Path | None = None) -> subprocess.CompletedProcess[str]:
        """
        Source the shell configuration and call this function.

        :param project_root: The repository to run within; the current directory if not
            given.
        :return: The completed process, with output captured as text.
        """
        return subprocess.run(
            [
                "bash",
                "-c",
                f'source "{PluginLocation.PERSONAL_NOTES_CONFIGURATION_SCRIPT}" && {self}',
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
