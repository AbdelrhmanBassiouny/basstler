"""
The one thing about a skill's own documents worth asserting from code.

A skill states its procedure in prose, and the parts worth stating once live in a
document beside it that it links to. Nothing resolves that link until a session follows
it, so a document renamed or moved leaves the skill pointing at nothing and every run of
it short of the part that was extracted.
"""

from __future__ import annotations

import re

import pytest

from .constants.paths import RepositoryLocation, SkillDirectory

LINK_TARGET = re.compile(r"\]\(([^)]+)\)")
"""
Matches the target of a markdown link, whatever it points at.
"""


def linked_files(instructions: str) -> set[str]:
    """
    :param instructions: A skill's own text.
    :return: Every target it links to that names a file in the repository rather than a
        URL or a heading on the page itself.
    """
    return {
        target
        for target in LINK_TARGET.findall(instructions)
        if "://" not in target and not target.startswith("#")
    }


@pytest.mark.parametrize("skill_directory", SkillDirectory.skills())
def test_every_file_a_skill_links_to_is_there(skill_directory: SkillDirectory):
    directory = RepositoryLocation.PLUGIN / skill_directory
    instructions = directory / "SKILL.md"

    linked = linked_files(instructions.read_text())

    missing = {
        target for target in linked if not (directory / target).resolve().exists()
    }
    assert missing == set()
