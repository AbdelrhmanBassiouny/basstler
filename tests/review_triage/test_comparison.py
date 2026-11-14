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
from basstler.review_triage.renames import Rename, RenameMap

from .samples import TEMPLATE_REINDENTED, FileSample

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


# %% relative imports


def test_a_relative_import_following_its_file_s_move_is_mechanical():
    """
    A moved file whose relative import is respelled to reach the same module changes
    only its imports.
    """
    change = replace(
        FileSample.RELATIVE_IMPORT_MOVED.change(),
        path=PurePosixPath("tests/git/test_branch.py"),
        previous_path=PurePosixPath("tests/maintenance/test_branch.py"),
    )
    assert FileTriager(JudgmentContext()).triage(change) == MechanicalFile(
        change, frozenset({MechanicalChange.IMPORTS, MechanicalChange.MOVE})
    )


def test_a_relative_import_reaching_another_module_needs_review():
    """
    The same respelling in a file that did not move reaches another module.
    """
    change = replace(
        FileSample.RELATIVE_IMPORT_MOVED.change(),
        path=PurePosixPath("tests/git/test_branch.py"),
    )
    assert FileTriager(JudgmentContext()).triage(change) == FileNeedingReview(change)


# %% added package initializers


@pytest.mark.parametrize("text", ["", "\n"])
def test_an_added_empty_package_initializer_is_mechanical(text: str):
    change = FileChange(PurePosixPath("package/__init__.py"), None, text)
    assert FileTriager(JudgmentContext()).triage(change) == MechanicalFile(
        change, frozenset({MechanicalChange.EMPTY_PACKAGE})
    )


@pytest.mark.parametrize(
    "change",
    [
        FileChange(PurePosixPath("package/__init__.py"), None, "VALUE = 1\n"),
        FileChange(PurePosixPath("package/empty.py"), None, ""),
    ],
    ids=["with code", "another module"],
)
def test_another_added_file_needs_review(change: FileChange):
    assert FileTriager(JudgmentContext()).triage(change) == FileNeedingReview(change)


# %% other text files

MODULE_MOVED = RenameMap(
    (Rename("package.repository", "package.storage.repository", "test"),)
)
"""
The rename the template sample follows.
"""


def test_a_text_file_of_another_type_that_only_follows_a_rename_is_mechanical():
    """
    A template whose only change is a module rename is mechanical.
    """
    change = FileSample.TEMPLATE_RENAMED.change()
    assert FileTriager(JudgmentContext(MODULE_MOVED)).triage(change) == MechanicalFile(
        change, frozenset({MechanicalChange.RENAME})
    )


def test_a_text_file_of_another_type_whose_whitespace_changes_needs_review():
    """
    Whitespace can carry meaning in a file of unknown type, so a renamed line that is
    also reindented needs review.
    """
    change = replace(
        FileSample.TEMPLATE_RENAMED.change(), head_text=TEMPLATE_REINDENTED.read_text()
    )
    assert FileTriager(JudgmentContext(MODULE_MOVED)).triage(
        change
    ) == FileNeedingReview(change)


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
