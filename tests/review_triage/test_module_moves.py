"""
Detecting a moved module as a rename of its dotted path, and triaging the imports that
follow it.
"""

from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from basstler.review_triage.comparison import MechanicalChange
from basstler.review_triage.module_moves import ModuleMoveDetection
from basstler.review_triage.pull_request import PullRequestChanges
from basstler.review_triage.renames import Rename, RenameDecisions
from basstler.review_triage.triage import PullRequestTriager

from ..scratch_repository import ScratchRepository
from .conftest import committed_pull_request
from .samples import ModuleMoveSample

# %% the sample


@pytest.fixture
def module_move(scratch_repository: ScratchRepository) -> PullRequestChanges:
    """
    :return: The sample moving a module, committed to a scratch repository.
    """
    return committed_pull_request(
        scratch_repository, ModuleMoveSample.BASE_TREE, ModuleMoveSample.HEAD_TREE
    )


# %% detection


def test_a_moved_module_is_a_rename_of_its_dotted_path(
    module_move: PullRequestChanges,
):
    """
    A module moved into a subpackage is renamed from its old dotted path to its new one.
    """
    assert ModuleMoveDetection().decisions(module_move) == RenameDecisions(
        (
            Rename(
                "package.repository",
                "package.storage.repository",
                ModuleMoveDetection.label,
            ),
        )
    )


def test_imports_following_a_moved_module_are_mechanical(
    module_move: PullRequestChanges,
):
    """
    A file importing the moved module from its new path changes only its imports.
    """
    triage = PullRequestTriager().triage(module_move)
    assert {file.change.path: file.kinds for file in triage.mechanical_files} == {
        PurePosixPath("caller.py"): frozenset({MechanicalChange.IMPORTS}),
        PurePosixPath("package/storage/repository.py"): frozenset(
            {MechanicalChange.MOVE}
        ),
    }
