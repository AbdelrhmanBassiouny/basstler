"""
The file versions and pull requests the review triage suites read.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any

from basstler.review_triage.comparison import FileChange

from ..constants.paths import DatasetLocation

# %% one file in two versions


class FileSample(StrEnum):
    """
    A file in a base and a head version, by the directory holding both.
    """

    BEHAVIOUR_CHANGED = "behaviour-changed"
    CODE_REFORMATTED = "code-reformatted"
    DOCSTRING_REFLOWED = "docstring-reflowed"
    DOCSTRING_REWORDED = "docstring-reworded"
    DOCUMENTATION_REFLOWED = "documentation-reflowed"
    DOCUMENTATION_RENAMED = "documentation-renamed"
    IDENTIFIER_RENAMED = "identifier-renamed"
    IMPORT_SOURCE_CHANGED = "import-source-changed"
    IMPORTS_REORDERED = "imports-reordered"
    STRING_LITERAL_RENAMED = "string-literal-renamed"

    @property
    def directory(self) -> Path:
        """
        The directory holding both versions.
        """
        return DatasetLocation.REVIEW_TRIAGE / self

    def change(self) -> FileChange:
        """
        :return: The change from the base to the head version, at a path with their
            suffix.
        """
        base = next(self.directory.glob("base.*"))
        head = next(self.directory.glob("head.*"))
        return FileChange(
            PurePosixPath(f"sample{base.suffix}"), base.read_text(), head.read_text()
        )


# %% pull request descriptions


class DescriptionSample(StrEnum):
    """
    A pull request description, by its file name.
    """

    DECLARING = "description.md"
    WITHOUT_DECLARATION = "description-without-declaration.md"
    REJECTING_RENAME = "description-rejecting-rename.md"

    def read(self) -> str:
        """
        :return: The description.
        """
        return (DatasetLocation.REVIEW_TRIAGE / self).read_text()


# %% the pull request


class PullRequestSample(StrEnum):
    """
    The parts of the sample pull request: its two trees, its REST payload and its
    report.
    """

    BASE_TREE = "base"
    HEAD_TREE = "head"
    PAYLOAD = "pull-request.json"
    REPORT = "report.md"

    @property
    def path(self) -> Path:
        """
        Where the part is.
        """
        return DatasetLocation.REVIEW_TRIAGE / "pull-request" / self

    def files(self) -> dict[Path, str]:
        """
        :return: The content of each file of this tree, by its path in the tree.
        """
        return {
            file.relative_to(self.path): file.read_text()
            for file in self.path.rglob("*")
            if file.is_file()
        }

    def payload(self) -> dict[str, Any]:
        """
        :return: The REST payload, parsed.
        """
        return json.loads(self.path.read_text())
