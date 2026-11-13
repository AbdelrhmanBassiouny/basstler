"""
Judging one file's change: mechanical when a judgment proves it cannot alter what the
file does or says, otherwise in need of review.
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


class ChangeKind(StrEnum):
    """
    The base of every enumeration of mechanical change kinds; an extension declares
    its own kinds by subclassing it.
    """


class MechanicalChange(ChangeKind):
    """
    The kinds of mechanical change the built-in judgments find.
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


ChangeKinds = frozenset[ChangeKind]
"""
The kinds of change one judgment found.
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
    The file's content in the base commit, ``None`` when it is added or binary.
    """

    head_text: str | None
    """
    The file's content in the head commit, ``None`` when it is deleted or binary.
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


# %% judgments


class FileJudgment(ABC):
    """
    Decides whether the change of the files it applies to is mechanical.
    """

    @abstractmethod
    def applies_to(self, change: FileChange) -> bool:
        """
        :param change: A file the pull request changes.
        :return: Whether this judgment decides it.
        """

    @abstractmethod
    def changes(self, change: FileChange, renames: RenameMap) -> ChangeKinds | None:
        """
        :param change: A file this judgment applies to.
        :param renames: The renames the pull request makes throughout.
        :return: What the change consists of, ``None`` when it is not provably
            mechanical.
        """


class ContentComparison(FileJudgment, ABC):
    """
    Compares both text versions of the files whose name has one of its suffixes.
    """

    @classproperty
    @abstractmethod
    def suffixes(cls) -> frozenset[str]:
        """
        The file name suffixes of the files this comparison reads.
        """

    @abstractmethod
    def text_changes(
        self, base_text: str, head_text: str, renames: RenameMap
    ) -> ChangeKinds | None:
        """
        :param base_text: The file's content in the base commit.
        :param head_text: The file's content in the head commit.
        :param renames: The renames the pull request makes throughout.
        :return: What the change consists of, ``None`` when it is not provably
            mechanical.
        """

    def applies_to(self, change: FileChange) -> bool:
        return (
            change.base_text is not None
            and change.head_text is not None
            and change.path.suffix in self.suffixes
        )

    def changes(self, change: FileChange, renames: RenameMap) -> ChangeKinds | None:
        return self.text_changes(change.base_text, change.head_text, renames)


class ProseComparison(ContentComparison):
    """
    Compares prose: documentation files, docstrings and comments.
    """

    @classproperty
    def suffixes(cls) -> frozenset[str]:
        return frozenset({".md", ".rst", ".txt"})

    def text_changes(
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

    def text_changes(
        self, base_text: str, head_text: str, renames: RenameMap
    ) -> ChangeKinds | None:
        base = PythonSource(base_text)
        head = PythonSource(head_text)
        kinds: set[ChangeKind] = set()
        head_code = head.code(RenameMap())
        if base.code(RenameMap()) != head_code:
            if base.code(renames) != head_code:
                return None
            kinds.add(MechanicalChange.RENAME)
        if base.import_statements != head.import_statements:
            if not base.imports(renames).agrees_with(head.imports(RenameMap())):
                return None
            kinds.add(MechanicalChange.IMPORTS)
        prose_pairs = [
            *zip(base.documentation, head.documentation, strict=True),
            (base.comments, head.comments),
        ]
        for base_prose, head_prose in prose_pairs:
            prose_kinds = self.prose.text_changes(base_prose, head_prose, renames)
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
    Judges each changed file by the first judgment that applies to it; a file no
    judgment applies to is mechanical only when its content is unchanged.
    """

    renames: RenameMap
    """
    The renames the pull request makes throughout.
    """

    judgments: tuple[FileJudgment, ...] = (PythonComparison(), ProseComparison())
    """
    The judgments, tried in order.
    """

    def triage(self, change: FileChange) -> FileTriage:
        """
        :param change: A file the pull request changes.
        :return: Whether a reviewer has to read it.
        """
        kinds = self.judged_changes(change)
        if change.previous_path is not None and kinds is not None:
            kinds |= {MechanicalChange.MOVE}
        if not kinds:
            return FileNeedingReview(change)
        return MechanicalFile(change, kinds)

    def judged_changes(self, change: FileChange) -> ChangeKinds | None:
        """
        :param change: A file the pull request changes.
        :return: What its content change consists of, ``None`` when it is not
            provably mechanical.
        """
        if change.head_text is not None and change.base_text == change.head_text:
            return NO_CHANGE
        for judgment in self.judgments:
            if judgment.applies_to(change):
                return judgment.changes(change, self.renames)
        return None
