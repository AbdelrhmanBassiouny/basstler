"""
Judging one file's change as mechanical or needing review.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import PurePosixPath

import pytest

from basstler.review_triage.comparison import (
    ChangeKind,
    ChangeKinds,
    FileChange,
    FileJudgment,
    FileNeedingReview,
    FileTriager,
    JudgmentContext,
    MechanicalChange,
    MechanicalFile,
    ProseComparison,
    PythonComparison,
)
from basstler.review_triage.renames import RenameMap

from .samples import FileSample

# %% file contents


@pytest.mark.parametrize(
    ("sample", "kinds"),
    [
        (FileSample.IMPORTS_REORDERED, {MechanicalChange.IMPORTS}),
        (
            FileSample.IDENTIFIER_RENAMED,
            {MechanicalChange.IMPORTS, MechanicalChange.RENAME},
        ),
        (FileSample.DOCSTRING_REFLOWED, {MechanicalChange.FORMATTING}),
        (FileSample.CODE_REFORMATTED, {MechanicalChange.FORMATTING}),
        (FileSample.DOCUMENTATION_RENAMED, {MechanicalChange.RENAME}),
        (
            FileSample.DOCUMENTATION_REFLOWED,
            {MechanicalChange.RENAME, MechanicalChange.FORMATTING},
        ),
    ],
)
def test_a_mechanical_change_is_reported_with_its_kinds(
    sample: FileSample, kinds: set[MechanicalChange], old_name_renamed: RenameMap
):
    """
    Each sample whose change cannot alter what the file does or says is mechanical, with
    the kinds of change it consists of.
    """
    change = sample.change()
    assert FileTriager(JudgmentContext(old_name_renamed)).triage(
        change
    ) == MechanicalFile(change, frozenset(kinds))


@pytest.mark.parametrize(
    "sample",
    [
        FileSample.IMPORT_SOURCE_CHANGED,
        FileSample.STRING_LITERAL_RENAMED,
        FileSample.DOCSTRING_REWORDED,
        FileSample.BEHAVIOUR_CHANGED,
    ],
)
def test_a_change_of_meaning_needs_review(
    sample: FileSample, old_name_renamed: RenameMap
):
    """
    A changed import source, string literal, docstring wording or expression needs
    review, renames or not.
    """
    change = sample.change()
    assert FileTriager(JudgmentContext(old_name_renamed)).triage(
        change
    ) == FileNeedingReview(change)


def test_a_rename_the_pull_request_does_not_make_needs_review():
    """
    Renamed identifiers are mechanical only when the pull request makes the rename
    throughout.
    """
    change = FileSample.IDENTIFIER_RENAMED.change()
    assert FileTriager(JudgmentContext()).triage(change) == FileNeedingReview(change)


# %% whole files


def test_an_unchanged_moved_file_is_mechanical():
    """
    A file moved without changing its content is a move.
    """
    change = replace(
        FileSample.BEHAVIOUR_CHANGED.change(),
        head_text=FileSample.BEHAVIOUR_CHANGED.change().base_text,
        previous_path=PurePosixPath("old/sample.py"),
    )
    assert FileTriager(JudgmentContext()).triage(change) == MechanicalFile(
        change, frozenset({MechanicalChange.MOVE})
    )


@pytest.mark.parametrize(
    "change",
    [
        replace(FileSample.BEHAVIOUR_CHANGED.change(), base_text=None),
        replace(FileSample.BEHAVIOUR_CHANGED.change(), head_text=None),
        FileChange(PurePosixPath("logo.png"), None, None, is_binary=True),
        replace(
            FileSample.DOCUMENTATION_RENAMED.change(), path=PurePosixPath("sample.yaml")
        ),
    ],
    ids=["added", "deleted", "binary", "unjudged type"],
)
def test_a_file_no_judgment_proves_mechanical_needs_review(change: FileChange):
    """
    An added, deleted or binary file, or a changed file of a type nothing judges, needs
    review.
    """
    assert FileTriager(JudgmentContext()).triage(change) == FileNeedingReview(change)


# %% extending the triage


class GeneratedChange(ChangeKind):
    """
    The kind of change an extension declares.
    """

    GENERATED = "generated"


class GeneratedFileJudgment(FileJudgment):
    """
    Judges every file under a generated directory mechanical.
    """

    def applies_to(self, change: FileChange) -> bool:
        return change.path.parts[0] == "generated"

    def changes(
        self, change: FileChange, context: JudgmentContext
    ) -> ChangeKinds | None:
        return frozenset({GeneratedChange.GENERATED})


def test_an_extension_judgment_decides_the_files_it_applies_to():
    """
    A judgment placed first decides its files, with change kinds its extension declares.
    """
    change = replace(
        FileSample.BEHAVIOUR_CHANGED.change(), path=PurePosixPath("generated/sample.py")
    )
    triager = FileTriager(
        JudgmentContext(),
        (GeneratedFileJudgment(), PythonComparison(), ProseComparison()),
    )
    assert triager.triage(change) == MechanicalFile(
        change, frozenset({GeneratedChange.GENERATED})
    )
