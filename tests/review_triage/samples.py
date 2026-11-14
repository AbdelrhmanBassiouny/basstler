"""
The file versions and pull requests the review triage suites read.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any

from basstler.class_property import classproperty
from basstler.review_triage.comparison import FileChange
from basstler.review_triage.definitions import DefinitionIndex, SourceDefinitions

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
    IDENTITY_DECORATOR_ADDED = "identity-decorator-added"
    IMPORT_SOURCE_CHANGED = "import-source-changed"
    IMPORTS_REORDERED = "imports-reordered"
    KEYWORD_ARGUMENTS_ADDED = "keyword-arguments-added"
    KEYWORD_ARGUMENTS_REORDERED = "keyword-arguments-reordered"
    KEYWORD_ARGUMENTS_SWAPPED = "keyword-arguments-swapped"
    KEYWORD_ARGUMENTS_UNKNOWN_CALLEE = "keyword-arguments-unknown-callee"
    KEYWORD_ONLY_PARAMETERS = "keyword-only-parameters"
    RELATIVE_IMPORT_MOVED = "relative-import-moved"
    STRING_LITERAL_RENAMED = "string-literal-renamed"
    TEMPLATE_RENAMED = "template-renamed"

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

    def base_definitions(self) -> DefinitionIndex:
        """
        :return: What the base version defines, as the base commit's definitions.
        """
        base = next(self.directory.glob("base.*"))
        return DefinitionIndex(SourceDefinitions((base.read_text(),)))


SIGNATURE_DEFINITIONS = DatasetLocation.REVIEW_TRIAGE / "signatures" / "definitions.py"
"""
The file whose definitions the signature suite reads.
"""


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


class SampleTrees(StrEnum):
    """
    The parts of a sample pull request kept in one directory, its two trees among them.
    """

    @classproperty
    def directory_name(cls) -> str:
        """
        The name of the directory holding the parts.
        """
        raise NotImplementedError

    @property
    def path(self) -> Path:
        """
        Where the part is.
        """
        return DatasetLocation.REVIEW_TRIAGE / self.directory_name / self

    def files(self) -> dict[Path, str]:
        """
        :return: The content of each file of this tree, by its path in the tree.
        """
        return {
            file.relative_to(self.path): file.read_text()
            for file in self.path.rglob("*")
            if file.is_file()
        }


class PullRequestSample(SampleTrees):
    """
    The parts of the sample pull request: its two trees, its REST payload and its
    report.
    """

    BASE_TREE = "base"
    HEAD_TREE = "head"
    PAYLOAD = "pull-request.json"
    REPORT = "report.md"

    @classproperty
    def directory_name(cls) -> str:
        return "pull-request"

    def payload(self) -> dict[str, Any]:
        """
        :return: The REST payload, parsed.
        """
        return json.loads(self.path.read_text())


# %% the module move


class ModuleMoveSample(SampleTrees):
    """
    A pull request moving a module into a subpackage and importing it from there.
    """

    BASE_TREE = "base"
    HEAD_TREE = "head"

    @classproperty
    def directory_name(cls) -> str:
        return "module-move"


# %% the definition move


class DefinitionMoveSample(SampleTrees):
    """
    A pull request moving classes out of a module that stays, into one that exists and
    one it adds, and importing them from there.
    """

    BASE_TREE = "base"
    HEAD_TREE = "head"

    @classproperty
    def directory_name(cls) -> str:
        return "definition-move"


TEMPLATE_REINDENTED = (
    DatasetLocation.REVIEW_TRIAGE / "template-renamed" / "reindented.py.jinja"
)
"""
The renamed template's head version, its renamed line also indented.
"""
