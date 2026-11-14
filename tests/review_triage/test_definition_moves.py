"""
Detecting a definition moved from one module to another as a rename of its dotted path,
and triaging the imports that follow it.
"""

from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from basstler.review_triage.comparison import MechanicalChange
from basstler.review_triage.definition_moves import DefinitionMoveDetection
from basstler.review_triage.pull_request import PullRequestChanges
from basstler.review_triage.renames import Rename, RenameDecisions
from basstler.review_triage.triage import PullRequestTriager

from ..scratch_repository import ScratchRepository
from .conftest import committed_pull_request
from .samples import DefinitionMoveSample

# %% the sample


@pytest.fixture
def definition_move(scratch_repository: ScratchRepository) -> PullRequestChanges:
    """
    :return: The sample moving definitions between modules, committed.
    """
    return committed_pull_request(
        scratch_repository,
        DefinitionMoveSample.BASE_TREE,
        DefinitionMoveSample.HEAD_TREE,
    )


# %% detection


def test_a_moved_definition_is_a_rename_of_its_dotted_path(
    definition_move: PullRequestChanges,
):
    """
    A class moved out of a module that stays is renamed to its path in the module that
    now defines it, whether that module existed before or is new.
    """
    assert DefinitionMoveDetection().decisions(definition_move) == RenameDecisions(
        (
            Rename(
                "package.board.Field",
                "package.record.Field",
                DefinitionMoveDetection.label,
            ),
            Rename(
                "package.board.Priority",
                "package.priority.Priority",
                DefinitionMoveDetection.label,
            ),
        )
    )


def test_imports_following_a_moved_definition_are_mechanical(
    definition_move: PullRequestChanges,
):
    """
    A file importing the moved classes from their new modules changes only its imports.
    """
    triage = PullRequestTriager().triage(definition_move)
    assert {file.change.path: file.kinds for file in triage.mechanical_files} == {
        PurePosixPath("caller.py"): frozenset({MechanicalChange.IMPORTS}),
    }
