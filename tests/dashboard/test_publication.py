"""
Tests for :mod:`basstler.dashboard.publication`: the files a dashboard is written as.
"""

from __future__ import annotations

from pathlib import Path

from basstler.dashboard.publication import DashboardArtifact
from basstler.locations import DashboardArtifactFile


def artifact(**contents: str) -> DashboardArtifact:
    """
    :param contents: Each file's content, by the member name of its
        :class:`DashboardArtifactFile`; a file not named is empty.
    :return: The artifact made of those files.
    """
    return DashboardArtifact(
        files={file: contents.get(file._name_, "") for file in DashboardArtifactFile}
    )


# %% the written files


def test_writing_puts_every_file_at_its_published_path(tmp_path: Path):
    written = artifact(PAGE="page", STYLE="style", SCRIPT="script", CONTENT="content")
    written.write_to(tmp_path)
    assert {
        file: (tmp_path / file).read_text() for file in DashboardArtifactFile
    } == written.files
