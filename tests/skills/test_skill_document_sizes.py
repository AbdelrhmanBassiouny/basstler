"""
How much text a skill hands a session before it has done anything.

Every document a skill links to is one a session following it reads, so the size of a
skill is its own document plus everything reachable from it by links.
"""

from __future__ import annotations

from enum import IntEnum
from pathlib import Path

import pytest

from ..constants.paths import RepositoryLocation, SkillDirectory, SkillFile
from .test_skill_documents import document_identifier, linked_files, skill_documents

# %% the limits


class SkillDocumentLimit(IntEnum):
    """
    The most characters skill text may hold, at about four characters a token.
    """

    DOCUMENT_LENGTH = 20_000
    """
    One skill document.
    """

    KICKOFF_READING_LENGTH = 20_000
    """
    Everything ``plan-item-kickoff`` hands a session: about 5k tokens.
    """


# %% reading a skill


def reading_set(document: Path) -> set[Path]:
    """
    :param document: The document a session starts from.
    :return: It and every markdown document reachable from it by links.
    """
    reached: set[Path] = set()
    pending = [document.resolve()]
    while pending:
        current = pending.pop()
        if current in reached:
            continue
        reached.add(current)
        pending += [
            (current.parent / target).resolve()
            for target in linked_files(current.read_text())
            if target.endswith(".md")
        ]
    return reached


KICKOFF_SKILL = (
    RepositoryLocation.PLUGIN
    / SkillDirectory.PLAN_ITEM_KICKOFF
    / SkillFile.INSTRUCTIONS
)
"""
The kickoff skill's own document.
"""


# %% the caps


@pytest.mark.parametrize("document", skill_documents(), ids=document_identifier)
def test_no_skill_document_is_over_its_length(document: Path):
    assert len(document.read_text()) <= SkillDocumentLimit.DOCUMENT_LENGTH


def test_a_kickoff_hands_a_session_at_most_its_reading_length():
    length = sum(len(path.read_text()) for path in reading_set(KICKOFF_SKILL))

    assert length <= SkillDocumentLimit.KICKOFF_READING_LENGTH


def test_the_kickoff_reading_set_follows_the_kickoffs_links():
    """
    Guards the cap above against passing on a reading set that stopped at the skill.
    """
    linked = {
        (KICKOFF_SKILL.parent / target).resolve()
        for target in linked_files(KICKOFF_SKILL.read_text())
    }

    assert linked <= reading_set(KICKOFF_SKILL)
