"""
A whole pull request triaged: its renames and the verdict on each file it changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from basstler.review_triage.commit_tree import CommitTree
from basstler.review_triage.comparison import (
    FileJudgment,
    FileNeedingReview,
    FileTriage,
    FileTriager,
    JudgmentContext,
    MechanicalFile,
    EmptyPackageAddition,
    ProseComparison,
    RenamedTextComparison,
)
from basstler.review_triage.declaration import DescriptionDeclaration
from basstler.review_triage.detection import RenameDetection
from basstler.review_triage.keyword_arguments import KeywordArgumentComparison
from basstler.review_triage.definition_moves import DefinitionMoveDetection
from basstler.review_triage.file_moves import FileMoveDetection
from basstler.review_triage.module_moves import ModuleMoveDetection
from basstler.review_triage.pull_request import PullRequestChanges, TriagedPullRequest
from basstler.review_triage.rename_sources import RenameSource
from basstler.review_triage.renames import RenameMap
from basstler.review_triage.definitions import DefinitionIndex

# %% the triage


@dataclass(frozen=True)
class PullRequestTriage:
    """
    Which of a pull request's files a reviewer has to read.
    """

    pull_request: TriagedPullRequest
    """
    The pull request triaged.
    """

    renames: RenameMap
    """
    The renames applied in judging its files.
    """

    files: tuple[FileTriage, ...]
    """
    The verdict on each file it changes.
    """

    @property
    def mechanical_files(self) -> tuple[MechanicalFile, ...]:
        """
        The files a reviewer need not read.
        """
        return tuple(file for file in self.files if isinstance(file, MechanicalFile))

    @property
    def files_needing_review(self) -> tuple[FileNeedingReview, ...]:
        """
        The files a reviewer has to read.
        """
        return tuple(file for file in self.files if isinstance(file, FileNeedingReview))


# %% triaging


@dataclass(frozen=True)
class PullRequestTriager:
    """
    Triages a pull request with a configurable set of rename sources and file judgments.
    """

    rename_sources: tuple[RenameSource, ...] = (
        RenameDetection(),
        ModuleMoveDetection(),
        DefinitionMoveDetection(),
        FileMoveDetection(),
        DescriptionDeclaration(),
    )
    """
    The sources of the pull request's renames, a later source outranking an earlier.
    """

    judgments: tuple[FileJudgment, ...] = (
        KeywordArgumentComparison(),
        ProseComparison(),
        EmptyPackageAddition(),
        RenamedTextComparison(),
    )
    """
    The judgments of each file, the first one applying to a file deciding it.
    """

    def triage(self, changes: PullRequestChanges) -> PullRequestTriage:
        """
        :param changes: A pull request and the files it changes.
        :return: The verdict on each of its files.
        """
        renames = RenameMap.of(
            source.decisions(changes) for source in self.rename_sources
        )
        base_definitions = DefinitionIndex(
            CommitTree(changes.commits.git, changes.commits.base_commit)
        )
        triager = FileTriager(
            JudgmentContext(renames, base_definitions), self.judgments
        )
        return PullRequestTriage(
            changes.pull_request,
            renames,
            tuple(triager.triage(change) for change in changes.files),
        )
