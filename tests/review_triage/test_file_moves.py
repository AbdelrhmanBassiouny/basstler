"""
Detecting a moved file as a rename of the path prose refers to it by.
"""

from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from basstler.review_triage.file_moves import FileMoveDetection
from basstler.review_triage.pull_request import PullRequestChanges
from basstler.review_triage.renames import Rename, RenameDecisions

from ..scratch_repository import ScratchRepository
from .conftest import committed_pull_request
from .samples import ModuleMoveSample


@pytest.fixture
def module_move(scratch_repository: ScratchRepository) -> PullRequestChanges:
    """
    :return: The sample moving a module, committed to a scratch repository.
    """
    return committed_pull_request(
        scratch_repository, ModuleMoveSample.BASE_TREE, ModuleMoveSample.HEAD_TREE
    )


# %% detection


def test_a_moved_file_is_a_rename_of_its_path_below_the_shared_directories(
    module_move: PullRequestChanges,
):
    assert FileMoveDetection().decisions(module_move) == RenameDecisions(
        (
            Rename(
                "repository.py",
                "storage/repository.py",
                FileMoveDetection.label,
                is_file_path=True,
            ),
        )
    )


@pytest.mark.parametrize(
    ("old", "new", "differing"),
    [
        ("src/package/old.py", "src/package/new.py", ("old.py", "new.py")),
        ("src/a/old.py", "src/b/c/old.py", ("a/old.py", "b/c/old.py")),
    ],
)
def test_the_shared_leading_directories_are_left_out(
    old: str, new: str, differing: tuple[str, str]
):
    assert FileMoveDetection.differing_paths(
        PurePosixPath(old), PurePosixPath(new)
    ) == tuple(map(PurePosixPath, differing))
