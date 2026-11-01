"""
The files a plan's dashboard Artifact is written as.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from basstler.locations import DashboardArtifactFile

# %% the written files


@dataclass(frozen=True)
class DashboardArtifact:
    """
    A plan's dashboard as the files its Artifact is published as.
    """

    files: dict[DashboardArtifactFile, str]
    """
    Each published file's content.
    """

    def write_to(self, directory: Path) -> None:
        """
        Write every file at its published path under ``directory``.

        :param directory: An existing directory.
        """
        for file, content in self.files.items():
            (directory / file).write_text(content)
