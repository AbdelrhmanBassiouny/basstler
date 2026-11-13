"""
Tests that the setup skill names only rows and statuses check-setup.sh reports, so a
renamed check cannot leave the skill telling a session to look for a row that never
appears.
"""

from __future__ import annotations

import re

import pytest

from basstler.setup.report import CheckStatus, RepositoryCheck, SetupCheck

from ..constants.paths import RepositoryLocation, SkillDirectory, SkillFile

SETUP_SKILL = (
    RepositoryLocation.PLUGIN
    / SkillDirectory.SETUP_PERSONAL_NOTES
    / SkillFile.INSTRUCTIONS
)
"""
The setup skill's own document.
"""

ROW_REFERENCE = re.compile(r"`(?P<word>[a-z_]+)` rows?\b")
"""
How the skill names a row: by its check or by its status, in code, before the word
*row*.
"""

# %% the rows the skill names


@pytest.mark.parametrize(
    "word",
    sorted(
        {
            match["word"]
            for match in ROW_REFERENCE.finditer(SETUP_SKILL.read_text(encoding="utf-8"))
        }
    ),
)
def test_every_row_the_setup_skill_names_is_one_check_setup_reports(word: str):
    """
    A word before *row* is either a check the script reports or a status it gives.
    """
    assert word in {*SetupCheck, *RepositoryCheck, *CheckStatus}
