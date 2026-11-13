"""
Judging one file's change: mechanical when the head version equals the base version
once the allowed transformations are undone, otherwise in need of review.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePosixPath

from basstler.class_property import classproperty
from basstler.review_triage.python_source import PythonSource
from basstler.review_triage.renames import RenameMap

# %% what a mechanical change consists of


class MechanicalChange(StrEnum):
    """
    A kind of change that cannot alter what a file does or says.
    """

    MOVE = "move"
    """
    The file was moved to another path.
    """

    IMPORTS = "imports"
    """
    Imports were added, removed or reordered, each name both versions import still bound
    to the same thing.
    """

    RENAME = "rename"
    """
    Identifiers the pull request renames throughout were replaced, in code, docstrings
    or comments.
    """

    FORMATTING = "formatting"
    """
    Only the layout of code, docstrings or comments changed.
    """


ChangeKinds = frozenset[MechanicalChange]
"""
The kinds of change one comparison found.
"""

NO_CHANGE: ChangeKinds = frozenset()
"""
The kinds of change of two versions that are equal.
"""


# %% one file's change


@dataclass(frozen=True)
class FileChange:
    """
    One file a pull request changes, in both its versions.
    """

    path: PurePosixPath
    """
    Where the file is in the head commit, or was in the base commit when it is deleted.
    """

    base_text: str | None
    """
    The file's content in the base commit, ``None`` when the pull request adds it.
    """

    head_text: str | None
    """
    The file's content in the head commit, ``None`` when the pull request deletes it.
    """

    previous_path: PurePosixPath | None = None
    """
    Where the file was in the base commit, when the pull request moves it.
    """

    is_binary: bool = False
    """
    Whether git compares the file as binary, which leaves both texts unread.
    """


@dataclass(frozen=True)
class FileTriage(ABC):
    """
    The verdict on one changed file.
    """

    change: FileChange
    """
    The change judged.
    """


@dataclass(frozen=True)
class MechanicalFile(FileTriage):
    """
    A file whose change is provably mechanical, so a reviewer need not read it.
    """

    kinds: ChangeKinds = NO_CHANGE
    """
    What the change consists of.
    """


@dataclass(frozen=True)
class FileNeedingReview(FileTriage):
    """
    A file whose change could not be shown to be mechanical.
    """


# %% comparing the content of two versions


class ContentComparison(ABC):
    """
    Compares two versions of the files of one type.
    """

    @classproperty
    @abstractmethod
    def suffixes(cls) -> frozenset[str]:
        """
        The file name suffixes of the files this comparison reads.
        """

    @abstractmethod
    def changes(
        self, base_text: str, head_text: str, renames: RenameMap
    ) -> ChangeKinds | None:
        """
        :param base_text: The file's content in the base commit.
        :param head_text: The file's content in the head commit.
        :param renames: The renames the pull request makes throughout.
        :return: What the change consists of, ``None`` when it is not provably
            mechanical.
        """


class ProseComparison(ContentComparison):
    """
    Compares prose: documentation files, docstrings and comments.
    """

    @classproperty
    def suffixes(cls) -> frozenset[str]:
        return frozenset({".md", ".rst", ".txt"})

    def changes(
        self, base_text: str, head_text: str, renames: RenameMap
    ) -> ChangeKinds | None:
        if base_text == head_text:
            return NO_CHANGE
        renamed = renames.renamed_prose(base_text)
        if renamed == head_text:
            return frozenset({MechanicalChange.RENAME})
        if base_text.split() == head_text.split():
            return frozenset({MechanicalChange.FORMATTING})
        if renamed.split() == head_text.split():
            return frozenset({MechanicalChange.RENAME, MechanicalChange.FORMATTING})
        return None


@dataclass(frozen=True)
class PythonComparison(ContentComparison):
    """
    Compares Python files by their syntax trees, their imports, their docstrings and
    their comments.
    """

    prose: ProseComparison = field(default_factory=ProseComparison)
    """
    How the docstrings and comments are compared.
    """

    @classproperty
    def suffixes(cls) -> frozenset[str]:
        return frozenset({".py", ".pyi"})

    def changes(
        self, base_text: str, head_text: str, renames: RenameMap
    ) -> ChangeKinds | None:
        base = PythonSource(base_text)
        head = PythonSource(head_text)
        kinds: set[MechanicalChange] = set()
        head_code = head.code(RenameMap())
        if base.code(RenameMap()) != head_code:
            if base.code(renames) != head_code:
                return None
            kinds.add(MechanicalChange.RENAME)
        head_imports = head.imports(RenameMap())
        if base.imports(RenameMap()) != head_imports:
            if not base.imports(renames).agrees_with(head_imports):
                return None
            kinds.add(MechanicalChange.IMPORTS)
        prose_pairs = [
            *zip(base.documentation, head.documentation, strict=True),
            (base.comments, head.comments),
        ]
        for base_prose, head_prose in prose_pairs:
            prose_kinds = self.prose.changes(base_prose, head_prose, renames)
            if prose_kinds is None:
                return None
            kinds |= prose_kinds
        if not kinds and base_text != head_text:
            kinds.add(MechanicalChange.FORMATTING)
        return frozenset(kinds)


# %% judging a file


@dataclass(frozen=True)
class FileTriager:
    """
    Judges each changed file by the comparison of its type.
    """

    renames: RenameMap
    """
    The renames the pull request makes throughout.
    """

    comparisons: tuple[ContentComparison, ...] = (
        PythonComparison(),
        ProseComparison(),
    )
    """
    The comparisons by file type; a file of any other type is mechanical only when
    its content is unchanged.
    """

    def triage(self, change: FileChange) -> FileTriage:
        """
        :param change: A file the pull request changes.
        :return: Whether a reviewer has to read it.
        """
        if change.is_binary or change.base_text is None or change.head_text is None:
            return FileNeedingReview(change)
        kinds = self.content_changes(change)
        if kinds is None:
            return FileNeedingReview(change)
        if change.previous_path is not None:
            kinds |= {MechanicalChange.MOVE}
        return MechanicalFile(change, kinds)

    def content_changes(self, change: FileChange) -> ChangeKinds | None:
        """
        :param change: A file the pull request changes, in both versions.
        :return: What its content change consists of, ``None`` when it is not provably
            mechanical.
        """
        if change.base_text == change.head_text:
            return NO_CHANGE
        for comparison in self.comparisons:
            if change.path.suffix in comparison.suffixes:
                return comparison.changes(
                    change.base_text, change.head_text, self.renames
                )
        return None
